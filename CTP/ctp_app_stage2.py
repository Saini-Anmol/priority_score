# CTP/ctp_app_stage2.py
# CTP Stage 2 Runner — Frontend / Manual Demand Integration
#
# Usage (run from project root):
#     python CTP/ctp_app_stage2.py
#
# Reads:
#     CTP_combined_vector_demand_DDMMYYYY.xlsx  (CTP Stage 1 output)
#     CTP/ctp_manual_frontend_demand.xlsx        (CPT manual entries)
#
# Output:
#     CTP/CTP_frontend_demand_DDMMYYYY.xlsx
#     — Sheet "PCR_DDMMYYYY" : PCR final ranked output (manual + automated)
#     — Sheet "TBR_DDMMYYYY" : TBR final ranked output (manual + automated)

import os
import sys
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------------------------
# PATH SETUP
# ---------------------------------------------------------------------------
_CTP_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CTP_DIR)

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _CTP_DIR not in sys.path:
    sys.path.insert(0, _CTP_DIR)

# Run from project root so ./data/... paths resolve correctly
os.chdir(_PROJECT_ROOT)

from ctp_frontend_processor import process_ctp_frontend_override


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def run_ctp_stage2():
    print("=" * 70)
    print("  CTP SUPPLY CHAIN INTELLIGENCE — Stage 2")
    print("  Frontend / Manual Demand Integration")
    print("  Plant: 1900  |  Tyre Types: PCR + TBR")
    print("=" * 70)
    print()

    date_str = input("Enter date of CTP Stage 1 output (DD.MM.YYYY): ").strip()

    try:
        date_obj    = datetime.strptime(date_str, "%d.%m.%Y")
        ddmmyyyy    = date_obj.strftime("%d%m%Y")
        date_label  = date_obj.strftime("%d-%m-%Y")
    except ValueError:
        print("❌ Invalid date format. Use DD.MM.YYYY")
        return

    # ── Locate Stage 1 output ────────────────────────────────────────────────
    stage1_file = os.path.join(_CTP_DIR, f"CTP_combined_vector_demand_{ddmmyyyy}.xlsx")

    if not os.path.exists(stage1_file):
        print(f"❌ CTP Stage 1 output not found: {stage1_file}")
        print(f"   Please run CTP/ctp_app.py first for date {date_label}")
        return

    print(f"\nReading CTP Stage 1 output: {os.path.basename(stage1_file)}")

    # ── Read PCR and TBR sheets ───────────────────────────────────────────────
    xl         = pd.ExcelFile(stage1_file)
    all_sheets = xl.sheet_names

    pcr_sheet = next((s for s in all_sheets if s.upper().startswith("PCR")), None)
    tbr_sheet = next((s for s in all_sheets if s.upper().startswith("TBR")), None)

    if pcr_sheet is None and tbr_sheet is None:
        print(f"❌ No PCR or TBR sheets found in {os.path.basename(stage1_file)}")
        print(f"   Found sheets: {all_sheets}")
        return

    pcr_df = xl.parse(pcr_sheet) if pcr_sheet else pd.DataFrame()
    tbr_df = xl.parse(tbr_sheet) if tbr_sheet else pd.DataFrame()

    print(f"  PCR sheet '{pcr_sheet}': {len(pcr_df)} rows")
    print(f"  TBR sheet '{tbr_sheet}': {len(tbr_df)} rows")

    # ── Run Stage 2 ──────────────────────────────────────────────────────────
    pcr_final, tbr_final = process_ctp_frontend_override(pcr_df, tbr_df, ddmmyyyy)

    # ── Write output ─────────────────────────────────────────────────────────
    output_file = os.path.join(_CTP_DIR, f"CTP_frontend_demand_{ddmmyyyy}.xlsx")

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        if pcr_final is not None and not pcr_final.empty:
            pcr_final.to_excel(writer, sheet_name=f"PCR_{ddmmyyyy}", index=False)
            print(f"\n  ✓ Sheet 'PCR_{ddmmyyyy}': {len(pcr_final)} rows")

        if tbr_final is not None and not tbr_final.empty:
            tbr_final.to_excel(writer, sheet_name=f"TBR_{ddmmyyyy}", index=False)
            print(f"  ✓ Sheet 'TBR_{ddmmyyyy}': {len(tbr_final)} rows")

    # ── Executive Summary ────────────────────────────────────────────────────
    print(f"\n✅ CTP Stage 2 complete: {os.path.basename(output_file)}")
    print("=" * 70)
    print("  EXECUTIVE SUMMARY")
    print("=" * 70)

    for label, df in [("PCR", pcr_final), ("TBR", tbr_final)]:
        if df is None or df.empty:
            continue
        manual_rows = df[df.get("Source", pd.Series("")) == "Manual"] if "Source" in df.columns else pd.DataFrame()
        auto_rows   = df[df.get("Source", pd.Series("")) == "Automated"] if "Source" in df.columns else df
        hp_count    = int((manual_rows["HighestPriority"] == 1).sum()) if not manual_rows.empty and "HighestPriority" in manual_rows.columns else 0

        print(f"\n  {label}:")
        print(f"    Manual entries           : {len(manual_rows)}  (HP=1: {hp_count})")
        print(f"    Automated entries        : {len(auto_rows)}")
        print(f"    Total rows               : {len(df)}")
        if "ConsolidationPriorityScore" in df.columns:
            top = df["ConsolidationPriorityScore"].max()
            print(f"    Top ConsolidationScore   : {top:.6f}")

    print()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_ctp_stage2()
