# V1/Reports/stage1_demand.py
# ---------------------------------------------------------------------------
# STAGE 1: DEMAND SCORING PROCESSOR
# Replaces old demand_processor.py and app.py
# ---------------------------------------------------------------------------

import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

# Import centralized configuration and utilities
import V1.Setups.config as config
from V1.Utilities.math_utils import minmax_normalize
from V1.Utilities.data_loaders import get_history_bor_data

# ---------------------------------------------------------------------------
# HISTORY PENETRATION HELPER (Specific to Stage 1 Logic)
# ---------------------------------------------------------------------------
def _compute_history_penetration(today_bpr: pd.DataFrame, today_bor: pd.DataFrame, date_str: str, n: int) -> pd.Series:
    """
    Compute HistoryPenetrationScore scored INDEPENDENTLY per (SKUCode, Market).

    A SKU in RE and OE gets two separate scores — RE history and OE history
    are computed entirely independently.

    Scoring rules (per market row):
      • 0  : Penetration < BLACK threshold today → score 0
      • 1  : Penetration >= threshold today → at least 1
      • k  : Penetration >= threshold for k consecutive days ending today
      • n  : Max streak (all n days black for this SKU+Market)

    Missing BOR files (weekends/holidays) → streak continues unbroken.
    """
    today = datetime.strptime(date_str, "%d%m%Y")

    def _get_penetrations(bor_df: pd.DataFrame) -> dict:
        if 'Virtual Norm' not in bor_df.columns or 'Stock' not in bor_df.columns:
            return {}
        df = bor_df.copy()
        df['SKUCode'] = df['SKUCode'].astype(str)
        df['_pen'] = np.where(
            df['Virtual Norm'] == 0, 0,
            (df['Virtual Norm'] - df['Stock']) / df['Virtual Norm'] * 100
        )
        if 'Market' not in df.columns:
            df['Market'] = df['Location Code'].str.split('_').str[1].replace(
                {'FG10': 'RE', 'OE10': 'OE', 'ST10': 'ST', 'OTR10': 'OTR'}
            )
        return df.groupby(['SKUCode', 'Market'])['_pen'].max().to_dict()

    today_pens = _get_penetrations(today_bor)
    all_keys   = list(today_pens.keys())   

    day_pens = [today_pens]

    for day_offset in range(1, n):
        past_date = today - timedelta(days=day_offset)
        bor_path  = os.path.join(
            config.BASE_DATA_PATH, 'Vectordata', 'BOR',
            f'BORColorBandwiseReport__{past_date.strftime("%d-%m-%Y")}.csv'
        )

        if not os.path.exists(bor_path):
            day_pens.append({})           # missing day → streak intact
            continue

        try:
            past_bor = pd.read_csv(bor_path)
            past_bor['SKUCode'] = past_bor['SKUCode'].astype(str)
            if 'Location Code' in past_bor.columns:
                past_bor = past_bor[past_bor['Location Code'].str.startswith('1300')]
            day_pens.append(_get_penetrations(past_bor))
        except Exception:
            day_pens.append({})           # unreadable → streak intact

    black_threshold = config.HISTORY_PENETRATION_BLACK
    scores: dict = {}

    for (sku, market) in all_keys:
        if today_pens.get((sku, market), 0.0) < black_threshold:
            scores[(sku, market)] = 0
            continue

        streak = 0
        for day_idx in range(n):
            pen = day_pens[day_idx].get((sku, market), None)
            if pen is None:
                continue          # missing BOR file → skip, streak intact
            if pen < black_threshold:
                break             # below threshold → streak ends
            streak += 1

        scores[(sku, market)] = streak

    return pd.Series(scores, name='HistoryPenetrationScore', dtype=int)


