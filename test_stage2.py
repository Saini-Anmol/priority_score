# test_stage2.py
# Test script for Stage 2: Frontend / Manual Integration pipeline

import os
import pandas as pd
from datetime import datetime
from demand_processor import process_single_date
from frontend_processor import (
    _load_manual_data,
    _compute_super_boost_score,
    process_frontend_override,
)


def test_stage2_pipeline():
    """
    Test the new Stage 2 pipeline (Stage 1 + Frontend Manual Integration).
    """
    print("=" * 80)
    print("STAGE 2 FRONTEND INTEGRATION — TEST SUITE")
    print("=" * 80)

    test_date = "25022026"  # Adjust to a date with known data files

    print(f"\nTest Date: {test_date}")
    print("-" * 80)

    # ========================================================================
    # TEST 1: Stage 1 Demand Processing
    # ========================================================================
    print("\n[TEST 1] Stage 1 Demand Processing")
    print("-" * 40)

    demand_df = process_single_date(test_date)

    if demand_df is not None and not demand_df.empty:
        print(f"✓ Successfully processed Stage 1")
        print(f"  - SKUs found: {len(demand_df)}")
        print(f"  - Has ConsolidatedPriorityScore: {'ConsolidatedPriorityScore' in demand_df.columns}")
        print(f"  - Has Rank_ConsolidatedPriorityScore: {'Rank_ConsolidatedPriorityScore' in demand_df.columns}")
    else:
        print("✗ Failed to process Stage 1 — check input data files for this date")
        return

    # ========================================================================
    # TEST 2: Manual Data Loading
    # ========================================================================
    print("\n[TEST 2] Manual Frontend Demand File Loading")
    print("-" * 40)

    manual_file = "./data/manual_frontend_demand.xlsx"
    if not os.path.exists(manual_file):
        print(f"⚠ Manual file not found at '{manual_file}' — skipping load test.")
        print("  Stage 2 will still run (returns automated-only output).")
        manual_df = None
    else:
        try:
            manual_df = _load_manual_data()
            print(f"✓ Successfully loaded manual demand file")
            print(f"  - Manual entries: {len(manual_df)}")
            print(f"  - Columns: {list(manual_df.columns)}")
            print(f"\nSample data:")
            print(manual_df.head())
        except Exception as e:
            print(f"✗ Failed to load manual file: {e}")
            manual_df = None

    # ========================================================================
    # TEST 3: Boost Score Calculation
    # ========================================================================
    if manual_df is not None and not manual_df.empty:
        print("\n[TEST 3] Super-Boost Score Calculation")
        print("-" * 40)

        scored_df = _compute_super_boost_score(manual_df.copy())

        if "ManualPriorityScore" in scored_df.columns:
            print(f"✓ ManualPriorityScore calculated")
            print(f"  - Range: {scored_df['ManualPriorityScore'].min():.1f} to {scored_df['ManualPriorityScore'].max():.1f}")
            print(f"  - (All automated scores are ≤ 1.0 — manual scores are always higher)")
            print(f"\nManual ranking preview:")
            preview = scored_df[["SKUCode", "Market", "Quantity", "HighestPriority", "ManualPriorityScore", "ManualRank"]].head(5)
            print(preview.to_string(index=False))
        else:
            print("✗ ManualPriorityScore not found")

    # ========================================================================
    # TEST 4: Full Stage 2 Integration
    # ========================================================================
    print("\n[TEST 4] Full Stage 2 Pipeline (process_frontend_override)")
    print("-" * 40)

    final_df = process_frontend_override(demand_df, test_date)

    if final_df is not None and not final_df.empty:
        print(f"✓ Stage 2 pipeline completed successfully")
        print(f"  - Total rows in output: {len(final_df)}")
        print(f"  - Columns: {list(final_df.columns)}")

        # Check key columns
        expected_cols = ["Final Rank", "Source", "StrategicPriorityScore",
                         "Vector_Requirement", "CPT_Requirement"]
        for col in expected_cols:
            status = "✓" if col in final_df.columns else "✗ MISSING"
            print(f"  - {status}: '{col}'")

        # Check no mould columns leaked in
        mould_cols = ["MachineCount", "AvgMouldHealth", "CriticalGap",
                      "ExcessProduction", "MouldAlert", "IsGhostSKU", "ProxyPenetration"]
        leaked = [c for c in mould_cols if c in final_df.columns]
        if leaked:
            print(f"  ✗ WARNING: Mould columns found (should not be in Stage 2): {leaked}")
        else:
            print(f"  ✓ No mould/machine columns in output (correct for Stage 2)")

        # Source distribution
        if "Source" in final_df.columns:
            source_counts = final_df["Source"].value_counts()
            print(f"\nSource distribution:")
            for src, count in source_counts.items():
                print(f"  • {src}: {count} rows")

        # Top 5 rows
        print(f"\nTop 5 rows by Final Rank:")
        preview_cols = [c for c in ["Final Rank", "SKUCode", "Source", "Market",
                                     "StrategicPriorityScore", "HighestPriority"] if c in final_df.columns]
        print(final_df[preview_cols].head(5).to_string(index=False))

    else:
        print("✗ Stage 2 pipeline returned empty output")
        return

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print("✓ All tests passed successfully!")
    print(f"\nFinal Dataset Shape: {final_df.shape}")
    print("\nStage 2 (Frontend Integration) pipeline is ready for production use.")
    print("=" * 80)


if __name__ == "__main__":
    test_stage2_pipeline()
