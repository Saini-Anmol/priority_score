# config_stage2.py
# Stage 2: Frontend / Manual Integration Configuration
#
# Stage 2 no longer uses mould/machine deployment data.
# That configuration lives in deployment_processor.py (used by Stage 3 only).

import os

# ---------------------------------------------------------------------------
# 1. OUTPUT PATH
# ---------------------------------------------------------------------------
BASE_DATA_PATH     = "./data"
STAGE2_OUTPUT_FILE = "deployment_analysis_report.xlsx"

# ---------------------------------------------------------------------------
# 2. MANUAL INPUT FILE
# ---------------------------------------------------------------------------
MANUAL_INPUT_FILE = os.path.join(BASE_DATA_PATH, "manual_frontend_demand.xlsx")

# ---------------------------------------------------------------------------
# 3. PRIORITY BOOST PARAMETERS
# Assign manual entries a score that always exceeds any automated score (0–1).
# ManualPriorityScore = BOOST_BASE + (HighestPriority × BOOST_MULTIPLIER)
# ---------------------------------------------------------------------------
BOOST_BASE       = 10.0  # Floor score for any manual entry
BOOST_MULTIPLIER = 1.0   # Extra score for entries flagged as "Highest Priority"