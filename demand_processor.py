# demand_processor.py
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
import config # Import the settings



# ---------------------------------------------------------------------------
# MIN-MAX NORMALISATION HELPER
# ---------------------------------------------------------------------------

def _minmax(series: pd.Series) -> pd.Series:
    """
    Min-max normalize a Series to [0, 1].
    Formula: (x - min) / (max - min)
    Returns 0.0 everywhere when max == min (avoids division by zero).
    """
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.0, index=series.index)
    return (series - mn) / (mx - mn)


# ---------------------------------------------------------------------------
# HISTORY PENETRATION HELPER
# ---------------------------------------------------------------------------

def compute_history_penetration(today_bpr: pd.DataFrame, today_bor: pd.DataFrame, date_str: str, n: int) -> pd.Series:
    """
    Compute HistoryPenetrationScore — a DISCRETE integer in [0, 10].

    Scoring rules:
      • 0  : SKU is Red (or unknown) today — no streak credit at all.
      • 1  : SKU is Black today with Penetration >= 100%.
      • 2  : Black + Penetration >= 100% for today AND yesterday.
      • ...
      • N  : Black + Penetration >= 100% every consecutive day from today
             back through the last N-1 days (streak of N days, max = N = 10).

    A day is considered "in black" ONLY when:
        Penetration = (Virtual Norm - Stock) / Virtual Norm * 100  >= 100%
    (i.e., stock is at or below zero relative to the virtual norm).

    This penetration is computed identically to Stage 1 / Stage 2 logic,
    reading raw BOR files (filtered to plant-1300 locations).

    The streak breaks as soon as a day is found where Penetration < 100%
    (even if colour is Black) — or if files are missing for that day.

    Args:
        today_bpr  : BPR DataFrame for today  (SKUCode, On hand Inv. Color)
        today_bor  : BOR DataFrame for today  (already filtered to plant-1300;
                     has SKUCode, Virtual Norm, Stock and optionally Penetration)
        date_str   : Today's date in DDMMYYYY format.
        n          : Lookback window (config.HISTORY_PENETRATION_N). Max score = n.

    Returns:
        pd.Series indexed by SKUCode with discrete integer scores in [0, n].
    """
    today = datetime.strptime(date_str, "%d%m%Y")

    # ------------------------------------------------------------------
    # Helper: compute average Penetration per SKU from a raw BOR DataFrame.
    # Uses (Virtual Norm - Stock) / Virtual Norm * 100 — same as Stage 1/2.
    # Returns {sku: penetration_percent}  (NOT clipped; can exceed 100).
    # ------------------------------------------------------------------
    def _get_penetrations(bor_df: pd.DataFrame) -> dict:
        if 'Virtual Norm' not in bor_df.columns or 'Stock' not in bor_df.columns:
            return {}
        df = bor_df.copy()
        df['SKUCode'] = df['SKUCode'].astype(str)
        # Recompute from raw columns to stay in sync with Stage 1 formula
        df['_pen'] = np.where(
            df['Virtual Norm'] == 0, 0,
            (df['Virtual Norm'] - df['Stock']) / df['Virtual Norm'] * 100
        )
        # Average across all 1300-locations for this SKU
        return df.groupby('SKUCode')['_pen'].mean().to_dict()

    # ------------------------------------------------------------------
    # Step 1 — Determine TODAY's state for each SKU from BOR only.
    # NOTE: We deliberately do NOT use the BPR colour column here.
    # The BPR dominant colour is majority-voted across ALL location types
    # (JIT, Depot, Feeder, PWH …), while BOR is plant-1300 only.
    # Those two can disagree, causing pen=100% SKUs to get score=0.
    # Per spec: "black" = penetration >= 100% from BOR. Period.
    # ------------------------------------------------------------------
    today_pens = _get_penetrations(today_bor)
    all_skus   = list(today_pens.keys())

    # ------------------------------------------------------------------
    # Step 2 — Build day-by-day penetration snapshots for days [0 … n-1].
    #          day_pens[i]  = {sku: penetration_pct}  for offset i from today.
    #          day 0 = today (already computed above).
    # ------------------------------------------------------------------
    day_pens = [today_pens]  # index 0 = today, 1 = yesterday, …

    for day_offset in range(1, n):        # offsets 1 … n-1
        past_date = today - timedelta(days=day_offset)
        bor_path  = (
            f'{config.BASE_DATA_PATH}/Vectordata/BOR/'
            f'BORColorBandwiseReport__{past_date.strftime("%d-%m-%Y")}.csv'
        )

        if not os.path.exists(bor_path):
            day_pens.append({})           # missing day → empty dict
            continue

        try:
            past_bor = pd.read_csv(bor_path)
            past_bor['SKUCode'] = past_bor['SKUCode'].astype(str)
            if 'Location Code' in past_bor.columns:
                past_bor = past_bor[past_bor['Location Code'].str.startswith('1300')]
            day_pens.append(_get_penetrations(past_bor))
        except Exception:
            day_pens.append({})           # unreadable file → empty dict

    # ------------------------------------------------------------------
    # Step 3 — Score each SKU.
    # Black threshold: config.HISTORY_PENETRATION_BLACK (default 100%).
    # User can lower this (e.g. 95) to be more lenient about what counts as "black".
    #   Rule:
    #     • today_pen < BLACK  → score = 0  ("red": not depleted enough today)
    #     • today_pen >= BLACK → walk backward counting consecutive black days:
    #         for each day (0=today, 1=yesterday, …):
    #             BOR missing (holiday)   → continue (skip, streak intact)
    #             penetration >= BLACK    → streak += 1
    #             penetration < BLACK     → break (streak ends)
    #         score = streak   (discrete integer, max = n)
    # ------------------------------------------------------------------
    black_threshold = config.HISTORY_PENETRATION_BLACK
    scores: dict = {}

    for sku in all_skus:
        # Gate: if today's BOR penetration < threshold, SKU is "red" → score 0
        if today_pens.get(sku, 0.0) < black_threshold:
            scores[sku] = 0
            continue

        streak = 0
        for day_idx in range(n):          # 0 = today, 1 = yesterday, …
            pen = day_pens[day_idx].get(sku, None)

            if pen is None:
                continue                  # missing file = holiday → skip, streak intact

            if pen < black_threshold:
                break                     # reading below threshold → streak ends

            streak += 1                   # pen >= threshold → count this day

        scores[sku] = streak

    return pd.Series(scores, name='HistoryPenetrationScore', dtype=int)


