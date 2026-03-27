# CTP/ctp_app_stage3.py
# CTP Stage 3 Runner — Machine Deployment Analysis
#
# Reads CTP Stage 2 output (CTP_frontend_demand_DDMMYYYY.xlsx),
# overlays daily mould report data, applies gap flags and yield adjustment.
#
# Usage (run from project root):
#     python CTP/ctp_app_stage3.py
#
# Input files:
#     CTP/CTP_frontend_demand_DDMMYYYY.xlsx     (CTP Stage 2 output)
#     data/Vectordata/Daily Mould Report/        (same BTP mould report location)
#
# Output:
#     CTP/CTP_frontend_running_demand_DDMMYYYY.xlsx
#     — Sheet "PCR_DDMMYYYY" : PCR final ranked output with deployment metrics
#     — Sheet "TBR_DDMMYYYY" : TBR final ranked output with deployment metrics
#     — History BOR tabs      : Last N days of BOR data for reference

import os
import sys
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# PATH SETUP
# ---------------------------------------------------------------------------
_CTP_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CTP_DIR)

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _CTP_DIR not in sys.path:
    sys.path.insert(0, _CTP_DIR)

os.chdir(_PROJECT_ROOT)

# BTP deployment processor is plant-agnostic — reuse it directly
from deployment_processor import (
    merge_demand_with_deployment,
    calculate_proxy_penetration,
    apply_gap_flags,
)
from ctp_deployment_processor import clean_mould_report_ctp
import ctp_config as config

# History BOR: reuse BTP helper (reads same BOR files)
from demand_processor import get_history_bor_data

# ---------------------------------------------------------------------------
# CONSTANTS (yield factors — can be moved to ctp_config.py later)
# ---------------------------------------------------------------------------
YIELD_FACTORS = {'OE': 0.95, 'EXP': 0.95}   # OE and EXP need over-production
YIELD_K       = {'OE': 0,    'EXP': 0}       # Safety buffer units


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _apply_yield(row) -> int:
    """Quality-adjusted production quantity (same logic as BTP Stage 3)."""
    mkt    = str(row.get("Market", ""))
    req    = row.get("Requirement", 0)
    if pd.isna(req):
        req = 0
    factor = YIELD_FACTORS.get(mkt, 1.0)
    k      = YIELD_K.get(mkt, 0)
    if factor < 1.0:
        return int(math.ceil(req / factor + k))
    return int(req + k)


