# V1/Routes/btp_pipeline.py
# ---------------------------------------------------------------------------
# BTP PIPELINE ORCHESTRATOR
# The core controller that chains all 5 business logic stages together 
# in-memory. Eliminates the need for intermediate Excel files.
# ---------------------------------------------------------------------------

import os

# Import the 5 core business logic modules from the Reports folder
from V1.Reports.stage1_demand import run_stage1
from V1.Reports.stage2_deployment import run_stage2
from V1.Reports.stage3_refinement import run_stage3
from V1.Reports.stage4_manual import run_stage4
from V1.Reports.stage5_yield import run_stage5

# Import the centralized Excel writer from Utilities
from V1.Utilities.excel_writer import write_final_output
# NEW: Import your database connection and upload utilities
from V1.Setups.connection import get_database_connection
from V1.Utilities.db_writer import upload_dataframe_to_sql

def run_btp_pipeline(ddmmyyyy: str):
    """
    Executes the 5-Stage BTP Pipeline entirely in-memory.
    
    Args:
        ddmmyyyy (str): The target date formatted as DDMMYYYY.
    """
    print(f"\n🚀 Initiating BTP Pipeline Orchestration for {ddmmyyyy}...\n")

    # NEW: Initialize Database Connection early so Stage 4 can use it to read data
    print("☁️ Initializing database connection...")
    db_engine = get_database_connection()

    # ---------------------------------------------------------
    # STAGE 1: Demand Scoring
    # Reads raw BOR, BMR, BPR data and computes base priority scores.
    # Also fetches historical BOR data for the final output tabs.
    # ---------------------------------------------------------
    df_stage1, history_bor = run_stage1(ddmmyyyy)
    
    # Safety Check: Stop the pipeline if Stage 1 fails (e.g., missing files)
    if df_stage1 is None or df_stage1.empty:
        raise ValueError("Stage 1 failed to generate demand data. Pipeline aborted.")

    # ---------------------------------------------------------
    # STAGE 2: Machine Deployment Analysis
    # Merges current running moulds, applies machine penalties (Proxy Penetration),
    # and identifies Ghost SKUs running without demand.
    # ---------------------------------------------------------
    df_stage2 = run_stage2(df_stage1, ddmmyyyy)

    # ---------------------------------------------------------
    # STAGE 3: Max-Demand Refinement
    # Creates `Updated_Requirement` by taking the maximum of Vector demand, 
    # OE Dispatch Orders (oe_demand.csv), and Average Sales (avg_sales.csv).
    # ---------------------------------------------------------
    df_stage3 = run_stage3(df_stage2, ddmmyyyy)

    # ---------------------------------------------------------
    # STAGE 4: Manual / Frontend Integration
    # Merges manual overrides (CPT) and applies the 4-step HP weighted scoring
    # to guarantee manual SKUs rank above automated SKUs.
    # ---------------------------------------------------------
    df_stage4 = run_stage4(df_stage3, ddmmyyyy, db_engine)

    # ---------------------------------------------------------
    # STAGE 5: Yield Factor Adjustment
    # Inflates OE/EXP requirements based on quality yields and redistributes 
    # (subtracts) the difference from the RE market to prevent overproduction.
    # ---------------------------------------------------------
    final_df = run_stage5(df_stage4)

# ---------------------------------------------------------
    # FINAL OUTPUT 1: Write to Excel
    # This produces your vector_final_demand_DDMMYYYY.xlsx file
    # ---------------------------------------------------------
    output_filename = f"requirement_summary_{ddmmyyyy}.xlsx"
    print(f"\n💾 Formatting and writing final output to {output_filename}...")
    
    write_final_output(
        final_df=final_df, 
        history_bor=history_bor, 
        output_filename=output_filename, 
        main_sheet_name=ddmmyyyy
    )

    # # FINAL OUTPUT 2: Upload to MySQL Database
    # # This uploads the exact same 'final_df' to the cloud!
    # # ---------------------------------------------------------
    # if db_engine:
    #     upload_dataframe_to_sql(
    #         df=final_df, 
    #         table_name="btp_requirement",  
    #         engine=db_engine
    #     )