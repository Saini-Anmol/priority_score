# create_config_excel.py
import pandas as pd
import os

def create_config_template():
    """Generates the config_input.xlsx template for the BTP Pipeline."""
    
    config_data = [
        # --- Market Weights ---
        {"Parameter": "MARKET_WEIGHTS_OE", "Default_Value": 5, "User_Input": "", "Description": "Weight for OE market"},
        {"Parameter": "MARKET_WEIGHTS_ST", "Default_Value": 4, "User_Input": "", "Description": "Weight for ST market"},
        {"Parameter": "MARKET_WEIGHTS_EXP", "Default_Value": 3, "User_Input": "", "Description": "Weight for EXP market"},
        {"Parameter": "MARKET_WEIGHTS_OTR", "Default_Value": 2, "User_Input": "", "Description": "Weight for OTR market"},
        {"Parameter": "MARKET_WEIGHTS_RE", "Default_Value": 1, "User_Input": "", "Description": "Weight for RE market"},
        
        # --- Market Priority ---
        {"Parameter": "MARKET_PRIORITY_OE", "Default_Value": 1, "User_Input": "", "Description": "Rank priority for OE"},
        {"Parameter": "MARKET_PRIORITY_ST", "Default_Value": 2, "User_Input": "", "Description": "Rank priority for ST"},
        {"Parameter": "MARKET_PRIORITY_EXP", "Default_Value": 3, "User_Input": "", "Description": "Rank priority for EXP"},
        {"Parameter": "MARKET_PRIORITY_OTR", "Default_Value": 4, "User_Input": "", "Description": "Rank priority for OTR"},
        {"Parameter": "MARKET_PRIORITY_RE", "Default_Value": 5, "User_Input": "", "Description": "Rank priority for RE"},

        # --- Location Weights ---
        {"Parameter": "LOCATION_WEIGHTS_JIT", "Default_Value": 5, "User_Input": "", "Description": "Weight for JIT location"},
        {"Parameter": "LOCATION_WEIGHTS_Depot", "Default_Value": 4, "User_Input": "", "Description": "Weight for Depot"},
        {"Parameter": "LOCATION_WEIGHTS_Depot_Mobility", "Default_Value": 4, "User_Input": "", "Description": "Weight for Depot Mobility"},
        {"Parameter": "LOCATION_WEIGHTS_Feeder", "Default_Value": 3, "User_Input": "", "Description": "Weight for Feeder"},
        {"Parameter": "LOCATION_WEIGHTS_PWH", "Default_Value": 1, "User_Input": "", "Description": "Weight for PWH"},

        # --- Base Scoring Weightages ---
        {"Parameter": "SCORING_market_weightage", "Default_Value": 0.25, "User_Input": "", "Description": "Weight of market score"},
        {"Parameter": "SCORING_penetration_weightage", "Default_Value": 0.35, "User_Input": "", "Description": "Weight of penetration score"},
        {"Parameter": "SCORING_requirement_weightage", "Default_Value": 0.30, "User_Input": "", "Description": "Weight of requirement score"},
        {"Parameter": "SCORING_top_sku_weightage", "Default_Value": 0.10, "User_Input": "", "Description": "Weight of Top SKU flag"},

        # --- Inventory Health Factors ---
        {"Parameter": "INVENTORY_BLACK_FACTOR", "Default_Value": 2.0, "User_Input": "", "Description": "Multiplier for Black inventory level"},
        {"Parameter": "INVENTORY_RED_FACTOR", "Default_Value": 1.0, "User_Input": "", "Description": "Multiplier for Red inventory level"},

        # --- Strategic Norm Multipliers ---
        {"Parameter": "RE_NORM_MULTIPLIER", "Default_Value": 1.0, "User_Input": "", "Description": "Target adjustment for RE"},
        {"Parameter": "OE_NORM_MULTIPLIER", "Default_Value": 1.0, "User_Input": "", "Description": "Target adjustment for OE"},
        {"Parameter": "ST_NORM_MULTIPLIER", "Default_Value": 1.0, "User_Input": "", "Description": "Target adjustment for ST"},
        {"Parameter": "OTR_NORM_MULTIPLIER", "Default_Value": 1.0, "User_Input": "", "Description": "Target adjustment for OTR"},

        # --- Yield Factors (Stage 5) ---
        {"Parameter": "YIELD_FACTOR_OE", "Default_Value": 0.95, "User_Input": "", "Description": "Yield expectation for OE"},
        {"Parameter": "YIELD_FACTOR_EXP", "Default_Value": 0.95, "User_Input": "", "Description": "Yield expectation for EXP"},
        {"Parameter": "YIELD_K_OE", "Default_Value": 0, "User_Input": "", "Description": "Constant adjustment for OE"},
        {"Parameter": "YIELD_K_EXP", "Default_Value": 0, "User_Input": "", "Description": "Constant adjustment for EXP"},

        # --- Consolidated Priority Weightages ---
        {"Parameter": "CONSOLIDATED_demand_priority", "Default_Value": 0.40, "User_Input": "", "Description": "Weight of base demand score"},
        {"Parameter": "CONSOLIDATED_inventory_priority", "Default_Value": 0.20, "User_Input": "", "Description": "Weight of inventory health"},
        {"Parameter": "CONSOLIDATED_price_priority", "Default_Value": 0.20, "User_Input": "", "Description": "Weight of ASP/revenue potential"},
        {"Parameter": "CONSOLIDATED_history_penetration", "Default_Value": 0.20, "User_Input": "", "Description": "Weight of historical buffer streaks"},

        # --- Historical Penetration Logic ---
        {"Parameter": "HISTORY_PENETRATION_N", "Default_Value": 10, "User_Input": "", "Description": "Days to look back for streaks"},
        {"Parameter": "HISTORY_PENETRATION_BLACK", "Default_Value": 60.0, "User_Input": "", "Description": "Threshold percentage to trigger a black day"},

        # --- Constants & Defaults ---
        {"Parameter": "EFFICIENCY_FACTOR", "Default_Value": 0.85, "User_Input": "", "Description": "OEE/Efficiency standard"},
        {"Parameter": "DEFAULT_ASP", "Default_Value": 2500, "User_Input": "", "Description": "Fallback Average Selling Price"},
        {"Parameter": "DEFAULT_CURE_TIME", "Default_Value": 20, "User_Input": "", "Description": "Fallback curing cycle time (minutes)"},
    ]

    df = pd.DataFrame(config_data)
    
    output_file = "config_input.xlsx"
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Stage1_Config", index=False)
        
    print(f"✅ Configuration template successfully generated at: {os.path.abspath(output_file)}")
    print("You can now open this file in Excel to adjust parameters under 'User_Input'.")

if __name__ == "__main__":
    create_config_template()