# V1/Setups/config.py
# ---------------------------------------------------------------------------
# UNIFIED CONFIGURATION MODULE
# Combines Stage 1 and Stage 2 configurations.
# All tunable parameters are loaded from config_input.xlsx (Stage1_Config sheet).
# Run `python create_config_excel.py` once to generate the Excel template.
# ---------------------------------------------------------------------------

import os
import sys
import pandas as pd
from dotenv import load_dotenv

# Load environment variables (like BASE_DATA_PATH) from .env file at the root
load_dotenv()

# ---------------------------------------------------------------------------
# 1. FILE PATHS (Configured via .env or defaults to standard local structure)
# ---------------------------------------------------------------------------
# Use the .env file if available, otherwise default to "./data" at the project root
BASE_DATA_PATH = os.getenv("BASE_DATA_PATH", "./data")
OUTPUT_FILE    = "combined_data_output.xlsx"

# Point to the root directory where config_input.xlsx lives (2 levels up from V1/Setups/)
_ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_FILE = os.path.join(_ROOT_DIR, "config_input.xlsx")
_SHEET_NAME  = "Stage1_Config"

# ---------------------------------------------------------------------------
# 2. LOAD EXCEL CONFIG (Stage 1 Dynamic Config)
# ---------------------------------------------------------------------------
def _load_config() -> dict:
    """
    Read Stage1_Config sheet from config_input.xlsx.
    For each row: value = User_Input if not blank/NaN, else Default_Value.
    Returns a dict {Parameter: resolved_value}.
    """
    if not os.path.exists(_CONFIG_FILE):
        print(
            f"\n❌ ERROR: 'config_input.xlsx' not found at {_CONFIG_FILE}.\n"
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
            try:
                if isinstance(default, float) and default == int(default):
                    value = type(default)(user)
                else:
                    value = type(default)(user)
            except (ValueError, TypeError):
                value = user  
        else:
            value = default

        config[param] = value
    return config

_cfg = _load_config()

def _get(key: str):
    if key not in _cfg:
        raise KeyError(
            f"Parameter '{key}' not found in {_SHEET_NAME} sheet of config_input.xlsx. "
            "Re-run create_config_excel.py to regenerate the template."
        )
    return _cfg[key]

# ---------------------------------------------------------------------------
# 3. MARKET WEIGHTS (Higher number = Higher Priority)
# ---------------------------------------------------------------------------
MARKET_WEIGHTS = {
    'OE':  int(_get("MARKET_WEIGHTS_OE")),
    'ST':  int(_get("MARKET_WEIGHTS_ST")),
    'EXP': int(_get("MARKET_WEIGHTS_EXP")),
    'OTR': int(_get("MARKET_WEIGHTS_OTR")),   
    'RE':  int(_get("MARKET_WEIGHTS_RE")),
}

MARKET_PRIORITY = {
    'OE':  int(_get("MARKET_PRIORITY_OE")),
    'ST':  int(_get("MARKET_PRIORITY_ST")),
    'EXP': int(_get("MARKET_PRIORITY_EXP")),
    'OTR': int(_get("MARKET_PRIORITY_OTR")),   
    'RE':  int(_get("MARKET_PRIORITY_RE")),
}

# ---------------------------------------------------------------------------
# 4. LOCATION WEIGHTS & SCORING PARAMS 
# ---------------------------------------------------------------------------
LOCATION_WEIGHTS = {
    'JIT':            int(_get("LOCATION_WEIGHTS_JIT")),
    'Depot':          int(_get("LOCATION_WEIGHTS_Depot")),
    'Depot Mobility': int(_get("LOCATION_WEIGHTS_Depot_Mobility")),
    'Feeder':         int(_get("LOCATION_WEIGHTS_Feeder")),
    'PWH':            int(_get("LOCATION_WEIGHTS_PWH")),
}

SCORING_PARAMS = {
    "market_weightage":      float(_get("SCORING_market_weightage")),
    "penetration_weightage": float(_get("SCORING_penetration_weightage")),
    "requirement_weightage": float(_get("SCORING_requirement_weightage")),
    "top_sku_weightage":     float(_get("SCORING_top_sku_weightage")),
}

INVENTORY_SCORE_FACTORS = {
    "black": float(_get("INVENTORY_BLACK_FACTOR")),  
    "red":   float(_get("INVENTORY_RED_FACTOR")),    
}

# ---------------------------------------------------------------------------
# 5. STRATEGIC TARGETS & YIELDS
# ---------------------------------------------------------------------------
NORM_MULTIPLIERS = {
    'RE':  float(_get("RE_NORM_MULTIPLIER")),
    'OE':  float(_get("OE_NORM_MULTIPLIER")),
    'ST':  float(_get("ST_NORM_MULTIPLIER")),
    'OTR': float(_get("OTR_NORM_MULTIPLIER")),   
}

YIELD_FACTORS = {
    'OE':  float(_get("YIELD_FACTOR_OE")),
    'EXP': float(_get("YIELD_FACTOR_EXP")),
}
YIELD_K = {
    'OE':  int(_get("YIELD_K_OE")),
    'EXP': int(_get("YIELD_K_EXP")),
}
YIELD_FACTOR = YIELD_FACTORS.get("OE", 0.95)   

# ---------------------------------------------------------------------------
# 6. CONSOLIDATED WEIGHTS & HISTORY PARAMS
# ---------------------------------------------------------------------------
CONSOLIDATED_WEIGHTS = {
    "demand_priority":       float(_get("CONSOLIDATED_demand_priority")),       
    "inventory_priority":    float(_get("CONSOLIDATED_inventory_priority")),    
    "price_priority":        float(_get("CONSOLIDATED_price_priority")),        
    "history_penetration":   float(_get("CONSOLIDATED_history_penetration")),   
}

HISTORY_PENETRATION_N     = int(_get("HISTORY_PENETRATION_N"))
HISTORY_PENETRATION_BLACK = float(_get("HISTORY_PENETRATION_BLACK"))

EFFICIENCY_FACTOR  = float(_get("EFFICIENCY_FACTOR"))
DEFAULT_ASP        = int(_get("DEFAULT_ASP"))
DEFAULT_CURE_TIME  = int(_get("DEFAULT_CURE_TIME"))

# ===========================================================================
# STAGE 2 / STAGE 3 MANUAL OVERRIDE CONFIGURATION (from old config_stage2.py)
# ===========================================================================

MANUAL_INPUT_FILE = os.path.join(BASE_DATA_PATH, "manual_frontend_demand.xlsx")

# WEIGHTED SCORING PARAMETERS (Must sum to 1.0)
W_MARKET      = 0.30   # Weight for market urgency factor
W_QTY         = 0.40   # Weight for quantity factor  (higher qty = more urgent)
W_TARGET_DATE = 0.30   # Weight for target date urgency (closer date = more urgent)

# MARKET SCORE MAPPING (For manual scoring: higher = more urgent)
MARKET_SCORE = {
    "OE":   4,
    "OE10": 4,
    "ST":   3,
    "EXP":  2,
    "OTR":  2,
    "RE":   1,
}