# test_stage2.py
# Test script for Stage 2 deployment analysis

import pandas as pd
from datetime import datetime
from demand_processor import process_single_date
from deployment_processor import (
    clean_mould_report,
    merge_demand_with_deployment,
    calculate_proxy_penetration,
    apply_gap_flags
)

def test_stage2_pipeline():
    """
    Test the Stage 2 pipeline with a known date.
    """
    print("=" * 80)
    print("STAGE 2 DEPLOYMENT ANALYSIS - TEST SUITE")
    print("=" * 80)
    
    test_date = "02012026"  # Known date with complete data files
    
    print(f"\nTest Date: {test_date}")
    print("-" * 80)
    
    # ========================================================================
    # TEST 1: Mould Report Loading
    # ========================================================================
    print("\n[TEST 1] Mould Report Loading and Cleaning")
    print("-" * 40)
    
    mould_df = clean_mould_report(test_date)
    
    if mould_df is not None and not mould_df.empty:
        print(f"✓ Successfully loaded mould report")
        print(f"  - SKUs found: {len(mould_df)}")
        print(f"  - Columns: {list(mould_df.columns)}")
        print(f"\nSample data:")
        print(mould_df.head())
    else:
        print("✗ Failed to load mould report")
        return
    
    # ========================================================================
    # TEST 2: Stage 1 Processing
    # ========================================================================
    print("\n[TEST 2] Stage 1 Demand Processing")
    print("-" * 40)
    
    demand_df = process_single_date(test_date)
    
    if demand_df is not None and not demand_df.empty:
        print(f"✓ Successfully processed Stage 1")
        print(f"  - SKUs found: {len(demand_df)}")
        print(f"  - Has ConsolidatedPriorityScore: {'ConsolidatedPriorityScore' in demand_df.columns}")
    else:
        print("✗ Failed to process Stage 1")
        return
    
    # ========================================================================
    # TEST 3: Master Join
    # ========================================================================
    print("\n[TEST 3] Master Join (Demand + Mould)")
    print("-" * 40)
    
    merged_df = merge_demand_with_deployment(demand_df, mould_df)
    
    if not merged_df.empty:
        print(f"✓ Successfully merged datasets")
        print(f"  - Total SKUs: {len(merged_df)}")
        print(f"  - SKUs with machines: {(merged_df['MachineCount'] > 0).sum()}")
        print(f"  - SKUs without machines: {(merged_df['MachineCount'] == 0).sum()}")
    else:
        print("✗ Join resulted in empty dataframe")
        return
    
    # ========================================================================
    # TEST 4: Proxy Penetration Calculation
    # ========================================================================
    print("\n[TEST 4] Proxy Penetration Calculation")
    print("-" * 40)
    
    merged_df = calculate_proxy_penetration(merged_df)
    
    if 'ProxyPenetration' in merged_df.columns and 'ProxyRank' in merged_df.columns:
        print(f"✓ Proxy Penetration calculated")
        print(f"  - Range: {merged_df['ProxyPenetration'].min():.4f} to {merged_df['ProxyPenetration'].max():.4f}")
        print(f"\nSample comparison (Top 5):")
        sample = merged_df[['SKUCode', 'MachineCount', 'ConsolidatedPriorityScore', 'ProxyPenetration', 'ProxyRank']].head()
        print(sample.to_string(index=False))
    else:
        print("✗ Failed to calculate Proxy Penetration")
        return
    
    # ========================================================================
    # TEST 5: Gap Analysis Flags
    # ========================================================================
    print("\n[TEST 5] Gap Analysis Flags")
    print("-" * 40)
    
    merged_df = apply_gap_flags(merged_df)
    
    critical_gaps = merged_df['CriticalGap'].sum()
    excess_production = merged_df['ExcessProduction'].sum()
    mould_alerts = merged_df['MouldAlert'].sum()
    
    print(f"✓ Gap flags applied")
    print(f"  - Critical Gaps: {critical_gaps}")
    print(f"  - Excess Production: {excess_production}")
    print(f"  - Mould Alerts: {mould_alerts}")
    
    if critical_gaps > 0:
        print(f"\nCritical Gap Examples:")
        gaps = merged_df[merged_df['CriticalGap']][['SKUCode', 'Rank_ConsolidatedPriorityScore', 'MachineCount']].head(5)
        print(gaps.to_string(index=False))
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print("✓ All tests passed successfully!")
    print(f"\nFinal Dataset Shape: {merged_df.shape}")
    print(f"Columns: {len(merged_df.columns)}")
    print("\nStage 2 pipeline is ready for production use.")
    print("=" * 80)


if __name__ == "__main__":
    test_stage2_pipeline()
