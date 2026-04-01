# deployment_processor.py
# Stage 3: Machine Deployment Analysis Processing Engine
#
# This module is self-contained — it does NOT import from config_stage2
# (which is Stage 2's frontend config). All deployment constants are
# defined locally below and can be tuned here directly.

import pandas as pd
import numpy as np
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# DEPLOYMENT CONSTANTS  (Stage 3 — mould / machine analysis)
# ---------------------------------------------------------------------------
BASE_DATA_PATH     = "./data"
MOULD_REPORT_PATH  = os.path.join(BASE_DATA_PATH, "Vectordata", "Daily Mould Report")

MOULD_LIFE_THRESHOLD   = 0.9    # Alert when avg mould health exceeds this fraction
MACHINE_COUNT_PENALTY  = 0.05  # Priority reduction per running machine
CRITICAL_GAP_RANK      = 50    # Top-N rank threshold for Critical Gap flag
EXCESS_PRODUCTION_RANK = 200   # Below-N rank threshold for Excess Production flag
EXCESS_MACHINE_COUNT   = 2     # Min machines to trigger Excess Production flag

# Ghost SKU defaults (running on machines but absent from Vector demand)
GHOST_SKU_REQUIREMENT = 0
GHOST_SKU_PENETRATION = 0
GHOST_SKU_MARKET      = "RE"
GHOST_SKU_CURE_TIME   = 20.0

def clean_mould_report(date_str):
    """
    Load and clean the mould report for a given date.
    
    Args:
        date_str (str): Date in format DDMMYYYY
    
    Returns:
        pd.DataFrame: Cleaned mould data with SKUCode, MachineCount, AvgMouldHealth
    """
    # Construct the file path
    # Format: DDMMYYYY MouldDetails.csv
    file_path = os.path.join(MOULD_REPORT_PATH, f"{date_str} MouldDetails.csv")
    
    if not os.path.exists(file_path):
        print(f"Warning: Mould report not found for {date_str}")
        return None
    
    try:
        # Load the mould report
        mould_df = pd.read_csv(file_path)
        
        # Ensure SKUCode is string type for joining
        mould_df['Sapcode'] = mould_df['Sapcode'].astype(str)
        
        # Calculate mould health percentage (Mould life / Target life)
        mould_df['MouldHealth'] = mould_df['Mould life'] / mould_df['Target life']
        
        # Group by SKUCode to handle machines with RH/LH sides
        # WCNAME represents the physical machine, but we count per SKU
        # Each WCNAME+Side combination is one production unit, so we count unique WCNAME values
        agg_rules = {
            'WCNAME': 'nunique',   # Count unique machines running this SKU
            'MouldHealth': 'mean'  # Average mould health across all machines
        }
        if 'Recipe' in mould_df.columns:
            agg_rules['Recipe'] = 'first'
            
        mould_summary = mould_df.groupby('Sapcode').agg(agg_rules).reset_index()
        mould_summary['MouldHealth'] = mould_summary['MouldHealth'].round(2)

        
        # Rename columns for clarity
        rename_map = {
            'Sapcode': 'SKUCode',
            'WCNAME': 'MachineCount',
            'MouldHealth': 'AvgMouldHealth'
        }
        if 'Recipe' in mould_summary.columns:
            rename_map['Recipe'] = 'Mould_Recipe'
            
        mould_summary.rename(columns=rename_map, inplace=True)
        
        return mould_summary
    
    except Exception as e:
        print(f"Error processing mould report for {date_str}: {str(e)}")
        return None


def _build_ghost_sku_rows(mould_df: pd.DataFrame, demand_df: pd.DataFrame) -> pd.DataFrame:
    """
    Full Outer Join — Stage 2 half:
    Find SKUs present in the mould report but absent from Vector demand
    ("Ghost Production") and return them as rows with imputed defaults.

    Ghost SKUs receive:
    - Requirement / Vector_Requirement = 0  (no active demand)
    - Penetration                       = 0
    - Market                            = GHOST_SKU_MARKET
    - IsGhostSKU                        = True
    - ConsolidatedPriorityScore(_p)     = min(existing) * 0.5
      → guaranteed below every real SKU without hardcoding
    """
    demand_skus = set(demand_df['SKUCode'].astype(str))
    ghost_mask  = ~mould_df['SKUCode'].isin(demand_skus)
    ghost_mould = mould_df[ghost_mask].copy()

    if ghost_mould.empty:
        return pd.DataFrame()

    # Minimum existing score — ghost rows sit below this
    score_floor = 0.0
    for score_col in ['ConsolidatedPriorityScore_p', 'ConsolidatedPriorityScore']:
        if score_col in demand_df.columns:
            col_min = pd.to_numeric(demand_df[score_col], errors='coerce').min()
            if pd.notna(col_min):
                score_floor = float(col_min)
                break
    ghost_score = score_floor * 0.5  # always below the lowest real SKU

    ghost_rows = pd.DataFrame()
    ghost_rows['SKUCode']                    = ghost_mould['SKUCode'].values
    if 'Mould_Recipe' in ghost_mould.columns:
        ghost_rows['SKU Description']        = ghost_mould['Mould_Recipe'].values
    ghost_rows['size']                       = pd.to_numeric(
        ghost_mould['SKUCode'].str[8:10], errors='coerce').fillna(0).astype('Int64').values
    ghost_rows['Market']                     = GHOST_SKU_MARKET
    ghost_rows['Requirement']                = GHOST_SKU_REQUIREMENT
    ghost_rows['Vector_Requirement']         = GHOST_SKU_REQUIREMENT
    ghost_rows['Penetration']                = GHOST_SKU_PENETRATION
    ghost_rows['Cure Time']                  = GHOST_SKU_CURE_TIME
    ghost_rows['MachineCount']               = ghost_mould['MachineCount'].values
    ghost_rows['AvgMouldHealth']             = ghost_mould['AvgMouldHealth'].values
    ghost_rows['ConsolidatedPriorityScore']  = ghost_score
    ghost_rows['IsGhostSKU']                 = True

    print(f"[Stage 2] Ghost SKUs detected (running but no Vector demand): {len(ghost_rows)}")
    return ghost_rows


