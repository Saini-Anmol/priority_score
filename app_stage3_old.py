# app_stage3.py
# Stage 3: Unified Orchestrator — Demand + Deployment + Manual Strategic Override
#
# Pipeline:
#   Stage 1 → process_single_date()          (demand_processor.py)
#   Stage 2 → process_deployment_analysis()  (deployment_processor.py)
#   Stage 3 → process_manual_override()      (manual_integration_processor.py)
#
# Output: vector_frontend_running_demand_<DDMMYYYY>.xlsx  (date-wise sheet tabs)

import os
import numpy as np
import pandas as pd
from datetime import datetime

import config
from demand_processor import process_single_date, get_history_bor_data
from deployment_processor import process_deployment_analysis
from manual_integration_processor import process_manual_override


STAGE3_OUTPUT_FILE = "final_hybrid_deployment_report.xlsx"  # overridden dynamically below


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
        output_file    = f"vector_frontend_running_demand_{date_formatted}.xlsx"

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
        # The processor guarantees: Final Rank col-0, manual entries at top.
        if "Final Rank" in hybrid_df.columns:
            hybrid_df = hybrid_df.sort_values("Final Rank", ascending=True).reset_index(drop=True)

        # ====================================================================
        # YIELD FACTOR — Updated_Requirement  (quality-adjusted production qty)
        # ====================================================================
        # OE / EXP: manufacturers need to over-produce to account for defects.
        #   Updated_Requirement = ceil(Requirement / yield_factor + k)
        #   yield_factor = 0.95 means 95% of output is top-quality; k = safety buffer
        # RE / ST / OTR / Manual / others: quality is not the primary concern,
        #   so Updated_Requirement = Requirement  (no adjustment, yield = 100%)
        # Config parameters: YIELD_FACTOR_OE, YIELD_FACTOR_EXP, YIELD_K_OE, YIELD_K_EXP
        # ====================================================================
        if "Requirement" in hybrid_df.columns and "Market" in hybrid_df.columns:
            def _apply_yield(row):
                mkt = str(row.get("Market", ""))
                req = row.get("Requirement", 0)
                if pd.isna(req):
                    req = 0
                factor = config.YIELD_FACTORS.get(mkt, 1.0)
                k      = config.YIELD_K.get(mkt, 0)
                if factor < 1.0:
                    return int(np.ceil(req / factor + k))
                return int(req + k)  # factor = 1.0 → no adjustment

            hybrid_df["Updated_Requirement"] = hybrid_df.apply(_apply_yield, axis=1)
            print(f"[OUTPUT] Yield factor applied — Updated_Requirement column added")
        else:
            print("[OUTPUT] Skipping yield factor (Requirement or Market column missing)")

        # ====================================================================
        # GHOST SKU MARKET CORRECTION
        # Reassign Ghost SKUs from default 'RE' to 'OE' if they appear in oe_demand.csv.
        # This ensures Stage 4 applies OE logic (max(Stage3, oe_demand)) for them.
        # ====================================================================
        oe_demand_path = os.path.join(config.BASE_DATA_PATH, "oe_demand.csv")
        if os.path.exists(oe_demand_path) and "IsGhostSKU" in hybrid_df.columns:
            try:
                _oe_df = pd.read_csv(oe_demand_path, skiprows=2, header=0, encoding="latin1")
                _oe_skus = set(_oe_df["PRODUCT CODE"].astype(str).str.strip().str.upper())
                ghost_oe_mask = (
                    hybrid_df["IsGhostSKU"].fillna(False).astype(bool) &
                    hybrid_df["SKUCode"].astype(str).str.strip().str.upper().isin(_oe_skus)
                )
                n_corrected = ghost_oe_mask.sum()
                if n_corrected > 0:
                    hybrid_df.loc[ghost_oe_mask, "Market"] = "OE"
                    print(f"[OUTPUT] Ghost SKU market corrected RE→OE for {n_corrected} SKU(s) found in oe_demand.csv")
            except Exception as _e:
                print(f"[WARN] Could not apply Ghost SKU OE correction: {_e}")


        desc_lookup: dict = {}
        if "SKU Description" in hybrid_df.columns:
            desc_lookup = (
                hybrid_df.dropna(subset=["SKUCode"])
                .drop_duplicates("SKUCode")
                .set_index("SKUCode")["SKU Description"]
                .to_dict()
            )

        # Load historical BOR data (used for extra Excel tabs)
        n_days = config.HISTORY_PENETRATION_N
        print(f"[OUTPUT] Loading BOR history for last {n_days} days...")
        history_bor = get_history_bor_data(date_formatted, n_days)

        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:

            # ── Tab 1: Full Stage 3 hybrid output ──────────────────────────
            hybrid_df.to_excel(writer, sheet_name=date_formatted, index=False)
            print(f"  [Tab 1] {date_formatted} — {len(hybrid_df)} rows (Stage 3 output)")

            # ── Tabs 2…N+1: Daily BOR penetration snapshots ────────────────
            # Sheet name format: DD-MM-YYYY (e.g. 23-02-2026)
            # Columns: SKUCode | SKU Description | Location Code | Norm | Virtual Norm | Stock | Penetration
            tabs_written = 0
            for date_label, bor_df in history_bor:
                if bor_df is None or bor_df.empty:
                    print(f"  [History Tab] {date_label} — skipped (no BOR file)")
                    continue

                bor_df = bor_df.copy()

                # Attach SKU Description from the hybrid output
                bor_df["SKU Description"] = bor_df["SKUCode"].map(desc_lookup).fillna("")

                # Column order: identification first, then BOR metrics
                priority_cols = ["SKUCode", "SKU Description", "Location Code",
                                 "Norm ", "Virtual Norm", "Stock", "Penetration"]
                ordered = [c for c in priority_cols if c in bor_df.columns]
                remaining = [c for c in bor_df.columns if c not in ordered]
                bor_df = bor_df[ordered + remaining]

                # Sheet name must be ≤ 31 chars; DD-MM-YYYY = 10 chars ✓
                bor_df.to_excel(writer, sheet_name=date_label, index=False)
                tabs_written += 1
                print(f"  [History Tab] {date_label} — {len(bor_df)} rows")

        print(f"\n✓ Report successfully generated: {output_file}")
        print(f"  Sheet : {date_formatted}  (Stage 3 output)")
        print(f"  Rows  : {len(hybrid_df)}")
        print(f"  History BOR tabs written: {tabs_written} of {n_days}")


        # ====================================================================
        # EXECUTIVE SUMMARY
        # ====================================================================
        print("\n[INSIGHTS] Executive Summary")
        print("-" * 80)

        manual_rows  = hybrid_df[hybrid_df["Source"] == "Manual"]
        auto_rows    = hybrid_df[hybrid_df["Source"] == "Automated"]



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

