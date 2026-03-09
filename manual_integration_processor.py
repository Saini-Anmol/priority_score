# manual_integration_processor.py
# Stage 3: Manual Strategic Override — Hybrid Synthesis Engine
#
# Reads ./data/manual_frontend_demand.xlsx and scores manually-entered SKUs
# using the SAME principled 4-step weighted scoring pipeline as Stage 2
# (frontend_processor.py), guaranteeing full consistency between the two stages.
#
# Scoring guarantee (final output order):
#   1st  →  Manual SKUs with HighestPriority = 1  (ordered by ConsolidationPriorityScore desc)
#   2nd  →  Manual SKUs with HighestPriority = 0  (ordered by ConsolidationPriorityScore desc)
#   3rd  →  Automated SKUs                         (ordered by ConsolidatedPriorityScore)
#
# Weights and market scores are shared via config_stage2 for full Stage 2/3 consistency.
# This file does NOT import or modify any Stage 1 source files.

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
# INTERNAL HELPERS  (mirrors frontend_processor.py logic exactly)
# ---------------------------------------------------------------------------

def _load_manual_data() -> pd.DataFrame:
    """
    Load and validate the manual frontend demand Excel file.

    Expected columns (whitespace-stripped):
        SKU Code | SKU Description | Market | Quantity | Target Date | Highest Priority

    'Target Date' is optional — defaults to today if absent.
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
        raise ValueError(f"Manual demand file is missing required columns: {missing}")

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
    Four-step manual scoring pipeline — identical to Stage 2 (frontend_processor.py).

    Step 1 — weighted_score
        Weighted sum of min-max normalised Market, Quantity, Target Date.
        Weights: W_MARKET, W_QTY, W_TARGET_DATE from config_stage2 (must sum to 1).
        Result range: [0, 1].

    Step 2 — Identify HP=1 sub-group and pre-rank.
        Among HighestPriority=1 rows, rank by weighted_score ASCENDING:
            rank 1 = lowest weighted_score (smallest boost later)
            rank P = highest weighted_score (largest boost later)

    Step 3 — modified_priority_score
        max_ws = max(weighted_score) across ALL manual rows.
        For HP=1 rows:
            modified_priority_score = max_ws * (1 + priority_rank / P)
            → range: (max_ws, 2 * max_ws]  → always above ALL HP=0 scores ≤ max_ws
        For HP=0 rows:
            modified_priority_score = weighted_score   (unchanged)

    Step 4 — ConsolidationPriorityScore  (guarantees all manual > all automated)
        overall_rank = rank of each manual row by modified_priority_score ASCENDING
            (rank 1 = lowest, rank N = highest = most urgent)
        ConsolidationPriorityScore = max_auto * (1 + overall_rank / N)
            → range: (max_auto, 2 * max_auto]  → all manual above all automated ✓

    Args:
        df       : cleaned manual DataFrame from _load_manual_data()
        max_auto : max(ConsolidatedPriorityScore) from Stage 2 automated rows

    Returns:
        df with columns: weighted_score, modified_priority_score,
                         ConsolidationPriorityScore, priority_rank, manual_rank
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
        hp1_idx = df.index[priority_mask]
        df.loc[hp1_idx, "priority_rank"] = (
            df.loc[hp1_idx, "weighted_score"]
            .rank(ascending=True, method="first")
            .astype(int)
        )
        df.loc[hp1_idx, "modified_priority_score"] = (
            max_ws * (1.0 + df.loc[hp1_idx, "priority_rank"] / P)
        ).round(6)

    # ── Step 4: ConsolidationPriorityScore ────────────────────────────────────
    # overall_rank: 1 = lowest modified_priority_score, N = highest (most urgent)
    df["overall_rank"] = (
        df["modified_priority_score"]
        .rank(ascending=True, method="first")
        .astype(int)
    )
    df["ConsolidationPriorityScore"] = (
        max_auto * (1.0 + df["overall_rank"] / N)
    ).round(6)

    # manual_rank: rank within the manual block, 1 = most urgent
    df["manual_rank"] = (
        df["ConsolidationPriorityScore"]
        .rank(ascending=False, method="first")
        .astype(int)
    )

    # Sort by manual_rank for clean display
    df = df.sort_values("manual_rank", ascending=True).reset_index(drop=True)

    # Logging
    hp1_df = df[df["HighestPriority"] == 1]
    hp0_df = df[df["HighestPriority"] == 0]
    print(f"[STAGE 3] Manual scoring complete:")
    print(f"  - Total manual rows       : {N}")
    print(f"  - HighestPriority=1 rows  : {P}")
    print(f"  - max_ws (step 3 base)    : {max_ws:.6f}")
    print(f"  - max_auto (step 4 base)  : {max_auto:.6f}")
    if not hp1_df.empty:
        print(f"  - HP=1 ConsolidationScore range: "
              f"[{hp1_df['ConsolidationPriorityScore'].min():.6f}, "
              f"{hp1_df['ConsolidationPriorityScore'].max():.6f}]")
    if not hp0_df.empty:
        print(f"  - HP=0 ConsolidationScore range: "
              f"[{hp0_df['ConsolidationPriorityScore'].min():.6f}, "
              f"{hp0_df['ConsolidationPriorityScore'].max():.6f}]")

    return df


def _attach_mould_metrics(manual_df: pd.DataFrame, stage2_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join Stage 2 mould metrics (MachineCount, AvgMouldHealth) onto manual entries.
    SKUs not found in the mould report get 0 for both columns.
    """
    mould_cols = ["SKUCode", "MachineCount", "AvgMouldHealth"]
    available  = [c for c in mould_cols if c in stage2_df.columns]

    if len(available) < 3:
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

    vector_req_lookup is keyed by (SKUCode, Market) tuples to prevent
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

    # --- Manual-specific metrics (Stage 2-aligned column names) ---
    manual_rows["Quantity"]                    = manual_df["Quantity"]
    manual_rows["Target Date"]                 = manual_df["Target Date"].astype(str)
    manual_rows["HighestPriority"]             = manual_df["HighestPriority"]
    manual_rows["weighted_score"]              = manual_df["weighted_score"]
    manual_rows["modified_priority_score"]     = manual_df["modified_priority_score"]
    manual_rows["manual_rank"]                 = manual_df["manual_rank"]
    manual_rows["ConsolidationPriorityScore"]  = manual_df["ConsolidationPriorityScore"]

    # --- Multi-Source Requirement Transparency ---
    # Vector_Requirement: looked up by (SKUCode, Market) — 0 if no same-market
    # automated row exists (e.g. Govt market has no vector data).
    # Summed across all location rows for that (SKU, Market) pair.
    manual_rows["Vector_Requirement"] = [
        vector_req_lookup.get((sku, mkt), 0)
        for sku, mkt in zip(manual_df["SKUCode"], manual_df["Market"].astype(str).str.strip())
    ]
    manual_rows["CPT_Requirement"]     = manual_df["Quantity"]
    manual_rows["Requirement"]         = manual_df["Quantity"]

    # Manual entries are actively demanded — treat as fully buffer-depleted (100% penetration)
    manual_rows["Penetration"]         = 100.0

    # Ghost SKU flag: manual entries are always real demand
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

    # ProxyRank for manual entries = manual_rank (occupies top N positions)
    manual_rows["ProxyRank"]           = manual_df["manual_rank"]

    return manual_rows


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def process_manual_override(stage2_df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """
    Stage 3 entry point: Hybrid Synthesis.

    Uses the SAME 4-step weighted scoring as Stage 2 for full consistency.

    Steps:
        1. Load manual demand Excel.
        2. Compute weighted scores + HighestPriority boost + automated-ceiling lift.
        3. Capture Vector_Requirement by (SKUCode, Market) before removing superseded rows.
        4. Build manual rows + tag automated rows.
        5. Supersede automated rows on (SKUCode, Market) match.
        6. Concatenate and sort by ConsolidationPriorityScore descending.
        7. Assign Final Rank.

    Final output order guaranteed:
        HP=1 manual  →  HP=0 manual  →  Automated (all by score desc within group)
    """
    print(f"[STAGE 3] Starting Manual Strategic Override for {date_str}")

    # ── Helper: automated-only path ──────────────────────────────────────────
    def _automated_only(df):
        df = df.copy()
        df["Source"]           = "Automated"
        req                    = "Requirement"
        df["Vector_Requirement"] = df[req] if req in df.columns else 0
        df["CPT_Requirement"]  = 0
        df = df.sort_values("ConsolidatedPriorityScore", ascending=False).reset_index(drop=True)
        df["Final Rank"]       = df.index + 1
        return _select_output_columns(df)

    # ── Step 1: Load manual data ─────────────────────────────────────────────
    print("[STAGE 3] Loading manual demand file...")
    try:
        manual_df = _load_manual_data()
        print(f"[STAGE 3] Loaded {len(manual_df)} manual entries")
    except FileNotFoundError as e:
        print(f"[STAGE 3] Warning: {e}")
        print("[STAGE 3] No manual file — returning Stage 2 output (automated only).")
        return _automated_only(stage2_df)

    if manual_df.empty:
        print("[STAGE 3] No manual entries — returning Stage 2 output (automated only).")
        return _automated_only(stage2_df)

    # ── Step 2: Compute weighted scores ──────────────────────────────────────
    print("[STAGE 3] Computing weighted priority scores...")

    # max_auto: ceiling that all manual scores must exceed
    score_col = "ConsolidatedPriorityScore"
    max_auto  = float(
        pd.to_numeric(stage2_df[score_col], errors="coerce").max()
        if score_col in stage2_df.columns else 1.0
    )
    if max_auto <= 0:
        max_auto = 1.0   # safety guard

    manual_df = _compute_weighted_score(manual_df, max_auto)

    # ── Step 3: Capture Vector_Requirement before removing superseded rows ───
    # KEY: (SKUCode, Market) composite key — Govt-market entries get 0,
    # not a quantity borrowed from RE/OE rows for the same SKU code.
    auto_df = stage2_df.copy()
    auto_df["SKUCode"] = auto_df["SKUCode"].astype(str).str.strip()
    auto_df["Market"]  = auto_df["Market"].astype(str).str.strip()

    req_col = "Requirement"
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

    # ── Step 4: Build manual rows + tag automated rows ───────────────────────
    manual_rows = _build_manual_rows(manual_df, stage2_df, vector_req_lookup)
    n_manual    = len(manual_rows)

    # ── Step 5: Supersede automated rows by (SKUCode, Market) match ─────────
    # A Govt-market manual entry does NOT remove RE/OE automated rows
    # for the same SKU code.
    pairs_to_supersede = set(
        zip(manual_df["SKUCode"].str.strip(), manual_df["Market"].astype(str).str.strip())
    )
    auto_df["_pair"] = list(zip(auto_df["SKUCode"], auto_df["Market"]))
    superseded_mask  = auto_df["_pair"].isin(pairs_to_supersede)
    n_superseded     = superseded_mask.sum()
    auto_df          = auto_df[~superseded_mask].drop(columns=["_pair"]).copy()

    if n_superseded > 0:
        print(f"[STAGE 3] Removed {n_superseded} automated row(s) superseded by manual entries")

    # Tag automated rows
    auto_df["Source"]                     = "Automated"
    auto_df["Vector_Requirement"]         = auto_df[req_col] if req_col in auto_df.columns else 0
    auto_df["CPT_Requirement"]            = 0
    auto_df["ConsolidationPriorityScore"] = pd.to_numeric(
        auto_df.get(score_col, pd.Series(0.0, index=auto_df.index)), errors="coerce"
    ).fillna(0)

    if "IsGhostSKU" not in auto_df.columns:
        auto_df["IsGhostSKU"] = False

    # Re-rank automated rows starting after the last manual rank
    auto_df = auto_df.sort_values("ProxyRank", ascending=True).reset_index(drop=True)
    auto_df["ProxyRank"] = auto_df.index + n_manual + 1

    # ── Step 6: Vertical merge ───────────────────────────────────────────────
    hybrid_df = pd.concat([manual_rows, auto_df], ignore_index=True, sort=False)

    # ── Data imputation ───────────────────────────────────────────────────────
    _NUMERIC_FILL_ZERO = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Updated_Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration', 'NormPenetration', 'NormRequirement',
        'PriorityScore_Inventory', 'NormInventoryScore',
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',
        'PriorityScore', 'ConsolidatedPriorityScore', 'ConsolidationPriorityScore',
        'ProxyPenetration', 'ProxyRank',
        'ASP', 'daily_cure', 'rev_pot', 'price_priority',
        'MarketWeight', 'TopSKUFlag', 'HighestPriority', 'manual_rank',
        'weighted_score', 'modified_priority_score',
    ]
    for col in _NUMERIC_FILL_ZERO:
        if col in hybrid_df.columns:
            hybrid_df[col] = pd.to_numeric(hybrid_df[col], errors='coerce').fillna(0)

    for col in ['SKU Description', 'Source', 'Target Date']:
        if col in hybrid_df.columns:
            hybrid_df[col] = hybrid_df[col].fillna('')

    # ── Step 7: Final Rank — sort by ConsolidationPriorityScore descending ───
    # HP=1 manual first → HP=0 manual → Automated (same guarantee as Stage 2).
    hybrid_df = hybrid_df.sort_values(
        "ConsolidationPriorityScore", ascending=False
    ).reset_index(drop=True)
    hybrid_df["Final Rank"] = hybrid_df.index + 1

    print(f"[STAGE 3] Override complete:")
    print(f"  - Manual entries at top : {n_manual}")
    print(f"  - Automated entries     : {len(auto_df)}")
    print(f"  - Total rows in output  : {len(hybrid_df)}")

    return _select_output_columns(hybrid_df)


