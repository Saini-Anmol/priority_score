# app_stage3.py
# Stage 3: Unified Orchestrator — Demand + Deployment + Manual Strategic Override
#
# Pipeline:
#   Stage 1 → process_single_date()          (demand_processor.py)
#   Stage 2 → process_deployment_analysis()  (deployment_processor.py)
#   Stage 3 → process_manual_override()      (manual_integration_processor.py)
#
# Output: final_hybrid_deployment_report.xlsx  (date-wise sheet tabs)

import pandas as pd
from datetime import datetime

from demand_processor import process_single_date
from deployment_processor import process_deployment_analysis
from manual_integration_processor import process_manual_override


STAGE3_OUTPUT_FILE = "final_hybrid_deployment_report.xlsx"


def run_hybrid_analysis():
    """
    Run the full three-stage hybrid analysis pipeline.

    Process:
        1. Accept a date from the user.
        2. Stage 1 — Demand Prioritization.
        3. Stage 2 — Machine Deployment Analysis.
        4. Stage 3 — Manual Strategic Override / Hybrid Synthesis.
        5. Write final_hybrid_deployment_report.xlsx.
    """
    print("=" * 80)
    print("VECTOR SUPPLY CHAIN INTELLIGENCE SYSTEM")
    print("Stage 1: Demand  |  Stage 2: Deployment  |  Stage 3: Manual Override")
    print("=" * 80)
    print()

    date_str = input("Enter analysis date (DD.MM.YYYY): ")

    try:
        date_obj       = datetime.strptime(date_str, "%d.%m.%Y")
        date_formatted = date_obj.strftime("%d%m%Y")

        print(f"\nProcessing analysis for: {date_obj.strftime('%d-%m-%Y')}")
        print("-" * 80)

        # ====================================================================
        # STAGE 1: DEMAND PRIORITIZATION
        # ====================================================================
        print("\n[STAGE 1] Demand Prioritization Analysis")
        print("-" * 80)

        demand_df = process_single_date(date_formatted)

        if demand_df is None or demand_df.empty:
            print("\nError: Could not process Stage 1 data. Missing input files.")
            print("Please ensure all required files exist for the selected date.")
            return

        print(f"[STAGE 1] Successfully processed {len(demand_df)} SKUs")

        # ====================================================================
        # STAGE 2: MACHINE DEPLOYMENT ANALYSIS
        # ====================================================================
        print("\n[STAGE 2] Machine Deployment Analysis")
        print("-" * 80)

        stage2_df = process_deployment_analysis(demand_df, date_formatted)

        # ====================================================================
        # STAGE 3: MANUAL STRATEGIC OVERRIDE
        # ====================================================================
        print("\n[STAGE 3] Manual Strategic Override")
        print("-" * 80)

        hybrid_df = process_manual_override(stage2_df, date_formatted)

        # ====================================================================
        # OUTPUT GENERATION
        # ====================================================================
        print("\n[OUTPUT] Generating Hybrid Excel Report")
        print("-" * 80)

        # Final Rank and column order are set by the processor — just sort and write.
        # The processor guarantees: Final Rank col-0, manual top, overstock bottom.
        if "Final Rank" in hybrid_df.columns:
            hybrid_df = hybrid_df.sort_values("Final Rank", ascending=True).reset_index(drop=True)

        with pd.ExcelWriter(STAGE3_OUTPUT_FILE, engine="openpyxl") as writer:
            hybrid_df.to_excel(writer, sheet_name=date_formatted, index=False)

        print(f"\n✓ Report successfully generated: {STAGE3_OUTPUT_FILE}")
        print(f"  Sheet : {date_formatted}")
        print(f"  Rows  : {len(hybrid_df)}")

        # ====================================================================
        # EXECUTIVE SUMMARY
        # ====================================================================
        print("\n[INSIGHTS] Executive Summary")
        print("-" * 80)

        manual_rows  = hybrid_df[hybrid_df["Source"] == "Manual"]
        auto_rows    = hybrid_df[hybrid_df["Source"] == "Automated"]

        # Overstock rows for summary (Automated only, Penetration > 100)
        if "Penetration" in hybrid_df.columns:
            pen_numeric    = pd.to_numeric(hybrid_df["Penetration"], errors="coerce").fillna(0)
            overstock_rows = hybrid_df[(pen_numeric > 100) & (hybrid_df["Source"] != "Manual")]
            n_overstock    = len(overstock_rows)
        else:
            n_overstock = 0

        print(f"Manual Override:")
        print(f"  • Total manual entries injected : {len(manual_rows)}")
        if "HighestPriority" in manual_rows.columns:
            hp_count = len(manual_rows[manual_rows["HighestPriority"] == 1])
            print(f"  • Flagged 'Highest Priority'    : {hp_count}")

        print(f"\nAutomated Production Status:")
        if "MachineCount" in auto_rows.columns:
            skus_in_prod     = len(auto_rows[auto_rows["MachineCount"] > 0])
            skus_not_in_prod = len(auto_rows[auto_rows["MachineCount"] == 0])
        else:
            skus_in_prod, skus_not_in_prod = "N/A", "N/A"
        print(f"  • SKUs currently in production  : {skus_in_prod}")
        print(f"  • SKUs NOT in production        : {skus_not_in_prod}")

        if "CriticalGap" in hybrid_df.columns:
            critical_gaps     = len(hybrid_df[hybrid_df["CriticalGap"] == True])  # noqa: E712
            excess_production = len(hybrid_df[hybrid_df["ExcessProduction"] == True]) if "ExcessProduction" in hybrid_df.columns else 0  # noqa: E712
            mould_alerts      = len(hybrid_df[hybrid_df["MouldAlert"] == True])       if "MouldAlert"       in hybrid_df.columns else 0  # noqa: E712

            print(f"\nAction Required:")
            print(f"  • 🔴 Critical Gaps (high-priority, not running)       : {critical_gaps}")
            print(f"  • ⚠️  Excess Production (low-priority, many machines)  : {excess_production}")
            print(f"  • 🔧 Mould Alerts (nearing end of life)               : {mould_alerts}")
            print(f"  • 📦 Overstock items (Penetration > 100%, sent to end): {n_overstock}")

        print("\n" + "=" * 80)
        print("Hybrid Analysis Complete!")
        print("=" * 80)

    except ValueError:
        print("\nError: Invalid date format. Please use DD.MM.YYYY format.")
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_hybrid_analysis()
