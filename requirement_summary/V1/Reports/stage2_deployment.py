# V1/Reports/stage2_deployment.py
# ---------------------------------------------------------------------------
# STAGE 2: MACHINE DEPLOYMENT ANALYSIS
# Merges Stage 1 demand with Daily Mould Reports to track running machines,
# calculate Proxy Penetration, and identify Ghost SKUs.
# ---------------------------------------------------------------------------

import pandas as pd
import numpy as np
import os
import glob

# Import centralized configuration and tools
from V1.Setups.config import BASE_DATA_PATH
from V1.Utilities.data_loaders import load_oe_demand

# ---------------------------------------------------------------------------
# DEPLOYMENT CONSTANTS (Stage 2 — mould / machine analysis)
# ---------------------------------------------------------------------------
MOULD_REPORT_PATH = os.path.join(BASE_DATA_PATH, "Vectordata", "Daily Mould Report")
MOULD_LIFE_THRESHOLD = 0.9 # Alert when avg mould health exceeds this fraction
MACHINE_COUNT_PENALTY = 0.05 # Priority reduction per running machine (5%)
CRITICAL_GAP_RANK = 50 # Top-N rank threshold for Critical Gap flag
EXCESS_PRODUCTION_RANK = 200 # Below-N rank threshold for Excess Production flag
EXCESS_MACHINE_COUNT = 2 # Min machines to trigger Excess Production flag

# Ghost SKU defaults (running on machines but absent from Vector demand)
GHOST_SKU_REQUIREMENT = 0
GHOST_SKU_PENETRATION = 0
GHOST_SKU_MARKET = "RE"
GHOST_SKU_CURE_TIME = 20.0


def _clean_mould_report(date_str: str) -> pd.DataFrame:
    """Load and clean the mould report for a given date."""
    file_path = os.path.join(MOULD_REPORT_PATH, f"{date_str} MouldDetails.csv")
    
    if not os.path.exists(file_path):
        print(f"  [WARN] Mould report not found for {date_str} at {file_path}")
        return None
        
    try:
        mould_df = pd.read_csv(file_path)
        mould_df['Sapcode'] = mould_df['Sapcode'].astype(str)
        
        # Calculate mould health percentage (Mould life / Target life)
        mould_df['MouldHealth'] = mould_df['Mould life'] / mould_df['Target life']
        
        # Group by SKUCode to handle machines with RH/LH sides
        agg_rules = {'WCNAME': 'nunique', 'MouldHealth': 'mean'}
        if 'Recipe' in mould_df.columns:
            agg_rules['Recipe'] = 'first'
            
        mould_summary = mould_df.groupby('Sapcode').agg(agg_rules).reset_index()
        mould_summary['MouldHealth'] = mould_summary['MouldHealth'].round(2)
        
        rename_map = {'Sapcode': 'SKUCode', 'WCNAME': 'MachineCount', 'MouldHealth': 'AvgMouldHealth'}
        if 'Recipe' in mould_summary.columns:
            rename_map['Recipe'] = 'Mould_Recipe'
            
        mould_summary.rename(columns=rename_map, inplace=True)
        return mould_summary
    except Exception as e:
        print(f"  [ERROR] Processing mould report for {date_str}: {str(e)}")
        return None


def _build_ghost_sku_rows(mould_df: pd.DataFrame, demand_df: pd.DataFrame) -> pd.DataFrame:
    """
    Find SKUs present in the mould report but absent from Vector demand ("Ghost Production").
    Ghost SKUs receive 0 requirement, 0 penetration, and a score below the lowest real SKU.
    """
    demand_skus = set(demand_df['SKUCode'].astype(str))
    ghost_mask = ~mould_df['SKUCode'].isin(demand_skus)
    ghost_mould = mould_df[ghost_mask].copy()

    if ghost_mould.empty:
        return pd.DataFrame()

    # Minimum existing score — ghost rows sit below this
    score_floor = 0.0
    for score_col in ['ConsolidatedPriorityScore']:
        if score_col in demand_df.columns:
            col_min = pd.to_numeric(demand_df[score_col], errors='coerce').min()
            if pd.notna(col_min):
                score_floor = float(col_min)
                break
    ghost_score = score_floor * 0.5 # always below the lowest real SKU

    ghost_rows = pd.DataFrame()
    ghost_rows['SKUCode'] = ghost_mould['SKUCode'].values
    if 'Mould_Recipe' in ghost_mould.columns:
        ghost_rows['SKU Description'] = ghost_mould['Mould_Recipe'].values
    ghost_rows['size'] = pd.to_numeric(ghost_mould['SKUCode'].str[8:10], errors='coerce').fillna(0).astype('Int64').values
    ghost_rows['Market'] = GHOST_SKU_MARKET
    ghost_rows['Requirement'] = GHOST_SKU_REQUIREMENT
    ghost_rows['Vector_Requirement'] = GHOST_SKU_REQUIREMENT
    ghost_rows['Penetration'] = GHOST_SKU_PENETRATION
    ghost_rows['Cure Time'] = GHOST_SKU_CURE_TIME
    ghost_rows['MachineCount'] = ghost_mould['MachineCount'].values
    ghost_rows['AvgMouldHealth'] = ghost_mould['AvgMouldHealth'].values
    ghost_rows['ConsolidatedPriorityScore'] = ghost_score
    ghost_rows['IsGhostSKU'] = True

    print(f"  [Stage 2] Ghost SKUs detected (running but no Vector demand): {len(ghost_rows)}")
    return ghost_rows


