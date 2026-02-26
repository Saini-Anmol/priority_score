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
        output_end_date = end_date.strftime("%d%m%Y")
        output_file = f"combined_vector_demand_{output_end_date}.xlsx"
        with pd.ExcelWriter(output_file) as writer:
            for date, data in df_dict.items():
                data.to_excel(writer, sheet_name=date, index=False)
        print(f"Successfully generated: {output_file}")
    else:
        print("Error: No data found for the selected range.")

if __name__ == "__main__":
    run_report()