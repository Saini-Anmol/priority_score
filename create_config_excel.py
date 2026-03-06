#!/usr/bin/env python3
"""
create_config_excel.py
----------------------
Run this script ONCE to generate config_input.xlsx.
The file will be created in the same directory as this script.

Usage:
    python create_config_excel.py
"""

import pandas as pd
import os

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_input.xlsx")

# ---------------------------------------------------------------------------
# Stage 1 Config Parameters
# ---------------------------------------------------------------------------
stage1_rows = [
    # --- Market Weights (Higher number = Higher Priority) ---
    ("MARKET_WEIGHTS_OE",                  4,    ""),
    ("MARKET_WEIGHTS_ST",                  3,    ""),
    ("MARKET_WEIGHTS_EXP",                 2,    ""),
    ("MARKET_WEIGHTS_OTR",                 2,    ""),  # Off-the-road tyres — same default as EXP
    ("MARKET_WEIGHTS_RE",                  1,    ""),
    # --- Market Priority (For ranking — lower number = higher priority) ---
    ("MARKET_PRIORITY_OE",                 1,    ""),
    ("MARKET_PRIORITY_ST",                 2,    ""),
    ("MARKET_PRIORITY_EXP",               3,    ""),
    ("MARKET_PRIORITY_OTR",               4,    ""),  # Off-the-road tyres
    ("MARKET_PRIORITY_RE",                 5,    ""),
    # --- Location Weights ---
    ("LOCATION_WEIGHTS_JIT",               5,    ""),
    ("LOCATION_WEIGHTS_Depot",             4,    ""),
    ("LOCATION_WEIGHTS_Depot_Mobility",    3,    ""),
    ("LOCATION_WEIGHTS_Feeder",            2,    ""),
    ("LOCATION_WEIGHTS_PWH",               1,    ""),
    # --- Market Norm Multipliers (fraction of Virtual Norm used as Adjusted_Target) ---
    # 1.0 = 100% of Virtual Norm; 0.5 = 50% of Virtual Norm, etc.
    ("RE_NORM_MULTIPLIER",                 1.0,  ""),
    ("OE_NORM_MULTIPLIER",                 1.0,  ""),
    ("ST_NORM_MULTIPLIER",                 1.0,  ""),
    ("OTR_NORM_MULTIPLIER",                1.0,  ""),  # Off-the-road tyres
    # --- Scoring Params ---
    ("SCORING_market_weightage",           0.25, ""),
    ("SCORING_penetration_weightage",      0.35, ""),
    ("SCORING_requirement_weightage",      0.30, ""),
    ("SCORING_top_sku_weightage",          0.10, ""),
    # --- Inventory Score Factors ---
    # Black stockout contributes more than Red; adjust freely (e.g. 1.0 / 0.5)
    ("INVENTORY_BLACK_FACTOR",             1.0,  ""),
    ("INVENTORY_RED_FACTOR",               0.5,  ""),
    # --- Consolidated Score Weights (Demand + Inventory + Price + History Penetration) ---
    # Weights sum to 1.0. Set history_penetration = 0 to disable it.
    # Setting price_priority = 0 gives pure Demand+Inventory+History scoring.
    ("CONSOLIDATED_demand_priority",       0.35, ""),
    ("CONSOLIDATED_inventory_priority",    0.25, ""),
    ("CONSOLIDATED_price_priority",        0.25, ""),
    ("CONSOLIDATED_history_penetration",   0.15, ""),
    # --- History Penetration Lookback Window ---
    # N = number of past days to look back for consecutive black streak scoring
    # Score = consecutive black days from today (max N); Red today = 0
    ("HISTORY_PENETRATION_N",              10,   ""),
    ("HISTORY_PENETRATION_BLACK",          100,  ""),  # Min penetration % to count a day as "black"
    # --- Yield Factor (Quality Adjustment for Updated_Requirement in Stage 3) ---
    # OE and EXP: Updated_Requirement = ceil(Requirement / yield_factor + k)
    # RE, ST, OTR and others: yield_factor = 1.0, k = 0  (Updated_Requirement = Requirement)
    # yield_factor represents top-quality product ratio (e.g. 0.95 = 95% top quality)
    # k is the extra safety buffer (number of additional products to produce)
    ("YIELD_FACTOR_OE",                   0.95, ""),  # 95% top-quality for OE
    ("YIELD_FACTOR_EXP",                  0.95, ""),  # 95% top-quality for EXP
    ("YIELD_K_OE",                        0,    ""),  # Extra buffer for OE (units)
    ("YIELD_K_EXP",                       0,    ""),  # Extra buffer for EXP (units)
    # --- Production Constants ---
    ("EFFICIENCY_FACTOR",                  0.9,  ""),
    ("DEFAULT_ASP",                        3000, ""),
    ("DEFAULT_CURE_TIME",                  15,   ""),
]

# ---------------------------------------------------------------------------
# Stage 2 Config Parameters
# ---------------------------------------------------------------------------
stage2_rows = [
    # --- Weighted Scoring: weights must sum to 1.0 ---
    # These control how Market urgency, Quantity, and Target Date urgency
    # each contribute to the manual entry's weighted_score.
    ("MANUAL_W_MARKET",       0.30, ""),  # Weight for market urgency factor
    ("MANUAL_W_QTY",          0.40, ""),  # Weight for quantity factor (higher qty = more urgent)
    ("MANUAL_W_TARGET_DATE",  0.30, ""),  # Weight for target date urgency (closer date = more urgent)

    # --- Market Score Mapping (higher numeric = more urgent) ---
    # These are min-max normalised before combining with qty and date factors.
    ("MANUAL_MARKET_OE",      4,    ""),
    ("MANUAL_MARKET_OE10",    4,    ""),
    ("MANUAL_MARKET_ST",      3,    ""),
    ("MANUAL_MARKET_EXP",     2,    ""),
    ("MANUAL_MARKET_OTR",     2,    ""),
    ("MANUAL_MARKET_RE",      1,    ""),
]

# ---------------------------------------------------------------------------
# Build DataFrames
# ---------------------------------------------------------------------------
COLUMNS = ["Parameter", "Default_Value", "User_Input"]

df_stage1 = pd.DataFrame(stage1_rows, columns=COLUMNS)
df_stage2 = pd.DataFrame(stage2_rows, columns=COLUMNS)

# ---------------------------------------------------------------------------
# Write to Excel
# ---------------------------------------------------------------------------
with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
    df_stage1.to_excel(writer, sheet_name="Stage1_Config", index=False)
    df_stage2.to_excel(writer, sheet_name="Stage2_Config", index=False)

print(f"✅ config_input.xlsx created successfully at:\n   {OUTPUT_PATH}")
print("\nSheets created:")
print(f"  • Stage1_Config  — {len(df_stage1)} parameters")
print(f"  • Stage2_Config  — {len(df_stage2)} parameters")
print("\nTo customise a value, enter it in the 'User_Input' column.")
print("\nStage 2 Config guide:")
print("  • MANUAL_W_MARKET + MANUAL_W_QTY + MANUAL_W_TARGET_DATE must sum to 1.0")
print("  • MANUAL_MARKET_* values control relative market urgency (higher = more urgent)")
