# CTP/ctp_app_stage4.py
# CTP Stage 4: Updated_Requirement Refinement
#
# Reads CTP Stage 3 output (CTP_frontend_running_demand_DDMMYYYY.xlsx) and
# updates ONLY the Updated_Requirement column using:
#
#   OE  market  → max(Stage3_Updated_Req, avg_sales[SKU,OE],  oe_dispatch[SKU])
#   RE  market  → max(Stage3_Updated_Req, avg_sales[SKU,RE])
#   EXP market  → max(Stage3_Updated_Req, avg_sales[SKU,EXP])
#   All others  → Stage3_Updated_Req unchanged
#
# If a SKU is not found in any reference file → keep Stage3 value.
# Both PCR and TBR sheets are updated. History tabs are copied unchanged.
#
# Output: CTP/CTP_stage4_running_demand_DDMMYYYY.xlsx

import os
import sys
import math
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------------------------
# PATH SETUP
# ---------------------------------------------------------------------------
_CTP_DIR      = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CTP_DIR)

if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _CTP_DIR not in sys.path:
    sys.path.insert(0, _CTP_DIR)

os.chdir(_PROJECT_ROOT)

AVG_SALES_FILE  = os.path.join(_CTP_DIR, "data", "avg_sales.csv")
OE_DEMAND_FILE  = os.path.join(_CTP_DIR, "data", "oe_demand.csv")

# ---------------------------------------------------------------------------
# LOADERS
# ---------------------------------------------------------------------------

def _load_avg_sales() -> dict:
    """
    Load CTP avg_sales.csv and return {(SKUCode_str, market_upper): avg_qty}.
    Market values normalised to uppercase.
    Auto-detects header row by finding 'Market'.
    """
    if not os.path.exists(AVG_SALES_FILE):
        return {}

    raw = pd.read_csv(AVG_SALES_FILE, encoding="latin1", header=None)
    header_row = None
    for i, row in raw.iterrows():
        if row.astype(str).str.contains('Market', case=False).any():
            header_row = i
            break

    if header_row is None:
        print("  [WARN] Could not detect header row in CTP avg_sales.csv — skipping")
        return {}

    df = pd.read_csv(AVG_SALES_FILE, encoding="latin1", skiprows=header_row, header=0)
    df.columns = df.columns.str.strip()

    # Find columns robustly
    sku_col = next((c for c in df.columns if 'sku' in c.lower() or 'code' in c.lower()), df.columns[0])
    mkt_col = next((c for c in df.columns if 'market' in c.lower()), None)
    avg_col = next((c for c in df.columns if 'avg' in c.lower() or 'sales' in c.lower()), None)

    if mkt_col is None or avg_col is None:
        print(f"  [WARN] CTP avg_sales.csv columns not recognised: {list(df.columns)}")
        return {}

    df[sku_col] = df[sku_col].astype(str).str.strip().str.upper()
    df[mkt_col] = df[mkt_col].astype(str).str.strip().str.upper()

    df["_avg"] = (
        df[avg_col].astype(str)
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )

    result = {}
    for _, row in df.iterrows():
        sku = row[sku_col]
        mkt = row[mkt_col]
        val = row["_avg"]
        if not sku or sku in ("nan", "NaN", ""):
            continue
        if pd.isna(val) or val <= 0:
            continue
        result[(sku, mkt)] = val

    print(f"  [AVG SALES]  Loaded {len(result)} (SKU, Market) entries from CTP avg_sales.csv")
    return result


def _load_oe_demand() -> dict:
    """
    Load CTP oe_demand.csv and return {SKUCode_str: dispatch_qty}.
    Auto-detects header by looking for 'PRODUCT CODE' or 'Item Code'.
    """
    if not os.path.exists(OE_DEMAND_FILE):
        return {}

    raw = pd.read_csv(OE_DEMAND_FILE, encoding="latin1", header=None)
    header_row = None
    for i, row in raw.iterrows():
        if row.astype(str).str.contains('CODE', case=False).any():
            header_row = i
            break

    if header_row is None:
        print("  [WARN] Could not detect header row in CTP oe_demand.csv — skipping")
        return {}

    df = pd.read_csv(OE_DEMAND_FILE, skiprows=header_row, header=0, encoding="latin1")
    df.columns = df.columns.str.strip()

    sku_col = next((c for c in df.columns if 'code' in c.lower() or 'product' in c.lower()), None)
    qty_col = next((c for c in df.columns if 'dispatch' in c.lower() or 'req' in c.lower()), None)

    if not sku_col or not qty_col:
        print(f"  [WARN] CTP oe_demand.csv columns not recognised: {list(df.columns)}")
        return {}

    df[sku_col] = df[sku_col].astype(str).str.strip().str.upper()
    df[qty_col] = pd.to_numeric(df[qty_col], errors="coerce")

    result = {}
    for _, row in df.iterrows():
        sku = row[sku_col]
        val = row[qty_col]
        if not sku or sku == "nan" or sku == "NAN":
            continue
        if pd.isna(val) or val <= 0:
            continue
        result[sku] = val

    print(f"  [OE DEMAND]  Loaded {len(result)} SKU entries from CTP oe_demand.csv")
    return result


