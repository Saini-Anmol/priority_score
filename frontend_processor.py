# frontend_processor.py
# Stage 2: Frontend / Manual Demand Integration Engine
#
# Reads ./data/manual_frontend_demand.xlsx and scores those SKUs using a
# principled weighted score based on Market, Quantity, and Target Date.
# HighestPriority=1 rows are guaranteed to rank above all others.
#
# This processor is scoped to Stage 2 only — it does NOT include any
# machine deployment (mould) logic. Stage 3 continues to use
# manual_integration_processor.py (which also attaches mould metrics).

import os
from datetime import datetime
import pandas as pd
import numpy as np
import config_stage2

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
MANUAL_INPUT_FILE = "./data/manual_frontend_demand.xlsx"

_TODAY = datetime.now().date()


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _load_manual_data() -> pd.DataFrame:
    """
    Load and validate the manual frontend demand Excel file.

    Expected columns (case-insensitive strip):
        SKU Code | SKU Description | Market | Quantity | Target Date | Highest Priority

    'Target Date' is optional — defaults to today if absent (neutral urgency).

    Returns a cleaned DataFrame with standardised column names.
    """
    if not os.path.exists(MANUAL_INPUT_FILE):
        raise FileNotFoundError(
            f"Manual demand file not found: '{MANUAL_INPUT_FILE}'\n"
            "Please create the file at ./data/manual_frontend_demand.xlsx"
        )

    df = pd.read_excel(MANUAL_INPUT_FILE)
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
        raise ValueError(f"Manual demand file is missing required columns: {missing}")

    # Type enforcement
    df["SKUCode"]         = df["SKUCode"].astype(str).str.strip()
    df["Market"]          = df["Market"].astype(str).str.strip()
    df["Quantity"]        = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["HighestPriority"] = pd.to_numeric(df["HighestPriority"], errors="coerce").fillna(0).astype(int)

    # Target Date: parse to date; fallback to today  (neutral urgency)
    if "Target Date" in df.columns:
        df["Target Date"] = pd.to_datetime(df["Target Date"], errors="coerce").dt.date
        df["Target Date"] = df["Target Date"].fillna(_TODAY)
    else:
        df["Target Date"] = _TODAY

    df = df[df["SKUCode"].str.len() > 0].copy()
    return df


def _extract_size(sku_series: pd.Series):
    """
    Extract rim size from SKUCode (characters at index [8:10]).
    Matches the exact logic in demand_processor.py.
    """
    return pd.to_numeric(sku_series.str[8:10], errors="coerce").fillna(0).astype("Int64")


def _minmax(series: pd.Series) -> pd.Series:
    """
    Min-max normalization.  Returns 1.0 for all rows if range == 0
    (prevents division by zero when all values are identical).
    """
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(1.0, index=series.index)
    return (series - lo) / (hi - lo)


