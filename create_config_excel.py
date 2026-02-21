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
    # --- Market Weights ---
    ("MARKET_WEIGHTS_OE",                  4,    ""),
    ("MARKET_WEIGHTS_ST",                  3,    ""),
    ("MARKET_WEIGHTS_EXP",                 2,    ""),
    ("MARKET_WEIGHTS_RE",                  1,    ""),
    # --- Market Priority ---
    ("MARKET_PRIORITY_OE",                 1,    ""),
    ("MARKET_PRIORITY_ST",                 2,    ""),
    ("MARKET_PRIORITY_EXP",               3,    ""),
    ("MARKET_PRIORITY_RE",                 4,    ""),
    # --- Location Weights ---
    ("LOCATION_WEIGHTS_JIT",               5,    ""),
    ("LOCATION_WEIGHTS_Depot",             4,    ""),
    ("LOCATION_WEIGHTS_Depot_Mobility",    3,    ""),
    ("LOCATION_WEIGHTS_Feeder",            2,    ""),
    ("LOCATION_WEIGHTS_PWH",               1,    ""),
    # --- Scoring Params ---
    ("SCORING_market_weightage",           0.25, ""),
    ("SCORING_penetration_weightage",      0.35, ""),
    ("SCORING_requirement_weightage",      0.30, ""),
    ("SCORING_top_sku_weightage",          0.10, ""),
    # --- Inventory Score Factors ---
    # Black stockout contributes more than Red; adjust freely (e.g. 1.0 / 0.5)
    ("INVENTORY_BLACK_FACTOR",             1.0,  ""),
    ("INVENTORY_RED_FACTOR",               0.5,  ""),
    # --- Consolidated Score Weights (Demand + Inventory + Price) ---
    # Setting CONSOLIDATED_price_priority = 0 gives pure Demand+Inventory scoring
    ("CONSOLIDATED_demand_priority",       0.4,  ""),
    ("CONSOLIDATED_inventory_priority",    0.3,  ""),
    ("CONSOLIDATED_price_priority",        0.3,  ""),
    # --- Production Constants ---
    ("EFFICIENCY_FACTOR",                  0.9,  ""),
    ("DEFAULT_ASP",                        3000, ""),
    ("DEFAULT_CURE_TIME",                  15,   ""),
]

# ---------------------------------------------------------------------------
# Stage 2 Config Parameters
# ---------------------------------------------------------------------------
stage2_rows = [
    # --- Mould Health ---
    ("MOULD_LIFE_THRESHOLD",    0.9,  ""),
    # --- Proxy Penetration ---
    ("MACHINE_COUNT_PENALTY",   0.05, ""),
    # --- Gap Analysis ---
    ("CRITICAL_GAP_RANK",       50,   ""),
    ("EXCESS_PRODUCTION_RANK",  200,  ""),
    ("EXCESS_MACHINE_COUNT",    2,    ""),
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
print("Leave 'User_Input' blank to use the Default_Value.")
