# V1/Reports/stage3_refinement.py
# ---------------------------------------------------------------------------
# STAGE 3: MAX-DEMAND REFINEMENT
# Updates the 'Requirement' column by taking the maximum between Vector Demand,
# OE Dispatch Orders (for OE market), and Average Historical Sales (for RE/EXP).
# ---------------------------------------------------------------------------

import math
import pandas as pd

# Import our modular data loaders
from V1.Utilities.data_loaders import load_avg_sales, load_oe_demand

def _compute_req(base_req: float, stock: float, sku: str, market: str,
                 avg_sales: dict, oe_demand: dict) -> int:
    """
    Core Logic Rules:
      OE  → max(oe_demand[sku] - stock, base_req - stock)
      RE  → max(avg_sales[(sku,RE)] - stock, base_req - stock)
      Others (EXP, Govt, etc.) → base_req unchanged (vector requirement)

    All results are floored at 0 (never negative).
    """
    if market == 'OE':
        oe = oe_demand.get(sku, 0)
        return max(0, math.ceil(max(oe - stock, base_req - stock)))
    elif market == 'RE':
        avg = avg_sales.get((sku, 'RE'), 0)
        return max(0, math.ceil(max(avg - stock, base_req - stock)))
    else:
        # EXP, Govt, and all other markets → vector requirement unchanged
        return math.ceil(base_req)

def run_stage3(stage2_df: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """
    Main orchestration function for Stage 3 Refinement.
    Takes the in-memory Stage 2 DataFrame and applies the Max-Demand logic.
    """
    print(f"\n[Stage 3] Running Max-Demand Refinement for {date_str}...")
    
    # Load reference files using our clean utilities
    avg_sales = load_avg_sales()
    oe_demand = load_oe_demand()

    df = stage2_df.copy()

    if 'Requirement' not in df.columns or 'Market' not in df.columns:
        print('  [ERROR] "Requirement" or "Market" column not found in Stage 2 dataframe.')
        return df

    # Apply max logic to calculate Updated_Requirement
    updated_reqs = []
    oe_qty_col   = []
    avg_qty_col  = []

    for _, row in df.iterrows():
        sku    = str(row['SKUCode']).strip().upper()
        market = str(row['Market']).strip().upper()
        req    = pd.to_numeric(row.get('Requirement', 0), errors='coerce')
        stock  = pd.to_numeric(row.get('Stock', 0), errors='coerce')
        
        if pd.isna(req): req = 0.0
        if pd.isna(stock): stock = 0.0

        oe_val  = oe_demand.get(sku, 0)
        avg_val = avg_sales.get((sku, market), 0)

        updated_reqs.append(_compute_req(req, stock, sku, market, avg_sales, oe_demand))
        oe_qty_col.append(oe_val)
        avg_qty_col.append(round(avg_val, 1))

    df['Updated_Requirement'] = updated_reqs
    df['oe_demand_qty']       = oe_qty_col
    df['avg_sales_qty']       = avg_qty_col

    changed = int((df['Updated_Requirement'] != pd.to_numeric(df['Requirement'], errors='coerce').fillna(0).apply(math.ceil)).sum())
    
    print(f"  - SKUs with Updated_Requirement > Requirement : {changed}")
    print(f"  - SKUs unchanged                              : {len(df) - changed}")

    return df