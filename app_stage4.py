# app_stage4.py
# BTP Stage 4: Frontend / Manual SKU Integration
#
# Pipeline:
#   Reads:  vector_stage3_DDMMYYYY.xlsx          (Stage 3 output)
#           data/manual_frontend_demand.xlsx       (manual demand input)
#   Writes: vector_stage4_DDMMYYYY.xlsx
#
# Logic:
#   - For SKUs present in BOTH Stage 3 and manual file:
#       Updated_Requirement = CPT_Requirement (frontend qty wins)
#       Source = "Manual"
#   - For SKUs present ONLY in manual file (new rows):
#       Added as new rows with Updated_Requirement = CPT_Requirement
#       Automated fields = 0/NaN
#   - Re-computes Final Rank: Manual (HP=1 first, then HP=0), then Automated

import os
import numpy as np
import pandas as pd
from datetime import datetime, date as date_type

import config
from manual_integration_processor import process_manual_override

# Stage 4 does NOT enforce a fixed column list.
# It passes Stage 3 columns through and adds manual-integration columns on top.
# oe_demand_qty and avg_sales_qty are already in Stage 3 output.


def _final_rank(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rank rows:  Manual HP=1 first → Manual HP=0 → Automated
    Within each group: ConsolidatedPriorityScore descending.
    """
    df = df.copy()

    def _group(row):
        src = str(row.get('Source', 'Vector')).strip().lower()
        hp  = int(row.get('HighestPriority', 0) or 0)
        if src == 'cpt' and hp == 1:
            return 0
        if src == 'cpt' and hp == 0:
            return 1
        return 2

    df['_group']  = df.apply(_group, axis=1)
    df['_score']  = pd.to_numeric(df.get('ConsolidatedPriorityScore', 0), errors='coerce').fillna(0)
    df = df.sort_values(['_group', '_score'], ascending=[True, False]).reset_index(drop=True)
    df['Final Rank'] = df.index + 1
    df.drop(columns=['_group', '_score'], inplace=True)
    return df


def run_stage4():
    print('=' * 70)
    print('  BTP STAGE 4 — Frontend / Manual SKU Integration')
    print('  Manual demand file: data/manual_frontend_demand.xlsx')
    print('=' * 70)
    print()

    date_str = input('Enter date (DD.MM.YYYY): ').strip()
    try:
        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
    except ValueError:
        print('❌ Invalid date format. Use DD.MM.YYYY')
        return

    ddmmyyyy   = date_obj.strftime('%d%m%Y')
    stage3_file = f'vector_stage3_{ddmmyyyy}.xlsx'
    output_file = f'vector_stage4_{ddmmyyyy}.xlsx'

    if not os.path.exists(stage3_file):
        print(f'❌ Stage 3 output not found: {stage3_file}')
        return

    # ── Load Stage 3 output ──────────────────────────────────────────────────
    print(f'\nReading Stage 3 output: {stage3_file}')
    xl         = pd.ExcelFile(stage3_file)
    all_sheets = xl.sheet_names
    main_sheet = all_sheets[0]
    df         = xl.parse(main_sheet)
    print(f'  {len(df)} rows loaded')

    # ── Run manual override via existing processor ────────────────────────────
    # process_manual_override expects the stage2 df; it returns a hybrid df
    # with manual rows at the top and re-computed scores.
    print('\n[Stage 4] Integrating manual/frontend demand...')
    try:
        hybrid_df = process_manual_override(df, ddmmyyyy)
    except FileNotFoundError as e:
        print(f'  [WARN] {e}')
        print('  No manual demand file found — using Stage 3 output as-is.')
        hybrid_df = df.copy()

    # ── CPT_Requirement: backend for frontend qty already set by processor,
    #    but ensure Updated_Requirement = CPT_Requirement for Manual SKUs ────
    if 'CPT_Requirement' in hybrid_df.columns and 'Source' in hybrid_df.columns:
        manual_mask = hybrid_df['Source'].str.strip().str.lower() == 'cpt'
        cpt_vals = pd.to_numeric(hybrid_df.loc[manual_mask, 'CPT_Requirement'],
                                 errors='coerce').fillna(0).astype(int)
        hybrid_df.loc[manual_mask, 'Updated_Requirement'] = cpt_vals
        n_manual = manual_mask.sum()
        print(f'  Manual SKUs → Updated_Requirement = CPT_Requirement : {n_manual} rows')

    # ── Re-rank ───────────────────────────────────────────────────────────────
    hybrid_df = _final_rank(hybrid_df)

    # ── SKU Description lookup for history BOR tabs ───────────────────────────
    desc_lookup = {}
    if 'SKU Description' in hybrid_df.columns:
        desc_lookup = (
            hybrid_df.dropna(subset=['SKUCode'])
            .drop_duplicates('SKUCode')
            .set_index('SKUCode')['SKU Description']
            .to_dict()
        )

    # ── History BOR tabs ──────────────────────────────────────────────────────
    from demand_processor import get_history_bor_data
    n_days = config.HISTORY_PENETRATION_N
    print(f'\n[Stage 4] Loading BOR history for last {n_days} days...')
    history_bor = get_history_bor_data(ddmmyyyy, n_days)

    # ── Write output ──────────────────────────────────────────────────────────
    print(f'\nWriting Stage 4 output: {output_file}')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        hybrid_df.to_excel(writer, sheet_name=main_sheet, index=False)
        print(f'  [Tab 1] {main_sheet} — {len(hybrid_df)} rows')

        tabs_written = 0
        for date_label, bor_df in history_bor:
            if bor_df is None or bor_df.empty:
                print(f'  [History Tab] {date_label} — skipped')
                continue
            bor_df = bor_df.copy()
            bor_df['SKU Description'] = bor_df['SKUCode'].map(desc_lookup).fillna('')
            priority_cols = ['SKUCode', 'SKU Description', 'Location Code',
                             'Norm ', 'Virtual Norm', 'Stock', 'Penetration']
            ordered   = [c for c in priority_cols if c in bor_df.columns]
            remaining = [c for c in bor_df.columns if c not in ordered]
            bor_df    = bor_df[ordered + remaining]
            bor_df.to_excel(writer, sheet_name=date_label, index=False)
            tabs_written += 1
            print(f'  [History Tab] {date_label} — {len(bor_df)} rows')

    manual_ct = int((hybrid_df.get('Source', pd.Series([])) == 'Manual').sum()) if 'Source' in hybrid_df.columns else 0
    print(f'\n✅ Stage 4 complete: {output_file}')
    print(f'   Total rows   : {len(hybrid_df)}')
    print(f'   Manual SKUs  : {manual_ct}')
    print(f'   History tabs : {tabs_written} of {n_days}')
    print(f'   Columns      : {len(hybrid_df.columns)}')


if __name__ == '__main__':
    run_stage4()
