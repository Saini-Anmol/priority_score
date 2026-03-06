# manual_integration_processor.py
# Stage 3: Manual Strategic Override — Hybrid Synthesis Engine
#
# Reads ./data/manual_frontend_demand.xlsx and injects those SKUs at the
# absolute top of the production ranking, above every automated entry.
# This file does NOT import or modify any Stage 1 / Stage 2 source files.

import os
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
MANUAL_INPUT_FILE = "./data/manual_frontend_demand.xlsx"

# The automated pipeline produces ConsolidatedPriorityScore in [0, 1].
# We assign manual entries a score of BOOST_BASE + (Highest_Priority * BOOST_MULTIPLIER)
# so they always sit 10× above the theoretical maximum automated score.
BOOST_BASE              = 10.0  # Floor score for any manual entry
BOOST_MULTIPLIER        = 1.0   # Extra score for entries flagged as "Highest Priority"



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
        "SKU Code":        "SKUCode",
        "SKU Description": "SKU Description",   # keep as-is
        "Market":          "Market",
        "Quantity":        "Quantity",
        "Highest Priority":"HighestPriority",
    }
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

    # Ensure required columns exist
    required = ["SKUCode", "Quantity", "Market", "HighestPriority"]
    missing = [c for c in required if c not in df.columns]
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

    # Rank within the manual block only
    df = df.sort_values(
        by=["ManualPriorityScore", "Quantity"],
        ascending=[False, False]
    ).reset_index(drop=True)

    df["ManualRank"] = df.index + 1   # 1-based rank within manual block

    return df


