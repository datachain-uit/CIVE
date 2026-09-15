import os
import json
import logging
from typing import Dict, Any, List
from datasets import load_dataset
from transformers import pipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Loading SahandNZ/cryptonews-articles-with-price-momentum-labels from HuggingFace...")
    # Load dataset
    try:
        dataset = load_dataset("SahandNZ/cryptonews-articles-with-price-momentum-labels", split="train")
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        return

    logger.info(f"Loaded {len(dataset)} articles. Setting up FinBERT pipeline...")
    # Setup FinBERT pipeline for sentiment analysis
    try:
        sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    except Exception as e:
        logger.error(f"Failed to load FinBERT model: {e}")
        return

    logger.info("Processing articles...")
    results = []
    
    # Process max 5000 items to keep backtest fast but statistically meaningful
    limit = 5000
    for idx, row in enumerate(dataset):
        if idx >= limit:
            break
            
        date = row.get("datetime")
        text = row.get("text")
        
        if not text or not date:
            continue
            
        try:
            # truncate to avoid errors
            text_truncated = text[:1500] 
            res = sentiment_pipeline(text_truncated)[0]
            label = res['label']
            score = res['score']
            
            # Map FinBERT labels to -20 to 20 sentiment score (Market Power Score contribution)
            mapped_score = 0
            if label == 'positive':
                mapped_score = score * 20.0
            elif label == 'negative':
                mapped_score = -score * 20.0
                
            results.append({
                "date": str(date),
                "text": text[:100], # store snippet
                "sentiment_label": label,
                "sentiment_score": mapped_score
            })
        except Exception as e:
            logger.warning(f"Error processing row {idx}: {e}")
            
        if (idx + 1) % 500 == 0:
            logger.info(f"Processed {idx + 1} articles...")
            
    output_path = os.path.join(os.path.dirname(__file__), "..", "results", "historical_ai_data.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    logger.info(f"Successfully saved {len(results)} scored articles to {output_path}")

if __name__ == "__main__":
    main()
