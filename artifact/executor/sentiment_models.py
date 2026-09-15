"""
sentiment_models.py
====================
Multi-model sentiment scoring module for the Proof-of-Trade IEEE paper.

Implements a common interface (SentimentModel) with six concrete backends:
  - FinBERT   (Araci 2019, arXiv:1908.10063) — local HuggingFace transformers
  - FinGPT    (Yang et al. 2023, arXiv:2306.06031) — HuggingFace FinGPT-Forecaster
  - Llama-3   (Meta 2024) — Ollama local inference API
  - Gemini    (Google 2023) — google-generativeai SDK
  - GPT-4o    (OpenAI 2024) — openai SDK
  - Ensemble  — weighted average of all available models

Design principles
-----------------
* Graceful degradation: each model catches its own ImportError / API errors
  and returns None instead of crashing. Multi-model runners skip unavailable
  models automatically.
* Normalised output: all models return float in [-1.0, 1.0] where
  -1 = strong bearish, 0 = neutral, +1 = strong bullish.
* Paper traceability: each class exposes ``paper_citation`` for BibTeX key.

Usage (for backtester integration)
-----------------------------------
    from executor.sentiment_models import FinBERTSentiment, GeminiSentiment, EnsembleSentiment

    texts = ["Bitcoin ETF approval boosts institutional demand",
             "Fed rate hike fears pressure crypto markets"]

    model = FinBERTSentiment()
    score = model.score(texts)           # float in [-1, 1]
    name  = model.name                   # "FinBERT"
    cite  = model.paper_citation         # "finbert2019"
"""
from __future__ import annotations

import logging
import os
import json
import time
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────── #
#  Abstract base                                                               #
# ─────────────────────────────────────────────────────────────────────────── #

class SentimentModel(ABC):
    """Abstract sentiment scoring interface."""

    name: str = "base"
    paper_citation: str = ""          # BibTeX key in references.bib

    @abstractmethod
    def score(self, texts: list[str]) -> Optional[float]:
        """
        Score a list of financial text snippets.

        Parameters
        ----------
        texts : list[str]
            News headlines / article summaries (max ~20 items recommended).

        Returns
        -------
        float in [-1.0, 1.0] or None if the model is unavailable.
        """
        ...

    def is_available(self) -> bool:
        """Quick availability check (no API call)."""
        try:
            self.score(["test"])
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────────── #
#  FinBERT  (Araci 2019)                                                       #
# ─────────────────────────────────────────────────────────────────────────── #

class FinBERTSentiment(SentimentModel):
    """
    Financial sentiment using ProsusAI/finbert (BERT fine-tuned on finance text).

    Reference
    ---------
    Araci, Dogu (2019). "FinBERT: Financial Sentiment Analysis with
    Pre-trained Language Models." arXiv:1908.10063  [\\cite{finbert2019}]

    Requirements
    ------------
    pip install transformers torch
    """

    name = "FinBERT"
    paper_citation = "finbert2019"
    _MODEL_ID = "ProsusAI/finbert"

    def __init__(self) -> None:
        self._pipeline = None

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from transformers import pipeline as hf_pipeline  # type: ignore
            self._pipeline = hf_pipeline(
                "text-classification",
                model=self._MODEL_ID,
                tokenizer=self._MODEL_ID,
                top_k=None,
                device=-1,          # CPU; set to 0 for GPU
                truncation=True,
                max_length=512,
            )
            logger.info("[FinBERT] Model loaded: %s", self._MODEL_ID)
        except ImportError:
            raise RuntimeError("transformers/torch not installed. Run: pip install transformers torch")

    @staticmethod
    def _label_to_score(label: str) -> float:
        return {"positive": 1.0, "negative": -1.0, "neutral": 0.0}.get(label.lower(), 0.0)

    def score(self, texts: list[str]) -> Optional[float]:
        try:
            self._load()
            if not texts:
                return 0.0
            results = self._pipeline(texts, batch_size=8)
            scores: list[float] = []
            for result in results:
                # result is a list of {"label": ..., "score": ...} dicts
                best = max(result, key=lambda x: x["score"])
                scores.append(self._label_to_score(best["label"]) * best["score"])
            return sum(scores) / len(scores) if scores else 0.0
        except Exception as exc:
            logger.warning("[FinBERT] Inference failed: %s", exc)
            return None


