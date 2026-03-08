# ctp_app.py
# CTP Stage 1 Runner — Plant 1900 (PCR + TBR)
#
# Usage (run from project root):
#     python CTP/ctp_app.py
#
# Output:
#     CTP_combined_vector_demand_<DDMMYYYY>.xlsx
#     — Sheet "PCR_<DDMMYYYY>" : PCR SKU priority scores
#     — Sheet "TBR_<DDMMYYYY>" : TBR SKU priority scores

import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# PATH SETUP — allow running from project root OR from CTP/ subfolder
# ---------------------------------------------------------------------------
_CTP_DIR     = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CTP_DIR)

# Ensure project root is in sys.path (for data folder resolution)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
# Ensure CTP dir is in sys.path (for ctp_config and ctp_demand_processor)
if _CTP_DIR not in sys.path:
    sys.path.insert(0, _CTP_DIR)

# Change working directory to project root so relative paths (./data/...) resolve correctly
os.chdir(_PROJECT_ROOT)

from ctp_demand_processor import process_single_date


def run_ctp_report():
    print("=" * 70)
    print("  CTP Supply Chain Intelligence — Stage 1 Demand Prioritization")
    print("  Plant: 1900  |  Tyre Types: PCR + TBR")
    print("=" * 70)

    # ── DATE RANGE INPUT ─────────────────────────────────────────────────────
    start_str = input("\nEnter start date (DD.MM.YYYY): ").strip()
    end_str   = input("Enter end date   (DD.MM.YYYY): ").strip()

    try:
        start_date = datetime.strptime(start_str, "%d.%m.%Y")
        end_date   = datetime.strptime(end_str,   "%d.%m.%Y")
    except ValueError:
        print("\n❌ ERROR: Invalid date format. Please use DD.MM.YYYY (e.g. 26.02.2026)")
        return

    if end_date < start_date:
        print("\n❌ ERROR: End date must be on or after start date.")
        return

    days  = (end_date - start_date).days + 1
    print(f"\nProcessing {days} date(s) from {start_str} to {end_str} ...\n")

    pcr_dict: dict = {}   # date_str → PCR DataFrame
    tbr_dict: dict = {}   # date_str → TBR DataFrame

    for i in range(days):
        current_date = (start_date + timedelta(days=i)).strftime("%d%m%Y")
        print(f"[{i+1}/{days}] Processing: {current_date}")
        pcr_df, tbr_df = process_single_date(current_date)

        if pcr_df is not None and not pcr_df.empty:
            pcr_dict[current_date] = pcr_df
        if tbr_df is not None and not tbr_df.empty:
            tbr_dict[current_date] = tbr_df

    # ── WRITE OUTPUT ─────────────────────────────────────────────────────────
    if not pcr_dict and not tbr_dict:
        print("\n⚠  No data found for any date in the selected range.")
        print("   Check that BOR/BPR/BMR files exist in ./data/Vectordata/")
        return

    output_end_date = end_date.strftime("%d%m%Y")
    output_file     = os.path.join(_CTP_DIR, f"CTP_combined_vector_demand_{output_end_date}.xlsx")

    print(f"\nWriting output to: {output_file}")
    print("-" * 70)

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:

        # PCR sheets
        for date_str, df in pcr_dict.items():
            sheet_name = f"PCR_{date_str}"
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  ✓ Sheet '{sheet_name}': {len(df)} PCR SKUs")

        # TBR sheets
        for date_str, df in tbr_dict.items():
            sheet_name = f"TBR_{date_str}"
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  ✓ Sheet '{sheet_name}': {len(df)} TBR SKUs")

    print(f"\n✅ Successfully generated: {os.path.basename(output_file)}")
    total_pcr = sum(len(df) for df in pcr_dict.values())
    total_tbr = sum(len(df) for df in tbr_dict.values())
    print(f"   Total PCR SKU-rows: {total_pcr}")
    print(f"   Total TBR SKU-rows: {total_tbr}")
    print(f"   Total sheets: {len(pcr_dict) + len(tbr_dict)}")


if __name__ == "__main__":
    run_ctp_report()
