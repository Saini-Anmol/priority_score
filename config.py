# config.py

# 1. FILE PATHS
BASE_DATA_PATH = "./data"
OUTPUT_FILE = "combined_data_output.xlsx"

# 2. MARKET WEIGHTS (How important is each market?)
# Higher number = Higher Priority
MARKET_WEIGHTS = {
    'OE': 4, 
    'ST': 3, 
    'EXP': 2, 
    'RE': 1
}

# 3. MARKET PRIORITY (For ranking - lower is higher priority)
MARKET_PRIORITY = {
    'OE': 1, 
    'ST': 2, 
    'EXP': 3, 
    'RE': 4
}

# 4. LOCATION WEIGHTS (How important is the warehouse type?)
LOCATION_WEIGHTS = {
    'JIT': 5,
    'Depot': 4,
    'Depot Mobility': 3,
    'Feeder': 2,
    'PWH': 1
}

# 5. SCORE CALCULATION WEIGHTS (The % contribution to final score)
SCORING_PARAMS = {
    "market_weightage": 0.25,
    "penetration_weightage": 0.35,
    "requirement_weightage": 0.30,
    "top_sku_weightage": 0.10
}

# 6. TIER 1 CONSOLIDATED WEIGHTS (Initial scoring - Demand + Inventory)
TIER1_WEIGHTS = {
    "demand_priority": 0.6,     # Importance of Market/Penetration/Requirement
    "inventory_priority": 0.4   # Importance of Red/Black stockouts
}

# 7. TIER 2 CONSOLIDATED WEIGHTS (Final scoring - Demand + Inventory + Price)
TIER2_WEIGHTS = {
    "demand_priority": 0.4,     # Importance of Market/Penetration/Requirement
    "inventory_priority": 0.3,  # Importance of Red/Black stockouts
    "price_priority": 0.3       # Importance of Revenue/Daily capacity
}

# 8. PRODUCTION CONSTANTS
EFFICIENCY_FACTOR = 0.9
DEFAULT_ASP = 3000
DEFAULT_CURE_TIME = 15