def _select_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Select and order Stage 3 output columns.

    Column groups (A → Z order):
        A    : Final Rank
        B–D  : SKU Identification
        E–H  : Source & Manual Inputs
        I–K  : Manual Scoring Intermediates
        L    : Market
        M–O  : Production Targets
        P–W  : Demand Signals (incl. Updated_Requirement)
        X–Z  : SKU Attributes
        AA–AB: Inventory Signals
        AC–AD: History Penetration
        AE–AL: Deployment Metrics & Gap Flags   ← Stage 3-only columns
        AM–AQ: Revenue & Efficiency
        AR   : Stage 1 Raw Score (PriorityScore)
        AS   : Stage 1 Final Score (ConsolidatedPriorityScore)
        AT   : ──► FINAL STAGE 3 SCORE (ConsolidationPriorityScore — always last)
    """
    output_columns = [
        # A — Final Rank
        'Final Rank',

        # B–D — SKU Identification
        'SKUCode', 'SKU Description', 'size',

        # E–H — Source & Manual Inputs
        'Source', 'HighestPriority', 'Target Date', 'Quantity',

        # I–K — Manual Scoring Intermediates
        # weighted_score          : Step 1 weighted input (market + qty + date, range 0–1)
        # modified_priority_score : Step 3 HP=1 boosted score
        # manual_rank             : rank within manual block (1 = most urgent)
        'weighted_score', 'modified_priority_score', 'manual_rank',

        # L — Market
        'Market',

        # M–O — Production Targets
        'Norm ', 'Virtual Norm', 'Adjusted_Target',

        # P–W — Demand Signals
        'Stock',
        'Vector_Requirement', 'CPT_Requirement',
        'Requirement', 'Updated_Requirement',
        'Penetration', 'NormPenetration', 'NormRequirement',

        # X–Z — SKU Attributes
        'TopSKUFlag', 'MarketWeight', 'priority',

        # AA–AB — Inventory Signals
        'PriorityScore_Inventory', 'NormInventoryScore',

        # AC–AD — History Penetration
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',

        # AE–AL — Deployment Metrics & Gap Flags  (Stage 3-only)
        'MachineCount', 'AvgMouldHealth',
        'ProxyPenetration', 'ProxyRank',
        'CriticalGap', 'ExcessProduction', 'MouldAlert', 'IsGhostSKU',

        # AM–AQ — Revenue & Efficiency
        'ASP', 'Cure Time', 'daily_cure', 'rev_pot', 'price_priority',

        # AR — Stage 1 raw score (before manual override lift)
        'PriorityScore',

        # AS — ──► FINAL STAGE 3 SCORE (always last column)
        # ConsolidatedPriorityScore (Stage 1 automated baseline) is intentionally
        # excluded here — ConsolidationPriorityScore IS the final score in Stage 3.
        'ConsolidationPriorityScore',
    ]

    result = df[[c for c in output_columns if c in df.columns]]
    # Rename final score column for clean, consistent Stage 3 output label
    return result.rename(columns={'ConsolidationPriorityScore': 'ConsolidatedPriorityScore'})