def merge_demand_with_deployment(demand_df, mould_df):
    """
    Full Outer Join equivalent between Demand Summary and Mould Report.

    - All demand SKUs are included (left join for mould metrics).
    - Ghost SKUs (in mould but not in demand) are appended with imputed
      defaults so factory operations have 100% visibility.

    Args:
        demand_df (pd.DataFrame): Output from Stage 1 (Demand Summary)
        mould_df  (pd.DataFrame): Cleaned mould data

    Returns:
        pd.DataFrame: Combined dataframe with full deployment visibility
    """
    # Tag all real demand rows as non-ghost
    demand_df['IsGhostSKU'] = False

    if mould_df is None or mould_df.empty:
        demand_df['MachineCount']  = 0
        demand_df['AvgMouldHealth']= 0
        return demand_df

    # Ensure SKUCode is string type
    demand_df['SKUCode'] = demand_df['SKUCode'].astype(str)

    # Left join: bring mould metrics onto demand rows
    merged_df = demand_df.merge(mould_df, on='SKUCode', how='left')
    merged_df['MachineCount']  = merged_df['MachineCount'].fillna(0).astype(int)
    merged_df['AvgMouldHealth']= merged_df['AvgMouldHealth'].fillna(0)

    # Overwrite SKU description with Recipe from daily mould report if available
    if 'Mould_Recipe' in merged_df.columns:
        has_recipe = merged_df['Mould_Recipe'].notna()
        if 'SKU Description' not in merged_df.columns:
            merged_df['SKU Description'] = np.nan
        merged_df.loc[has_recipe, 'SKU Description'] = merged_df.loc[has_recipe, 'Mould_Recipe']
        merged_df.drop(columns=['Mould_Recipe'], inplace=True)

    # Append Ghost SKU rows (full outer join — right-side orphans)
    ghost_df = _build_ghost_sku_rows(mould_df, demand_df)
    if not ghost_df.empty:
        merged_df = pd.concat([merged_df, ghost_df], ignore_index=True, sort=False)

    return merged_df


def calculate_proxy_penetration(df):
    """
    Calculate Proxy Penetration based on machine count.
    
    Logic: SKUs already running on multiple machines get a priority adjustment
    Formula: ProxyPenetration = ConsolidatedPriorityScore * (1 - (MachineCount * penalty))
    
    Args:
        df (pd.DataFrame): Merged dataframe with MachineCount
    
    Returns:
        pd.DataFrame: Dataframe with ProxyPenetration and ProxyRank columns
    """
    # Calculate the adjustment factor
    # More machines = lower urgency (already in production)
    penalty_factor = 1 - (df['MachineCount'] * MACHINE_COUNT_PENALTY)
    
    # Ensure penalty doesn't go negative
    penalty_factor = penalty_factor.clip(lower=0)
    
    # Calculate Proxy Penetration (rounded to 2 decimal places)
    df['ProxyPenetration'] = (df['ConsolidatedPriorityScore'] * penalty_factor).round(2)
    
    # Create new ranking based on Proxy Penetration
    df['ProxyRank'] = df['ProxyPenetration'].rank(ascending=False, method='min').astype(int)
    
    return df


def apply_gap_flags(df):
    """
    Apply gap analysis flags to identify critical issues.
    
    Flags:
    - CriticalGap: High-priority SKUs not being manufactured
    - ExcessProduction: Low-priority SKUs using many machines
    - MouldAlert: Moulds nearing end of life
    
    Args:
        df (pd.DataFrame): Dataframe with deployment metrics
    
    Returns:
        pd.DataFrame: Dataframe with gap analysis flags
    """
    # Use Rank_ConsolidatedPriorityScore (from Stage 1) for gap analysis
    rank_col = 'Rank_ConsolidatedPriorityScore' if 'Rank_ConsolidatedPriorityScore' in df.columns else 'ProxyRank'
    
    # Critical Gap: High-priority SKU with no machines
    df['CriticalGap'] = (
        (df[rank_col] <= CRITICAL_GAP_RANK) & 
        (df['MachineCount'] == 0)
    )
    
    # Excess Production: Low-priority SKU with many machines
    df['ExcessProduction'] = (
        (df[rank_col] > EXCESS_PRODUCTION_RANK) & 
        (df['MachineCount'] > EXCESS_MACHINE_COUNT)
    )
    
    # Mould Alert: Mould life exceeds threshold
    df['MouldAlert'] = df['AvgMouldHealth'] > MOULD_LIFE_THRESHOLD
    
    return df


