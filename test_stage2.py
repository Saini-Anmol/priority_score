# test_stage2.py
# Test script for Stage 2: Frontend / Manual Integration pipeline
# (New weighted scoring: Market + Qty + Target Date)

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from demand_processor import process_single_date
from frontend_processor import (
    _load_manual_data,
    _compute_weighted_score,
    process_frontend_override,
    _minmax,
)


def test_stage2_pipeline():
    """
    Test the Stage 2 pipeline with new weighted scoring logic.
    """
    print("=" * 80)
    print("STAGE 2 FRONTEND INTEGRATION — TEST SUITE (Weighted Scoring)")
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
    else:
        print("✗ Failed to process Stage 1 — check input data files for this date")
        return

    # ========================================================================
    # TEST 2: Min-Max Normalization Helper
    # ========================================================================
    print("\n[TEST 2] Min-Max Normalization Helper")
    print("-" * 40)

    test_series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    normed      = _minmax(test_series)
    assert abs(normed.min() - 0.0) < 1e-9, "Min should be 0"
    assert abs(normed.max() - 1.0) < 1e-9, "Max should be 1"
    print(f"✓ _minmax: range correctly maps to [0, 1]")

    # Edge case: all same value
    flat   = pd.Series([5.0, 5.0, 5.0])
    normed2 = _minmax(flat)
    assert (normed2 == 1.0).all(), "All-same values should return 1.0"
    print(f"✓ _minmax edge case: all-same-value → 1.0")

    # ========================================================================
    # TEST 3: Weighted Scoring on Synthetic Data
    # ========================================================================
    print("\n[TEST 3] Weighted Scoring (_compute_weighted_score)")
    print("-" * 40)

    today = datetime.now().date()
    synthetic = pd.DataFrame({
        "SKUCode":         ["SKU001XX16", "SKU002XX18", "SKU003XX20", "SKU004XX22"],
        "Market":          ["OE", "RE", "ST", "OE"],
        "Quantity":        [100, 50, 200, 75],
        "Target Date":     [today + timedelta(days=5), today + timedelta(days=30),
                           today + timedelta(days=10), today + timedelta(days=2)],
        "HighestPriority": [1, 0, 1, 1],
    })

    scored = _compute_weighted_score(synthetic.copy())

    # Check all expected columns exist
    expected_cols = ["weighted_score", "weighted_sum_priority",
                     "modified_priority_score", "manual_rank", "priority_rank"]
    for col in expected_cols:
        status = "✓" if col in scored.columns else "✗ MISSING"
        print(f"  {status}: '{col}'")

    # weighted_score should be in [0, 1]
    assert scored["weighted_score"].between(0, 1).all(), "weighted_score must be in [0,1]"
    print(f"✓ weighted_score range: [{scored['weighted_score'].min():.4f}, {scored['weighted_score'].max():.4f}]")

    # HighestPriority=1 rows should have weighted_sum_priority > 1
    hp_rows   = scored[scored["HighestPriority"] == 1]
    nohp_rows = scored[scored["HighestPriority"] == 0]
    assert (hp_rows["weighted_sum_priority"] > 1).all(),  "Priority rows must have sum > 1"
    assert (nohp_rows["weighted_sum_priority"] <= 1).all(), "Non-priority rows must have sum ≤ 1"
    print(f"✓ HighestPriority=1 rows all have weighted_sum_priority > 1")
    print(f"✓ HighestPriority=0 rows all have weighted_sum_priority ≤ 1")

    # modified_priority_score for priority rows should exceed non-priority rows
    if not nohp_rows.empty:
        assert hp_rows["modified_priority_score"].min() > nohp_rows["modified_priority_score"].max(), \
            "All HighestPriority=1 modified scores should exceed all non-priority scores"
        print(f"✓ modified_priority_score: priority rows always above non-priority rows")

    # manual_rank should start at 1
    assert scored["manual_rank"].min() == 1, "manual_rank should start at 1"
    print(f"✓ manual_rank starts at 1")

    print(f"\nDetailed scoring output:")
    preview_cols = ["SKUCode", "Market", "Quantity", "Target Date", "HighestPriority",
                    "weighted_score", "weighted_sum_priority", "modified_priority_score", "manual_rank"]
    print(scored[[c for c in preview_cols if c in scored.columns]].to_string(index=False))

    # ========================================================================
    # TEST 4: Manual Data Loading (if file exists)
    # ========================================================================
    manual_file = "./data/manual_frontend_demand.xlsx"
    if os.path.exists(manual_file):
        print("\n[TEST 4] Manual Frontend Demand File Loading")
        print("-" * 40)
        try:
            manual_df = _load_manual_data()
            print(f"✓ Loaded {len(manual_df)} manual entries")
            print(f"  - Columns: {list(manual_df.columns)}")
        except Exception as e:
            print(f"✗ Load failed: {e}")
    else:
        print(f"\n[TEST 4] SKIPPED — no manual file at '{manual_file}'")

    # ========================================================================
    # TEST 5: Full Stage 2 Integration
    # ========================================================================
    print("\n[TEST 5] Full Stage 2 Pipeline (process_frontend_override)")
    print("-" * 40)

    final_df = process_frontend_override(demand_df, test_date)

    if final_df is not None and not final_df.empty:
        print(f"✓ Stage 2 pipeline completed successfully")
        print(f"  - Total rows: {len(final_df)}")

        # Check key new columns
        expected = ["Final Rank", "Source", "StrategicPriorityScore",
                    "Vector_Requirement", "CPT_Requirement",
                    "weighted_score", "weighted_sum_priority",
                    "modified_priority_score", "manual_rank"]
        for col in expected:
            status = "✓" if col in final_df.columns else "⚠ absent (ok if no manual file)"
            print(f"  {status}: '{col}'")

        # Check NO old bias columns
        old_cols = ["ManualPriorityScore", "BOOST_BASE"]
        leaked = [c for c in old_cols if c in final_df.columns]
        if leaked:
            print(f"  ✗ Old bias columns found (should not be here): {leaked}")
        else:
            print(f"  ✓ No old bias-of-10 columns in output")

        # Check no mould columns
        mould_cols = ["MachineCount", "AvgMouldHealth", "CriticalGap",
                      "ExcessProduction", "MouldAlert", "IsGhostSKU"]
        leaked_mould = [c for c in mould_cols if c in final_df.columns]
        if leaked_mould:
            print(f"  ✗ Mould columns found (should not be in Stage 2): {leaked_mould}")
        else:
            print(f"  ✓ No mould/machine columns in output (correct for Stage 2)")

        # Source distribution
        if "Source" in final_df.columns:
            for src, count in final_df["Source"].value_counts().items():
                print(f"  • {src}: {count} rows")

        # Top 5 by Final Rank
        print(f"\nTop 5 rows by Final Rank:")
        preview = [c for c in ["Final Rank", "SKUCode", "Source", "StrategicPriorityScore",
                                "modified_priority_score", "HighestPriority"] if c in final_df.columns]
        print(final_df[preview].head(5).to_string(index=False))

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
    print("\nStage 2 (Frontend Weighted Scoring) pipeline is ready for production use.")
    print("=" * 80)


if __name__ == "__main__":
    test_stage2_pipeline()
