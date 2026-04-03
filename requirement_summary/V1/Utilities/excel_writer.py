# V1/Utilities/excel_writer.py
# ---------------------------------------------------------------------------
# CENTRALIZED EXCEL EXPORTER
# Handles writing the final in-memory DataFrame and historical BOR tabs
# to the final .xlsx file.
# ---------------------------------------------------------------------------

import pandas as pd

def write_final_output(final_df: pd.DataFrame, history_bor: list, output_filename: str, main_sheet_name: str):
    """
    Writes the final processed dataframe to Excel, appending the historical 
    BOR data as separate tabs for transparency.
    
    Args:
        final_df: The fully processed DataFrame from Stage 5.
        history_bor: List of tuples (date_label, DataFrame) from data_loaders.py.
        output_filename: The name of the resulting Excel file.
        main_sheet_name: The name for the primary data tab (usually DDMMYYYY).
    """
    # Create a quick SKU description lookup to map onto historical tabs
    # This prevents us from having blank descriptions on the history sheets
    desc_lookup = {}
    if 'SKU Description' in final_df.columns:
        desc_lookup = (
            final_df.dropna(subset=['SKUCode'])
            .drop_duplicates('SKUCode')
            .set_index('SKUCode')['SKU Description']
            .to_dict()
        )

    with pd.ExcelWriter(output_filename, engine='openpyxl') as writer:
        # 1. Write the main dataframe (Stage 5 Output)
        final_df.to_excel(writer, sheet_name=main_sheet_name, index=False)
        print(f"  [Tab 1] {main_sheet_name} — {len(final_df)} rows")

        # 2. Write the History BOR tabs (from the last N days)
        tabs_written = 0
        for date_label, bor_df in history_bor:
            if bor_df is None or bor_df.empty:
                print(f"  [History Tab] {date_label} — skipped (no BOR file)")
                continue
                
            bor_df = bor_df.copy()
            # Map description back in for readability using the Stage 5 lookup
            bor_df['SKU Description'] = bor_df['SKUCode'].astype(str).str.strip().map(desc_lookup).fillna('')
            
            # Enforce column order for history tabs
            priority_cols = ['SKUCode', 'SKU Description', 'Location Code',
                             'Norm ', 'Virtual Norm', 'Stock', 'Penetration']
            ordered   = [c for c in priority_cols if c in bor_df.columns]
            remaining = [c for c in bor_df.columns if c not in ordered]
            bor_df    = bor_df[ordered + remaining]
            
            bor_df.to_excel(writer, sheet_name=date_label, index=False)
            tabs_written += 1
            print(f"  [History Tab] {date_label} — {len(bor_df)} rows")
            
    print(f"✅ Full pipeline output successfully written to {output_filename}")