# ---------------------------------------------------------------------------
# HISTORY BOR DATA EXPORT HELPER
# ---------------------------------------------------------------------------

def get_history_bor_data(date_str: str, n: int) -> list:
    """
    Load and return raw BOR data for the last N days (today + N-1 historical).

    Used by app_stage3.py to write per-day penetration tabs in the output Excel.

    For each day:
        - Reads BORColorBandwiseReport__DD-MM-YYYY.csv from the BOR folder.
        - Filters to Location Code starting with '1300' (plant-1300).
        - Computes Penetration = (Virtual Norm - Stock) / Virtual Norm * 100.
        - Keeps columns: SKUCode, Location Code, Norm , Virtual Norm, Stock, Penetration.
        - Missing files (weekends / holidays) → (date_label, None) in the result.

    Args:
        date_str : Today's date in DDMMYYYY format.
        n        : Number of days to look back (config.HISTORY_PENETRATION_N).

    Returns:
        list of (date_label: str, df: pd.DataFrame | None)
        Ordered most-recent-first (index 0 = today).
        date_label is in 'DD-MM-YYYY' format.
    """
    today  = datetime.strptime(date_str, "%d%m%Y")
    result = []

    for day_offset in range(n):           # 0 = today, 1 = yesterday, …
        past_date  = today - timedelta(days=day_offset)
        date_label = past_date.strftime("%d-%m-%Y")
        bor_path   = (
            f'{config.BASE_DATA_PATH}/Vectordata/BOR/'
            f'BORColorBandwiseReport__{date_label}.csv'
        )

        if not os.path.exists(bor_path):
            result.append((date_label, None))
            continue

        try:
            df = pd.read_csv(bor_path)
            df['SKUCode'] = df['SKUCode'].astype(str)

            # Filter to plant-1300 locations only
            if 'Location Code' in df.columns:
                df = df[df['Location Code'].str.startswith('1300')].copy()

            # Compute Penetration from raw columns (same formula as Stage 1 / 2)
            if 'Virtual Norm' in df.columns and 'Stock' in df.columns:
                df['Penetration'] = np.where(
                    df['Virtual Norm'] == 0, 0,
                    (df['Virtual Norm'] - df['Stock']) / df['Virtual Norm'] * 100
                )

            # Keep only the columns useful for the history tab
            keep = ['SKUCode', 'Location Code', 'Norm ', 'Virtual Norm', 'Stock', 'Penetration']
            keep = [c for c in keep if c in df.columns]
            result.append((date_label, df[keep].reset_index(drop=True)))

        except Exception as exc:
            print(f"[HISTORY BOR] Could not read {bor_path}: {exc}")
            result.append((date_label, None))

    return result