def _ghost_sku_oe_correction(df: pd.DataFrame) -> pd.DataFrame:
    """Correct Ghost SKU market from RE → OE if SKU is actively present in oe_demand.csv."""
    if 'IsGhostSKU' not in df.columns:
        return df
    try:
        # Utilize our modular data loader
        oe_dict = load_oe_demand()
        if not oe_dict:
            return df
            
        oe_skus = set(str(k).strip().upper() for k in oe_dict.keys())
        mask = (
            df['IsGhostSKU'].fillna(False).astype(bool) &
            df['SKUCode'].astype(str).str.strip().str.upper().isin(oe_skus)
        )
        n = mask.sum()
        if n > 0:
            df.loc[mask, 'Market'] = 'OE'
            print(f'  [Stage 2] Ghost SKU market RE→OE corrected: {n} SKU(s)')
    except Exception as e:
        print(f'  [WARN] Ghost SKU OE correction failed: {e}')
    return df


def run_stage2(stage1_df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """
    Main orchestration function for Stage 2 deployment analysis.
    Takes the in-memory Stage 1 DataFrame and merges Mould data.
    """
    print(f"\n[Stage 2] Starting deployment analysis for {date_str}...")
    
    mould_df = _clean_mould_report(date_str)
    
    # Merge demand with deployment data
    stage1_df['IsGhostSKU'] = False
    
    if mould_df is None or mould_df.empty:
        stage1_df['MachineCount']  = 0
        stage1_df['AvgMouldHealth']= 0.0
        merged_df = stage1_df
    else:
        stage1_df['SKUCode'] = stage1_df['SKUCode'].astype(str)
        merged_df = stage1_df.merge(mould_df, on='SKUCode', how='left')
        merged_df['MachineCount']  = merged_df['MachineCount'].fillna(0).astype(int)
        merged_df['AvgMouldHealth']= merged_df['AvgMouldHealth'].fillna(0.0)

        if 'Mould_Recipe' in merged_df.columns:
            has_recipe = merged_df['Mould_Recipe'].notna()
            if 'SKU Description' not in merged_df.columns:
                merged_df['SKU Description'] = np.nan
            merged_df.loc[has_recipe, 'SKU Description'] = merged_df.loc[has_recipe, 'Mould_Recipe']
            merged_df.drop(columns=['Mould_Recipe'], inplace=True)

        ghost_df = _build_ghost_sku_rows(mould_df, stage1_df)
        if not ghost_df.empty:
            merged_df = pd.concat([merged_df, ghost_df], ignore_index=True, sort=False)

    # Correct Ghost SKU Markets using OE Demand
    merged_df = _ghost_sku_oe_correction(merged_df)

    # Calculate Proxy Penetration
    penalty_factor = (1 - (merged_df['MachineCount'] * MACHINE_COUNT_PENALTY)).clip(lower=0)
    merged_df['ProxyPenetration'] = (merged_df['ConsolidatedPriorityScore'] * penalty_factor).round(2)
    merged_df['ProxyRank'] = merged_df['ProxyPenetration'].rank(ascending=False, method='min').astype(int)
    
    # Apply Gap Flags
    rank_col = 'Rank_ConsolidatedPriorityScore' if 'Rank_ConsolidatedPriorityScore' in merged_df.columns else 'ProxyRank'
    merged_df['CriticalGap'] = ((merged_df[rank_col] <= CRITICAL_GAP_RANK) & (merged_df['MachineCount'] == 0))
    merged_df['ExcessProduction'] = ((merged_df[rank_col] > EXCESS_PRODUCTION_RANK) & (merged_df['MachineCount'] > EXCESS_MACHINE_COUNT))
    merged_df['MouldAlert'] = merged_df['AvgMouldHealth'] > MOULD_LIFE_THRESHOLD
    
    print(f"  - Critical Gaps      : {merged_df['CriticalGap'].sum()}")
    print(f"  - Excess Production  : {merged_df['ExcessProduction'].sum()}")
    print(f"  - Mould Alerts       : {merged_df['MouldAlert'].sum()}")

    # Sort and return
    merged_df = merged_df.sort_values('ConsolidatedPriorityScore', ascending=False).reset_index(drop=True)
    merged_df['Final Rank'] = merged_df.index + 1

    return merged_df