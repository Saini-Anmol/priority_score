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
        if b_col in pivoted.columns: pivoted['PriorityScore_Inventory'] += pivoted[b_col] * weight
        if r_col in pivoted.columns: pivoted['PriorityScore_Inventory'] += pivoted[r_col] * (weight * 0.5)

    # --- DEMAND SCORING (BOR & BMR) ---
    bor_v = bor_v[bor_v['Location Code'].str.startswith('1300')].copy()
    bor_v['Market'] = bor_v['Location Code'].str.split('_').str[1].replace({'FG10': 'RE', 'OE10': 'OE', 'ST10': 'ST'})
    bor_v['Market'] = bor_v['Market'].astype(str)  # Ensure string type
    bor_v['Penetration'] = np.where(bor_v['Virtual Norm'] == 0, 0, (bor_v['Virtual Norm'] - bor_v['Stock']) / bor_v['Virtual Norm'] * 100)
    bor_v = bor_v.merge(bpr_v[['SKUCode', 'Location Code', 'Top SKU']], on=['SKUCode', 'Location Code'], how='left')

    bmr_v.columns = bmr_v.iloc[0]; bmr_v = bmr_v.drop(index=0).reset_index(drop=True)
    bmr_v = bmr_v[bmr_v['Plant Code'] == '1300'].rename(columns={'Item Code': 'SKUCode', 'Pending CCR Qty': 'Requirement', 'BPP': 'Penetration'})
    bmr_v['SKUCode'] = bmr_v['SKUCode'].astype(str)  # Ensure string type
    bmr_v['Market'], bmr_v['Top SKU'] = 'EXP', 'T'

    combined = pd.concat([bmr_v, bor_v], ignore_index=True)
    combined = combined[combined['Requirement'] != 0].copy()
    
    # Apply User Params from config
    combined['MarketWeight'] = combined['Market'].map(config.MARKET_WEIGHTS)
    combined['MarketPriority'] = combined['Market'].map(config.MARKET_PRIORITY)
    combined['TopSKUFlag'] = combined['Top SKU'].apply(lambda x: 1 if x == 'T' else 0)
    
    combined['NormPenetration'] = combined['Penetration'] / combined['Penetration'].max()
    combined['NormRequirement'] = combined['Requirement'] / combined['Requirement'].max()

    # Generate priority tuple (for sorting compatibility with original)
    combined['priority'] = combined.apply(
        lambda row: (row['MarketPriority'], -row['Penetration'], -row['Requirement'], -row['TopSKUFlag']), 
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

    # TIER 1 CONSOLIDATED SCORE (Demand + Inventory only)
    combined['ConsolidatedPriorityScore'] = (
        combined['PriorityScore'] * config.TIER1_WEIGHTS["demand_priority"] +
        combined['NormInventoryScore'] * config.TIER1_WEIGHTS["inventory_priority"]
    )

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

    # TIER 2 CONSOLIDATED SCORE (Demand + Inventory + Price)
    combined['ConsolidatedPriorityScore_p'] = (
        combined['PriorityScore'] * config.TIER2_WEIGHTS["demand_priority"] +
        combined['NormInventoryScore'] * config.TIER2_WEIGHTS["inventory_priority"] +
        combined['price_priority'] * config.TIER2_WEIGHTS["price_priority"]
    )

    # DUAL RANKING SYSTEM (matching original script)
    combined['Rank_ConsolidatedPriorityScore'] = combined['ConsolidatedPriorityScore'].rank(ascending=False, method='min')
    combined['Rank_ConsolidatedPriorityScore_p'] = combined['ConsolidatedPriorityScore_p'].rank(ascending=False, method='min')

    # Sort by both ranks (matching original)
    combined = combined.sort_values(by=['Rank_ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore_p'], ascending=[True, True])

    # SELECT ONLY REQUIRED COLUMNS (matching original output)
    output_columns = [
        'SKUCode', 'SKU Description', 'Market', 'Penetration', 'Requirement', 
        'Norm ', 'Virtual Norm', 'Stock', 'Top SKU', 'MarketPriority', 'TopSKUFlag', 'priority', 'MarketWeight', 
        'NormPenetration', 'NormRequirement', 'PriorityScore',
        'PriorityScore_Inventory', 'NormInventoryScore',
        'ConsolidatedPriorityScore', 'ASP', 'Cure Time', 'daily_cure',
        'rev_pot', 'price_priority', 'ConsolidatedPriorityScore_p',
        'Rank_ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore_p'
    ]
    
    # Only select columns that exist
    available_cols = [col for col in output_columns if col in combined.columns]
    combined = combined[available_cols]
    
    return combined