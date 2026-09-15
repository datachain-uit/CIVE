import asyncio
import json
import aiohttp
import time
import argparse
import re
from tqdm.asyncio import tqdm

PROMPT_TEMPLATE = """You are a professional crypto market analyst. Analyze the following news headlines.
HEADLINE: "{text}"
TASK:
1. Assess the overall sentiment impact on Bitcoin/Crypto markets.
2. Return ONLY a JSON object with this exact format (no markdown, no other text):
{{"score": <integer from -20 to +20>}}
SCORING GUIDE:
- +20 to +11: Very bullish
- +10 to +1: Mildly bullish
- 0: Neutral / mixed signals
- -1 to -10: Mildly bearish
- -11 to -20: Very bearish
"""

async def fetch_score(session, model, text, sem):
    async with sem:
        prompt = PROMPT_TEMPLATE.format(text=text)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0}
        }
        try:
            async with session.post("http://localhost:11434/api/generate", json=payload, timeout=60) as resp:
                resp.raise_for_status()
                data = await resp.json()
                response_text = data.get("response", "")
                
                try:
                    parsed = json.loads(response_text)
                    score = int(parsed.get("score", 0))
                    return max(-20, min(20, score))
                except Exception:
                    # fallback heuristic if JSON fails
                    numbers = re.findall(r'-?\d+', response_text)
                    if numbers:
                        return max(-20, min(20, int(numbers[0])))
                    return 0
        except Exception as e:
            # Silently fail for individual timeouts to not disrupt the batch
            return 0

async def process_batch(items, model, concurrency):
    sem = asyncio.Semaphore(concurrency)
    # Using a larger connection pool for local GPU hammering
    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_score(session, model, item['text'], sem) for item in items]
        scores = await tqdm.gather(*tasks, desc=f"Scoring with {model}")
        return scores

def main():
    parser = argparse.ArgumentParser(description="Batch LLM inference via Ollama API")
    parser.add_argument("--model", type=str, default="llama3:latest", help="Ollama model tag")
    parser.add_argument("--concurrency", type=int, default=50, help="Concurrent requests to Ollama")
    parser.add_argument("--input", type=str, default="results/historical_ai_data_shifted.json")
    args = parser.parse_args()

    print(f"Loading data from {args.input}...")
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {args.input} not found.")
        return
        
    # Standardize model name for filename
    safe_model = args.model.replace(':', '_').replace('.', '_')
        
    print(f"Loaded {len(data)} items. Starting batch inference with model '{args.model}'...")
    start_time = time.time()
    
    # Run async loop
    scores = asyncio.run(process_batch(data, args.model, args.concurrency))
    
    # Merge scores back
    for item, score in zip(data, scores):
        item['sentiment_score'] = score
        item['llm_backend'] = args.model
        
    out_path = f"results/llm_sentiment_{safe_model}.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    elapsed = time.time() - start_time
    print(f"Done in {elapsed:.1f}s. Saved to {out_path}.")
    print(f"Average speed: {len(data) / elapsed:.1f} items/sec.")

if __name__ == "__main__":
    main()
