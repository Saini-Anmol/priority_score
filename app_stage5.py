# app_stage5.py
# BTP Stage 5: Yield Factor — Quality-Adjusted Production Quantity
#
# Pipeline:
#   Reads:  vector_stage4_DDMMYYYY.xlsx  (Stage 4 output)
#   Writes: vector_stage5_DDMMYYYY.xlsx
#
# Applies in-place to Updated_Requirement for OE and EXP markets:
#   Updated_Requirement = ceil(Updated_Requirement / YIELD_FACTOR)
# Manual SKUs are never adjusted.
# YIELD_FACTOR is read from config.py (default 0.95).

import os
import math
import pandas as pd
from datetime import datetime

import config


def run_stage5():
    print('=' * 70)
    print('  BTP STAGE 5 — Yield Factor Adjustment')
    print(f'  Yield Factor: {config.YIELD_FACTOR}  (markets: OE, EXP only)')
    print('=' * 70)
    print()

    date_str = input('Enter date (DD.MM.YYYY): ').strip()
    try:
        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
    except ValueError:
        print('❌ Invalid date format. Use DD.MM.YYYY')
        return

    ddmmyyyy   = date_obj.strftime('%d%m%Y')
    stage4_file = f'vector_stage4_{ddmmyyyy}.xlsx'
    output_file = f'vector_stage5_{ddmmyyyy}.xlsx'

    if not os.path.exists(stage4_file):
        print(f'❌ Stage 4 output not found: {stage4_file}')
        return

    print(f'\nReading Stage 4 output: {stage4_file}')
    xl         = pd.ExcelFile(stage4_file)
    all_sheets = xl.sheet_names
    main_sheet = all_sheets[0]
    df         = xl.parse(main_sheet)
    print(f'  {len(df)} rows loaded')

    for req in ['Updated_Requirement', 'Market']:
        if req not in df.columns:
            print(f'❌ Required column "{req}" not found in Stage 4 output.')
            return

    yield_factor = config.YIELD_FACTOR
    if yield_factor <= 0 or yield_factor > 1:
        print(f'❌ Invalid YIELD_FACTOR={yield_factor}. Must be between 0 and 1.')
        return

    changed        = 0
    skipped_manual = 0
    for i, row in df.iterrows():
        market = str(row['Market']).strip().upper()
        source = str(row.get('Source', 'Automated')).strip()
        upd_req = pd.to_numeric(row['Updated_Requirement'], errors='coerce')

        if pd.isna(upd_req):
            upd_req = 0.0

        # Manual SKUs: never adjust
        if source.lower() == 'cpt':
            skipped_manual += 1
            continue

        if market in ('OE', 'EXP') and yield_factor < 1.0:
            new_val = math.ceil(upd_req / yield_factor)
            if new_val != upd_req:
                df.at[i, 'Updated_Requirement'] = new_val
                changed += 1

    print(f'\n  Yield factor applied  (OE+EXP)    : {changed} SKUs')
    print(f'  Manual SKUs kept unchanged        : {skipped_manual}')
    print(f'  Other SKUs unchanged              : {len(df) - changed - skipped_manual}')

    # Write output — copy all history tabs unchanged
    print(f'\nWriting Stage 5 output: {output_file}')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=main_sheet, index=False)
        for sheet in all_sheets[1:]:
            hist_df = xl.parse(sheet)
            hist_df.to_excel(writer, sheet_name=sheet, index=False)
            print(f'  [Copied unchanged] {sheet}')

    print(f'\n✅ Stage 5 complete: {output_file}')
    print(f'   Final rows     : {len(df)}')
    print(f'   Yield-adjusted : {changed} SKUs')
    print(f'   YIELD_FACTOR   : {yield_factor}  →  OE example: 200 → {math.ceil(200/yield_factor)}')


if __name__ == '__main__':
    run_stage5()