# ---------------------------------------------------------------------------
# MAIN STAGE 1 PROCESSOR
# ---------------------------------------------------------------------------

def process_single_date(date_str):

    date = datetime.strptime(date_str, "%d%m%Y")
    
    # Paths constructed from config
    file_path1 = f'{config.BASE_DATA_PATH}/Vectordata/SPOR/Single_Production_Order_Report_{date.strftime("%d%m%Y")}.csv'
    file_path2 = f'{config.BASE_DATA_PATH}/Vectordata/BOR/BORColorBandwiseReport__{date.strftime("%d-%m-%Y")}.csv'
    file_path3 = f'{config.BASE_DATA_PATH}/Vectordata/BMR/Prod_OverAll_BMReport__{date.strftime("%d_%m_%Y")}.xlsx'
    file_path4 = f'{config.BASE_DATA_PATH}/Vectordata/BPR/BufferPenetrationReport__{date.strftime("%d-%m-%Y")}.csv'

    if not all(os.path.exists(f) for f in [file_path1, file_path2, file_path3, file_path4]):
        print(f"Skipping {date_str}: Missing files.")
        return None

    # Load Data
    bpr_v = pd.read_csv(file_path4)
    bor_v = pd.read_csv(file_path2)
    bmr_v = pd.read_excel(file_path3)

    # ENSURE STRING TYPES FOR MERGE KEYS (prevent empty merges)
    bpr_v['SKUCode'] = bpr_v['SKUCode'].astype(str)
    bor_v['SKUCode'] = bor_v['SKUCode'].astype(str)

    # --- INVENTORY SCORING (BPR) ---
    bpr_v['Location Type'] = bpr_v['Location Type'].replace('depot', 'Depot')
    filtered_colors = bpr_v[bpr_v['On hand Inv. Color'].isin(['Black', 'Red'])]
    pivoted = filtered_colors.groupby(['SKUCode', 'Location Type', 'On hand Inv. Color']).size().unstack(fill_value=0).reset_index()
    pivoted.rename(columns={'Black': 'Black Count', 'Red': 'Red Count'}, inplace=True)
    pivoted = pivoted.pivot(index='SKUCode', columns='Location Type', values=['Black Count', 'Red Count']).fillna(0)
    pivoted.columns = [f"{color}_{loc}" for color, loc in pivoted.columns]
    pivoted.reset_index(inplace=True)

    pivoted['InventoryScore'] = 0
    for loc, weight in config.LOCATION_WEIGHTS.items():
        b_col, r_col = f'Black Count_{loc}', f'Red Count_{loc}'
        if b_col in pivoted.columns:
            pivoted['InventoryScore'] += pivoted[b_col] * weight * config.INVENTORY_SCORE_FACTORS["black"]
        if r_col in pivoted.columns:
            pivoted['InventoryScore'] += pivoted[r_col] * weight * config.INVENTORY_SCORE_FACTORS["red"]

    # --- DEMAND SCORING (BOR & BMR) ---
    bor_v = bor_v[bor_v['Location Code'].str.startswith('1300')].copy()
    bor_v['Market'] = bor_v['Location Code'].str.split('_').str[1].replace(
        {'FG10': 'RE', 'OE10': 'OE', 'ST10': 'ST', 'OTR10': 'OTR'}
    )
    bor_v['Market'] = bor_v['Market'].astype(str)  # Ensure string type
    
    # --- STRATEGIC NORM ADJUSTMENT (config-driven multipliers) ---
    # Adjusted_Target = Virtual Norm × Market Multiplier
    # Defaults: RE=1.0, OE=1.0, ST=1.0 (all 100% of Virtual Norm)
    # Users can override in config_input.xlsx (e.g. RE=0.5 for conservative RE target)
    bor_v['Adjusted_Target'] = bor_v.apply(
        lambda row: row['Virtual Norm'] * config.NORM_MULTIPLIERS.get(row['Market'], 1.0),
        axis=1
    )
    
    # Requirement = max(0, Adjusted_Target - Stock)
    bor_v['Requirement'] = np.maximum(bor_v['Adjusted_Target'] - bor_v['Stock'], 0)
    
    # Penetration ALWAYS uses 100% Virtual Norm as the baseline (config requirement).
    # This gives a true picture of buffer depletion regardless of market type.
    # Penetration = (Virtual Norm - Stock) / Virtual Norm * 100
    bor_v['Penetration'] = np.where(
        bor_v['Virtual Norm'] == 0,
        0,
        (bor_v['Virtual Norm'] - bor_v['Stock']) / bor_v['Virtual Norm'] * 100
    )
    bor_v = bor_v.merge(bpr_v[['SKUCode', 'Location Code', 'Top SKU']], on=['SKUCode', 'Location Code'], how='left')

    bmr_v.columns = bmr_v.iloc[0]; bmr_v = bmr_v.drop(index=0).reset_index(drop=True)
    bmr_v = bmr_v[bmr_v['Plant Code'] == '1300'].rename(columns={'Item Code': 'SKUCode', 'Pending CCR Qty': 'Requirement', 'BPP': 'Penetration'})
    bmr_v['SKUCode'] = bmr_v['SKUCode'].astype(str)  # Ensure string type
    bmr_v['Market'], bmr_v['Top SKU'] = 'EXP', 'T'
    
    # For BMR data (EXP market), Adjusted_Target is not applicable as BMR doesn't have Virtual Norm
    # The Requirement and Penetration are already calculated in BMR
    bmr_v['Adjusted_Target'] = np.nan  # BMR doesn't have Virtual Norm to calculate from

    combined = pd.concat([bmr_v, bor_v], ignore_index=True)
    combined = combined[combined['Requirement'] != 0].copy()
    
    # Extract rim size from SKUCode (positions 8:10 = 9th and 10th characters)
    # Convert to numeric and handle invalid values
    combined['size'] = pd.to_numeric(combined['SKUCode'].str[8:10], errors='coerce').fillna(0).astype('Int64')
    
    # Apply User Params from config
    combined['MarketWeight'] = combined['Market'].map(config.MARKET_WEIGHTS)
    combined['TopSKUFlag'] = combined['Top SKU'].apply(lambda x: 1 if x == 'T' else 0)
    
    combined['NormPenetration'] = _minmax(combined['Penetration'])
    combined['NormRequirement'] = _minmax(combined['Requirement'])

    # Generate priority tuple — uses -MarketWeight as lead key (higher weight = higher urgency)
    # MarketPriority removed: MarketWeight already encodes the same ordering (higher = more important)
    combined['priority'] = combined.apply(
        lambda row: (-row['MarketWeight'], -row['Penetration'], -row['Requirement'], -row['TopSKUFlag']),
        axis=1
    )

    combined['PriorityScore'] = (
        combined['MarketWeight'] * config.SCORING_PARAMS["market_weightage"] +
        combined['NormPenetration'] * config.SCORING_PARAMS["penetration_weightage"] +
        combined['NormRequirement'] * config.SCORING_PARAMS["requirement_weightage"] +
        combined['TopSKUFlag'] * config.SCORING_PARAMS["top_sku_weightage"]
    )

    # --- REVENUE & EFFICIENCY (Dispatch & Curing) ---
    combined = combined.merge(pivoted[['SKUCode', 'InventoryScore']], on='SKUCode', how='left').fillna(0)
    combined['NormInventoryScore'] = _minmax(combined['InventoryScore'])

    dispatch = pd.read_csv(f"{config.BASE_DATA_PATH}/DISPATCH1.csv", encoding='ISO-8859-1')
    dispatch['Amt.in loc.cur.'] = dispatch['Amt.in loc.cur.'].replace({',': ''}, regex=True)
    dispatch['Amt.in loc.cur.'] = pd.to_numeric(dispatch['Amt.in loc.cur.'], errors='coerce')
    dispatch['Quantity'] = pd.to_numeric(dispatch['Quantity'], errors='coerce')
    dispatch['ASP'] = dispatch['Amt.in loc.cur.'] / dispatch['Quantity']

    # --- MARKET-AWARE ASP ---
    # OE market uses OE-channel ASP; all other markets (RE, ST, OTR, EXP) share the RE-channel ASP.
    # We derive the market group from each SKU's Market column in combined,
    # join it onto the dispatch rows, then group by (Material, Market_Group).
    combined['_mkt_grp'] = combined['Market'].apply(lambda m: 'OE' if m == 'OE' else 'RE')

    sku_mkt_map = (
        combined[['SKUCode', '_mkt_grp']]
        .drop_duplicates()
        .rename(columns={'SKUCode': 'Material', '_mkt_grp': 'Market_Group'})
    )

    dispatch_1300 = dispatch[dispatch['Plant'] == 1300].copy()
    dispatch_1300['Material'] = dispatch_1300['Material'].astype(str)
    dispatch_merged = dispatch_1300.merge(sku_mkt_map, on='Material', how='left')
    dispatch_merged['Market_Group'] = dispatch_merged['Market_Group'].fillna('RE')

    asp_map = dispatch_merged.groupby(['Material', 'Market_Group'])['ASP'].mean()

    combined['ASP'] = combined.apply(
        lambda row: asp_map.get((row['SKUCode'], row['_mkt_grp']), config.DEFAULT_ASP),
        axis=1
    )
    combined.drop(columns=['_mkt_grp'], inplace=True)

    curing = pd.read_csv(f"{config.BASE_DATA_PATH}/curing_cycletime.csv").sort_values('Cure Time', ascending=False).drop_duplicates('SKUCode')
    combined = combined.merge(curing[['SKUCode', 'Cure Time']], on='SKUCode', how='left')
    combined['Cure Time'] = combined['Cure Time'].fillna(config.DEFAULT_CURE_TIME) + 2.5
    
    combined['daily_cure'] = np.ceil((1440 / combined['Cure Time']) * config.EFFICIENCY_FACTOR).astype(int)
    combined['rev_pot'] = combined['ASP'] * combined['daily_cure']
    combined['PriceScore'] = _minmax(combined['rev_pot'])

    # --- HISTORY PENETRATION SCORING ---
    # Discrete streak count [0, N]:
    #   0  = SKU is Red today (BPR color != Black)
    #   1  = Black today with Penetration >= 100%
    #   k  = Black + Pen >= 100% for k consecutive days ending today
    #   N  = Black + Pen >= 100% for all N days (max score)
    # Penetration recomputed from raw BOR: (Virtual Norm - Stock) / Virtual Norm * 100.
    n_days = config.HISTORY_PENETRATION_N
    history_scores = compute_history_penetration(bpr_v, bor_v, date_str, n_days)
    combined['HistoryPenetrationScore'] = combined['SKUCode'].map(history_scores).fillna(0).astype(int)
    # Normalize to [0, 1]: max possible score = n_days (discrete integer, so divide by N)
    combined['NormHistoryPenetrationScore'] = _minmax(combined['HistoryPenetrationScore'])

    # CONSOLIDATED SCORE (Demand + Inventory + Price + History Penetration)
    # Weights are fully configurable via config_input.xlsx.
    # Set price_priority = 0 for pure Demand+Inventory+History scoring.
    # Set history_penetration = 0 to disable streak-based scoring.
    combined['ConsolidatedPriorityScore'] = (
        combined['PriorityScore']            * config.CONSOLIDATED_WEIGHTS["demand_priority"] +
        combined['NormInventoryScore']       * config.CONSOLIDATED_WEIGHTS["inventory_priority"] +
        combined['PriceScore']               * config.CONSOLIDATED_WEIGHTS["price_priority"] +
        combined['NormHistoryPenetrationScore'] * config.CONSOLIDATED_WEIGHTS["history_penetration"]
    )

    # SINGLE RANKING — one consolidated score, one rank
    combined['Rank_ConsolidatedPriorityScore'] = combined['ConsolidatedPriorityScore'].rank(ascending=False, method='min')

    # Sort by consolidated rank
    combined = combined.sort_values(by='Rank_ConsolidatedPriorityScore', ascending=True)

    # --- ROUNDING ---
    # Penetration: 2 decimal places
    combined['Penetration'] = combined['Penetration'].round(2)
    # All score columns: 3 decimal places
    for _score_col in [
        'PriorityScore', 'PriceScore',
        'ConsolidatedPriorityScore',
    ]:
        if _score_col in combined.columns:
            combined[_score_col] = combined[_score_col].round(3)

    # SELECT ONLY REQUIRED COLUMNS (matching original output)
    # Columns ordered to tell a clear left-to-right story:
    # Group 1: Identification (Who)
    # Group 2: Targets + Market context (Goal)
    # Group 3: Demand Signals (How urgent?)
    # Group 4: SKU Attributes (Context)
    # Group 5: Inventory Signals (Stock health)
    # Group 6: Revenue & Efficiency (Value)
    # Group 7: History Penetration (Streak)
    # Group 8: Scoring & Ranking (Final verdict)
    # NOTE: 'priority' tuple, 'NormInventoryScore', 'NormHistoryPenetrationScore'
    #        are computed internally for scoring but intentionally excluded here.
    output_columns = [
        # --- Group 1: Identification ---
        'SKUCode', 'SKU Description', 'size',

        # --- Group 2: Targets + Market context ---
        'Market', 'Norm ', 'Virtual Norm', 'Adjusted_Target',

        # --- Group 3: Demand Signals ---
        'Stock', 'Requirement', 'Penetration',

        # --- Group 4: SKU Attributes ---
        'TopSKUFlag',

        # --- Group 5: Inventory Signals ---
        'InventoryScore',

        # --- Group 6: Revenue & Efficiency ---
        'ASP', 'Cure Time', 'PriceScore',

        # --- Group 7: History Penetration ---
        'HistoryPenetrationScore',

        # --- Group 8: Scoring & Ranking ---
        'PriorityScore',
        'ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore',
    ]

    # Only select columns that exist
    available_cols = [col for col in output_columns if col in combined.columns]
    combined = combined[available_cols]

    return combined