def _select_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Select and order Stage 3 output columns,
    identical structure to BTP Stage 3 output.
    """
    output_columns = [
        # Ranking
        'Final Rank',
        # Identification
        'SKUCode', 'SKU Description', 'size',
        # Source & Manual Inputs
        'Source', 'HighestPriority', 'Target Date', 'Quantity',
        # Manual Scoring
        'weighted_score', 'modified_priority_score', 'manual_rank',
        # Market
        'Market',
        # Targets
        'Norm ', 'Virtual Norm', 'Adjusted_Target',
        # Demand Signals
        'Stock', 'Vector_Requirement', 'CPT_Requirement',
        'Requirement', 'Updated_Requirement',
        # Penetration
        'Penetration',
        # SKU Attributes
        'TopSKUFlag', 'HistoryPenetrationScore',
        # Deployment Metrics
        'MachineCount', 'AvgMouldHealth',
        'ProxyPenetration', 'ProxyRank',
        # Gap Flags
        'CriticalGap', 'ExcessProduction', 'MouldAlert', 'IsGhostSKU',
        # Revenue
        'ASP', 'Cure Time',
        # Scores
        'PriorityScore',
        'ConsolidatedPriorityScore',
    ]
    return df[[c for c in output_columns if c in df.columns]]


def _process_one_type(df: pd.DataFrame, date_str: str, tyre_type: str) -> pd.DataFrame:
    """
    Apply Stage 3 deployment analysis to one tyre type DataFrame.

    Args:
        df         : Stage 2 output for this tyre type (PCR or TBR)
        date_str   : DDMMYYYY
        tyre_type  : 'PCR' or 'TBR' (for logging)

    Returns:
        Fully enriched Stage 3 DataFrame with deployment metrics + gap flags
    """
    print(f"\n  === {tyre_type} — Stage 3 Deployment Analysis ===")

    # Ensure ConsolidatedPriorityScore exists (may be named ConsolidationPriorityScore in Stage 2)
    if "ConsolidatedPriorityScore" not in df.columns:
        if "ConsolidationPriorityScore" in df.columns:
            df = df.copy()
            df["ConsolidatedPriorityScore"] = df["ConsolidationPriorityScore"]
        else:
            df = df.copy()
            df["ConsolidatedPriorityScore"] = 0.0

    # ── Deployment analysis (mould report) ────────────────────────────────────
    mould_df = clean_mould_report_ctp(tyre_type, date_str)   # reads from CTP mould report path

    if mould_df is not None:
        print(f"  [MOULD] Found {len(mould_df)} SKUs in mould report")
    else:
        print(f"  [MOULD] No mould report found for {date_str} — MachineCount=0 for all")

    merged_df = merge_demand_with_deployment(df, mould_df)
    merged_df = calculate_proxy_penetration(merged_df)
    merged_df = apply_gap_flags(merged_df)

    # ── Ensure Requirement column exists for yield calc ───────────────────────
    if "Requirement" not in merged_df.columns:
        merged_df["Requirement"] = 0

    # ── Yield-adjusted Updated_Requirement ────────────────────────────────────
    merged_df["Updated_Requirement"] = merged_df.apply(_apply_yield, axis=1)
    print(f"  [YIELD] Updated_Requirement calculated for {tyre_type}")

    # ── Final Rank ─────────────────────────────────────────────────────────────
    sort_col = "ConsolidatedPriorityScore"
    merged_df = merged_df.sort_values(sort_col, ascending=False).reset_index(drop=True)
    merged_df["Final Rank"] = merged_df.index + 1

    # ── Impute numerics ────────────────────────────────────────────────────────
    _NUMERIC_FILL = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration', 'HistoryPenetrationScore',
        'PriorityScore', 'ConsolidatedPriorityScore',
        'MachineCount', 'AvgMouldHealth',
        'ProxyPenetration', 'ProxyRank', 'Updated_Requirement',
        'ASP', 'HighestPriority', 'manual_rank',
        'weighted_score', 'modified_priority_score',
    ]
    for col in _NUMERIC_FILL:
        if col in merged_df.columns:
            merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)

    for col in ['SKU Description', 'Source', 'Target Date']:
        if col in merged_df.columns:
            merged_df[col] = merged_df[col].fillna('')

    critical_gaps     = merged_df.get('CriticalGap',     pd.Series(False)).sum()
    excess_production = merged_df.get('ExcessProduction', pd.Series(False)).sum()
    mould_alerts      = merged_df.get('MouldAlert',      pd.Series(False)).sum()
    ghost_skus        = merged_df.get('IsGhostSKU',      pd.Series(False)).sum()

    print(f"  [{tyre_type}] Complete: {len(merged_df)} rows")
    print(f"    Critical Gaps      : {critical_gaps}")
    print(f"    Excess Production  : {excess_production}")
    print(f"    Mould Alerts       : {mould_alerts}")
    print(f"    Ghost SKUs         : {ghost_skus}")

    return _select_output_columns(merged_df)


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def run_ctp_stage3():
    print("=" * 70)
    print("  CTP SUPPLY CHAIN INTELLIGENCE — Stage 3")
    print("  Machine Deployment Analysis & Gap Flags")
    print("  Plant: 1900  |  Tyre Types: PCR + TBR")
    print("  [Mould Report: Separate CTP folders for PCR/TBR]")
    print("=" * 70)
    print()

    date_str = input("Enter date of CTP Stage 2 output (DD.MM.YYYY): ").strip()

    try:
        date_obj   = datetime.strptime(date_str, "%d.%m.%Y")
        ddmmyyyy   = date_obj.strftime("%d%m%Y")
        date_label = date_obj.strftime("%d-%m-%Y")
    except ValueError:
        print("❌ Invalid date format. Use DD.MM.YYYY")
        return

    # ── Locate Stage 2 output ────────────────────────────────────────────────
    stage2_file = os.path.join(_CTP_DIR, f"CTP_frontend_demand_{ddmmyyyy}.xlsx")

    if not os.path.exists(stage2_file):
        print(f"❌ CTP Stage 2 output not found: {stage2_file}")
        print(f"   Please run CTP/ctp_app_stage2.py first for date {date_label}")
        return

    print(f"Reading CTP Stage 2 output: {os.path.basename(stage2_file)}")

    xl         = pd.ExcelFile(stage2_file)
    all_sheets = xl.sheet_names

    pcr_sheet = next((s for s in all_sheets if s.upper().startswith("PCR")), None)
    tbr_sheet = next((s for s in all_sheets if s.upper().startswith("TBR")), None)

    if pcr_sheet is None and tbr_sheet is None:
        print(f"❌ No PCR or TBR sheets found in {os.path.basename(stage2_file)}")
        return

    pcr_df = xl.parse(pcr_sheet) if pcr_sheet else pd.DataFrame()
    tbr_df = xl.parse(tbr_sheet) if tbr_sheet else pd.DataFrame()

    print(f"  PCR sheet '{pcr_sheet}': {len(pcr_df)} rows")
    print(f"  TBR sheet '{tbr_sheet}': {len(tbr_df)} rows")

    # ── Run Stage 3 per tyre type ─────────────────────────────────────────────
    pcr_final = _process_one_type(pcr_df, ddmmyyyy, "PCR") if not pcr_df.empty else pd.DataFrame()
    tbr_final = _process_one_type(tbr_df, ddmmyyyy, "TBR") if not tbr_df.empty else pd.DataFrame()

    # ── History BOR tabs (same as BTP) ───────────────────────────────────────
    n_days = config.HISTORY_PENETRATION_N
    print(f"\n[OUTPUT] Loading BOR history for last {n_days} days...")
    history_bor = get_history_bor_data(ddmmyyyy, n_days, plant_prefix="1900")

    # Build SKU description lookup for BOR history tabs
    desc_lookup: dict = {}
    for df in [pcr_final, tbr_final]:
        if df is not None and not df.empty and "SKU Description" in df.columns:
            partial = (
                df.dropna(subset=["SKUCode"])
                .drop_duplicates("SKUCode")
                .set_index("SKUCode")["SKU Description"]
                .to_dict()
            )
            desc_lookup.update(partial)

    # ── Write output ─────────────────────────────────────────────────────────
    output_file = os.path.join(_CTP_DIR, f"CTP_frontend_running_demand_{ddmmyyyy}.xlsx")

    print(f"\nWriting CTP Stage 3 output: {os.path.basename(output_file)}")

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:

        # PCR sheet
        if pcr_final is not None and not pcr_final.empty:
            pcr_final.to_excel(writer, sheet_name=f"PCR_{ddmmyyyy}", index=False)
            print(f"  ✓ Sheet 'PCR_{ddmmyyyy}': {len(pcr_final)} rows")

        # TBR sheet
        if tbr_final is not None and not tbr_final.empty:
            tbr_final.to_excel(writer, sheet_name=f"TBR_{ddmmyyyy}", index=False)
            print(f"  ✓ Sheet 'TBR_{ddmmyyyy}': {len(tbr_final)} rows")

        # History BOR tabs
        tabs_written = 0
        for hl, bor_df in history_bor:
            if bor_df is None or bor_df.empty:
                print(f"  [History Tab] {hl} — skipped (no BOR file)")
                continue
            bor_df = bor_df.copy()
            bor_df["SKU Description"] = bor_df["SKUCode"].map(desc_lookup).fillna("")
            priority_cols = ["SKUCode", "SKU Description", "Location Code",
                             "Norm ", "Virtual Norm", "Stock", "Penetration"]
            ordered   = [c for c in priority_cols if c in bor_df.columns]
            remaining = [c for c in bor_df.columns if c not in ordered]
            bor_df[ordered + remaining].to_excel(writer, sheet_name=hl, index=False)
            tabs_written += 1
            print(f"  [History Tab] {hl} — {len(bor_df)} rows")

    # ── Executive Summary ────────────────────────────────────────────────────
    print(f"\n✅ CTP Stage 3 complete: {os.path.basename(output_file)}")
    print("=" * 70)
    for label, df in [("PCR", pcr_final), ("TBR", tbr_final)]:
        if df is None or df.empty:
            continue
        manual  = df[df["Source"] == "Manual"] if "Source" in df.columns else pd.DataFrame()
        auto    = df[df["Source"] == "Automated"] if "Source" in df.columns else df
        gaps    = int(df.get("CriticalGap", pd.Series(False)).sum())
        excess  = int(df.get("ExcessProduction", pd.Series(False)).sum())
        moulds  = int(df.get("MouldAlert", pd.Series(False)).sum())
        ghosts  = int(df.get("IsGhostSKU", pd.Series(False)).sum())
        print(f"\n  {label}:")
        print(f"    Manual entries    : {len(manual)}")
        print(f"    Automated entries : {len(auto)}")
        print(f"    Total rows        : {len(df)}")
        print(f"    🔴 Critical Gaps  : {gaps}")
        print(f"    ⚠️  Excess Prod.  : {excess}")
        print(f"    🔧 Mould Alerts   : {moulds}")
        print(f"    👻 Ghost SKUs     : {ghosts}")

    print(f"\n  History BOR tabs written : {tabs_written} of {n_days}")
    print()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_ctp_stage3()
