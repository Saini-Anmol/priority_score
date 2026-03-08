# ctp_config.py
# CTP Stage 1 Configuration — Plant 1900 (PCR + TBR)
#
# All paths are relative to the project ROOT (one level above this CTP/ folder).
# Run ctp_app.py from the project root:  python CTP/ctp_app.py
#
# ─── DESIGN NOTE ────────────────────────────────────────────────────────────
# This file intentionally does NOT import from the BTP config.py.
# CTP is a completely independent pipeline so that changes to BTP
# parameters never silently affect CTP scoring.
# ────────────────────────────────────────────────────────────────────────────

import os

# ---------------------------------------------------------------------------
# 1. PLANT IDENTIFIER
# ---------------------------------------------------------------------------
CTP_PLANT_CODE     = 1900          # int  — used for DISPATCH filter
CTP_PLANT_PREFIX   = '1900'        # str  — used for Location Code startswith filter

# ---------------------------------------------------------------------------
# 2. FILE PATHS  (relative to project root, i.e. one folder above CTP/)
# ---------------------------------------------------------------------------
BASE_DATA_PATH = "./data"          # Same raw daily files as BTP (BOR/BPR/BMR)

CTP_DIR              = os.path.dirname(os.path.abspath(__file__))   # …/Vector_Project/CTP/
PCR_CURE_FILE        = os.path.join(CTP_DIR, "PCR Curing cycle time.xlsx")
TBR_CURE_FILE        = os.path.join(CTP_DIR, "TBR curing cycle time.xlsx")
PCR_SKU_LIST_FILE    = os.path.join(CTP_DIR, "SKU_List.xlsx")
CTP_DISPATCH_FILE    = os.path.join(CTP_DIR, "CTP TYRE DESPATCH DEC 24 TO NOV 25.XLSX")

# ---------------------------------------------------------------------------
# 3. MARKET WEIGHTS  (Higher number = Higher Priority)
#    Same logic as BTP — OE is most critical, RE is least
# ---------------------------------------------------------------------------
MARKET_WEIGHTS = {
    'OE':  4,
    'OE10': 4,
    'ST':  3,
    'EXP': 2,
    'OTR': 2,
    'RE':  1,
}

# ---------------------------------------------------------------------------
# 4. LOCATION WEIGHTS  (Warehouse type importance)
# ---------------------------------------------------------------------------
LOCATION_WEIGHTS = {
    'JIT':            5,
    'Depot':          4,
    'Depot Mobility': 3,
    'Feeder':         2,
    'PWH':            1,
}

# ---------------------------------------------------------------------------
# 5. INVENTORY SCORE FACTORS
# ---------------------------------------------------------------------------
INVENTORY_SCORE_FACTORS = {
    'black': 1.0,   # Weight multiplier for Black (critical) stockouts
    'red':   0.5,   # Weight multiplier for Red (warning) stockouts
}

# ---------------------------------------------------------------------------
# 6. NORM MULTIPLIERS  (fraction of Virtual Norm used as Adjusted_Target)
#    1.0 = 100% of Virtual Norm (default for all markets)
# ---------------------------------------------------------------------------
NORM_MULTIPLIERS = {
    'RE':  1.0,
    'OE':  1.0,
    'OE10':1.0,
    'ST':  1.0,
    'OTR': 1.0,
}

# ---------------------------------------------------------------------------
# 7. SCORING WEIGHTS  (% contribution to PriorityScore — must sum to 1.0)
# ---------------------------------------------------------------------------
SCORING_PARAMS = {
    'market_weightage':      0.25,
    'penetration_weightage': 0.35,
    'requirement_weightage': 0.30,
    'top_sku_weightage':     0.10,
}

# ---------------------------------------------------------------------------
# 8. CONSOLIDATED SCORE WEIGHTS  (Demand + Inventory + Price + History)
#    Must sum to 1.0
# ---------------------------------------------------------------------------
CONSOLIDATED_WEIGHTS = {
    'demand_priority':     0.35,
    'inventory_priority':  0.25,
    'price_priority':      0.25,
    'history_penetration': 0.15,
}

# ---------------------------------------------------------------------------
# 9. HISTORY PENETRATION PARAMETERS
# ---------------------------------------------------------------------------
HISTORY_PENETRATION_N     = 10     # Lookback window in days (max streak score)
HISTORY_PENETRATION_BLACK = 100.0  # Min penetration % for a day to count as "black"

# ---------------------------------------------------------------------------
# 10. PRODUCTION CONSTANTS
# ---------------------------------------------------------------------------
EFFICIENCY_FACTOR = 0.90     # Machine efficiency for daily_cure calculation
DEFAULT_ASP       = 3000     # Fallback ASP when no dispatch history exists (₹)
DEFAULT_CURE_TIME = 15       # Fallback cure time in minutes