# ─────────────────────────────────────────────────────────────────────────── #
#  FinGPT  (Yang et al. 2023)                                                  #
# ─────────────────────────────────────────────────────────────────────────── #

class FinGPTSentiment(SentimentModel):
    """
    Financial sentiment using FinGPT-Forecaster (LLAMA fine-tuned on finance).

    Reference
    ---------
    Yang, Hongyang et al. (2023). "FinGPT: Open-Source Financial Large
    Language Models." arXiv:2306.06031  [\\cite{fingpt2023}]

    Requirements
    ------------
    pip install transformers torch peft
    (Model: FinGPT/fingpt-forecaster_dow30_llama2-7b_lora on HuggingFace)
    """

    name = "FinGPT"
    paper_citation = "fingpt2023"
    _MODEL_ID = "FinGPT/fingpt-forecaster_dow30_llama2-7b_lora"
    _BASE_MODEL = "NousResearch/Llama-2-7b-hf"

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
            from peft import PeftModel  # type: ignore
            logger.info("[FinGPT] Loading base model %s ...", self._BASE_MODEL)
            base = AutoModelForCausalLM.from_pretrained(
                self._BASE_MODEL,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
            )
            self._model = PeftModel.from_pretrained(base, self._MODEL_ID)
            self._tokenizer = AutoTokenizer.from_pretrained(self._BASE_MODEL)
            self._model.eval()
            logger.info("[FinGPT] Model loaded.")
        except ImportError:
            raise RuntimeError("pip install transformers torch peft  required for FinGPT")

    def _classify_output(self, text: str) -> float:
        t = text.strip().lower()
        if "increase" in t or "up" in t or "positive" in t or "bullish" in t:
            return 1.0
        if "decrease" in t or "down" in t or "negative" in t or "bearish" in t:
            return -1.0
        return 0.0

    def score(self, texts: list[str]) -> Optional[float]:
        try:
            self._load()
            import torch
            scores: list[float] = []
            for text in texts[:10]:  # limit to 10 for speed
                prompt = (
                    "Instruction: What is the sentiment of this news? "
                    "Please choose an answer from {increase, decrease, neutral}.\n"
                    f"Input: {text}\n"
                    "Answer:"
                )
                inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
                with torch.no_grad():
                    out = self._model.generate(
                        **inputs, max_new_tokens=10, do_sample=False
                    )
                result = self._tokenizer.decode(out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
                scores.append(self._classify_output(result))
            return sum(scores) / len(scores) if scores else 0.0
        except Exception as exc:
            logger.warning("[FinGPT] Inference failed: %s", exc)
            return None


# ─────────────────────────────────────────────────────────────────────────── #
#  Llama-3  (Meta 2024) via Ollama                                             #
# ─────────────────────────────────────────────────────────────────────────── #

class LlamaSentiment(SentimentModel):
    """
    Financial sentiment using Llama 3.1 via Ollama local inference server.

    Reference
    ---------
    Meta AI (2024). "Llama 3: Herd of Models." arXiv:2407.21783
    Ollama: https://ollama.com  [\\cite{llama3_2024}]

    Requirements
    ------------
    1. Install Ollama: https://ollama.com/download
    2. Pull model: ollama pull llama3.1:8b
    3. Start server: ollama serve   (default: http://localhost:11434)
    """

    name = "Llama-3.1-8B"
    paper_citation = "llama3_2024"

    _SYSTEM_PROMPT = (
        "You are a financial sentiment classifier. "
        "Given news headlines, output ONLY a JSON object: "
        '{"score": <float from -1.0 to 1.0>, "reasoning": "<one sentence>"} '
        "where -1.0 = strongly bearish, 0.0 = neutral, 1.0 = strongly bullish. "
        "No other text."
    )

    def __init__(
        self,
        model: str = "llama3.1:8b",
        host: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._host = host

    def score(self, texts: list[str]) -> Optional[float]:
        try:
            import requests as req  # already in deps
            news_block = "\n".join(f"- {t}" for t in texts[:15])
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": f"News:\n{news_block}"},
                ],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 80},
            }
            resp = req.post(f"{self._host}/api/chat", json=payload, timeout=60)
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            # Extract JSON from response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(content[start:end])
                raw = float(data.get("score", 0.0))
                return max(-1.0, min(1.0, raw))
            logger.warning("[Llama] Could not parse JSON from: %s", content[:200])
            return None
        except Exception as exc:
            logger.warning("[Llama] Request failed: %s", exc)
            return None


