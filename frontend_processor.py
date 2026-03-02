# frontend_processor.py
# Stage 2: Frontend / Manual Demand Integration Engine
#
# Reads ./data/manual_frontend_demand.xlsx and scores manually-entered SKUs
# using a principled 4-step weighted scoring pipeline.
#
# Scoring guarantee (final output order):
#   1st  →  Manual SKUs with HighestPriority = 1  (ordered by score desc)
#   2nd  →  Manual SKUs with HighestPriority = 0  (ordered by score desc)
#   3rd  →  Vector / Automated SKUs               (ordered by ConsolidatedPriorityScore)
#
# This module is Stage 2 scoped — no mould/machine logic.
# Stage 3 continues to use manual_integration_processor.py.

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
# HELPERS
# ---------------------------------------------------------------------------

def _load_manual_data() -> pd.DataFrame:
    """
    Load and validate ./data/manual_frontend_demand.xlsx

    Expected columns (whitespace-stripped):
        SKU Code | SKU Description | Market | Quantity | Target Date | Highest Priority

    'Target Date' is optional — defaults to today (neutral urgency) if absent.
    Returns a cleaned DataFrame with standardised internal column names.
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
        raise ValueError(f"Manual demand file is missing columns: {missing}")

    df["SKUCode"]         = df["SKUCode"].astype(str).str.strip()
    df["Market"]          = df["Market"].astype(str).str.strip()
    df["Quantity"]        = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["HighestPriority"] = pd.to_numeric(df["HighestPriority"], errors="coerce").fillna(0).astype(int)

    if "Target Date" in df.columns:
        df["Target Date"] = pd.to_datetime(df["Target Date"], errors="coerce").dt.date.fillna(_TODAY)
    else:
        df["Target Date"] = _TODAY

    return df[df["SKUCode"].str.len() > 0].copy()


def _extract_size(sku_series: pd.Series):
    """Extract rim size from SKUCode[8:10], matching demand_processor.py logic."""
    return pd.to_numeric(sku_series.str[8:10], errors="coerce").fillna(0).astype("Int64")


def _minmax(series: pd.Series) -> pd.Series:
    """Min-max normalization. Returns 1.0 for all rows if the range is zero."""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(1.0, index=series.index)
    return (series - lo) / (hi - lo)


def _compute_weighted_score(df: pd.DataFrame, max_auto: float) -> pd.DataFrame:
    """
    Four-step manual scoring pipeline.

    Step 1 — weighted_score  (no HighestPriority factor)
        Weighted sum of min-max normalised Market, Quantity, Target Date.
        Weights: W_MARKET, W_QTY, W_TARGET_DATE (must sum to 1, from config).
        Result range: [0, 1].

    Step 2 — Identify HP=1 sub-group and pre-rank.
        Among HighestPriority=1 rows, rank by weighted_score ASCENDING:
            rank 1 = lowest weighted_score (smallest boost later)
            rank P = highest weighted_score (largest boost later)
        This preserves the relative ordering within the priority block.

    Step 3 — modified_priority_score
        max_ws = max(weighted_score) across ALL manual rows.
        For HP=1 rows:
            modified_priority_score = max_ws * (1 + priority_rank / P)
            → range: (max_ws, 2 * max_ws]  → always above ALL HP=0 scores ≤ max_ws
        For HP=0 rows:
            modified_priority_score = weighted_score   (unchanged)

    Step 4 — StrategicPriorityScore  (guarantees all manual > all automated)
        overall_rank = rank of each manual row by modified_priority_score ASCENDING
            (rank 1 = lowest, rank N = highest = most urgent)
        StrategicPriorityScore = max_auto * (1 + overall_rank / N)
            → range: (max_auto, 2 * max_auto]  → all manual above all automated ✓

    Args:
        df       : cleaned manual DataFrame from _load_manual_data()
        max_auto : max(ConsolidatedPriorityScore) from Stage 1 output

    Returns:
        df with columns: weighted_score, modified_priority_score,
                         StrategicPriorityScore, priority_rank, manual_rank
    """
    N = len(df)

    # ── Step 1: weighted_score ────────────────────────────────────────────────
    market_scores = df["Market"].map(config_stage2.MARKET_SCORE).fillna(1).astype(float)
    norm_market   = _minmax(market_scores)
    norm_qty      = _minmax(df["Quantity"].astype(float))

    days_remaining = df["Target Date"].apply(
        lambda d: max((d - _TODAY).days, 0) if isinstance(d, type(_TODAY)) else 0
    ).astype(float)
    norm_date = 1.0 - _minmax(days_remaining)   # invert: closer date = higher score

    df = df.copy()
    df["weighted_score"] = (
        config_stage2.W_MARKET      * norm_market +
        config_stage2.W_QTY         * norm_qty    +
        config_stage2.W_TARGET_DATE * norm_date
    ).round(6)

    # ── Step 2 & 3: modified_priority_score ───────────────────────────────────
    max_ws        = df["weighted_score"].max()
    priority_mask = df["HighestPriority"] == 1
    P             = int(priority_mask.sum())

    df["priority_rank"]          = 0
    df["modified_priority_score"] = df["weighted_score"]   # default for HP=0

    if P > 0:
        # Rank HP=1 rows by weighted_score ASCENDING:
        #   rank 1 = lowest ws → smallest boost (max_ws * (1 + 1/P))
        #   rank P = highest ws → largest boost (max_ws * 2.0)
        # This preserves relative ordering: higher ws → higher final score.
        hp1_idx = df.index[priority_mask]
        df.loc[hp1_idx, "priority_rank"] = (
            df.loc[hp1_idx, "weighted_score"]
            .rank(ascending=True, method="first")
            .astype(int)
        )
        df.loc[hp1_idx, "modified_priority_score"] = (
            max_ws * (1.0 + df.loc[hp1_idx, "priority_rank"] / P)
        ).round(6)

    # ── Step 4: StrategicPriorityScore ───────────────────────────────────────
    # overall_rank: 1 = lowest modified_priority_score, N = highest (most urgent)
    # This preserves all relative orderings established in Steps 1-3.
    df["overall_rank"] = (
        df["modified_priority_score"]
        .rank(ascending=True, method="first")
        .astype(int)
    )
    df["StrategicPriorityScore"] = (
        max_auto * (1.0 + df["overall_rank"] / N)
    ).round(6)

    # manual_rank: rank within the manual block, 1 = most urgent
    # (descending StrategicPriorityScore → rank 1 = highest score)
    df["manual_rank"] = (
        df["StrategicPriorityScore"]
        .rank(ascending=False, method="first")
        .astype(int)
    )

    # Sort by manual_rank for clean display
    df = df.sort_values("manual_rank", ascending=True).reset_index(drop=True)

    # Logging
    hp1_df  = df[df["HighestPriority"] == 1]
    hp0_df  = df[df["HighestPriority"] == 0]
    print(f"[STAGE 2] Manual scoring complete:")
    print(f"  - Total manual rows       : {N}")
    print(f"  - HighestPriority=1 rows  : {P}")
    print(f"  - max_ws (step 3 base)    : {max_ws:.6f}")
    print(f"  - max_auto (step 4 base)  : {max_auto:.6f}")
    if not hp1_df.empty:
        print(f"  - HP=1 StrategicScore range: "
              f"[{hp1_df['StrategicPriorityScore'].min():.6f}, "
              f"{hp1_df['StrategicPriorityScore'].max():.6f}]")
    if not hp0_df.empty:
        print(f"  - HP=0 StrategicScore range: "
              f"[{hp0_df['StrategicPriorityScore'].min():.6f}, "
              f"{hp0_df['StrategicPriorityScore'].max():.6f}]")

    return df


def _build_manual_rows(
    manual_df: pd.DataFrame,
    stage1_df: pd.DataFrame,
    vector_req_lookup: dict,
) -> pd.DataFrame:
    """
    Construct manual rows column-compatible with the Stage 1 DataFrame
    so they can be concatenated vertically without dtype issues.
    """
    rows = pd.DataFrame(index=manual_df.index)

    # Identity
    rows["SKUCode"]           = manual_df["SKUCode"]
    rows["SKU Description"]   = manual_df.get("SKU Description", pd.Series([""] * len(manual_df)))
    rows["size"]              = _extract_size(manual_df["SKUCode"])
    rows["Market"]            = manual_df["Market"]

    # Frontend input columns
    rows["Quantity"]          = manual_df["Quantity"]
    rows["Target Date"]       = manual_df["Target Date"].astype(str)
    rows["HighestPriority"]   = manual_df["HighestPriority"]

    # Scoring columns
    rows["weighted_score"]          = manual_df["weighted_score"]
    rows["modified_priority_score"] = manual_df["modified_priority_score"]
    rows["StrategicPriorityScore"]  = manual_df["StrategicPriorityScore"]
    rows["manual_rank"]             = manual_df["manual_rank"]

    # Requirement transparency
    rows["Vector_Requirement"] = manual_df["SKUCode"].map(vector_req_lookup).fillna(0)
    rows["CPT_Requirement"]    = manual_df["Quantity"]
    rows["Requirement"]        = manual_df["Quantity"]

    # Change 2: Manual SKUs always show 100% penetration (they are actively demanded)
    rows["Penetration"]        = 100.0

    rows["Source"] = "Manual"

    # Alias for downstream consumers
    rows["ConsolidatedPriorityScore"] = manual_df["StrategicPriorityScore"]

    return rows


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def process_frontend_override(stage1_df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """
    Stage 2 entry point: Frontend / Manual Hybrid Synthesis.

    Pipeline:
        1. Load manual demand file.
        2. Compute weighted scores + HighestPriority boost + automated-ceiling lift.
        3. Capture Vector_Requirement before removing superseded automated rows.
        4. Build manual rows + tag automated rows.
        5. Concatenate (manual on conceptual top; sorted by StrategicPriorityScore desc).
        6. Assign Final Rank 1 = most urgent.

    Final output order guaranteed:
        HP=1 manual  →  HP=0 manual  →  Automated (all by score desc within group)
    """
    print(f"[STAGE 2] Starting Frontend Override for {date_str}")

    # ── Helper: automated-only path ──────────────────────────────────────────
    def _automated_only(df):
        df = df.copy()
        df["Source"]                 = "Automated"
        req                          = "Requirement"
        df["Vector_Requirement"]     = df[req] if req in df.columns else 0
        df["CPT_Requirement"]        = 0
        df["StrategicPriorityScore"] = df.get(
            "ConsolidatedPriorityScore", pd.Series(0.0, index=df.index))
        df = df.sort_values("StrategicPriorityScore", ascending=False).reset_index(drop=True)
        df["Rank_ConsolidatedPriorityScore"] = df.index + 1
        return _select_output_columns(df)

    # ── Step 1: Load manual data ─────────────────────────────────────────────
    print("[STAGE 2] Loading manual demand file...")
    try:
        manual_df = _load_manual_data()
        print(f"[STAGE 2] Loaded {len(manual_df)} manual entries")
    except FileNotFoundError as e:
        print(f"[STAGE 2] Warning: {e}")
        print("[STAGE 2] No manual file — returning Stage 1 output (automated only).")
        return _automated_only(stage1_df)

    if manual_df.empty:
        print("[STAGE 2] No manual entries — returning Stage 1 output (automated only).")
        return _automated_only(stage1_df)

    # ── Step 2: Compute weighted scores ──────────────────────────────────────
    print("[STAGE 2] Computing weighted priority scores...")

    # max_auto: ceiling that all manual scores must exceed
    score_col = "ConsolidatedPriorityScore"
    max_auto  = float(
        pd.to_numeric(stage1_df[score_col], errors="coerce").max()
        if score_col in stage1_df.columns else 1.0
    )
    if max_auto <= 0:
        max_auto = 1.0   # safety guard

    manual_df = _compute_weighted_score(manual_df, max_auto)

    # ── Step 3: Capture Vector_Requirement before removing superseded rows ───
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

    # ── Step 4: Build manual rows + tag automated rows ───────────────────────
    manual_rows  = _build_manual_rows(manual_df, stage1_df, vector_req_lookup)
    n_manual     = len(manual_rows)

    # Change 3: Only supersede an automated row when the manual CPT demand differs
    # from the Vector demand.  If both are the same quantity, keep BOTH rows
    # (one Automated, one Manual) — they represent the same SKU from two sources.
    skus_to_supersede = set()
    for _, mrow in manual_df.iterrows():
        sku       = mrow["SKUCode"]
        vec_req   = vector_req_lookup.get(sku, 0)
        cpt_req   = float(mrow["Quantity"])
        if vec_req != cpt_req:          # different demand → manual takes precedence
            skus_to_supersede.add(sku)
        # same demand → keep both rows

    superseded   = auto_df["SKUCode"].isin(skus_to_supersede)
    n_superseded = superseded.sum()
    auto_df      = auto_df[~superseded].copy()
    if n_superseded > 0:
        print(f"[STAGE 2] Removed {n_superseded} automated row(s) superseded by manual entries")
    n_kept_both = len(manual_skus) - n_superseded
    if n_kept_both > 0:
        print(f"[STAGE 2] Kept {n_kept_both} SKU(s) as both Automated + Manual (same demand qty)")

    auto_df["Source"]             = "Automated"
    auto_df["Vector_Requirement"] = auto_df[req_col] if req_col in auto_df.columns else 0
    auto_df["CPT_Requirement"]    = 0
    auto_df["StrategicPriorityScore"] = pd.to_numeric(
        auto_df.get(score_col, pd.Series(0.0)), errors="coerce"
    ).fillna(0)

    # ── Step 5: Concatenate and sort ─────────────────────────────────────────
    hybrid_df = pd.concat([manual_rows, auto_df], ignore_index=True, sort=False)

    # ── Data imputation ───────────────────────────────────────────────────────
    _NUMERIC_FILL_ZERO = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration', 'NormPenetration', 'NormRequirement',
        'PriorityScore_Inventory', 'NormInventoryScore',
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',
        'PriorityScore', 'ConsolidatedPriorityScore',
        'ASP', 'daily_cure', 'rev_pot', 'price_priority',
        'MarketWeight', 'TopSKUFlag', 'HighestPriority', 'manual_rank',
        'weighted_score', 'modified_priority_score', 'StrategicPriorityScore',
    ]
    for col in _NUMERIC_FILL_ZERO:
        if col in hybrid_df.columns:
            hybrid_df[col] = pd.to_numeric(hybrid_df[col], errors='coerce').fillna(0)

    for col in ['SKU Description', 'Source', 'Target Date']:
        if col in hybrid_df.columns:
            hybrid_df[col] = hybrid_df[col].fillna('')

    # ── Step 6: Final Rank → stored in Rank_ConsolidatedPriorityScore ─────────
    # Sort descending: HP=1 manual first, HP=0 manual next, automated last.
    # Change 1: Use Rank_ConsolidatedPriorityScore as the rank column (no Final Rank).
    hybrid_df = hybrid_df.sort_values(
        "StrategicPriorityScore", ascending=False
    ).reset_index(drop=True)
    hybrid_df["Rank_ConsolidatedPriorityScore"] = hybrid_df.index + 1

    print(f"[STAGE 2] Frontend override complete:")
    print(f"  - Manual entries  : {n_manual}")
    print(f"  - Automated rows  : {len(auto_df)}")
    print(f"  - Total rows      : {len(hybrid_df)}")

    return _select_output_columns(hybrid_df)


def _select_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Select and order Stage 2 output columns."""
    output_columns = [
        # --- Rank (Change 1: Rank_ConsolidatedPriorityScore holds the final rank) ---
        'Rank_ConsolidatedPriorityScore',

        # --- Identification ---
        'SKUCode', 'SKU Description', 'size',

        # --- Source & Frontend Inputs ---
        'Source', 'HighestPriority', 'Target Date', 'Quantity',

        # --- Manual Scoring Breakdown ---
        'weighted_score', 'modified_priority_score', 'manual_rank',

        # --- Unified Strategic Score ---
        'StrategicPriorityScore',

        # --- Targets ---
        'Market', 'Norm ', 'Virtual Norm', 'Adjusted_Target',

        # --- Demand Signals ---
        'Stock', 'Vector_Requirement', 'CPT_Requirement', 'Requirement',
        'Penetration', 'NormPenetration', 'NormRequirement',

        # --- SKU Attributes ---
        'TopSKUFlag', 'MarketWeight', 'priority',

        # --- Inventory Signals ---
        'PriorityScore_Inventory', 'NormInventoryScore',

        # --- History Penetration ---
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',

        # --- Revenue & Efficiency ---
        'ASP', 'Cure Time', 'price_priority',

        # --- Scoring Details ---
        'PriorityScore', 'ConsolidatedPriorityScore',
    ]
    return df[[c for c in output_columns if c in df.columns]]
