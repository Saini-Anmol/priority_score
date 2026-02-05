# app_main.py
import pandas as pd
from datetime import datetime, timedelta
from demand_processor import process_single_date
import config

def run_report():
    print("Initializing Vector Prioritization Engine...")
    
    # In a real website, these would be variables sent from the UI
    start_str = input("Enter start date (DD.MM.YYYY): ")
    end_str = input("Enter end date (DD.MM.YYYY): ")

    start_date = datetime.strptime(start_str, "%d.%m.%Y")
    end_date = datetime.strptime(end_str, "%d.%m.%Y")
    
    days = (end_date - start_date).days + 1
    df_dict = {}

    for i in range(days):
        current_date = (start_date + timedelta(days=i)).strftime("%d%m%Y")
        print(f"Processing date: {current_date}")
        
        df = process_single_date(current_date)
        if df is not None:
            df_dict[current_date] = df

    if df_dict:
        with pd.ExcelWriter(config.OUTPUT_FILE) as writer:
            for date, data in df_dict.items():
                data.to_excel(writer, sheet_name=date, index=False)
        print(f"Successfully generated: {config.OUTPUT_FILE}")
    else:
        print("Error: No data found for the selected range.")

if __name__ == "__main__":
    run_report()