# demand_processor.py
import pandas as pd
import numpy as np
import os
from datetime import datetime
import config # Import the settings



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

    pivoted['PriorityScore_Inventory'] = 0
    for loc, weight in config.LOCATION_WEIGHTS.items():
        b_col, r_col = f'Black Count_{loc}', f'Red Count_{loc}'
        if b_col in pivoted.columns:
            pivoted['PriorityScore_Inventory'] += pivoted[b_col] * weight * config.INVENTORY_SCORE_FACTORS["black"]
        if r_col in pivoted.columns:
            pivoted['PriorityScore_Inventory'] += pivoted[r_col] * weight * config.INVENTORY_SCORE_FACTORS["red"]

    # --- DEMAND SCORING (BOR & BMR) ---
    bor_v = bor_v[bor_v['Location Code'].str.startswith('1300')].copy()
    bor_v['Market'] = bor_v['Location Code'].str.split('_').str[1].replace({'FG10': 'RE', 'OE10': 'OE', 'ST10': 'ST'})
    bor_v['Market'] = bor_v['Market'].astype(str)  # Ensure string type
    
    # --- STRATEGIC NORM ADJUSTMENT ---
    # Adjusted_Target drives Requirement:
    #   RE market: 50% of Virtual Norm (conservative target)
    #   OE / EXP:  100% of Virtual Norm
    bor_v['Adjusted_Target'] = bor_v.apply(
        lambda row: row['Virtual Norm'] * 0.5 if row['Market'] == 'RE' else row['Virtual Norm'],
        axis=1
    )
    
    # Requirement = max(0, Adjusted_Target - Stock)
    # RE gets 50% virtual norm target; OE/EXP get full virtual norm target
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
    
    combined['NormPenetration'] = combined['Penetration'] / combined['Penetration'].max()
    combined['NormRequirement'] = combined['Requirement'] / combined['Requirement'].max()

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
    combined = combined.merge(pivoted[['SKUCode', 'PriorityScore_Inventory']], on='SKUCode', how='left').fillna(0)
    combined['NormInventoryScore'] = combined['PriorityScore_Inventory'] / combined['PriorityScore_Inventory'].max()

    dispatch = pd.read_csv(f"{config.BASE_DATA_PATH}/DISPATCH1.csv", encoding='ISO-8859-1')
    dispatch['Amt.in loc.cur.'] = dispatch['Amt.in loc.cur.'].replace({',': ''}, regex=True)
    dispatch['Amt.in loc.cur.'] = pd.to_numeric(dispatch['Amt.in loc.cur.'], errors='coerce')
    dispatch['Quantity'] = pd.to_numeric(dispatch['Quantity'], errors='coerce')
    dispatch['ASP'] = dispatch['Amt.in loc.cur.'] / dispatch['Quantity']
    asp_map = dispatch[dispatch['Plant'] == 1300].groupby(['Material'])['ASP'].mean()
    combined['ASP'] = combined['SKUCode'].map(asp_map).fillna(config.DEFAULT_ASP)

    curing = pd.read_csv(f"{config.BASE_DATA_PATH}/curing_cycletime.csv").sort_values('Cure Time', ascending=False).drop_duplicates('SKUCode')
    combined = combined.merge(curing[['SKUCode', 'Cure Time']], on='SKUCode', how='left')
    combined['Cure Time'] = combined['Cure Time'].fillna(config.DEFAULT_CURE_TIME) + 2.5
    
    combined['daily_cure'] = np.ceil((1440 / combined['Cure Time']) * config.EFFICIENCY_FACTOR).astype(int)
    combined['rev_pot'] = combined['ASP'] * combined['daily_cure']
    combined['price_priority'] = combined['rev_pot'] / combined['rev_pot'].max()

    # CONSOLIDATED SCORE (Demand + Inventory + Price)
    # Weights are fully configurable. Set price_priority = 0 for pure Demand+Inventory scoring.
    combined['ConsolidatedPriorityScore'] = (
        combined['PriorityScore'] * config.CONSOLIDATED_WEIGHTS["demand_priority"] +
        combined['NormInventoryScore'] * config.CONSOLIDATED_WEIGHTS["inventory_priority"] +
        combined['price_priority'] * config.CONSOLIDATED_WEIGHTS["price_priority"]
    )

    # SINGLE RANKING — one consolidated score, one rank
    combined['Rank_ConsolidatedPriorityScore'] = combined['ConsolidatedPriorityScore'].rank(ascending=False, method='min')

    # Sort by consolidated rank
    combined = combined.sort_values(by='Rank_ConsolidatedPriorityScore', ascending=True)

    # SELECT ONLY REQUIRED COLUMNS (matching original output)
    # Columns ordered to tell a clear left-to-right story:
    # Group 1: Identification (Who)
    # Group 2: Targets (Goal)
    # Group 3: Demand Signals (How urgent?)
    # Group 4: Market & SKU Attributes (Context)
    # Group 5: Inventory Signals (Stock health)
    # Group 6: Revenue & Efficiency (Value)
    # Group 7: Scoring & Ranking (Final verdict)
    output_columns = [
        # --- Group 1: Identification ---
        'SKUCode', 'SKU Description', 'size',

        # --- Group 2: Targets ---
        'Market', 'Norm ', 'Virtual Norm', 'Adjusted_Target',

        # --- Group 3: Demand Signals ---
        'Stock', 'Requirement', 'Penetration',
        'NormPenetration', 'NormRequirement',

        # --- Group 4: Market & SKU Attributes ---
        'Top SKU', 'TopSKUFlag', 'MarketWeight', 'priority',

        # --- Group 5: Inventory Signals ---
        'PriorityScore_Inventory', 'NormInventoryScore',

        # --- Group 6: Revenue & Efficiency ---
        'ASP', 'Cure Time', 'daily_cure', 'rev_pot', 'price_priority',

        # --- Group 7: Scoring & Ranking ---
        'PriorityScore',
        'ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore',
    ]
    
    # Only select columns that exist
    available_cols = [col for col in output_columns if col in combined.columns]
    combined = combined[available_cols]
    
    return combined