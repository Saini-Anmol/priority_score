# V1/Utilities/data_loaders.py
# ---------------------------------------------------------------------------
# REFERENCE DATA LOADERS
# Holds the logic to load avg_sales.csv, oe_demand.csv, and historical BOR files.
# ---------------------------------------------------------------------------

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import paths from our centralized config
from V1.Setups.config import BASE_DATA_PATH

AVG_SALES_FILE = os.path.join(BASE_DATA_PATH, 'avg_sales.csv')
OE_DEMAND_FILE = os.path.join(BASE_DATA_PATH, 'oe_demand.csv')

def load_avg_sales() -> dict:
    """
    Load avg_sales.csv and return {(SKUCode_upper, Market_upper): avg_qty}.
    Market values are normalised to uppercase (Exp → EXP, OE → OE, RE → RE).
    
    Robustness added:
    - Auto-detects header row regardless of how many title rows the file has.
    - Handles comma-formatted numbers like '1,056.3' by stripping commas first.
    - Rows with missing SKU or missing/zero avg sales are skipped.
    """
    if not os.path.exists(AVG_SALES_FILE):
        print(f"  [WARN] avg_sales.csv not found at: {AVG_SALES_FILE}")
        return {}

    # Auto-detect header row: find the row that contains 'Market' keyword
    raw = pd.read_csv(AVG_SALES_FILE, encoding="latin1", header=None)
    header_row = None
    for i, row in raw.iterrows():
        if row.astype(str).str.contains('Market', case=False).any():
            header_row = i
            break

    if header_row is None:
        print("  [WARN] Could not detect header row in avg_sales.csv — skipping")
        return {}

    df = pd.read_csv(AVG_SALES_FILE, encoding="latin1", skiprows=header_row, header=0)
    df.columns = df.columns.str.strip()

    # Detect columns dynamically by partial name match (robust to minor name changes)
    sku_col = next((c for c in df.columns if 'code' in c.lower() or 'sku' in c.lower()), None)
    mkt_col = next((c for c in df.columns if c.lower() == 'market'), None)
    qty_col = next((c for c in df.columns if 'avg' in c.lower() or 'sale' in c.lower() or 'qty' in c.lower()), None)

    if not all([sku_col, mkt_col, qty_col]):
        print(f'  [WARN] avg_sales.csv: missing columns (sku={sku_col}, mkt={mkt_col}, qty={qty_col})')
        return {}

    df[sku_col] = df[sku_col].astype(str).str.strip().str.upper()
    df[mkt_col] = df[mkt_col].astype(str).str.strip().str.upper()
    
    # Strip commas from numbers like '1,056.3' before converting to numeric
    df[qty_col] = df[qty_col].astype(str).str.replace(',', '', regex=False)
    df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)

    result = {}
    for _, row in df.iterrows():
        sku = row[sku_col]
        mkt = row[mkt_col]
        val = row[qty_col]
        
        if not sku or sku in ("nan", "NaN", ""):
            continue
            
        # Store maximum value if duplicates exist
        result[(sku, mkt)] = max(result.get((sku, mkt), 0), val)

    print(f'  [AVG SALES] Loaded {len(result)} (SKU, Market) entries from avg_sales.csv')
    return result


def load_oe_demand() -> dict:
    """
    Load oe_demand.csv and return {SKUCode_upper: dispatch_qty}.
    All rows treated as OE market.
    Rows with missing PRODUCT CODE or missing Dispatch are skipped.
    """
    if not os.path.exists(OE_DEMAND_FILE):
        print(f"  [WARN] oe_demand.csv not found at: {OE_DEMAND_FILE}")
        return {}

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
        sku = row[code_col]
        val = row[qty_col]
        
        if not sku or sku == "nan":
            continue
            
        result[sku] = max(result.get(sku, 0), val)

    print(f'  [OE DEMAND] Loaded {len(result)} SKU entries from oe_demand.csv')
    return result


def get_history_bor_data(date_str: str, n: int, plant_prefix: str = '1300') -> list:
    """
    Load and return raw BOR data for the last N days (today + N-1 historical).
    Used by the excel_writer to write per-day penetration tabs in the final output Excel.
    
    For each day:
        - Reads BORColorBandwiseReport__DD-MM-YYYY.csv from the BOR folder.
        - Filters to Location Code starting with plant_prefix (default '1300').
        - Computes Penetration = (Virtual Norm - Stock) / Virtual Norm * 100.
        - Missing files (weekends / holidays) → (date_label, None) in the result, 
          leaving the streak intact.
    """
    today  = datetime.strptime(date_str, "%d%m%Y")
    result = []

    for day_offset in range(n):           # 0 = today, 1 = yesterday, …
        past_date  = today - timedelta(days=day_offset)
        date_label = past_date.strftime("%d-%m-%Y")
        bor_path   = os.path.join(BASE_DATA_PATH, 'Vectordata', 'BOR', f'BORColorBandwiseReport__{date_label}.csv')

        if not os.path.exists(bor_path):
            result.append((date_label, None))
            continue

        try:
            df = pd.read_csv(bor_path)
            df['SKUCode'] = df['SKUCode'].astype(str)

            # Filter to plant locations only
            if 'Location Code' in df.columns:
                df = df[df['Location Code'].str.startswith(plant_prefix)].copy()

            # Compute Penetration from raw columns (same formula as Stage 1 / 2)
            if 'Virtual Norm' in df.columns and 'Stock' in df.columns:
                df['Penetration'] = np.where(
                    df['Virtual Norm'] == 0, 0,
                    (df['Virtual Norm'] - df['Stock']) / df['Virtual Norm'] * 100
                )

            # Keep only the columns useful for the history tab
            keep = ['SKUCode', 'Location Code', 'Norm ', 'Virtual Norm', 'Stock', 'Penetration']
            keep = [c for c in keep if c in df.columns]
            result.append((date_label, df[keep].reset_index(drop=True)))

        except Exception as exc:
            print(f"  [HISTORY BOR] Could not read {bor_path}: {exc}")
            result.append((date_label, None))

    return result