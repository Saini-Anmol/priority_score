# config_stage2.py
# Stage 2: Frontend / Manual Integration Configuration
#
# Stage 2 scores manual/frontend entries using a principled weighted score
# based on Market, Quantity, and Target Date. Weights are configurable and
# must sum to 1.0.

# ---------------------------------------------------------------------------
# 1. OUTPUT PATH
# ---------------------------------------------------------------------------
STAGE2_OUTPUT_FILE = "deployment_analysis_report.xlsx"

# ---------------------------------------------------------------------------
# 2. MANUAL INPUT FILE
# ---------------------------------------------------------------------------
MANUAL_INPUT_FILE = "./data/manual_frontend_demand.xlsx"

# ---------------------------------------------------------------------------
# 3. WEIGHTED SCORING PARAMETERS
#    These three weights must sum to 1.0.
#    They control how Market urgency, Quantity, and Target Date urgency
#    each contribute to the manual entry's weighted_score.
# ---------------------------------------------------------------------------
W_MARKET      = 0.30   # Weight for market urgency factor
W_QTY         = 0.40   # Weight for quantity factor  (higher qty = more urgent)
W_TARGET_DATE = 0.30   # Weight for target date urgency (closer date = more urgent)

# ---------------------------------------------------------------------------
# 4. MARKET SCORE MAPPING
#    Maps market codes to numeric urgency scores (higher = more urgent).
#    These scores are min-max normalised before being combined with the
#    quantity and date factors.
# ---------------------------------------------------------------------------
MARKET_SCORE = {
    "OE":   4,
    "OE10": 4,
    "ST":   3,
    "EXP":  2,
    "OTR":  2,
    "RE":   1,
}