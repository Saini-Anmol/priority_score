# V1/Reports/stage5_yield.py
# ---------------------------------------------------------------------------
# STAGE 5: YIELD FACTOR ADJUSTMENT
# Applies in-place to Updated_Requirement for OE and EXP markets:
#   Updated_Requirement = ceil(Updated_Requirement / YIELD_FACTOR)
#
# Yield Redistribution:
#   When yield increases OE/EXP requirement for a SKU, and the same SKU
#   also has an RE market row, the yield increase is subtracted from the
#   RE row's Updated_Requirement (floored at 0). 
# ---------------------------------------------------------------------------

import math
import pandas as pd

# Import configuration
import V1.Setups.config as config

def run_stage5(df: pd.DataFrame) -> pd.DataFrame:
    """
    Main orchestration function for Stage 5 Yield Adjustment.
    Takes the in-memory Stage 4 DataFrame and returns the Final output DataFrame.
    """
    print(f"\n[Stage 5] Applying Yield Factor Adjustment (OE/EXP only)...")
    print(f"  - Yield Factor: {config.YIELD_FACTOR}")

    if 'Updated_Requirement' not in df.columns or 'Market' not in df.columns:
        print('  [ERROR] Required columns not found in Stage 4 dataframe.')
        return df

    yield_factor = config.YIELD_FACTOR
    if yield_factor <= 0 or yield_factor > 1:
        print(f'  [ERROR] Invalid YIELD_FACTOR={yield_factor}. Must be between 0 and 1.')
        return df

    # Ensure Updated_Requirement is numeric
    df['Updated_Requirement'] = pd.to_numeric(df['Updated_Requirement'], errors='coerce').fillna(0)

    # Build RE row index lookup: {SKUCode → row index of RE market}
    df['_sku_upper'] = df['SKUCode'].astype(str).str.strip().str.upper()
    df['_mkt_upper'] = df['Market'].astype(str).str.strip().str.upper()

    re_row_index = {}
    for idx, row in df.iterrows():
        if row['_mkt_upper'] == 'RE':
            re_row_index[row['_sku_upper']] = idx

    # Apply yield factor to OE/EXP, redistribute to RE
    changed         = 0
    changed_cpt     = 0
    redistributed   = 0

    for i, row in df.iterrows():
        market = row['_mkt_upper']
        source = str(row.get('Source', 'Vector')).strip()
        upd_req = float(row['Updated_Requirement'])

        # Yield applies to ALL OE/EXP rows (both Vector and CPT sources)
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
                    else:
                        pass # Skip redistribution if the RE row is a manual CPT override

    # Clean up temp columns
    df.drop(columns=['_sku_upper', '_mkt_upper'], inplace=True)

    print(f'  - Yield factor applied (Vector OE+EXP) : {changed} SKUs')
    print(f'  - Yield factor applied (CPT OE+EXP)    : {changed_cpt} SKUs')
    print(f'  - RE redistribution (yield offset)     : {redistributed} SKUs')
    
    return df