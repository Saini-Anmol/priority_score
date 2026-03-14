# CTP/ctp_frontend_processor.py
# CTP Stage 2: Frontend / Manual Demand Integration Engine
#
# Reads ./CTP/data/ctp_manual_frontend_demand.xlsx and scores manually-entered
# SKUs using the same 4-step weighted scoring pipeline as BTP Stage 2.
#
# Pipeline:
#   Stage 1 output (PCR + TBR DataFrames)
#   → Score manual entries (4-step)
#   → Supersede automated rows by (SKUCode, Market)
#   → Concat manual + remaining automated (per tyre type)
#   → Assign Final Rank per tyre type
#
# Scoring guarantee (final output order):
#   1st  →  Manual SKUs with HighestPriority = 1  (ordered by score desc)
#   2nd  →  Manual SKUs with HighestPriority = 0  (ordered by score desc)
#   3rd  →  Vector / Automated SKUs               (ordered by ConsolidatedPriorityScore desc)

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

# Allow running from project root or CTP/ subfolder
_CTP_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CTP_DIR)
if _CTP_DIR not in sys.path:
    sys.path.insert(0, _CTP_DIR)

from ctp_config import PCR_SKU_LIST_FILE

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
CTP_MANUAL_INPUT_FILE = os.path.join(_CTP_DIR, "ctp_manual_frontend_demand.xlsx")
_TODAY = datetime.now().date()

# Manual scoring weights (same as BTP Stage 2)
W_MARKET      = 0.30
W_QTY         = 0.40
W_TARGET_DATE = 0.30

MARKET_SCORE = {
    "OE":   4,
    "OE10": 4,
    "ST":   3,
    "EXP":  2,
    "OTR":  2,
    "RE":   1,
}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _minmax(series: pd.Series) -> pd.Series:
    """Min-max normalization. Returns 1.0 for all rows if range is zero."""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(1.0, index=series.index)
    return (series - lo) / (hi - lo)


def _extract_size(sku_series: pd.Series):
    """Extract rim size from SKUCode[8:10]."""
    return pd.to_numeric(sku_series.str[8:10], errors="coerce").fillna(0).astype("Int64")


def _load_pcr_sku_list() -> set:
    """Load PCR SKU list from SKU_List.xlsx — returns set of PCR SKUCodes."""
    try:
        df = pd.read_excel(PCR_SKU_LIST_FILE)
        col = df.columns[0]
        return set(df[col].astype(str).str.strip().tolist())
    except Exception as e:
        print(f"  [WARN] Could not load PCR SKU list: {e}")
        return set()


# ---------------------------------------------------------------------------
# LOAD MANUAL DATA
# ---------------------------------------------------------------------------

