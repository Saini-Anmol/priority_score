# config_stage2.py
# Stage 2: Machine Deployment Analysis Configuration

import os

# ============================================================================
# 1. MOULD REPORT PATHS
# ============================================================================
BASE_DATA_PATH = "./data"
MOULD_REPORT_PATH = os.path.join(BASE_DATA_PATH, "Vectordata", "Daily Mould Report")

# ============================================================================
# 2. MOULD HEALTH PARAMETERS
# ============================================================================
# Threshold for mould life alert (% of target life)
# Example: 0.9 means alert when mould has used 90% of its target life
MOULD_LIFE_THRESHOLD = 0.9

# ============================================================================
# 3. PROXY PENETRATION PARAMETERS
# ============================================================================
# Penalty factor per running machine (reduces priority when SKU is already in production)
# Example: 0.05 means each machine reduces priority by 5%
MACHINE_COUNT_PENALTY = 0.05

# ============================================================================
# 4. GAP ANALYSIS THRESHOLDS
# ============================================================================
# Critical Gap: High-priority SKUs not being manufactured
CRITICAL_GAP_RANK = 50  # SKUs with rank better than this value

# Excess Production: Low-priority SKUs using too many machines
EXCESS_PRODUCTION_RANK = 200  # SKUs with rank worse than this value
EXCESS_MACHINE_COUNT = 2      # Machine count threshold for excess production

# ============================================================================
# 5. OUTPUT CONFIGURATION
# ============================================================================
STAGE2_OUTPUT_FILE = "deployment_analysis_report.xlsx"
