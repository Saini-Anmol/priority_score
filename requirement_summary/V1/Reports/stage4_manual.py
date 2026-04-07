# V1/Reports/stage4_manual.py
# ---------------------------------------------------------------------------
# STAGE 4: MANUAL OVERRIDE & HYBRID SYNTHESIS
# Scores manually-entered SKUs using a 4-step weighted scoring pipeline.
# Guarantees final output order:
#   1st → Manual SKUs with HighestPriority = 1 (by ConsolidationPriorityScore desc)
#   2nd → Manual SKUs with HighestPriority = 0 (by ConsolidationPriorityScore desc)
#   3rd → Automated SKUs                       (by ProxyRank)
# ---------------------------------------------------------------------------

import os
from datetime import datetime
import pandas as pd
import numpy as np

# Import configuration and utilities
import V1.Setups.config as config
from V1.Utilities.math_utils import minmax_normalize, extract_rim_size
from V1.Utilities.data_loaders import load_avg_sales, load_oe_demand

_TODAY = datetime.now().date()

def _load_manual_data(db_engine) -> pd.DataFrame:
    """
    Load and validate the manual frontend demand Excel file.
    Expected columns: SKU Code | SKU Description | Market | Quantity | Target Date | Highest Priority
    'Target Date' is optional — defaults to today if absent.
    """
    if db_engine is None:
        raise ConnectionError("No active database connection to fetch manual demand.")

    query = "SELECT * FROM jkplanningV1.btp_demand_tracker WHERE changesIncorporated = 0"
    try:
        df = pd.read_sql(query, con=db_engine)
    except Exception as e:
        raise RuntimeError(f"Failed to read from database: {str(e)}")
    df.columns = df.columns.str.strip()

    rename_map = {
        "skuCode":         "SKUCode",
        "skuDescription":  "SKU Description",
        "market":           "Market",
        "quantity":         "Quantity",
        "targetDate":      "Target Date",
        "highestPriority": "HighestPriority",
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

    required = ["SKUCode", "Quantity", "Market", "HighestPriority"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Manual demand file is missing required columns: {missing}")

    df["SKUCode"]         = df["SKUCode"].astype(str).str.strip()
    df["Market"]          = df["Market"].astype(str).str.strip()
    df["Quantity"]        = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["HighestPriority"] = pd.to_numeric(df["HighestPriority"], errors="coerce").fillna(0).astype(int)

    if "Target Date" in df.columns:
        df["Target Date"] = pd.to_datetime(df["Target Date"], errors="coerce", dayfirst=True).dt.date.fillna(_TODAY)
    else:
        df["Target Date"] = _TODAY

    return df[df["SKUCode"].str.len() > 0].copy()

def _compute_weighted_score(df: pd.DataFrame, max_auto: float) -> pd.DataFrame:
    """
    Four-step manual scoring pipeline:
    Step 1: weighted_score (Market + Qty + Date normalisation)
    Step 2: Pre-rank HighestPriority=1 rows
    Step 3: modified_priority_score (Boost HP=1 rows)
    Step 4: ConsolidationPriorityScore (Guarantees manual > automated)
    """
    N = len(df)

    # ── Step 1: weighted_score ──
    market_scores = df["Market"].map(config.MARKET_SCORE).fillna(1).astype(float)
    norm_market   = minmax_normalize(market_scores, fallback=1.0)
    norm_qty      = minmax_normalize(df["Quantity"].astype(float), fallback=1.0)

    days_remaining = df["Target Date"].apply(lambda d: max((d - _TODAY).days, 0) if isinstance(d, type(_TODAY)) else 0).astype(float)
    norm_date = 1.0 - minmax_normalize(days_remaining, fallback=1.0)   # closer date = higher score

    df = df.copy()
    df["weighted_score"] = (
        config.W_MARKET * norm_market +
        config.W_QTY * norm_qty +
        config.W_TARGET_DATE * norm_date
    ).round(2)

    # ── Step 2 & 3: modified_priority_score ──
    max_ws        = df["weighted_score"].max()
    priority_mask = df["HighestPriority"] == 1
    P             = int(priority_mask.sum())

    df["priority_rank"] = 0
    df["modified_priority_score"] = df["weighted_score"]   # default for HP=0

    if P > 0:
        hp1_idx = df.index[priority_mask]
        df.loc[hp1_idx, "priority_rank"] = df.loc[hp1_idx, "weighted_score"].rank(ascending=True, method="first").astype(int)
        df.loc[hp1_idx, "modified_priority_score"] = (max_ws * (1.0 + df.loc[hp1_idx, "priority_rank"] / P)).round(2)

    # ── Step 4: ConsolidationPriorityScore ──
    df["overall_rank"] = df["modified_priority_score"].rank(ascending=True, method="first").astype(int)
    df["ConsolidationPriorityScore"] = (max_auto * (1.0 + df["overall_rank"] / N)).round(2)
    df["manual_rank"] = df["ConsolidationPriorityScore"].rank(ascending=False, method="first").astype(int)

    df = df.sort_values("manual_rank", ascending=True).reset_index(drop=True)
    return df

def _build_manual_rows(manual_df: pd.DataFrame, stage3_df: pd.DataFrame, vector_req_lookup: dict) -> pd.DataFrame:
    """Construct manual rows column-compatible with the Stage 3 DataFrame."""
    
    # Attach mould metrics if available
    mould_cols = ["SKUCode", "MachineCount", "AvgMouldHealth"]
    available  = [c for c in mould_cols if c in stage3_df.columns]
    
    if len(available) == 3:
        mould_lookup = stage3_df[available].drop_duplicates(subset="SKUCode")
        manual_df = manual_df.merge(mould_lookup, on="SKUCode", how="left")
        manual_df["MachineCount"]   = manual_df["MachineCount"].fillna(0).astype(int)
        manual_df["AvgMouldHealth"] = manual_df["AvgMouldHealth"].fillna(0.0)
    else:
        manual_df["MachineCount"] = 0
        manual_df["AvgMouldHealth"] = 0.0

    manual_rows = pd.DataFrame(index=manual_df.index)
    
    manual_rows["SKUCode"]             = manual_df["SKUCode"]
    manual_rows["SKU Description"]     = manual_df.get("SKU Description", pd.Series([""] * len(manual_df)))
    manual_rows["size"]                = extract_rim_size(manual_df["SKUCode"])
    manual_rows["Market"]              = manual_df["Market"]
    
    manual_rows["Quantity"]                    = manual_df["Quantity"]
    manual_rows["Target Date"]                 = manual_df["Target Date"].astype(str)
    manual_rows["HighestPriority"]             = manual_df["HighestPriority"]
    manual_rows["weighted_score"]              = manual_df["weighted_score"]
    manual_rows["modified_priority_score"]     = manual_df["modified_priority_score"]
    manual_rows["manual_rank"]                 = manual_df["manual_rank"]
    manual_rows["ConsolidationPriorityScore"]  = manual_df["ConsolidationPriorityScore"]

    # Transparency lookups
    manual_rows["Vector_Requirement"] = [vector_req_lookup.get((sku, mkt), 0) for sku, mkt in zip(manual_df["SKUCode"], manual_df["Market"].astype(str).str.strip())]
    manual_rows["CPT_Requirement"]    = manual_df["Quantity"]
    manual_rows["Requirement"]        = manual_df["Quantity"]
    manual_rows["Updated_Requirement"]= manual_df["Quantity"] # Force Updated to match Quantity for manual rows

    manual_rows["Penetration"]        = 100.0
    manual_rows["IsGhostSKU"]         = False
    manual_rows["Cure Time"]          = 20
    # Look up real values from reference files (not hardcoded 0)
    avg_sales = load_avg_sales()
    oe_demand = load_oe_demand()
    manual_rows["avg_sales_qty"] = [
        round(avg_sales.get((str(sku).strip().upper(), str(mkt).strip().upper()), 0), 1)
        for sku, mkt in zip(manual_df["SKUCode"], manual_df["Market"])
    ]
    manual_rows["oe_demand_qty"] = [
        oe_demand.get(str(sku).strip().upper(), 0)
        for sku in manual_df["SKUCode"]
    ]
    
    manual_rows["MachineCount"]       = manual_df["MachineCount"]
    manual_rows["AvgMouldHealth"]     = manual_df["AvgMouldHealth"]
    manual_rows["CriticalGap"]        = manual_df["MachineCount"] == 0
    manual_rows["ExcessProduction"]   = False
    manual_rows["MouldAlert"]         = manual_df["AvgMouldHealth"] > 0.9
    
    manual_rows["Source"]             = "CPT"
    manual_rows["ProxyRank"]          = manual_df["manual_rank"]
    
    return manual_rows


def _select_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Select and order output columns to match the old pipeline's Stage 4/5 output exactly.

    Column groups (A → Z order):
        A    : Final Rank
        B–D  : SKU Identification
        E–H  : Source & Manual Inputs
        I–K  : Manual Scoring Intermediates
        L    : Market
        M–O  : Production Targets
        P–W  : Demand Signals (incl. Updated_Requirement)
        X    : SKU Attributes
        Y    : History Penetration
        Z–AF : Deployment Metrics & Gap Flags
        AG–AH: Revenue & Efficiency
        AI   : Stage 1 Raw Score (PriorityScore)
        AJ   : Final Score (ConsolidatedPriorityScore — always last)
    """
    output_columns = [
        # A — Final Rank
        'Final Rank',

        # B–D — SKU Identification
        'SKUCode', 'SKU Description', 'size',

        # E–H — Source & Manual Inputs
        'Source', 'HighestPriority', 'Target Date', 'Quantity',

        # I–K — Manual Scoring Intermediates
        'weighted_score', 'modified_priority_score', 'manual_rank',

        # L — Market
        'Market',

        # M–O — Production Targets
        'Norm ', 'Virtual Norm', 'Adjusted_Target',

        # P–W — Demand Signals
        'Stock',
        'Vector_Requirement', 'CPT_Requirement',
        'Requirement', 'Updated_Requirement',
        'avg_sales_qty', 'oe_demand_qty',
        'Penetration',

        # X — SKU Attributes
        'TopSKUFlag',

        # Y — History Penetration
        'HistoryPenetrationScore',

        # Z–AF — Deployment Metrics & Gap Flags
        'MachineCount', 'AvgMouldHealth',
        'ProxyPenetration', 'ProxyRank',
        'CriticalGap', 'ExcessProduction', 'MouldAlert', 'IsGhostSKU',

        # AG–AH — Revenue & Efficiency
        'ASP', 'Cure Time',

        # AI — Stage 1 raw score
        'PriorityScore',

        # AJ — Final Score (always last column)
        'ConsolidatedPriorityScore',
    ]

    available = [c for c in output_columns if c in df.columns]
    return df[available]


def run_stage4(stage3_df: pd.DataFrame, date_str: str, db_engine) -> pd.DataFrame:
    """Main orchestration function for Stage 4 Frontend Integration."""
    print(f"\n[Stage 4] Starting Manual Override Integration for {date_str}...")

    def _automated_only(df):
        df = df.copy()
        df["Source"] = "Vector"
        df["Vector_Requirement"] = df.get("Requirement", 0)
        df["CPT_Requirement"]    = 0
        df["HighestPriority"]    = 0
        df["Target Date"]        = ""
        df["Quantity"]           = 0
        df["weighted_score"]     = 0.0
        df["modified_priority_score"] = 0.0
        df["manual_rank"]        = 0
        df["ConsolidationPriorityScore"] = pd.to_numeric(df.get("ConsolidatedPriorityScore", 0), errors="coerce").fillna(0)
        df = df.sort_values("ConsolidatedPriorityScore", ascending=False).reset_index(drop=True)
        df["Final Rank"] = df.index + 1
        return _select_output_columns(df.rename(columns={'ConsolidationPriorityScore': 'ConsolidatedPriorityScore'}))

    try:
        manual_df = _load_manual_data(db_engine)
        print(f"  - Loaded {len(manual_df)} manual entries")
    except FileNotFoundError as e:
        print(f"  [WARN] {e}")
        return _automated_only(stage3_df)

    if manual_df.empty:
        return _automated_only(stage3_df)

    # Calculate Ceiling
    score_col = "ConsolidatedPriorityScore"
    max_auto  = float(pd.to_numeric(stage3_df[score_col], errors="coerce").max() if score_col in stage3_df.columns else 1.0)
    if max_auto <= 0: max_auto = 1.0

    manual_df = _compute_weighted_score(manual_df, max_auto)

    # Match existing demands
    auto_df = stage3_df.copy()
    auto_df["SKUCode"] = auto_df["SKUCode"].astype(str).str.strip()
    auto_df["Market"]  = auto_df["Market"].astype(str).str.strip()

    req_col = "Requirement"
    vector_req_lookup = {}
    if req_col in auto_df.columns:
        manual_sku_mkt_pairs = set(zip(manual_df["SKUCode"].str.strip(), manual_df["Market"].astype(str).str.strip()))
        auto_df["_pair"] = list(zip(auto_df["SKUCode"], auto_df["Market"]))
        vector_req_lookup = auto_df[auto_df["_pair"].isin(manual_sku_mkt_pairs)].groupby(["SKUCode", "Market"])[req_col].sum().to_dict()
        auto_df.drop(columns=["_pair"], inplace=True)

    manual_rows = _build_manual_rows(manual_df, stage3_df, vector_req_lookup)
    n_manual    = len(manual_rows)

    # Supersede logic — always supersede matching (SKUCode, Market) pairs
    pairs_to_supersede = set(zip(manual_df["SKUCode"].str.strip(), manual_df["Market"].astype(str).str.strip()))
    auto_df["_pair"] = list(zip(auto_df["SKUCode"], auto_df["Market"]))
    superseded_mask  = auto_df["_pair"].isin(pairs_to_supersede)
    auto_df          = auto_df[~superseded_mask].drop(columns=["_pair"]).copy()

    # Tag automated rows
    auto_df["Source"]                     = "Vector"
    auto_df["Vector_Requirement"]         = auto_df[req_col] if req_col in auto_df.columns else 0
    auto_df["CPT_Requirement"]            = 0
    auto_df["ConsolidationPriorityScore"] = pd.to_numeric(auto_df.get(score_col, 0), errors="coerce").fillna(0)

    if "IsGhostSKU" not in auto_df.columns:
        auto_df["IsGhostSKU"] = False

    # Re-rank Automated rows
    if "ProxyRank" in auto_df.columns:
        auto_df = auto_df.sort_values("ProxyRank", ascending=True).reset_index(drop=True)
        auto_df["ProxyRank"] = auto_df.index + n_manual + 1

    # Vertical Merge
    hybrid_df = pd.concat([manual_rows, auto_df], ignore_index=True, sort=False)

    # ── Data imputation (same as old pipeline) ────────────────────────────────
    _NUMERIC_FILL_ZERO = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Updated_Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration',
        'PriorityScore', 'ConsolidatedPriorityScore', 'ConsolidationPriorityScore',
        'ProxyPenetration', 'ProxyRank',
        'ASP',
        'HighestPriority', 'manual_rank',
        'weighted_score', 'modified_priority_score',
    ]
    for col in _NUMERIC_FILL_ZERO:
        if col in hybrid_df.columns:
            hybrid_df[col] = pd.to_numeric(hybrid_df[col], errors='coerce').fillna(0).round(2)

    for col in ['SKU Description', 'Source', 'Target Date']:
        if col in hybrid_df.columns:
            hybrid_df[col] = hybrid_df[col].fillna('')

    # Final Rank sorting
    hybrid_df = hybrid_df.sort_values("ConsolidationPriorityScore", ascending=False).reset_index(drop=True)
    hybrid_df["Final Rank"] = hybrid_df.index + 1

    # Rename canonical score column (ConsolidationPriorityScore → ConsolidatedPriorityScore)
    # Drop the old ConsolidatedPriorityScore first to prevent .1 duplicate
    if 'ConsolidatedPriorityScore' in hybrid_df.columns and 'ConsolidationPriorityScore' in hybrid_df.columns:
        hybrid_df.drop(columns=['ConsolidatedPriorityScore'], inplace=True)
    hybrid_df = hybrid_df.rename(columns={'ConsolidationPriorityScore': 'ConsolidatedPriorityScore'})

    print(f"  - Override complete: {n_manual} Manual entries, {len(auto_df)} Automated entries")
    return _select_output_columns(hybrid_df)