# ---------------------------------------------------------------------------
# CORE LOGIC
# ---------------------------------------------------------------------------

def _compute_updated_req(stage3_val: float, sku: str, market: str,
                         avg_sales: dict, oe_demand: dict) -> float:
    """Refine Updated_Requirement based on max of candidates."""
    candidates = [stage3_val]
    market_upper = str(market).strip().upper()

    if market_upper == "OE":
        avg = avg_sales.get((sku, "OE"))
        oe  = oe_demand.get(sku)
        if avg is not None:
            candidates.append(avg)
        if oe is not None:
            candidates.append(oe)

    elif market_upper in ("RE", "EXP"):
        avg = avg_sales.get((sku, market_upper))
        if avg is not None:
            candidates.append(avg)

    return math.ceil(max(candidates))


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def run_ctp_stage4():
    print("=" * 70)
    print("  CTP STAGE 4 — Updated_Requirement Refinement")
    print("  Plant: 1900  |  Tyre Types: PCR + TBR")
    print("  Sources: CTP avg_sales.csv + oe_demand.csv → max per market rule")
    print("=" * 70)
    print()

    date_str = input("Enter date of CTP Stage 3 output (DD.MM.YYYY): ").strip()
    try:
        date = datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        print("❌ Invalid date format. Use DD.MM.YYYY")
        return

    ddmmyyyy   = date.strftime("%d%m%Y")
    stage3_file = os.path.join(_CTP_DIR, f"CTP_frontend_running_demand_{ddmmyyyy}.xlsx")

    if not os.path.exists(stage3_file):
        print(f"❌ CTP Stage 3 output not found: {stage3_file}")
        return

    # --- Load reference files ---
    print("\nLoading reference files...")
    avg_sales = _load_avg_sales()
    oe_demand = _load_oe_demand()

    # --- Load sheets from Stage 3 Excel ---
    print(f"\nReading CTP Stage 3 output: {os.path.basename(stage3_file)}")
    xl = pd.ExcelFile(stage3_file)
    all_sheets = xl.sheet_names

    pcr_sheets = [s for s in all_sheets if str(s).upper().startswith("PCR")]
    tbr_sheets = [s for s in all_sheets if str(s).upper().startswith("TBR")]
    history_sheets = [s for s in all_sheets if s not in pcr_sheets and s not in tbr_sheets]

    out_file = os.path.join(_CTP_DIR, f"CTP_stage4_running_demand_{ddmmyyyy}.xlsx")
    print(f"\nWriting CTP Stage 4 output: {os.path.basename(out_file)}")

    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        
        # Process PCR and TBR sheets
        total_changed = 0
        for sheet in (pcr_sheets + tbr_sheets):
            print(f"\n  Processing sheet: '{sheet}'")
            df = xl.parse(sheet)

            if "Updated_Requirement" not in df.columns:
                print(f"    [WARN] 'Updated_Requirement' not found in {sheet}. Copying unchanged.")
                df.to_excel(writer, sheet_name=sheet, index=False)
                continue

            changed = 0
            for i, row in df.iterrows():
                sku        = str(row.get("SKUCode", "")).strip().upper()
                market     = str(row.get("Market", "")).strip().upper()
                stage3_val = pd.to_numeric(row["Updated_Requirement"], errors="coerce")

                if pd.isna(stage3_val):
                    stage3_val = 0.0

                new_val = _compute_updated_req(stage3_val, sku, market, avg_sales, oe_demand)

                if new_val != stage3_val:
                    df.at[i, "Updated_Requirement"] = new_val
                    changed += 1

            total_changed += changed
            print(f"    Rows updated (value changed from Stage 3) : {changed}")
            print(f"    Rows unchanged                            : {len(df) - changed}")
            
            df.to_excel(writer, sheet_name=sheet, index=False)

        # Copy History Tabs
        for sheet in history_sheets:
            hist_df = xl.parse(sheet)
            hist_df.to_excel(writer, sheet_name=sheet, index=False)
            print(f"\n  [Copied unchanged] History Tab: '{sheet}'")

    print(f"\n✅ CTP Stage 4 complete: {os.path.basename(out_file)}")
    print(f"   Total rows updated across PCR & TBR: {total_changed}")
    print()

# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_ctp_stage4()
