import json
import random
from datetime import datetime, timedelta

def main():
    print("Loading historical_ai_data.json...")
    with open("results/historical_ai_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("No data found!")
        return

    # Sort data by original date just in case
    data.sort(key=lambda x: x['date'])

    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    
    total_items = len(data)
    time_step = (end_date - start_date) / max(total_items, 1)

    print(f"Shifting {total_items} records to span from {start_date} to {end_date}...")
    
    current_time = start_date
    for item in data:
        item['date'] = current_time.strftime("%Y-%m-%d %H:%M:%S")
        current_time += time_step

    out_path = "results/historical_ai_data_shifted.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    print(f"Saved to {out_path}")

if __name__ == "__main__":
    main()
