# config_stage2.py
# Stage 2: Machine Deployment Analysis Configuration
# All tunable thresholds are loaded from config_input.xlsx (Stage2_Config sheet).
# Run `python create_config_excel.py` once to generate the Excel template.

import os
import sys
import pandas as pd

# ---------------------------------------------------------------------------
# 1. MOULD REPORT PATHS  (not user-configurable — environment specific)
# ---------------------------------------------------------------------------
BASE_DATA_PATH    = "./data"
MOULD_REPORT_PATH = os.path.join(BASE_DATA_PATH, "Vectordata", "Daily Mould Report")
STAGE2_OUTPUT_FILE = "deployment_analysis_report.xlsx"

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_input.xlsx")
_SHEET_NAME  = "Stage2_Config"

# ---------------------------------------------------------------------------
# 2. LOAD EXCEL CONFIG
# ---------------------------------------------------------------------------
def _load_stage2_config() -> dict:
    """
    Read Stage2_Config sheet from config_input.xlsx.
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
            try:
                value = type(default)(user)
            except (ValueError, TypeError):
                value = user  # fall back to raw string if cast fails
        else:
            value = default

        config[param] = value

    return config

_cfg = _load_stage2_config()

# ---------------------------------------------------------------------------
# Helper: safely get a value
# ---------------------------------------------------------------------------
def _get(key: str):
    if key not in _cfg:
        raise KeyError(
            f"Parameter '{key}' not found in {_SHEET_NAME} sheet of config_input.xlsx. "
            "Re-run create_config_excel.py to regenerate the template."
        )
    return _cfg[key]

# ---------------------------------------------------------------------------
# 3. MOULD HEALTH PARAMETERS
# Threshold for mould life alert (% of target life)
# ---------------------------------------------------------------------------
MOULD_LIFE_THRESHOLD = float(_get("MOULD_LIFE_THRESHOLD"))

# ---------------------------------------------------------------------------
# 4. PROXY PENETRATION PARAMETERS
# Penalty factor per running machine (reduces priority when SKU is in production)
# ---------------------------------------------------------------------------
MACHINE_COUNT_PENALTY = float(_get("MACHINE_COUNT_PENALTY"))

# ---------------------------------------------------------------------------
# 5. GAP ANALYSIS THRESHOLDS
# ---------------------------------------------------------------------------
# Critical Gap: High-priority SKUs not being manufactured
CRITICAL_GAP_RANK = int(_get("CRITICAL_GAP_RANK"))

# Excess Production: Low-priority SKUs using too many machines
EXCESS_PRODUCTION_RANK = int(_get("EXCESS_PRODUCTION_RANK"))
EXCESS_MACHINE_COUNT   = int(_get("EXCESS_MACHINE_COUNT"))

# ---------------------------------------------------------------------------
# 6. GHOST SKU DEFAULTS
# SKUs running on machines but absent from Vector demand ("Ghost Production").
# These values are used for data imputation so the math never breaks.
# ---------------------------------------------------------------------------
GHOST_SKU_REQUIREMENT = 0       # No active Vector demand
GHOST_SKU_PENETRATION = 0       # No penetration signal
GHOST_SKU_MARKET      = "RE"    # Conservative default market
GHOST_SKU_CURE_TIME   = 20.0    # Default curing cycle time (minutes)