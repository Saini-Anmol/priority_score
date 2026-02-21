# config.py
# All tunable parameters are loaded from config_input.xlsx (Stage1_Config sheet).
# Run `python create_config_excel.py` once to generate the Excel template.

import os
import sys
import pandas as pd

# ---------------------------------------------------------------------------
# 1. FILE PATHS  (not user-configurable — environment specific)
# ---------------------------------------------------------------------------
BASE_DATA_PATH = "./data"
OUTPUT_FILE    = "combined_data_output.xlsx"

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_input.xlsx")
_SHEET_NAME  = "Stage1_Config"

# ---------------------------------------------------------------------------
# 2. LOAD EXCEL CONFIG
# ---------------------------------------------------------------------------
def _load_config() -> dict:
    """
    Read Stage1_Config sheet from config_input.xlsx.
    For each row: value = User_Input if not blank/NaN, else Default_Value.
    Returns a dict {Parameter: resolved_value}.
    """
    if not os.path.exists(_CONFIG_FILE):
        print(
            "\n❌ ERROR: 'config_input.xlsx' not found.\n"
            "   Please run the following command first to create it:\n"
            "       python create_config_excel.py\n"
        )
        sys.exit(1)

    try:
        df = pd.read_excel(_CONFIG_FILE, sheet_name=_SHEET_NAME, dtype={"User_Input": object})
    except Exception as e:
        print(f"\n❌ ERROR: Could not read '{_SHEET_NAME}' sheet from config_input.xlsx.\n   Details: {e}\n")
        sys.exit(1)

    config = {}
    for _, row in df.iterrows():
        param   = row["Parameter"]
        default = row["Default_Value"]
        user    = row["User_Input"]

        # Use User_Input only when it is a non-empty, non-NaN value
        if pd.notna(user) and str(user).strip() != "":
            # Preserve the type of the default value
            try:
                if isinstance(default, float) and default == int(default):
                    # Could be int or float — match default's actual type
                    value = type(default)(user)
                else:
                    value = type(default)(user)
            except (ValueError, TypeError):
                value = user  # fall back to raw string if cast fails
        else:
            value = default

        config[param] = value

    return config

_cfg = _load_config()

# ---------------------------------------------------------------------------
# Helper: safely get a value (raises KeyError with a clear message if missing)
# ---------------------------------------------------------------------------
def _get(key: str):
    if key not in _cfg:
        raise KeyError(
            f"Parameter '{key}' not found in {_SHEET_NAME} sheet of config_input.xlsx. "
            "Re-run create_config_excel.py to regenerate the template."
        )
    return _cfg[key]

# ---------------------------------------------------------------------------
# 3. MARKET WEIGHTS  (Higher number = Higher Priority)
# ---------------------------------------------------------------------------
MARKET_WEIGHTS = {
    'OE':  int(_get("MARKET_WEIGHTS_OE")),
    'ST':  int(_get("MARKET_WEIGHTS_ST")),
    'EXP': int(_get("MARKET_WEIGHTS_EXP")),
    'RE':  int(_get("MARKET_WEIGHTS_RE")),
}

# ---------------------------------------------------------------------------
# 4. MARKET PRIORITY  (For ranking — lower is higher priority)
# ---------------------------------------------------------------------------
MARKET_PRIORITY = {
    'OE':  int(_get("MARKET_PRIORITY_OE")),
    'ST':  int(_get("MARKET_PRIORITY_ST")),
    'EXP': int(_get("MARKET_PRIORITY_EXP")),
    'RE':  int(_get("MARKET_PRIORITY_RE")),
}

# ---------------------------------------------------------------------------
# 5. LOCATION WEIGHTS  (How important is the warehouse type?)
# ---------------------------------------------------------------------------
LOCATION_WEIGHTS = {
    'JIT':            int(_get("LOCATION_WEIGHTS_JIT")),
    'Depot':          int(_get("LOCATION_WEIGHTS_Depot")),
    'Depot Mobility': int(_get("LOCATION_WEIGHTS_Depot_Mobility")),
    'Feeder':         int(_get("LOCATION_WEIGHTS_Feeder")),
    'PWH':            int(_get("LOCATION_WEIGHTS_PWH")),
}

# ---------------------------------------------------------------------------
# 6. SCORE CALCULATION WEIGHTS  (% contribution to final score)
# ---------------------------------------------------------------------------
SCORING_PARAMS = {
    "market_weightage":      float(_get("SCORING_market_weightage")),
    "penetration_weightage": float(_get("SCORING_penetration_weightage")),
    "requirement_weightage": float(_get("SCORING_requirement_weightage")),
    "top_sku_weightage":     float(_get("SCORING_top_sku_weightage")),
}

# ---------------------------------------------------------------------------
# 7. INVENTORY SCORE FACTORS  (Black vs Red stockout contribution)
# ---------------------------------------------------------------------------
INVENTORY_SCORE_FACTORS = {
    "black": float(_get("INVENTORY_BLACK_FACTOR")),  # Weight multiplier for Black stockouts
    "red":   float(_get("INVENTORY_RED_FACTOR")),    # Weight multiplier for Red stockouts
}

# ---------------------------------------------------------------------------
# 8. CONSOLIDATED SCORE WEIGHTS  (Demand + Inventory + Price)
# Set price_priority = 0 to get pure Demand+Inventory scoring (former Tier 1)
# ---------------------------------------------------------------------------
CONSOLIDATED_WEIGHTS = {
    "demand_priority":    float(_get("CONSOLIDATED_demand_priority")),    # Market/Penetration/Requirement
    "inventory_priority": float(_get("CONSOLIDATED_inventory_priority")), # Red/Black stockouts
    "price_priority":     float(_get("CONSOLIDATED_price_priority")),     # Revenue/Daily capacity
}

# ---------------------------------------------------------------------------
# 9. PRODUCTION CONSTANTS
# ---------------------------------------------------------------------------
EFFICIENCY_FACTOR  = float(_get("EFFICIENCY_FACTOR"))
DEFAULT_ASP        = int(_get("DEFAULT_ASP"))
DEFAULT_CURE_TIME  = int(_get("DEFAULT_CURE_TIME"))