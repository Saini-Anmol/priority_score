# app_stage2.py
# Stage 2: Unified Application Runner (Stage 1 + Frontend/Manual Integration)
#
# Pipeline:
#   Stage 1 → process_single_date()        (demand_processor.py)
#   Stage 2 → process_frontend_override()  (frontend_processor.py)
#
# Output: deployment_analysis_report.xlsx  (date-wise sheet tab)

import pandas as pd
from datetime import datetime
from demand_processor import process_single_date
from frontend_processor import process_frontend_override

STAGE2_OUTPUT_FILE = "deployment_analysis_report.xlsx"


def run_integrated_analysis():
    """
    Run the integrated Stage 1 + Stage 2 analysis pipeline.

    Process:
    1. Accept a date from the user.
    2. Execute Stage 1 (Demand Prioritization).
    3. Execute Stage 2 (Frontend / Manual Integration).
    4. Generate consolidated Excel report.
    """
    print("=" * 80)
    print("VECTOR SUPPLY CHAIN INTELLIGENCE SYSTEM")
    print("Stage 1: Demand Prioritization  |  Stage 2: Frontend / Manual Integration")
    print("=" * 80)
    print()

    date_str = input("Enter analysis date (DD.MM.YYYY): ")

    try:
        date_obj       = datetime.strptime(date_str, "%d.%m.%Y")
        date_formatted = date_obj.strftime("%d%m%Y")

        print(f"\nProcessing analysis for: {date_obj.strftime('%d-%m-%Y')}")
        print("-" * 80)

        # ====================================================================
        # STAGE 1: DEMAND PRIORITIZATION
        # ====================================================================
        print("\n[STAGE 1] Demand Prioritization Analysis")
        print("-" * 80)

        demand_df = process_single_date(date_formatted)

        if demand_df is None or demand_df.empty:
            print("\nError: Could not process Stage 1 data. Missing input files.")
            print("Please ensure all required files exist for the selected date.")
            return

        print(f"[STAGE 1] Successfully processed {len(demand_df)} SKUs")

        # ====================================================================
        # STAGE 2: FRONTEND / MANUAL INTEGRATION
        # ====================================================================
        print("\n[STAGE 2] Frontend / Manual Integration")
        print("-" * 80)

        final_df = process_frontend_override(demand_df, date_formatted)

        # ====================================================================
        # OUTPUT GENERATION
        # ====================================================================
        print("\n[OUTPUT] Generating Excel Report")
        print("-" * 80)

        # Sort by Final Rank (most urgent first)
        if "Final Rank" in final_df.columns:
            final_df = final_df.sort_values("Final Rank", ascending=True)

        with pd.ExcelWriter(STAGE2_OUTPUT_FILE, engine='openpyxl') as writer:
            final_df.to_excel(writer, sheet_name=date_formatted, index=False)

        print(f"\n✓ Report successfully generated: {STAGE2_OUTPUT_FILE}")
        print(f"  Sheet: {date_formatted}")
        print(f"  Total SKUs analyzed: {len(final_df)}")

        # ====================================================================
        # EXECUTIVE SUMMARY
        # ====================================================================
        print("\n[INSIGHTS] Executive Summary")
        print("-" * 80)

        manual_rows = final_df[final_df["Source"] == "Manual"] if "Source" in final_df.columns else pd.DataFrame()
        auto_rows   = final_df[final_df["Source"] == "Automated"] if "Source" in final_df.columns else final_df

        print(f"Manual Override:")
        print(f"  • Total manual entries injected : {len(manual_rows)}")
        if "HighestPriority" in manual_rows.columns and not manual_rows.empty:
            hp_count = len(manual_rows[manual_rows["HighestPriority"] == 1])
            print(f"  • Flagged 'Highest Priority'    : {hp_count}")

        print(f"\nAutomated SKUs:")
        print(f"  • Total automated entries       : {len(auto_rows)}")

        if "ConsolidatedPriorityScore" in auto_rows.columns and not auto_rows.empty:
            top_score = auto_rows["ConsolidatedPriorityScore"].max()
            print(f"  • Highest automated score       : {top_score:.4f}")

        print("\n" + "=" * 80)
        print("Analysis Complete!")
        print("=" * 80)

    except ValueError:
        print("\nError: Invalid date format. Please use DD.MM.YYYY format.")
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_integrated_analysis()
