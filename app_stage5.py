# app_stage5.py
# BTP Stage 5: Yield Factor — Quality-Adjusted Production Quantity
#
# Pipeline:
#   Reads:  vector_stage4_DDMMYYYY.xlsx  (Stage 4 output)
#   Writes: vector_stage5_DDMMYYYY.xlsx
#
# Applies in-place to Updated_Requirement for OE and EXP markets:
#   Updated_Requirement = ceil(Updated_Requirement / YIELD_FACTOR)
#
# Yield Redistribution:
#   When yield increases OE/EXP requirement for a SKU, and the same SKU
#   also has an RE market row, the yield increase is subtracted from the
#   RE row's Updated_Requirement (floored at 0). If no RE row exists,
#   yield applies normally without any subtraction.
#
# Manual (CPT) SKUs are never adjusted.
# YIELD_FACTOR is read from config.py (default 0.95).

import os
import math
import pandas as pd
from datetime import datetime

import config


def run_stage5():
    print('=' * 70)
    print('  BTP STAGE 5 — Yield Factor Adjustment + RE Redistribution')
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

    # Ensure Updated_Requirement is numeric
    df['Updated_Requirement'] = pd.to_numeric(df['Updated_Requirement'], errors='coerce').fillna(0)

    # ── Build RE row index lookup: {SKUCode → row index of RE market} ─────────
    df['_sku_upper'] = df['SKUCode'].astype(str).str.strip().str.upper()
    df['_mkt_upper'] = df['Market'].astype(str).str.strip().str.upper()

    re_row_index = {}   # SKUCode → DataFrame index of RE row
    for idx, row in df.iterrows():
        if row['_mkt_upper'] == 'RE':
            re_row_index[row['_sku_upper']] = idx

    # ── Apply yield factor to OE/EXP, redistribute to RE ─────────────────────
    changed         = 0
    changed_cpt     = 0
    redistributed   = 0

    for i, row in df.iterrows():
        market = row['_mkt_upper']
        source = str(row.get('Source', 'Vector')).strip()
        upd_req = float(row['Updated_Requirement'])

        # Yield applies to ALL OE/EXP rows (both Vector and CPT sources)
        # CPT quantity is the base (set in Stage 4), yield increases it further
        if market in ('OE', 'EXP') and yield_factor < 1.0 and upd_req > 0:
            new_val   = math.ceil(upd_req / yield_factor)
            increase  = new_val - int(upd_req)

            if increase > 0:
                df.at[i, 'Updated_Requirement'] = new_val
                if source.lower() == 'cpt':
                    changed_cpt += 1
                else:
                    changed += 1

                # Redistribute: subtract 'increase' from same SKU's RE row
                # (only if the RE row is NOT a CPT/manual row — manual reqs are untouchable)
                sku = row['_sku_upper']
                re_idx = re_row_index.get(sku)
                if re_idx is not None:
                    re_source = str(df.at[re_idx, 'Source']).strip().lower() if 'Source' in df.columns else 'vector'
                    if re_source != 'cpt':
                        re_current = float(df.at[re_idx, 'Updated_Requirement'])
                        re_new     = max(0, re_current - increase)
                        df.at[re_idx, 'Updated_Requirement'] = int(re_new)
                        redistributed += 1
                        print(f'    {sku}: OE/EXP +{increase} → RE -{min(increase, int(re_current))}  '
                              f'(RE: {int(re_current)} → {int(re_new)})')
                    else:
                        print(f'    {sku}: OE/EXP +{increase} → RE skip (CPT row, not modified)')

    # Clean up temp columns
    df.drop(columns=['_sku_upper', '_mkt_upper'], inplace=True)

    print(f'\n  Yield factor applied (Vector OE+EXP) : {changed} SKUs')
    print(f'  Yield factor applied (CPT OE+EXP)    : {changed_cpt} SKUs')
    print(f'  RE redistribution (yield offset)     : {redistributed} SKUs')
    print(f'  Other SKUs unchanged                 : {len(df) - changed - changed_cpt}')

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
    print(f'   Redistributed  : {redistributed} SKUs (RE reduced)')
    print(f'   YIELD_FACTOR   : {yield_factor}  →  OE example: 200 → {math.ceil(200/yield_factor)}')


if __name__ == '__main__':
    run_stage5()
