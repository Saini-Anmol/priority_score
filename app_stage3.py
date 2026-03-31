# app_stage3.py
# BTP Stage 3: Max-Demand Refinement (oe_demand / avg_sales)
#
# Pipeline:
#   Reads:  vector_stage2_DDMMYYYY.xlsx              (Stage 2 output)
#           data/oe_demand.csv                        (OE dispatch orders)
#           data/avg_sales.csv                        (historical avg sales)
#   Writes: vector_stage3_DDMMYYYY.xlsx
#
# Adds columns:
#   Updated_Requirement = max(ref_data, Requirement) per market rule:
#       OE  → max(oe_demand[sku],     Requirement)
#       RE  → max(avg_sales[(sku,RE)], Requirement)
#       EXP → max(avg_sales[(sku,EXP)], Requirement)
#       Others → Requirement unchanged
#   oe_demand_qty  — lookup value used for OE comparison
#   avg_sales_qty  — lookup value used for RE/EXP comparison

import os
import math
import pandas as pd
from datetime import datetime

import config

AVG_SALES_FILE = os.path.join(config.BASE_DATA_PATH, 'avg_sales.csv')
OE_DEMAND_FILE = os.path.join(config.BASE_DATA_PATH, 'oe_demand.csv')


# ---------------------------------------------------------------------------
# LOADERS
# ---------------------------------------------------------------------------

def _load_avg_sales() -> dict:
    """
    Return {(SKUCode_upper, Market_upper): avg_qty}.
    Handles comma-formatted numbers like '1,056.3' by stripping commas first.
    """
    df = pd.read_csv(AVG_SALES_FILE, header=None, encoding='latin1')

    # Find header row (contains 'Market')
    hdr = None
    for i, row in df.iterrows():
        if any(str(v).strip().lower() == 'market' for v in row):
            hdr = i
            break
    if hdr is None:
        print('  [WARN] avg_sales.csv: could not detect header row')
        return {}

    df.columns = df.iloc[hdr].astype(str).str.strip()
    df = df.iloc[hdr + 1:].reset_index(drop=True)

    # Detect columns
    sku_col = next((c for c in df.columns if 'code' in c.lower() or 'sku' in c.lower()), None)
    mkt_col = next((c for c in df.columns if c.lower() == 'market'), None)
    qty_col = next((c for c in df.columns if 'avg' in c.lower() or 'sale' in c.lower() or 'qty' in c.lower()), None)

    if not all([sku_col, mkt_col, qty_col]):
        print(f'  [WARN] avg_sales.csv: missing columns (sku={sku_col}, mkt={mkt_col}, qty={qty_col})')
        return {}

    df[sku_col] = df[sku_col].astype(str).str.strip().str.upper()
    df[mkt_col] = df[mkt_col].astype(str).str.strip().str.upper()
    # Strip commas from numbers like '1,056.3' before converting
    df[qty_col] = df[qty_col].astype(str).str.replace(',', '', regex=False)
    df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)

    result = {}
    for _, row in df.iterrows():
        k = (row[sku_col], row[mkt_col])
        result[k] = max(result.get(k, 0), row[qty_col])

    print(f'  [AVG SALES] Loaded {len(result)} (SKU, Market) entries from avg_sales.csv')
    return result


def _load_oe_demand() -> dict:
    """Return {SKUCode_upper: dispatch_qty}."""
    df = pd.read_csv(OE_DEMAND_FILE, skiprows=2, header=0, encoding='latin1')
    df.columns = df.columns.str.strip()

    code_col = next((c for c in df.columns if 'product' in c.lower() or 'code' in c.lower()), None)
    qty_col  = next((c for c in df.columns if 'dispatch' in c.lower() or 'qty' in c.lower()), None)

    if not code_col or not qty_col:
        print(f'  [WARN] oe_demand.csv: missing columns (code={code_col}, qty={qty_col})')
        return {}

    df[code_col] = df[code_col].astype(str).str.strip().str.upper()
    df[qty_col]  = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)

    result = {}
    for _, row in df.iterrows():
        result[row[code_col]] = max(result.get(row[code_col], 0), row[qty_col])

    print(f'  [OE DEMAND] Loaded {len(result)} SKU entries from oe_demand.csv')
    return result


# ---------------------------------------------------------------------------
# CORE LOGIC
# ---------------------------------------------------------------------------