def _load_manual_data() -> pd.DataFrame:
    """
    Load and validate CTP manual demand file.
    Expected columns: SKU Code | Market | Quantity | Target Date | Highest Priority
    """
    if not os.path.exists(CTP_MANUAL_INPUT_FILE):
        raise FileNotFoundError(
            f"CTP manual demand file not found: '{CTP_MANUAL_INPUT_FILE}'\n"
            f"Please create: CTP/ctp_manual_frontend_demand.xlsx"
        )

    df = pd.read_excel(CTP_MANUAL_INPUT_FILE)
    df.columns = df.columns.str.strip()

    rename_map = {
        "SKU Code":         "SKUCode",
        "SKU Description":  "SKU Description",
        "Market":           "Market",
        "Quantity":         "Quantity",
        "Target Date":      "Target Date",
        "Highest Priority": "HighestPriority",
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

    required = ["SKUCode", "Quantity", "Market", "HighestPriority"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CTP manual demand file is missing columns: {missing}")

    df["SKUCode"]         = df["SKUCode"].astype(str).str.strip()
    df["Market"]          = df["Market"].astype(str).str.strip()
    df["Quantity"]        = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["HighestPriority"] = pd.to_numeric(df["HighestPriority"], errors="coerce").fillna(0).astype(int)

    if "Target Date" in df.columns:
        df["Target Date"] = pd.to_datetime(df["Target Date"], errors="coerce").dt.date.fillna(_TODAY)
    else:
        df["Target Date"] = _TODAY

    return df[df["SKUCode"].str.len() > 0].copy()


# ---------------------------------------------------------------------------
# 4-STEP SCORING PIPELINE (identical to BTP)
# ---------------------------------------------------------------------------

def _compute_weighted_score(df: pd.DataFrame, max_auto: float) -> pd.DataFrame:
    """
    Four-step manual scoring pipeline — same logic as BTP frontend_processor.py.

    Step 1 — weighted_score ∈ [0, 1]
        W_MARKET × norm_market + W_QTY × norm_qty + W_TARGET_DATE × (1 − norm_days)

    Step 2 — HP=1 pre-rank (ascending weighted_score within HP=1 group)

    Step 3 — modified_priority_score
        HP=1: max_ws × (1 + priority_rank / P)  → always > HP=0 scores
        HP=0: weighted_score

    Step 4 — StrategicPriorityScore (all manual > all automated)
        = max_auto × (1 + overall_rank / N)
    """
    N = len(df)

    # Step 1
    market_scores = df["Market"].map(MARKET_SCORE).fillna(1).astype(float)
    norm_market   = _minmax(market_scores)
    norm_qty      = _minmax(df["Quantity"].astype(float))
    days_remaining = df["Target Date"].apply(
        lambda d: max((d - _TODAY).days, 0) if isinstance(d, type(_TODAY)) else 0
    ).astype(float)
    norm_date = 1.0 - _minmax(days_remaining)

    df = df.copy()
    df["weighted_score"] = (
        W_MARKET      * norm_market +
        W_QTY         * norm_qty    +
        W_TARGET_DATE * norm_date
    ).round(6)

    # Steps 2 & 3
    max_ws        = df["weighted_score"].max()
    priority_mask = df["HighestPriority"] == 1
    P             = int(priority_mask.sum())

    df["priority_rank"]           = 0
    df["modified_priority_score"] = df["weighted_score"]

    if P > 0:
        hp1_idx = df.index[priority_mask]
        df.loc[hp1_idx, "priority_rank"] = (
            df.loc[hp1_idx, "weighted_score"]
            .rank(ascending=True, method="first")
            .astype(int)
        )
        df.loc[hp1_idx, "modified_priority_score"] = (
            max_ws * (1.0 + df.loc[hp1_idx, "priority_rank"] / P)
        ).round(6)

    # Step 4
    df["overall_rank"] = (
        df["modified_priority_score"]
        .rank(ascending=True, method="first")
        .astype(int)
    )
    df["StrategicPriorityScore"] = (
        max_auto * (1.0 + df["overall_rank"] / N)
    ).round(6)

    df["manual_rank"] = (
        df["StrategicPriorityScore"]
        .rank(ascending=False, method="first")
        .astype(int)
    )

    df = df.sort_values("manual_rank", ascending=True).reset_index(drop=True)

    print(f"  [CTP STAGE 2] Manual scoring complete: {N} entries "
          f"(HP=1: {P}, HP=0: {N - P})")
    print(f"  [CTP STAGE 2] max_ws={max_ws:.6f}  max_auto={max_auto:.6f}")
    return df


# ---------------------------------------------------------------------------
# BUILD MANUAL ROWS (column-compatible with Stage 1 output)
# ---------------------------------------------------------------------------

def _build_manual_rows(
    manual_df: pd.DataFrame,
    stage1_df: pd.DataFrame,
    vector_req_lookup: dict,
) -> pd.DataFrame:
    """Build manual rows matching Stage 1 column structure."""
    rows = pd.DataFrame(index=manual_df.index)

    rows["SKUCode"]         = manual_df["SKUCode"]
    rows["SKU Description"] = manual_df.get("SKU Description", pd.Series([""] * len(manual_df), index=manual_df.index))
    rows["size"]            = _extract_size(manual_df["SKUCode"])
    rows["Market"]          = manual_df["Market"]

    rows["Quantity"]          = manual_df["Quantity"]
    rows["Target Date"]       = manual_df["Target Date"].astype(str)
    rows["HighestPriority"]   = manual_df["HighestPriority"]

    rows["weighted_score"]           = manual_df["weighted_score"]
    rows["modified_priority_score"]  = manual_df["modified_priority_score"]
    rows["ConsolidationPriorityScore"] = manual_df["StrategicPriorityScore"]
    rows["manual_rank"]              = manual_df["manual_rank"]

    rows["Vector_Requirement"] = [
        vector_req_lookup.get((sku, mkt), 0)
        for sku, mkt in zip(manual_df["SKUCode"], manual_df["Market"].astype(str).str.strip())
    ]
    rows["CPT_Requirement"] = manual_df["Quantity"]
    rows["Requirement"]     = manual_df["Quantity"]
    rows["Penetration"]     = 100.0
    rows["Source"]          = "Manual"
    rows["ConsolidatedPriorityScore"] = manual_df["StrategicPriorityScore"]

    return rows


# ---------------------------------------------------------------------------
# SELECT OUTPUT COLUMNS (same structure as BTP Stage 2)
# ---------------------------------------------------------------------------

def _select_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Select and order Stage 2 output columns."""
    output_columns = [
        'Rank_ConsolidationPriorityScore',
        'SKUCode', 'SKU Description', 'size',
        'Source', 'HighestPriority', 'Target Date', 'Quantity',
        'weighted_score', 'modified_priority_score', 'manual_rank',
        'Market',
        'Norm ', 'Virtual Norm', 'Adjusted_Target',
        'Stock',
        'Vector_Requirement', 'CPT_Requirement', 'Requirement',
        'Penetration',
        'TopSKUFlag',
        'HistoryPenetrationScore',
        'ASP', 'Cure Time',
        'PriorityScore',
        'ConsolidationPriorityScore',
    ]
    return df[[c for c in output_columns if c in df.columns]]


# ---------------------------------------------------------------------------
# AUTOMATED-ONLY PATH
# ---------------------------------------------------------------------------

def _automated_only(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Source"]                     = "Automated"
    req = "Requirement"
    df["Vector_Requirement"]         = df[req] if req in df.columns else 0
    df["CPT_Requirement"]            = 0
    df["ConsolidationPriorityScore"] = pd.to_numeric(
        df.get("ConsolidatedPriorityScore", pd.Series(0.0, index=df.index)),
        errors="coerce"
    ).fillna(0)
    df = df.sort_values("ConsolidationPriorityScore", ascending=False).reset_index(drop=True)
    df["Rank_ConsolidationPriorityScore"] = df.index + 1
    return _select_output_columns(df)


# ---------------------------------------------------------------------------
# CORE PROCESSING (per tyre type)
# ---------------------------------------------------------------------------

def _process_one_type(
    stage1_df: pd.DataFrame,
    manual_df: pd.DataFrame,
    tyre_type: str,
) -> pd.DataFrame:
    """
    Run the full Stage 2 pipeline for one tyre type (PCR or TBR).

    Args:
        stage1_df : Stage 1 output filtered to this tyre type
        manual_df : Manual entries filtered (or labelled) for this tyre type
        tyre_type : 'PCR' or 'TBR' (for logging only)
    """
    print(f"\n  === {tyre_type} — Stage 2 Frontend Override ===")

    if manual_df.empty:
        print(f"  [CTP STAGE 2] No manual entries for {tyre_type} — automated only.")
        return _automated_only(stage1_df)

    # max_auto from Stage 1
    score_col = "ConsolidatedPriorityScore"
    max_auto  = float(
        pd.to_numeric(stage1_df[score_col], errors="coerce").max()
        if score_col in stage1_df.columns else 1.0
    )
    if max_auto <= 0:
        max_auto = 1.0

    # Score manual entries
    manual_scored = _compute_weighted_score(manual_df, max_auto)

    # Build vector_req_lookup keyed by (SKUCode, Market)
    auto_df = stage1_df.copy()
    auto_df["SKUCode"] = auto_df["SKUCode"].astype(str).str.strip()
    auto_df["Market"]  = auto_df["Market"].astype(str).str.strip()

    req_col = "Requirement"
    vector_req_lookup: dict = {}
    if req_col in auto_df.columns:
        manual_pairs = set(zip(manual_scored["SKUCode"].str.strip(), manual_scored["Market"].str.strip()))
        sku_mkt_list = list(zip(auto_df["SKUCode"], auto_df["Market"]))
        auto_df["_pair"] = sku_mkt_list
        vector_req_lookup = (
            auto_df[auto_df["_pair"].isin(manual_pairs)]
            .groupby(["SKUCode", "Market"])[req_col]
            .sum()
            .to_dict()
        )
        auto_df.drop(columns=["_pair"], inplace=True)

    # Build manual rows
    manual_rows = _build_manual_rows(manual_scored, stage1_df, vector_req_lookup)

    # Supersede automated rows
    pairs_to_supersede = set()
    for _, mrow in manual_scored.iterrows():
        sku    = mrow["SKUCode"]
        market = str(mrow["Market"]).strip()
        vec_req = vector_req_lookup.get((sku, market), 0)
        cpt_req = float(mrow["Quantity"])
        if vec_req != cpt_req:
            pairs_to_supersede.add((sku, market))

    auto_df["_pair"] = list(zip(
        auto_df["SKUCode"].astype(str).str.strip(),
        auto_df["Market"].astype(str).str.strip()
    ))
    superseded_mask = auto_df["_pair"].isin(pairs_to_supersede)
    n_superseded    = superseded_mask.sum()
    auto_df         = auto_df[~superseded_mask].drop(columns=["_pair"]).copy()

    if n_superseded > 0:
        print(f"  [CTP STAGE 2] Removed {n_superseded} automated row(s) superseded by manual")

    auto_df["Source"]             = "Automated"
    auto_df["Vector_Requirement"] = auto_df[req_col] if req_col in auto_df.columns else 0
    auto_df["CPT_Requirement"]    = 0
    auto_df["ConsolidationPriorityScore"] = pd.to_numeric(
        auto_df.get(score_col, pd.Series(0.0, index=auto_df.index)), errors="coerce"
    ).fillna(0)

    # Concat + sort
    hybrid_df = pd.concat([manual_rows, auto_df], ignore_index=True, sort=False)

    # Numeric fill
    _NUMERIC_FILL = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration', 'PriorityScore', 'ConsolidatedPriorityScore',
        'ConsolidationPriorityScore', 'ASP', 'HistoryPenetrationScore',
        'TopSKUFlag', 'HighestPriority', 'manual_rank',
        'weighted_score', 'modified_priority_score',
    ]
    for col in _NUMERIC_FILL:
        if col in hybrid_df.columns:
            hybrid_df[col] = pd.to_numeric(hybrid_df[col], errors='coerce').fillna(0)

    for col in ['SKU Description', 'Source', 'Target Date']:
        if col in hybrid_df.columns:
            hybrid_df[col] = hybrid_df[col].fillna('')

    hybrid_df = hybrid_df.sort_values(
        "ConsolidationPriorityScore", ascending=False
    ).reset_index(drop=True)
    hybrid_df["Rank_ConsolidationPriorityScore"] = hybrid_df.index + 1

    print(f"  [CTP STAGE 2] {tyre_type} complete: "
          f"{len(manual_rows)} manual + {len(auto_df)} automated = {len(hybrid_df)} total rows")

    return _select_output_columns(hybrid_df)


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def process_ctp_frontend_override(
    pcr_df: pd.DataFrame,
    tbr_df: pd.DataFrame,
    date_str: str,
) -> tuple:
    """
    CTP Stage 2 entry point.

    Args:
        pcr_df   : Stage 1 PCR output DataFrame
        tbr_df   : Stage 1 TBR output DataFrame
        date_str : DDMMYYYY string

    Returns:
        (pcr_final_df, tbr_final_df) tuple
    """
    print(f"\n[CTP STAGE 2] Starting Frontend Override for {date_str}")

    # Load manual data
    try:
        manual_df = _load_manual_data()
        print(f"[CTP STAGE 2] Loaded {len(manual_df)} manual entries from ctp_manual_frontend_demand.xlsx")
    except FileNotFoundError as e:
        print(f"[CTP STAGE 2] Warning: {e}")
        print("[CTP STAGE 2] No manual file — returning Stage 1 output (automated only).")
        return _automated_only(pcr_df), _automated_only(tbr_df)

    if manual_df.empty:
        print("[CTP STAGE 2] No manual entries — returning Stage 1 output (automated only).")
        return _automated_only(pcr_df), _automated_only(tbr_df)

    # Split manual entries into PCR and TBR by checking against PCR SKU list
    pcr_skus = _load_pcr_sku_list()

    if pcr_skus:
        pcr_manual = manual_df[manual_df["SKUCode"].isin(pcr_skus)].copy()
        tbr_manual = manual_df[~manual_df["SKUCode"].isin(pcr_skus)].copy()
    else:
        # Fallback: all manual entries applied to both (will supersede only matching SKUs)
        pcr_manual = manual_df.copy()
        tbr_manual = manual_df.copy()

    print(f"[CTP STAGE 2] Manual split — PCR: {len(pcr_manual)}, TBR: {len(tbr_manual)}")

    # Process each tyre type
    pcr_final = _process_one_type(pcr_df, pcr_manual, "PCR")
    tbr_final = _process_one_type(tbr_df, tbr_manual, "TBR")

    return pcr_final, tbr_final
