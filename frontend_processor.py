# frontend_processor.py
# Stage 2: Frontend / Manual Demand Integration Engine
#
# Reads ./data/manual_frontend_demand.xlsx and injects those SKUs at the
# absolute top of the priority ranking, above every automated entry.
#
# This processor is scoped to Stage 2 only — it does NOT include any
# machine deployment (mould) logic. Stage 3 continues to use
# manual_integration_processor.py (which also attaches mould metrics).

import os
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
MANUAL_INPUT_FILE = "./data/manual_frontend_demand.xlsx"

# The automated pipeline produces ConsolidatedPriorityScore in [0, 1].
# We assign manual entries a score of BOOST_BASE + (HighestPriority * BOOST_MULTIPLIER)
# so they always sit 10× above the theoretical maximum automated score.
BOOST_BASE       = 10.0  # Floor score for any manual entry
BOOST_MULTIPLIER = 1.0   # Extra score for entries flagged as "Highest Priority"


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _load_manual_data() -> pd.DataFrame:
    """
    Load and validate the manual frontend demand Excel file.

    Expected columns (case-insensitive strip):
        SKU Code | SKU Description | Market | Quantity | Highest Priority
    Returns a cleaned DataFrame with standardised column names.
    """
    if not os.path.exists(MANUAL_INPUT_FILE):
        raise FileNotFoundError(
            f"Manual demand file not found: '{MANUAL_INPUT_FILE}'\n"
            "Please create the file at ./data/manual_frontend_demand.xlsx"
        )

    df = pd.read_excel(MANUAL_INPUT_FILE)

    # Normalise column names (strip whitespace)
    df.columns = df.columns.str.strip()

    # Rename to internal standard names
    rename_map = {
        "SKU Code":         "SKUCode",
        "SKU Description":  "SKU Description",   # keep as-is
        "Market":           "Market",
        "Quantity":         "Quantity",
        "Highest Priority": "HighestPriority",
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

    # Ensure required columns exist
    required = ["SKUCode", "Quantity", "Market", "HighestPriority"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Manual demand file is missing required columns: {missing}")

    # Type enforcement
    df["SKUCode"]         = df["SKUCode"].astype(str).str.strip()
    df["Market"]          = df["Market"].astype(str).str.strip()
    df["Quantity"]        = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["HighestPriority"] = pd.to_numeric(df["HighestPriority"], errors="coerce").fillna(0).astype(int)

    # Drop rows with no SKUCode
    df = df[df["SKUCode"].str.len() > 0].copy()

    return df


def _extract_size(sku_series: pd.Series) -> pd.array:
    """
    Extract the rim size from SKUCode.
    Matches the exact logic in demand_processor.py:
        size = characters at index [8:10]  (9th and 10th characters)
    """
    return pd.to_numeric(sku_series.str[8:10], errors="coerce").fillna(0).astype("Int64")


def _compute_super_boost_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign a ManualPriorityScore that is guaranteed to exceed any automated score.

    Formula:
        ManualPriorityScore = BOOST_BASE + (HighestPriority × BOOST_MULTIPLIER)

    Ranking within the manual block:
        1. ManualPriorityScore descending  (Highest Priority = 1 → score 11.0 comes first)
        2. Quantity descending             (tiebreaker: larger requirement is more urgent)
    """
    df["ManualPriorityScore"] = BOOST_BASE + (df["HighestPriority"] * BOOST_MULTIPLIER)

    df = df.sort_values(
        by=["ManualPriorityScore", "Quantity"],
        ascending=[False, False]
    ).reset_index(drop=True)

    df["ManualRank"] = df.index + 1   # 1-based rank within manual block

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
      Vector_Requirement = what automated demand said for this SKU (before override)
      CPT_Requirement    = what the CPT (manual frontend) specified — takes precedence
      Requirement        = CPT_Requirement (used for all downstream calculations)

    Note: No mould/machine columns are added here (Stage 2 scope).
    Stage 3's manual_integration_processor.py adds those separately.
    """
    manual_rows = pd.DataFrame(index=manual_df.index)

    # --- Core identity columns ---
    manual_rows["SKUCode"]             = manual_df["SKUCode"]
    manual_rows["SKU Description"]     = manual_df.get("SKU Description", pd.Series([""] * len(manual_df)))
    manual_rows["size"]                = _extract_size(manual_df["SKUCode"])
    manual_rows["Market"]              = manual_df["Market"]

    # --- Manual-specific metrics ---
    manual_rows["Quantity"]            = manual_df["Quantity"]
    manual_rows["HighestPriority"]     = manual_df["HighestPriority"]
    manual_rows["ManualPriorityScore"] = manual_df["ManualPriorityScore"]
    manual_rows["ManualRank"]          = manual_df["ManualRank"]

    # --- Multi-Source Requirement Transparency ---
    # Vector_Requirement: what Stage 1 calculated for this SKU (0 if no demand)
    manual_rows["Vector_Requirement"]  = manual_df["SKUCode"].map(vector_req_lookup).fillna(0)
    # CPT_Requirement: the manager's override value — absolute precedence
    manual_rows["CPT_Requirement"]     = manual_df["Quantity"]
    # Requirement used for final calculations = CPT value
    manual_rows["Requirement"]         = manual_df["Quantity"]

    # --- Source tag ---
    manual_rows["Source"]              = "Manual"

    # ProxyRank for manual entries = ManualRank (occupies top N positions)
    manual_rows["ProxyRank"]           = manual_df["ManualRank"]

    # ConsolidatedPriorityScore alias (for any downstream consumers)
    manual_rows["ConsolidatedPriorityScore"] = manual_df["ManualPriorityScore"]

    return manual_rows


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def process_frontend_override(stage1_df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """
    Stage 2 entry point: Frontend / Manual Hybrid Synthesis.

    Steps:
        1. Load manual demand Excel.
        2. Compute Super-Boost priority scores.
        3. Capture Vector_Requirement for any manual SKUs (before removal).
        4. Remove automated rows whose SKUCode appears in the manual list
           (manual entry takes precedence).
        5. Offset automated ProxyRanks so they start after the last manual rank.
        6. Concatenate: manual rows on top, automated rows below.
        7. Assign StrategicPriorityScore and Final Rank columns.

    Args:
        stage1_df (pd.DataFrame): Full output from Stage 1 (demand processing).
        date_str  (str):          Date in DDMMYYYY format (for logging).

    Returns:
        pd.DataFrame: Hybrid DataFrame with manual entries at the top and
                      StrategicPriorityScore / Final Rank for all rows.
    """
    print(f"[STAGE 2] Starting Frontend Override for {date_str}")

    # ---- Step 1: Load & validate manual data ----
    print("[STAGE 2] Loading manual demand file...")
    try:
        manual_df = _load_manual_data()
        print(f"[STAGE 2] Loaded {len(manual_df)} manual entries")
    except FileNotFoundError as e:
        print(f"[STAGE 2] Warning: {e}")
        print("[STAGE 2] No manual file found — returning Stage 1 output with automated tags only.")
        stage1_df = stage1_df.copy()
        stage1_df["Source"]                    = "Automated"
        stage1_df["Vector_Requirement"]        = stage1_df.get("Requirement", 0)
        stage1_df["CPT_Requirement"]           = 0
        stage1_df["StrategicPriorityScore"]    = stage1_df.get("ConsolidatedPriorityScore", 0)
        stage1_df = stage1_df.sort_values("StrategicPriorityScore", ascending=False).reset_index(drop=True)
        stage1_df["Final Rank"]                = stage1_df.index + 1
        return _select_output_columns(stage1_df)

    if manual_df.empty:
        print("[STAGE 2] No manual entries — returning Stage 1 output with automated tags only.")
        stage1_df = stage1_df.copy()
        stage1_df["Source"]                    = "Automated"
        stage1_df["Vector_Requirement"]        = stage1_df.get("Requirement", 0)
        stage1_df["CPT_Requirement"]           = 0
        stage1_df["StrategicPriorityScore"]    = stage1_df.get("ConsolidatedPriorityScore", 0)
        stage1_df = stage1_df.sort_values("StrategicPriorityScore", ascending=False).reset_index(drop=True)
        stage1_df["Final Rank"]                = stage1_df.index + 1
        return _select_output_columns(stage1_df)

    # ---- Step 2: Compute Super-Boost scores & rank within manual block ----
    print("[STAGE 2] Computing Super-Boost priority scores...")
    manual_df = _compute_super_boost_score(manual_df)

    # ---- Step 3: Capture Vector_Requirement BEFORE removing superseded rows ----
    manual_skus = set(manual_df["SKUCode"].str.strip())
    auto_df = stage1_df.copy()
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

    # ---- Step 6: Tag automated rows, offset ProxyRank ----
    auto_df["Source"]             = "Automated"
    auto_df["Vector_Requirement"] = auto_df[req_col] if req_col in auto_df.columns else 0
    auto_df["CPT_Requirement"]    = 0

    # Re-rank automated rows starting after the last manual rank
    rank_col = "Rank_ConsolidatedPriorityScore" if "Rank_ConsolidatedPriorityScore" in auto_df.columns else None
    if rank_col:
        auto_df = auto_df.sort_values(rank_col, ascending=True).reset_index(drop=True)
    auto_df["ProxyRank"] = auto_df.index + n_manual + 1

    # ---- Step 7: Vertical merge — manual on top ----
    hybrid_df = pd.concat([manual_rows, auto_df], ignore_index=True, sort=False)

    # ---- DATA IMPUTATION: fill missing numeric values with 0 ----
    _NUMERIC_FILL_ZERO = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration', 'NormPenetration', 'NormRequirement',
        'PriorityScore_Inventory', 'NormInventoryScore',
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',
        'PriorityScore',
        'ConsolidatedPriorityScore',
        'ProxyRank',
        'ASP', 'daily_cure', 'rev_pot', 'price_priority',
        'MarketWeight', 'TopSKUFlag', 'ManualPriorityScore',
        'HighestPriority', 'ManualRank',
    ]
    for col in _NUMERIC_FILL_ZERO:
        if col in hybrid_df.columns:
            hybrid_df[col] = pd.to_numeric(hybrid_df[col], errors='coerce').fillna(0)

    # String columns: fill NaN with empty string
    _STRING_FILL_EMPTY = ['SKU Description', 'Source']
    for col in _STRING_FILL_EMPTY:
        if col in hybrid_df.columns:
            hybrid_df[col] = hybrid_df[col].fillna('')

    # ---- Unified StrategicPriorityScore (fully populated for every row) ----
    # Manual     → ManualPriorityScore   (super-boost value, e.g. 10–11)
    # Automated  → ConsolidatedPriorityScore
    hybrid_df["StrategicPriorityScore"] = np.where(
        hybrid_df["Source"] == "Manual",
        hybrid_df["ManualPriorityScore"],
        hybrid_df.get("ConsolidatedPriorityScore", pd.Series(0.0, index=hybrid_df.index))
    )

    # ---- Final Rank — sort by StrategicPriorityScore, stamp rank ----
    hybrid_df = hybrid_df.sort_values(
        "StrategicPriorityScore", ascending=False
    ).reset_index(drop=True)
    hybrid_df["Final Rank"] = hybrid_df.index + 1

    # Summary
    print(f"[STAGE 2] Frontend override complete:")
    print(f"  - Manual entries at top : {n_manual}")
    print(f"  - Automated entries     : {len(auto_df)}")
    print(f"  - Total rows in output  : {len(hybrid_df)}")

    return _select_output_columns(hybrid_df)


def _select_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Select and order Stage 2 output columns."""
    output_columns = [
        # --- Group 0: Primary Production Sequence ---
        'Final Rank',

        # --- Group 1: Identification ---
        'SKUCode', 'SKU Description', 'size',

        # --- Group 2: Source & Override Tag (manual-specific) ---
        'Source', 'HighestPriority', 'ManualPriorityScore', 'ManualRank',

        # --- Group 3: Unified Strategic Score ---
        'StrategicPriorityScore',

        # --- Group 4: Targets ---
        'Market', 'Norm ', 'Virtual Norm', 'Adjusted_Target',

        # --- Group 5: Demand Signals (Vector Need → CPT Override → Final) ---
        'Stock', 'Vector_Requirement', 'CPT_Requirement', 'Requirement', 'Penetration',
        'NormPenetration', 'NormRequirement',

        # --- Group 6: SKU Attributes ---
        'TopSKUFlag', 'MarketWeight', 'priority',

        # --- Group 7: Inventory Signals ---
        'PriorityScore_Inventory', 'NormInventoryScore',

        # --- Group 7b: History Penetration ---
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',

        # --- Group 8: Revenue & Efficiency ---
        'ASP', 'Cure Time', 'price_priority',

        # --- Group 9: Detailed Scoring Components ---
        'PriorityScore',
        'ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore',
    ]

    available_cols = [col for col in output_columns if col in df.columns]
    return df[available_cols]