def _compute_req(base_req: float, sku: str, market: str,
                 avg_sales: dict, oe_demand: dict) -> int:
    """
    OE  → max(oe_demand[sku], base_req)
    RE  → max(avg_sales[(sku,RE)], base_req)
    EXP → max(avg_sales[(sku,EXP)], base_req)
    Others → base_req unchanged
    """
    candidates = [base_req]

    if market == 'OE':
        oe = oe_demand.get(sku)
        if oe is not None:
            candidates.append(oe)
    elif market == 'RE':
        avg = avg_sales.get((sku, 'RE'))
        if avg is not None:
            candidates.append(avg)
    elif market == 'EXP':
        avg = avg_sales.get((sku, 'EXP'))
        if avg is not None:
            candidates.append(avg)

    return math.ceil(max(candidates))


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def run_stage3():
    print('=' * 70)
    print('  BTP STAGE 3 — Max-Demand Refinement')
    print('  Sources: oe_demand.csv + avg_sales.csv → max(ref, Requirement)')
    print('=' * 70)
    print()

    date_str = input('Enter date (DD.MM.YYYY): ').strip()
    try:
        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
    except ValueError:
        print('❌ Invalid date format. Use DD.MM.YYYY')
        return

    ddmmyyyy    = date_obj.strftime('%d%m%Y')
    stage2_file = f'vector_stage2_{ddmmyyyy}.xlsx'
    output_file = f'vector_stage3_{ddmmyyyy}.xlsx'

    if not os.path.exists(stage2_file):
        print(f'❌ Stage 2 output not found: {stage2_file}')
        return

    for f, label in [(AVG_SALES_FILE, 'avg_sales.csv'), (OE_DEMAND_FILE, 'oe_demand.csv')]:
        if not os.path.exists(f):
            print(f'❌ {label} not found at: {f}')
            return

    print('\nLoading reference files...')
    avg_sales = _load_avg_sales()
    oe_demand = _load_oe_demand()

    print(f'\nReading Stage 2 output: {stage2_file}')
    xl         = pd.ExcelFile(stage2_file)
    all_sheets = xl.sheet_names
    main_sheet = all_sheets[0]
    df         = xl.parse(main_sheet)
    print(f'  Main sheet: {main_sheet}  ({len(df)} rows, {len(all_sheets)} total sheets)')

    if 'Requirement' not in df.columns:
        print('❌ "Requirement" column not found in Stage 2 output.')
        return
    if 'Market' not in df.columns:
        print('❌ "Market" column not found in Stage 2 output.')
        return

    # ── Apply max logic → Updated_Requirement ────────────────────────────────
    updated_reqs = []
    oe_qty_col   = []
    avg_qty_col  = []

    for _, row in df.iterrows():
        sku    = str(row['SKUCode']).strip().upper()
        market = str(row['Market']).strip().upper()
        req    = pd.to_numeric(row.get('Requirement', 0), errors='coerce')
        if pd.isna(req):
            req = 0.0

        oe_val  = oe_demand.get(sku, 0)
        avg_val = avg_sales.get((sku, market), 0)

        updated_reqs.append(_compute_req(req, sku, market, avg_sales, oe_demand))
        oe_qty_col.append(oe_val)
        avg_qty_col.append(round(avg_val, 1))

    df['Updated_Requirement'] = updated_reqs
    df['oe_demand_qty']       = oe_qty_col
    df['avg_sales_qty']       = avg_qty_col

    changed = int((df['Updated_Requirement'] != pd.to_numeric(df['Requirement'], errors='coerce').fillna(0).apply(math.ceil)).sum())
    print(f'\n  SKUs with Updated_Requirement > Requirement : {changed}')
    print(f'  SKUs unchanged                              : {len(df) - changed}')
    print(f'  Added columns: Updated_Requirement, oe_demand_qty, avg_sales_qty')

    # ── Write output — copy all history tabs unchanged ────────────────────────
    print(f'\nWriting Stage 3 output: {output_file}')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=main_sheet, index=False)
        print(f'  [Tab 1] {main_sheet} — {len(df)} rows, {len(df.columns)} columns')

        for sheet in all_sheets[1:]:
            hist_df = xl.parse(sheet)
            hist_df.to_excel(writer, sheet_name=sheet, index=False)
            print(f'  [Copied unchanged] {sheet}')

    print(f'\n✅ Stage 3 complete: {output_file}')
    print(f'   Total rows : {len(df)}')
    print(f'   Columns    : {list(df.columns)}')


if __name__ == '__main__':
    run_stage3()