def process_deployment_analysis(demand_df, date_str):
    """
    Main orchestration function for Stage 2 deployment analysis.
    
    Args:
        demand_df (pd.DataFrame): Output from Stage 1 processing
        date_str (str): Date in format DDMMYYYY
    
    Returns:
        pd.DataFrame: Complete deployment analysis with all metrics
    """
    print(f"[Stage 2] Starting deployment analysis for {date_str}")
    
    # Step 1: Load and clean mould report
    print("[Stage 2] Loading mould report...")
    mould_df = clean_mould_report(date_str)
    
    if mould_df is not None:
        print(f"[Stage 2] Found {len(mould_df)} SKUs in mould report")
    
    # Step 2: Merge demand with deployment data
    print("[Stage 2] Merging demand with deployment data...")
    merged_df = merge_demand_with_deployment(demand_df, mould_df)
    
    # Step 3: Calculate Proxy Penetration
    print("[Stage 2] Calculating Proxy Penetration...")
    merged_df = calculate_proxy_penetration(merged_df)
    
    # Step 4: Apply gap analysis flags
    print("[Stage 2] Applying gap analysis flags...")
    merged_df = apply_gap_flags(merged_df)
    
    # Summary statistics
    critical_gaps    = merged_df['CriticalGap'].sum()
    excess_production= merged_df['ExcessProduction'].sum()
    mould_alerts     = merged_df['MouldAlert'].sum()
    ghost_skus       = merged_df['IsGhostSKU'].sum() if 'IsGhostSKU' in merged_df.columns else 0

    print(f"[Stage 2] Analysis complete:")
    print(f"  - Critical Gaps      : {critical_gaps}")
    print(f"  - Excess Production  : {excess_production}")
    print(f"  - Mould Alerts       : {mould_alerts}")
    print(f"  - Ghost SKUs (running, no demand): {ghost_skus}")

    # --- DATA IMPUTATION: fill missing numeric values with 0 ---
    # Ghost SKUs (and any other unmatched rows) will have NaN for demand/inventory
    # columns that couldn't be populated. Zero is the correct sentinel: no demand,
    # no stock, no score — which naturally keeps them at the bottom of any sort.
    _NUMERIC_FILL_ZERO = [
        'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
        'Requirement', 'Vector_Requirement', 'CPT_Requirement',
        'Penetration', 'NormPenetration', 'NormRequirement',
        'PriorityScore_Inventory', 'NormInventoryScore',
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',
        'PriorityScore',
        'ConsolidatedPriorityScore',
        'ProxyPenetration', 'ProxyRank',
        'ASP', 'daily_cure', 'rev_pot', 'price_priority',
        'MarketWeight', 'TopSKUFlag',
    ]
    for col in _NUMERIC_FILL_ZERO:
        if col in merged_df.columns:
            merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)

    # SELECT & ORDER OUTPUT COLUMNS — logical left-to-right narrative
    output_columns = [
        # --- Group 1: Identification ---
        'SKUCode', 'SKU Description', 'size',

        # --- Group 2: Targets ---
        'Market', 'Norm ', 'Virtual Norm', 'Adjusted_Target',

        # --- Group 3: Demand Signals ---
        'Stock', 'Requirement', 'Penetration',
        'NormPenetration', 'NormRequirement',

        # --- Group 4: SKU Attributes ---
        'TopSKUFlag', 'MarketWeight', 'priority',

        # --- Group 5: Inventory Signals ---
        'PriorityScore_Inventory', 'NormInventoryScore',

        # --- Group 5b: History Penetration ---
        'HistoryPenetrationScore', 'NormHistoryPenetrationScore',

        # --- Group 6: Deployment Metrics & Gap Flags ---
        'MachineCount', 'AvgMouldHealth',
        'ProxyPenetration', 'ProxyRank',
        'CriticalGap', 'ExcessProduction', 'MouldAlert', 'IsGhostSKU',

        # --- Group 7: Revenue & Efficiency ---
        'ASP', 'Cure Time', 'daily_cure', 'rev_pot', 'price_priority',

        # --- Group 8: Scoring & Ranking ---
        'InventoryScore', 'PriceScore',      # renamed equivalents (Stage 1 output names)
        'PriorityScore',
        'ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore',

    ]

    # Only include columns that actually exist in this run
    available_cols = [col for col in output_columns if col in merged_df.columns]
    return merged_df[available_cols]
