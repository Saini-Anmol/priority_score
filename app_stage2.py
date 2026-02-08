# app_stage2.py
# Stage 2: Unified Application Runner (Combines Stage 1 + Stage 2)

import pandas as pd
from datetime import datetime
from demand_processor import process_single_date
from deployment_processor import process_deployment_analysis
import config
import config_stage2

def run_integrated_analysis():
    """
    Run the integrated Stage 1 + Stage 2 analysis pipeline.
    
    Process:
    1. Accept a date from the user
    2. Execute Stage 1 (Demand Summary)
    3. Execute Stage 2 (Deployment Analysis)
    4. Generate consolidated Excel report
    """
    print("=" * 80)
    print("VECTOR SUPPLY CHAIN INTELLIGENCE SYSTEM")
    print("Stage 1: Demand Prioritization | Stage 2: Machine Deployment Analysis")
    print("=" * 80)
    print()
    
    # Get date input from user
    date_str = input("Enter analysis date (DD.MM.YYYY): ")
    
    try:
        # Parse and validate date
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")
        date_formatted = date_obj.strftime("%d%m%Y")
        
        print(f"\nProcessing analysis for: {date_obj.strftime('%d-%m-%Y')}")
        print("-" * 80)
        
        # ========================================================================
        # STAGE 1: DEMAND PRIORITIZATION
        # ========================================================================
        print("\n[STAGE 1] Demand Prioritization Analysis")
        print("-" * 80)
        
        demand_df = process_single_date(date_formatted)
        
        if demand_df is None or demand_df.empty:
            print("\nError: Could not process Stage 1 data. Missing input files.")
            print("Please ensure all required files exist for the selected date.")
            return
        
        print(f"[STAGE 1] Successfully processed {len(demand_df)} SKUs")
        
        # ========================================================================
        # STAGE 2: DEPLOYMENT ANALYSIS
        # ========================================================================
        print("\n[STAGE 2] Machine Deployment Analysis")
        print("-" * 80)
        
        final_df = process_deployment_analysis(demand_df, date_formatted)
        
        # ========================================================================
        # OUTPUT GENERATION
        # ========================================================================
        print("\n[OUTPUT] Generating Excel Report")
        print("-" * 80)
        
        output_file = config_stage2.STAGE2_OUTPUT_FILE
        
        # Sort by ProxyRank (most urgent first)
        final_df = final_df.sort_values('ProxyRank', ascending=True)
        
        # Write to Excel with date as sheet name
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            final_df.to_excel(writer, sheet_name=date_formatted, index=False)
        
        print(f"\n✓ Report successfully generated: {output_file}")
        print(f"  Sheet: {date_formatted}")
        print(f"  Total SKUs analyzed: {len(final_df)}")
        
        # ========================================================================
        # SUMMARY INSIGHTS
        # ========================================================================
        print("\n[INSIGHTS] Executive Summary")
        print("-" * 80)
        
        critical_gaps = final_df['CriticalGap'].sum()
        excess_production = final_df['ExcessProduction'].sum()
        mould_alerts = final_df['MouldAlert'].sum()
        skus_in_production = (final_df['MachineCount'] > 0).sum()
        skus_not_in_production = (final_df['MachineCount'] == 0).sum()
        
        print(f"Production Status:")
        print(f"  • SKUs currently in production: {skus_in_production}")
        print(f"  • SKUs NOT in production: {skus_not_in_production}")
        print()
        print(f"Action Required:")
        print(f"  • 🔴 Critical Gaps (High-priority, not running): {critical_gaps}")
        print(f"  • ⚠️  Excess Production (Low-priority, many machines): {excess_production}")
        print(f"  • 🔧 Mould Alerts (Nearing end of life): {mould_alerts}")
        
        if critical_gaps > 0:
            print(f"\n⚠️  ATTENTION: {critical_gaps} high-priority SKUs are not in production!")
            print("   Review the 'CriticalGap' column in the report.")
        
        print("\n" + "=" * 80)
        print("Analysis Complete!")
        print("=" * 80)
        
    except ValueError:
        print("\nError: Invalid date format. Please use DD.MM.YYYY format.")
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_integrated_analysis()
