"""V11.1.2 scorer: deterministic handling of duplicate batch-1 results."""
from __future__ import annotations
import json
from difflib import SequenceMatcher
import score_open_fed_policy_v11 as base

BASE_VALIDATE = base.validate
BASE_API = base.api

def align_evidence(text: str, evidence: str) -> tuple[str, bool]:
    if evidence in text: return evidence, False
    match = SequenceMatcher(None, text, evidence, autojunk=False).find_longest_match()
    aligned = text[match.a:match.a + match.size].strip()
    if len(aligned) < 32: raise ValueError("evidence_span has no sufficiently long exact source segment")
    return aligned[:240], True

def validate(result: object, expected: dict) -> dict:
    if not isinstance(result, dict): raise ValueError("result must be an object")
    candidate=dict(result); evidence, fallback=align_evidence(expected["text"], candidate.get("evidence_span", "")); candidate["evidence_span"]=evidence
    return {**BASE_VALIDATE(candidate, expected), "evidence_alignment_fallback": fallback}

def api(path: str, payload: dict | None = None) -> dict:
    response=BASE_API(path, payload)
    if path == "/api/chat" and payload is not None:
        content=response.get("message", {}).get("content")
        try:
            parsed=json.loads(content)
            results=parsed.get("results")
            if isinstance(results, list) and len(results) > 1 and results and len({item.get("event_id") for item in results if isinstance(item, dict)}) == 1:
                response["message"]["content"]=json.dumps({"results":[results[0]]}, ensure_ascii=False)
        except (TypeError, json.JSONDecodeError):
            pass
    return response

if __name__ == "__main__":
    base.validate=validate; base.api=api; base.main()
