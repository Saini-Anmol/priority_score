# main.py
# ---------------------------------------------------------------------------
# VECTOR SUPPLY CHAIN INTELLIGENCE SYSTEM
# Modular In-Memory Architecture (V1)
# Primary Entry Point
# ---------------------------------------------------------------------------

import os
from datetime import datetime
from dotenv import load_dotenv

# Import the orchestrator from the Routes folder
from V1.Routes.btp_pipeline import run_btp_pipeline

def main():
    print("=" * 70)
    print("  Vector Supply Chain Intelligence System - BTP Pipeline")
    print("  Modular In-Memory Architecture (V1)")
    print("=" * 70)
    print()
    
    # Load environment variables (like BASE_DATA_PATH) from the .env file
    load_dotenv()
    
    # Prompt user for the target date
    date_str = input("Enter date (DD.MM.YYYY): ").strip()
    
    try:
        # Validate date format before passing it down to the pipeline
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")
        ddmmyyyy = date_obj.strftime("%d%m%Y")
        
        # Trigger the main pipeline orchestrator
        run_btp_pipeline(ddmmyyyy)
        
        print(f"\n✅ Pipeline executed successfully for {date_str}.")
        
    except ValueError:
        print("\n❌ Invalid date format. Please use DD.MM.YYYY")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {str(e)}")

if __name__ == "__main__":
    main()