def _compute_weighted_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the six-step manual scoring pipeline:

    Step 1 — weighted_score:
        Weighted sum of min-max normalised Market, Quantity, and Target Date.
        Weights come from config (W_MARKET, W_QTY, W_TARGET_DATE); sum = 1.

    Step 2 — weighted_sum_priority:
        weighted_score + 1  if HighestPriority == 1, else weighted_score.
        Ensures all priority-flagged rows are > 1 while non-priority stay ≤ 1.

    Step 3 — priority_rank:
        Rank HighestPriority=1 rows by weighted_sum_priority descending.
        (Rank 1 = highest weighted score within the priority group.)

    Step 4 — max_score:
        max(weighted_sum_priority) across ALL manual rows.

    Step 5 — modified_priority_score:
        HighestPriority=1: max_score * (1 + priority_rank / max_priority_rank)
        HighestPriority=0: weighted_sum_priority  (unchanged)

    Step 6 — manual_rank:
        Rank ALL rows by modified_priority_score descending (rank 1 = most urgent).

    Returns df with new columns added in-place.
    """
    # ---- Step 1: Normalise factors ----

    # Market → numeric via config mapping, then normalise
    market_scores = df["Market"].map(config_stage2.MARKET_SCORE).fillna(1)
    norm_market   = _minmax(market_scores)

    # Quantity: higher = more urgent
    norm_qty = _minmax(df["Quantity"].astype(float))

    # Target Date: compute days remaining from today, then INVERT (closer = more urgent)
    days_remaining = df["Target Date"].apply(
        lambda d: max((d - _TODAY).days, 0) if isinstance(d, type(_TODAY)) else 0
    ).astype(float)
    # Invert: row with min days_remaining → norm = 1.0 (most urgent)
    norm_date = 1.0 - _minmax(days_remaining)

    # Weighted sum
    w_m = config_stage2.W_MARKET
    w_q = config_stage2.W_QTY
    w_d = config_stage2.W_TARGET_DATE

    df["weighted_score"] = (w_m * norm_market + w_q * norm_qty + w_d * norm_date).round(6)

    # ---- Step 2: weighted_sum_priority ----
    df["weighted_sum_priority"] = np.where(
        df["HighestPriority"] == 1,
        df["weighted_score"] + 1.0,
        df["weighted_score"]
    )

    # ---- Step 3: rank within HighestPriority=1 block (descending) ----
    priority_mask = df["HighestPriority"] == 1
    df["priority_rank"] = np.nan

    if priority_mask.any():
        # rank() with ascending=False → rank 1 = highest weighted_sum_priority
        df.loc[priority_mask, "priority_rank"] = (
            df.loc[priority_mask, "weighted_sum_priority"]
            .rank(ascending=False, method="min")
        )

    # ---- Step 4: max_score across ALL manual rows ----
    max_score      = df["weighted_sum_priority"].max()
    max_prio_rank  = int(priority_mask.sum())  # total count of HighestPriority=1 rows

    # ---- Step 5: modified_priority_score ----
    def _modified(row):
        if row["HighestPriority"] == 1 and max_prio_rank > 0:
            return max_score * (1.0 + row["priority_rank"] / max_prio_rank)
        return row["weighted_sum_priority"]

    df["modified_priority_score"] = df.apply(_modified, axis=1).round(6)

    # ---- Step 6: manual_rank (all rows, descending score → rank 1 = most urgent) ----
    df["manual_rank"] = (
        df["modified_priority_score"]
        .rank(ascending=False, method="min")
        .astype(int)
    )

    # Sort by manual_rank for clean ordering
    df = df.sort_values("manual_rank", ascending=True).reset_index(drop=True)

    print(f"[STAGE 2] Weighted scoring complete:")
    print(f"  - Total manual rows         : {len(df)}")
    print(f"  - HighestPriority=1 rows    : {max_prio_rank}")
    print(f"  - max_score (step 4)        : {max_score:.6f}")
    print(f"  - modified_priority range   : {df['modified_priority_score'].min():.6f} "
          f"to {df['modified_priority_score'].max():.6f}")

    return df


def _build_manual_rows(
    manual_df: pd.DataFrame,
    stage1_df: pd.DataFrame,
    vector_req_lookup: dict,
) -> pd.DataFrame:
    """
    Construct manual rows that are column-compatible with the Stage 1 DataFrame
    so they can be concatenated vertically without issues.

    Multi-Source Transparency:
      Vector_Requirement = what Stage 1 calculated for this SKU (before override)
      CPT_Requirement    = what the frontend/CPT specified — takes precedence
      Requirement        = CPT_Requirement (used for all downstream calculations)
    """
    manual_rows = pd.DataFrame(index=manual_df.index)

    # --- Core identity ---
    manual_rows["SKUCode"]           = manual_df["SKUCode"]
    manual_rows["SKU Description"]   = manual_df.get("SKU Description", pd.Series([""] * len(manual_df)))
    manual_rows["size"]              = _extract_size(manual_df["SKUCode"])
    manual_rows["Market"]            = manual_df["Market"]

    # --- Frontend input columns ---
    manual_rows["Quantity"]          = manual_df["Quantity"]
    manual_rows["Target Date"]       = manual_df["Target Date"].astype(str)
    manual_rows["HighestPriority"]   = manual_df["HighestPriority"]

    # --- New scoring columns ---
    manual_rows["weighted_score"]         = manual_df["weighted_score"]
    manual_rows["weighted_sum_priority"]  = manual_df["weighted_sum_priority"]
    manual_rows["modified_priority_score"]= manual_df["modified_priority_score"]
    manual_rows["manual_rank"]            = manual_df["manual_rank"]

    # --- Multi-Source Requirement Transparency ---
    manual_rows["Vector_Requirement"]= manual_df["SKUCode"].map(vector_req_lookup).fillna(0)
    manual_rows["CPT_Requirement"]   = manual_df["Quantity"]
    manual_rows["Requirement"]       = manual_df["Quantity"]

    # --- Source tag ---
    manual_rows["Source"]            = "Manual"

    # ConsolidatedPriorityScore alias for downstream consumers
    manual_rows["ConsolidatedPriorityScore"] = manual_df["modified_priority_score"]

    return manual_rows


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def process_frontend_override(stage1_df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """
    Stage 2 entry point: Frontend / Manual Hybrid Synthesis.

    Steps:
        1. Load manual demand Excel (Market, Qty, Target Date, HighestPriority).
        2. Compute weighted scoring (steps 1-6 above).
        3. Capture Vector_Requirement for any manual SKUs (before removal).
        4. Remove automated rows whose SKUCode appears in the manual list.
        5. Tag automated rows; re-sequence their ProxyRank after manual block.
        6. Concatenate: manual rows on top, automated rows below.
        7. Assign StrategicPriorityScore and Final Rank columns.

    Args:
        stage1_df (pd.DataFrame): Full output from Stage 1 (demand processing).
        date_str  (str):          Date in DDMMYYYY format (for logging).

    Returns:
        pd.DataFrame: Hybrid DataFrame with Final Rank and StrategicPriorityScore.
    """
    print(f"[STAGE 2] Starting Frontend Override for {date_str}")

    # ---- Helper: return automated-only output ----
    def _automated_only(df):
        df = df.copy()
        df["Source"]                 = "Automated"
        req = "Requirement"
        df["Vector_Requirement"]     = df[req] if req in df.columns else 0
        df["CPT_Requirement"]        = 0
        df["StrategicPriorityScore"] = df.get("ConsolidatedPriorityScore", pd.Series(0.0, index=df.index))
        df = df.sort_values("StrategicPriorityScore", ascending=False).reset_index(drop=True)
        df["Final Rank"]             = df.index + 1
        return _select_output_columns(df)

    # ---- Step 1: Load manual data ----
    print("[STAGE 2] Loading manual demand file...")
    try:
        manual_df = _load_manual_data()
        print(f"[STAGE 2] Loaded {len(manual_df)} manual entries")
    except FileNotFoundError as e:
        print(f"[STAGE 2] Warning: {e}")
        print("[STAGE 2] No manual file — returning Stage 1 output with automated tags only.")
        return _automated_only(stage1_df)

    if manual_df.empty:
        print("[STAGE 2] No manual entries — returning Stage 1 output with automated tags only.")
        return _automated_only(stage1_df)

    # ---- Step 2: Compute weighted scores (Steps 1-6) ----
    print("[STAGE 2] Computing weighted priority scores...")
    manual_df = _compute_weighted_score(manual_df)

    # ---- Step 3: Capture Vector_Requirement before removing superseded rows ----
    manual_skus = set(manual_df["SKUCode"].str.strip())
    auto_df     = stage1_df.copy()
    auto_df["SKUCode"] = auto_df["SKUCode"].astype(str).str.strip()

    req_col = "Requirement"
    vector_req_lookup: dict = {}
    if req_col in auto_df.columns:
        vector_req_lookup = (
            auto_df[auto_df["SKUCode"].isin(manual_skus)]
            .drop_duplicates("SKUCode")
            .set_index("SKUCode")[req_col]
            .to_dict()
        )

    # ---- Step 4: Build column-aligned manual rows ----
    manual_rows = _build_manual_rows(manual_df, stage1_df, vector_req_lookup)
    n_manual    = len(manual_rows)

    # ---- Step 5: Remove automated rows superseded by manual entries ----
    superseded   = auto_df["SKUCode"].isin(manual_skus)
    n_superseded = superseded.sum()
    auto_df      = auto_df[~superseded].copy()
    if n_superseded > 0:
        print(f"[STAGE 2] Removed {n_superseded} automated row(s) superseded by manual entries")

    # ---- Step 6: Tag automated rows, re-sequence ProxyRank ----
    auto_df["Source"]             = "Automated"
    auto_df["Vector_Requirement"] = auto_df[req_col] if req_col in auto_df.columns else 0
    auto_df["CPT_Requirement"]    = 0

    rank_col = "Rank_ConsolidatedPriorityScore" if "Rank_ConsolidatedPriorityScore" in auto_df.columns else None
    if rank_col:
        auto_df = auto_df.sort_values(rank_col, ascending=True).reset_index(drop=True)
    auto_df["ProxyRank"] = auto_df.index + n_manual + 1

    # ---- Step 7: Vertical merge — manual on top ----
    hybrid_df = pd.concat([manual_rows, auto_df], ignore_index=True, sort=False)

    # ---- DATA IMPUTATION: fill missing numerics with 0 ----
    _NUMERIC_FILL_ZERO = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration', 'NormPenetration', 'NormRequirement',
        'PriorityScore_Inventory', 'NormInventoryScore',
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',
        'PriorityScore', 'ConsolidatedPriorityScore', 'ProxyRank',
        'ASP', 'daily_cure', 'rev_pot', 'price_priority',
        'MarketWeight', 'TopSKUFlag',
        'HighestPriority', 'manual_rank',
        'weighted_score', 'weighted_sum_priority', 'modified_priority_score',
    ]
    for col in _NUMERIC_FILL_ZERO:
        if col in hybrid_df.columns:
            hybrid_df[col] = pd.to_numeric(hybrid_df[col], errors='coerce').fillna(0)

    _STRING_FILL_EMPTY = ['SKU Description', 'Source', 'Target Date']
    for col in _STRING_FILL_EMPTY:
        if col in hybrid_df.columns:
            hybrid_df[col] = hybrid_df[col].fillna('')

    # ---- Unified StrategicPriorityScore ----
    # Manual rows  → modified_priority_score (principled weighted score, priority rows > 1)
    # Automated    → ConsolidatedPriorityScore (Stage 1 output, always ≤ 1)
    hybrid_df["StrategicPriorityScore"] = np.where(
        hybrid_df["Source"] == "Manual",
        hybrid_df.get("modified_priority_score", pd.Series(0.0, index=hybrid_df.index)),
        hybrid_df.get("ConsolidatedPriorityScore", pd.Series(0.0, index=hybrid_df.index))
    )

    # ---- Final Rank ----
    hybrid_df = hybrid_df.sort_values(
        "StrategicPriorityScore", ascending=False
    ).reset_index(drop=True)
    hybrid_df["Final Rank"] = hybrid_df.index + 1

    print(f"[STAGE 2] Frontend override complete:")
    print(f"  - Manual entries  : {n_manual}")
    print(f"  - Automated entries: {len(auto_df)}")
    print(f"  - Total rows      : {len(hybrid_df)}")

    return _select_output_columns(hybrid_df)


def _select_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Select and order Stage 2 output columns."""
    output_columns = [
        # --- Group 0: Primary Production Sequence ---
        'Final Rank',

        # --- Group 1: Identification ---
        'SKUCode', 'SKU Description', 'size',

        # --- Group 2: Source & Frontend Inputs ---
        'Source', 'HighestPriority', 'Target Date', 'Quantity',

        # --- Group 3: Manual Scoring Breakdown ---
        'weighted_score', 'weighted_sum_priority',
        'modified_priority_score', 'manual_rank',

        # --- Group 4: Unified Strategic Score ---
        'StrategicPriorityScore',

        # --- Group 5: Targets ---
        'Market', 'Norm ', 'Virtual Norm', 'Adjusted_Target',

        # --- Group 6: Demand Signals (Vector Need → CPT Override → Final) ---
        'Stock', 'Vector_Requirement', 'CPT_Requirement', 'Requirement', 'Penetration',
        'NormPenetration', 'NormRequirement',

        # --- Group 7: SKU Attributes ---
        'TopSKUFlag', 'MarketWeight', 'priority',

        # --- Group 8: Inventory Signals ---
        'PriorityScore_Inventory', 'NormInventoryScore',

        # --- Group 8b: History Penetration ---
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',

        # --- Group 9: Revenue & Efficiency ---
        'ASP', 'Cure Time', 'price_priority',

        # --- Group 10: Detailed Scoring Components ---
        'PriorityScore',
        'ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore',
    ]

    available_cols = [col for col in output_columns if col in df.columns]
    return df[available_cols]