# ─────────────────────────────────────────────────────────────────────────── #
#  Gemini  (Google 2023)                                                        #
# ─────────────────────────────────────────────────────────────────────────── #

class GeminiSentiment(SentimentModel):
    """
    Financial sentiment using Google Gemini (existing integration).

    Reference
    ---------
    Google DeepMind (2023). "Gemini: A Family of Highly Capable
    Multimodal Models." arXiv:2312.11805  [\\cite{gemini2023}]

    Requirements
    ------------
    pip install google-generativeai
    Environment variable: GEMINI_API_KEY
    """

    name = "Gemini-2.5-Flash"
    paper_citation = "gemini2023"

    _PROMPT_TEMPLATE = (
        "You are a cryptocurrency market sentiment analyst. "
        "Score the overall sentiment of the following news headlines "
        "on a scale from -1.0 (strongly bearish) to +1.0 (strongly bullish). "
        "Return ONLY a JSON object: "
        '{"score": <float -1.0 to 1.0>}. '
        "No additional text.\n\nNews:\n{news}"
    )

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        self._model_name = model
        self._api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._client = None

    def _load(self) -> None:
        if self._client is not None:
            return
        try:
            import google.generativeai as genai  # type: ignore
            if not self._api_key:
                raise RuntimeError("GEMINI_API_KEY not set in environment")
            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self._model_name)
            logger.info("[Gemini] Model: %s", self._model_name)
        except ImportError:
            raise RuntimeError("pip install google-generativeai")

    def score(self, texts: list[str]) -> Optional[float]:
        try:
            self._load()
            news_block = "\n".join(f"- {t}" for t in texts[:20])
            prompt = self._PROMPT_TEMPLATE.format(news=news_block)
            response = self._client.generate_content(prompt)
            content = response.text.strip()
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(content[start:end])
                raw = float(data.get("score", 0.0))
                return max(-1.0, min(1.0, raw))
            return None
        except Exception as exc:
            logger.warning("[Gemini] Request failed: %s", exc)
            return None


# ─────────────────────────────────────────────────────────────────────────── #
#  GPT-4o  (OpenAI 2024)                                                        #
# ─────────────────────────────────────────────────────────────────────────── #

class GPTSentiment(SentimentModel):
    """
    Financial sentiment using GPT-4o-mini (OpenAI).

    Reference
    ---------
    OpenAI (2023). "GPT-4 Technical Report." arXiv:2303.08774
    [\\cite{gpt4report2023}]

    Requirements
    ------------
    pip install openai
    Environment variable: OPENAI_API_KEY
    """

    name = "GPT-4o-mini"
    paper_citation = "gpt4report2023"

    _SYSTEM = (
        "You are a cryptocurrency market sentiment analyst. "
        "Given news headlines, return ONLY valid JSON: "
        '{"score": <float from -1.0 to 1.0>}. '
        "No other text. -1.0=strongly bearish, 0=neutral, 1.0=strongly bullish."
    )

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._model = model
        self._api_key = os.getenv("OPENAI_API_KEY")
        self._client = None

    def _load(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import OpenAI  # type: ignore
            if not self._api_key:
                raise RuntimeError("OPENAI_API_KEY not set in environment")
            self._client = OpenAI(api_key=self._api_key)
            logger.info("[GPT] Model: %s", self._model)
        except ImportError:
            raise RuntimeError("pip install openai")

    def score(self, texts: list[str]) -> Optional[float]:
        try:
            self._load()
            news_block = "\n".join(f"- {t}" for t in texts[:15])
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._SYSTEM},
                    {"role": "user", "content": f"News:\n{news_block}"},
                ],
                temperature=0.0,
                max_tokens=50,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            raw = float(data.get("score", 0.0))
            return max(-1.0, min(1.0, raw))
        except Exception as exc:
            logger.warning("[GPT] Request failed: %s", exc)
            return None


