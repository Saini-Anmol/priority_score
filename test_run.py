#!/usr/bin/env python3
# Test script to run with preset date
import pandas as pd
from datetime import datetime, timedelta
from demand_processor import process_single_date
import config

def test_run():
    print("Testing Vector Prioritization Engine...")
    
    # Test with a single date
    start_date = datetime.strptime("02.01.2026", "%d.%m.%Y")
    end_date = datetime.strptime("02.01.2026", "%d.%m.%Y")
    
    days = (end_date - start_date).days + 1
    df_dict = {}

    for i in range(days):
        current_date = (start_date + timedelta(days=i)).strftime("%d%m%Y")
        print(f"Processing date: {current_date}")
        
        df = process_single_date(current_date)
        if df is not None:
            df_dict[current_date] = df
            print(f"  ✅ Success! Processed {len(df)} rows")
            print(f"  Columns: {len(df.columns)}")

    if df_dict:
        with pd.ExcelWriter(config.OUTPUT_FILE) as writer:
            for date, data in df_dict.items():
                data.to_excel(writer, sheet_name=date, index=False)
        print(f"\n✅ Successfully generated: {config.OUTPUT_FILE}")
        print(f"   Total sheets: {len(df_dict)}")
    else:
        print("\n❌ Error: No data found for the selected range.")

if __name__ == "__main__":
    test_run()