def _attach_mould_metrics(manual_df: pd.DataFrame, stage2_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join Stage 2 mould metrics (MachineCount, AvgMouldHealth) onto manual entries.
    SKUs not found in the mould report get 0 for both columns.
    """
    mould_cols = ["SKUCode", "MachineCount", "AvgMouldHealth"]
    available  = [c for c in mould_cols if c in stage2_df.columns]

    if len(available) < 3:
        # Mould data unavailable — fill with zeros
        manual_df["MachineCount"]   = 0
        manual_df["AvgMouldHealth"] = 0.0
        return manual_df

    mould_lookup = stage2_df[available].drop_duplicates(subset="SKUCode")

    manual_df = manual_df.merge(mould_lookup, on="SKUCode", how="left")
    manual_df["MachineCount"]   = manual_df["MachineCount"].fillna(0).astype(int)
    manual_df["AvgMouldHealth"] = manual_df["AvgMouldHealth"].fillna(0.0)

    return manual_df


def _build_manual_rows(
    manual_df: pd.DataFrame,
    stage2_df: pd.DataFrame,
    vector_req_lookup: dict,
) -> pd.DataFrame:
    """
    Construct manual rows that are column-compatible with the Stage 2 DataFrame
    so they can be concatenated vertically without issues.

    Multi-Source Transparency:
      Vector_Requirement = what automated demand said for this SKU+Market (before override)
      CPT_Requirement    = what the CPT (manual frontend) specified — takes precedence
      Requirement        = CPT_Requirement (used for all downstream calculations)

    vector_req_lookup is now keyed by (SKUCode, Market) tuples to prevent
    cross-market contamination (e.g. Govt market entry must not get RE/OE quantity).
    """
    # Attach mould metrics first
    manual_df = _attach_mould_metrics(manual_df, stage2_df)

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
    # Vector_Requirement: looked up by (SKUCode, Market) — 0 if no same-market
    # automated row exists (e.g. Govt market has no vector data)
    manual_rows["Vector_Requirement"] = [
        vector_req_lookup.get((sku, mkt), 0)
        for sku, mkt in zip(manual_df["SKUCode"], manual_df["Market"].astype(str).str.strip())
    ]
    # CPT_Requirement: the manager's override value — absolute precedence
    manual_rows["CPT_Requirement"]     = manual_df["Quantity"]
    # Requirement used for final calculations = CPT value
    manual_rows["Requirement"]         = manual_df["Quantity"]

    # --- Ghost SKU flag: manual entries are always real demand ---
    manual_rows["IsGhostSKU"]          = False

    # --- Deployment metrics (from Stage 2 join) ---
    manual_rows["MachineCount"]        = manual_df["MachineCount"]
    manual_rows["AvgMouldHealth"]      = manual_df["AvgMouldHealth"]

    # --- Gap flags ---
    manual_rows["CriticalGap"]         = manual_df["MachineCount"] == 0
    manual_rows["ExcessProduction"]    = False
    manual_rows["MouldAlert"]          = manual_df["AvgMouldHealth"] > 0.9

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

def process_manual_override(stage2_df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """
    Stage 3 entry point: Hybrid Synthesis.

    Steps:
        1. Load manual demand Excel.
        2. Compute Super-Boost priority scores.
        3. Attach mould metrics from Stage 2.
        4. Remove any automated rows whose SKUCode appears in the manual list
           (manual entry takes precedence).
        5. Offset automated ProxyRanks so they start after the last manual rank.
        6. Concatenate: manual rows on top, automated rows below.
        7. Assign a sequential FinalRank column (1, 2, 3 …).

    Args:
        stage2_df (pd.DataFrame): Full output from Stage 2 (deployment analysis).
        date_str  (str):          Date in DDMMYYYY format (for logging).

    Returns:
        pd.DataFrame: Hybrid DataFrame with manual entries at the top.
    """
    print(f"[STAGE 3] Starting Manual Strategic Override for {date_str}")

    # ---- Step 1: Load & validate manual data ----
    print("[STAGE 3] Loading manual demand file...")
    manual_df = _load_manual_data()
    print(f"[STAGE 3] Loaded {len(manual_df)} manual entries")

    if manual_df.empty:
        print("[STAGE 3] No manual entries found. Returning Stage 2 output unchanged.")
        stage2_df["Source"] = "Automated"
        stage2_df["FinalRank"] = range(1, len(stage2_df) + 1)
        return stage2_df

    # ---- Step 2: Compute Super-Boost scores & rank within manual block ----
    print("[STAGE 3] Computing Super-Boost priority scores...")
    manual_df = _compute_super_boost_score(manual_df)

    # ---- Step 3a: Capture Vector_Requirement BEFORE removing superseded rows ----
    # KEY FIX: Use (SKUCode, Market) as composite key so a Govt-market manual entry
    # does not inherit the vector quantity from an RE/OE row of the same SKU code.
    auto_df = stage2_df.copy()
    auto_df["SKUCode"] = auto_df["SKUCode"].astype(str).str.strip()
    auto_df["Market"]  = auto_df["Market"].astype(str).str.strip()

    req_col = "Requirement"  # Stage 2 output column holding the automated requirement
    vector_req_lookup: dict = {}
    if req_col in auto_df.columns:
        manual_sku_mkt_pairs = set(
            zip(manual_df["SKUCode"].str.strip(), manual_df["Market"].astype(str).str.strip())
        )
        auto_df["_pair"] = list(zip(auto_df["SKUCode"], auto_df["Market"]))
        vector_req_lookup = (
            auto_df[auto_df["_pair"].isin(manual_sku_mkt_pairs)]
            .groupby(["SKUCode", "Market"])[req_col]
            .sum()                             # sum all location rows for same SKU+Market
            .to_dict()
        )
        auto_df.drop(columns=["_pair"], inplace=True)

    # ---- Step 3b: Build column-aligned manual rows (with both requirement cols) ----
    manual_rows = _build_manual_rows(manual_df, stage2_df, vector_req_lookup)
    n_manual = len(manual_rows)

    # ---- Step 4: Remove automated rows superseded by manual entries ----
    # Match on (SKUCode, Market) so that a Govt-market manual entry does NOT remove
    # RE/OE automated rows for the same SKU code.
    manual_sku_mkt_pairs = set(
        zip(manual_df["SKUCode"].str.strip(), manual_df["Market"].astype(str).str.strip())
    )
    auto_df["_pair"] = list(zip(auto_df["SKUCode"], auto_df["Market"]))
    superseded       = auto_df["_pair"].isin(manual_sku_mkt_pairs)
    n_superseded     = superseded.sum()
    auto_df          = auto_df[~superseded].drop(columns=["_pair"]).copy()

    if n_superseded > 0:
        print(f"[STAGE 3] Removed {n_superseded} automated row(s) superseded by manual entries")

    # ---- Step 5: Tag automated rows, add dual-source cols & offset ProxyRank ----
    auto_df["Source"] = "Automated"
    # For automated rows: Vector demand IS the requirement; no CPT override
    auto_df["Vector_Requirement"] = auto_df[req_col] if req_col in auto_df.columns else 0
    auto_df["CPT_Requirement"]    = 0
    # Ensure IsGhostSKU propagates (set to False if absent)
    if "IsGhostSKU" not in auto_df.columns:
        auto_df["IsGhostSKU"] = False
    # Re-rank automated rows starting after the last manual rank
    auto_df = auto_df.sort_values("ProxyRank", ascending=True).reset_index(drop=True)
    auto_df["ProxyRank"] = auto_df.index + n_manual + 1

    # ---- Step 6: Vertical merge — manual on top ----
    hybrid_df = pd.concat([manual_rows, auto_df], ignore_index=True, sort=False)

    # ---- Step 6b: DATA IMPUTATION — fill all missing numeric values with 0 ----
    # Ensures every cell is populated across Manual / Automated / Ghost rows.
    # Zero is the correct sentinel for missing demand/inventory data.
    _NUMERIC_FILL_ZERO = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Updated_Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration', 'NormPenetration', 'NormRequirement',
        'PriorityScore_Inventory', 'NormInventoryScore',
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',
        'PriorityScore',
        'ConsolidatedPriorityScore',
        'ProxyPenetration', 'ProxyRank',
        'ASP', 'daily_cure', 'rev_pot', 'price_priority',
        'MarketWeight', 'TopSKUFlag', 'ManualPriorityScore',
        'HighestPriority', 'ManualRank',
    ]
    for col in _NUMERIC_FILL_ZERO:
        if col in hybrid_df.columns:
            hybrid_df[col] = pd.to_numeric(hybrid_df[col], errors='coerce').fillna(0)

    # String columns: fill NaN with empty string so no cell shows 'NaN'
    _STRING_FILL_EMPTY = ['SKU Description', 'Source']
    for col in _STRING_FILL_EMPTY:
        if col in hybrid_df.columns:
            hybrid_df[col] = hybrid_df[col].fillna('')

    # ---- Step 7: Unified StrategicPriorityScore (fully populated for every row) ----
    # Manual     → ManualPriorityScore   (super-boost value, e.g. 10–11)
    # Automated  → ConsolidatedPriorityScore (single configurable Demand+Inventory+Price score)
    hybrid_df["StrategicPriorityScore"] = np.where(
        hybrid_df["Source"] == "Manual",
        hybrid_df["ManualPriorityScore"],
        hybrid_df.get("ConsolidatedPriorityScore", pd.Series(0.0, index=hybrid_df.index))
    )

    # ---- Step 8: Final Rank — sort by StrategicPriorityScore then stamp rank ----
    # Must sort HERE so that automated rows with high scores are not buried by
    # whatever order the Stage-2 ProxyRank happened to leave them in.
    # Manual entries (score 10–11) always float above automated entries (score ≤ 1).
    hybrid_df = hybrid_df.sort_values(
        "StrategicPriorityScore", ascending=False
    ).reset_index(drop=True)
    hybrid_df["Final Rank"] = hybrid_df.index + 1

    # Summary
    print(f"[STAGE 3] Override complete:")
    print(f"  - Manual entries at top : {n_manual}")
    print(f"  - Automated entries     : {len(auto_df)}")
    print(f"  - Total rows in output  : {len(hybrid_df)}")

    # SELECT & ORDER OUTPUT COLUMNS — logical left-to-right narrative
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

        # --- Group 5: Demand Signals (Data Story: Vector Need → CPT Override → Final Gap) ---
        'Stock', 'Vector_Requirement', 'CPT_Requirement', 'Requirement', 'Updated_Requirement', 'Penetration',
        'NormPenetration', 'NormRequirement',

        # --- Group 6: SKU Attributes ---
        'TopSKUFlag', 'MarketWeight', 'priority',

        # --- Group 7: Inventory Signals ---
        'PriorityScore_Inventory', 'NormInventoryScore',

        # --- Group 7b: History Penetration ---
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',

        # --- Group 8: Deployment Metrics & Gap Flags ---
        'MachineCount', 'AvgMouldHealth',
        'ProxyPenetration', 'ProxyRank',
        'CriticalGap', 'ExcessProduction', 'MouldAlert', 'IsGhostSKU',

        # --- Group 9: Revenue & Efficiency ---
        'ASP', 'Cure Time', 'daily_cure', 'rev_pot', 'price_priority',

        # --- Group 10: Detailed Scoring Components ---
        'PriorityScore',
        'ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore',
    ]

    # Safe selection: only include columns present in the hybrid DataFrame
    available_cols = [col for col in output_columns if col in hybrid_df.columns]
    return hybrid_df[available_cols]