# ─────────────────────────────────────────────────────────────────────────── #
#  Ensemble  — weighted average of all available models                        #
# ─────────────────────────────────────────────────────────────────────────── #

class EnsembleSentiment(SentimentModel):
    """
    Weighted ensemble of all available sentiment models.

    Each model that returns a non-None score is included.
    Default weights are equal; override via ``weights`` dict.

    Example
    -------
    ensemble = EnsembleSentiment(
        models=[FinBERTSentiment(), GeminiSentiment(), LlamaSentiment()],
        weights={"FinBERT": 0.4, "Gemini-2.5-Flash": 0.4, "Llama-3.1-8B": 0.2},
    )
    score = ensemble.score(texts)
    """

    name = "Ensemble"
    paper_citation = ""   # ensemble of multiple; cite individual models

    def __init__(
        self,
        models: list[SentimentModel] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        if models is None:
            models = [
                FinBERTSentiment(),
                GeminiSentiment(),
                LlamaSentiment(),
                GPTSentiment(),
            ]
        self._models = models
        self._weights = weights or {}

    def score(self, texts: list[str]) -> Optional[float]:
        weighted_sum = 0.0
        weight_total = 0.0
        for model in self._models:
            s = model.score(texts)
            if s is None:
                continue
            w = self._weights.get(model.name, 1.0)
            weighted_sum += s * w
            weight_total += w
            logger.debug("[Ensemble] %s → %.4f (weight=%.2f)", model.name, s, w)
        if weight_total <= 0:
            return None
        result = weighted_sum / weight_total
        logger.info("[Ensemble] Combined score: %.4f (models=%d)", result, sum(
            1 for m in self._models if m.score(texts) is not None
        ))
        return result


# ─────────────────────────────────────────────────────────────────────────── #
#  Factory                                                                     #
# ─────────────────────────────────────────────────────────────────────────── #

_MODEL_REGISTRY: dict[str, type[SentimentModel]] = {
    "finbert": FinBERTSentiment,
    "fingpt": FinGPTSentiment,
    "llama": LlamaSentiment,
    "llama3": LlamaSentiment,
    "gemini": GeminiSentiment,
    "gpt": GPTSentiment,
    "gpt4": GPTSentiment,
    "ensemble": EnsembleSentiment,
}


def get_model(name: str) -> SentimentModel:
    """
    Instantiate a sentiment model by short name.

    Parameters
    ----------
    name : str
        One of: finbert, fingpt, llama, gemini, gpt, ensemble

    Returns
    -------
    SentimentModel instance
    """
    key = name.strip().lower()
    if key not in _MODEL_REGISTRY:
        raise ValueError(
            f"Unknown model '{name}'. Available: {', '.join(_MODEL_REGISTRY)}"
        )
    return _MODEL_REGISTRY[key]()


def list_available_models(texts: list[str] | None = None) -> list[str]:
    """Return names of models that respond successfully."""
    probe = texts or ["Bitcoin rises to new highs amid institutional demand."]
    available: list[str] = []
    for name, cls in _MODEL_REGISTRY.items():
        if name == "ensemble":
            continue
        try:
            model = cls()
            result = model.score(probe)
            if result is not None:
                available.append(model.name)
                logger.info("✓ %s available (score=%.4f)", model.name, result)
            else:
                logger.info("✗ %s returned None", model.name)
        except Exception as exc:
            logger.info("✗ %s unavailable: %s", name, exc)
    return available


if __name__ == "__main__":
    # Quick availability check
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    test_texts = [
        "Bitcoin ETF approval drives institutional interest",
        "Federal Reserve signals potential rate cuts",
        "Crypto market faces regulatory uncertainty in EU",
    ]
    print("=== Sentiment Model Availability Check ===")
    available = list_available_models(test_texts)
    print(f"\nAvailable models: {available}")

    if available:
        for model_name in available:
            model = get_model(model_name.split("-")[0].lower())
            s = model.score(test_texts)
            print(f"{model.name:25s}  score={s:+.4f}  cite=[{model.paper_citation}]")