# ---------------------------------------------------------------------------
# MAIN STAGE 1 PROCESSOR
# ---------------------------------------------------------------------------
def run_stage1(date_str: str) -> tuple[pd.DataFrame, list]:
    """
    Executes Stage 1 Demand processing.
    Returns: 
        - The processed Stage 1 DataFrame
        - The historical BOR data list (for later Excel tabs)
    """
    print(f"\n[Stage 1] Processing raw demand signals for {date_str}...")
    date = datetime.strptime(date_str, "%d%m%Y")
    
    # Paths constructed from config
    spor_path = os.path.join(config.BASE_DATA_PATH, 'Vectordata', 'SPOR', f'Single_Production_Order_Report_{date.strftime("%d%m%Y")}.csv')
    bor_path  = os.path.join(config.BASE_DATA_PATH, 'Vectordata', 'BOR', f'BORColorBandwiseReport__{date.strftime("%d-%m-%Y")}.csv')
    bmr_path  = os.path.join(config.BASE_DATA_PATH, 'Vectordata', 'BMR', f'Prod_OverAll_BMReport__{date.strftime("%d_%m_%Y")}.xlsx')
    bpr_path  = os.path.join(config.BASE_DATA_PATH, 'Vectordata', 'BPR', f'BufferPenetrationReport__{date.strftime("%d-%m-%Y")}.csv')

    # SPOR is optional — processing continues without it if it's missing
    mandatory_files = [bor_path, bmr_path, bpr_path]
    if not all(os.path.exists(f) for f in mandatory_files):
        print(f"❌ Error: Missing mandatory files (BOR/BMR/BPR) for {date_str}.")
        return None, []

    if not os.path.exists(spor_path):
        print(f"  [NOTE] SPOR file not found for {date_str} — continuing without it.")

    # Load Data
    bpr_v = pd.read_csv(bpr_path)
    bor_v = pd.read_csv(bor_path)
    bmr_v = pd.read_excel(bmr_path)

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
    bor_v['Adjusted_Target'] = bor_v.apply(
        lambda row: row['Virtual Norm'] * config.NORM_MULTIPLIERS.get(row['Market'], 1.0),
        axis=1
    )
    
    # Requirement = max(0, Adjusted_Target - Stock)
    bor_v['Requirement'] = np.maximum(bor_v['Adjusted_Target'] - bor_v['Stock'], 0)
    
    # Penetration ALWAYS uses 100% Virtual Norm as the baseline (config requirement).
    # This gives a true picture of buffer depletion regardless of market type.
    bor_v['Penetration'] = np.where(
        bor_v['Virtual Norm'] == 0,
        0,
        (bor_v['Virtual Norm'] - bor_v['Stock']) / bor_v['Virtual Norm'] * 100
    )
    bor_v = bor_v.merge(bpr_v[['SKUCode', 'Location Code', 'Top SKU']], on=['SKUCode', 'Location Code'], how='left')

    bmr_v.columns = bmr_v.iloc[0]; bmr_v = bmr_v.drop(index=0).reset_index(drop=True)
    bmr_v = bmr_v[bmr_v['Plant Code'] == '1300'].rename(columns={
        'Item Code':        'SKUCode',
        'Item Description': 'SKU Description',
        'Pending CCR Qty':  'Requirement',
        'BPP':              'Penetration',
    })
    bmr_v['SKUCode'] = bmr_v['SKUCode'].astype(str)  # Ensure string type
    bmr_v['Market'], bmr_v['Top SKU'] = 'EXP', 'T'
    
    # For BMR data (EXP market), Adjusted_Target is not applicable as BMR doesn't have Virtual Norm
    bmr_v['Adjusted_Target'] = np.nan  

    combined = pd.concat([bmr_v, bor_v], ignore_index=True)
    combined = combined[combined['Requirement'] != 0].copy()
    
    # Extract rim size from SKUCode (positions 8:10 = 9th and 10th characters)
    combined['size'] = pd.to_numeric(combined['SKUCode'].str[8:10], errors='coerce').fillna(0).astype('Int64')
    
    # Apply User Params from config
    combined['MarketWeight'] = combined['Market'].map(config.MARKET_WEIGHTS)
    combined['TopSKUFlag'] = combined['Top SKU'].apply(lambda x: 1 if x == 'T' else 0)
    
    combined['NormPenetration'] = minmax_normalize(combined['Penetration'])
    combined['NormRequirement'] = minmax_normalize(combined['Requirement'])

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
    combined = combined.merge(pivoted[['SKUCode', 'InventoryScore']], on='SKUCode', how='left')
    combined['InventoryScore'] = combined['InventoryScore'].fillna(0)  
    combined['NormInventoryScore'] = minmax_normalize(combined['InventoryScore'])

    dispatch = pd.read_csv(os.path.join(config.BASE_DATA_PATH, "DISPATCH1.csv"), encoding='ISO-8859-1')
    dispatch['Amt.in loc.cur.'] = dispatch['Amt.in loc.cur.'].replace({',': ''}, regex=True)
    dispatch['Amt.in loc.cur.'] = pd.to_numeric(dispatch['Amt.in loc.cur.'], errors='coerce')
    dispatch['Quantity'] = pd.to_numeric(dispatch['Quantity'], errors='coerce')
    dispatch['ASP'] = dispatch['Amt.in loc.cur.'] / dispatch['Quantity']

    # --- MARKET-AWARE ASP ---
    # OE market uses OE-channel ASP; all other markets (RE, ST, OTR, EXP) share the RE-channel ASP.
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

    curing = pd.read_csv(os.path.join(config.BASE_DATA_PATH, "curing_cycletime.csv")).sort_values('Cure Time', ascending=False).drop_duplicates('SKUCode')
    combined = combined.merge(curing[['SKUCode', 'Cure Time']], on='SKUCode', how='left')
    combined['Cure Time'] = combined['Cure Time'].fillna(config.DEFAULT_CURE_TIME) + 2.5
    
    combined['daily_cure'] = np.ceil((1440 / combined['Cure Time']) * config.EFFICIENCY_FACTOR).astype(int)
    combined['rev_pot'] = combined['ASP'] * combined['daily_cure']
    combined['PriceScore'] = minmax_normalize(combined['rev_pot'])

    # --- HISTORY PENETRATION SCORING ---
    n_days = config.HISTORY_PENETRATION_N
    history_scores = _compute_history_penetration(bpr_v, bor_v, date_str, n_days)
    _score_dict = history_scores.to_dict()   
    combined['HistoryPenetrationScore'] = [
        _score_dict.get((sku, mkt), 0)
        for sku, mkt in zip(combined['SKUCode'], combined['Market'])
    ]
    combined['HistoryPenetrationScore'] = combined['HistoryPenetrationScore'].astype(int)
    combined['NormHistoryPenetrationScore'] = minmax_normalize(combined['HistoryPenetrationScore'])

    # --- CONSOLIDATED SCORE ---
    combined['ConsolidatedPriorityScore'] = (
        combined['PriorityScore']               * config.CONSOLIDATED_WEIGHTS["demand_priority"] +
        combined['NormInventoryScore']          * config.CONSOLIDATED_WEIGHTS["inventory_priority"] +
        combined['PriceScore']                  * config.CONSOLIDATED_WEIGHTS["price_priority"] +
        combined['NormHistoryPenetrationScore'] * config.CONSOLIDATED_WEIGHTS["history_penetration"]
    )

    # SINGLE RANKING — one consolidated score, one rank
    combined['Rank_ConsolidatedPriorityScore'] = combined['ConsolidatedPriorityScore'].rank(ascending=False, method='min')

    # Sort by consolidated rank
    combined = combined.sort_values(by='Rank_ConsolidatedPriorityScore', ascending=True)

    # Formatting decimal places
    combined['Penetration'] = pd.to_numeric(combined['Penetration'], errors='coerce').round(2)
    if 'ASP' in combined.columns:
        combined['ASP'] = pd.to_numeric(combined['ASP'], errors='coerce').round(2)
    
    for _score_col in ['PriorityScore', 'PriceScore', 'ConsolidatedPriorityScore']:
        if _score_col in combined.columns:
            combined[_score_col] = pd.to_numeric(combined[_score_col], errors='coerce').round(2)

    # SELECT ONLY REQUIRED COLUMNS (matching original output)
    output_columns = [
        'SKUCode', 'SKU Description', 'size',
        'Market', 'Norm ', 'Virtual Norm', 'Adjusted_Target',
        'Stock', 'Requirement', 'Penetration',
        'TopSKUFlag',
        'InventoryScore',
        'ASP', 'Cure Time', 'PriceScore',
        'HistoryPenetrationScore',
        'PriorityScore', 'ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore',
    ]

    available_cols = [col for col in output_columns if col in combined.columns]
    combined = combined[available_cols]

    # Pre-fetch the history BOR data to pass alongside the dataframe
    print(f"  [Stage 1] Loading BOR history for the last {n_days} days...")
    history_bor = get_history_bor_data(date_str, n_days)

    return combined, history_bor