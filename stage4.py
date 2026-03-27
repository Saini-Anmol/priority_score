# stage4.py
# Stage 4: Updated_Requirement Refinement
#
# Reads Stage 3 output (vector_frontend_running_demand_DDMMYYYY.xlsx) and
# updates ONLY the Updated_Requirement column using:
#
#   OE  market  → max(Stage3_Updated_Req, avg_sales[SKU,OE],  oe_dispatch[SKU])
#   RE  market  → max(Stage3_Updated_Req, avg_sales[SKU,RE])
#   EXP market  → max(Stage3_Updated_Req, avg_sales[SKU,EXP])
#   All others  → Stage3_Updated_Req unchanged
#
# If a SKU is not found in any reference file → keep Stage3 value.
# All other columns and sheets are written unchanged.
#
# Output: vector_stage4_running_demand_DDMMYYYY.xlsx (same folder as Stage 3)

import os
import math
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
BASE_DATA_PATH  = "./data"
AVG_SALES_FILE  = os.path.join(BASE_DATA_PATH, "avg_sales.csv")
OE_DEMAND_FILE  = os.path.join(BASE_DATA_PATH, "oe_demand.csv")


# ---------------------------------------------------------------------------
# LOADERS
# ---------------------------------------------------------------------------

def _load_avg_sales() -> dict:
    """
    Load avg_sales.csv and return {(SKUCode_str, market_upper): avg_qty}.
    Market values normalised to uppercase (Exp → EXP, OE → OE, RE → RE).
    Rows with missing SKU or missing/zero avg sales are skipped.
    Auto-detects header row regardless of how many title rows the file has.
    """
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

    # Find columns by partial name match (robust to minor name changes)
    sku_col = next((c for c in df.columns if 'sku' in c.lower() or 'code' in c.lower()), df.columns[0])
    mkt_col = next((c for c in df.columns if 'market' in c.lower()), None)
    avg_col = next((c for c in df.columns if 'avg' in c.lower() or 'sales' in c.lower()), None)

    if mkt_col is None or avg_col is None:
        print(f"  [WARN] avg_sales.csv columns not recognised: {list(df.columns)}")
        return {}

    df[sku_col] = df[sku_col].astype(str).str.strip()
    df[mkt_col] = df[mkt_col].astype(str).str.strip().str.upper()

    # Handle comma-formatted numbers e.g. "1,204.67"
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

    print(f"  [AVG SALES]  Loaded {len(result)} (SKU, Market) entries from avg_sales.csv")
    return result



def _load_oe_demand() -> dict:
    """
    Load oe_demand.csv and return {SKUCode_str: dispatch_qty}.
    All rows treated as OE market.
    Rows with missing PRODUCT CODE or missing Dispatch are skipped.
    """
    df = pd.read_csv(OE_DEMAND_FILE, skiprows=2, header=0, encoding="latin1")

    sku_col  = "PRODUCT CODE"
    qty_col  = "Dispatch"

    df[sku_col] = df[sku_col].astype(str).str.strip()
    df[qty_col] = pd.to_numeric(df[qty_col], errors="coerce")

    result = {}
    for _, row in df.iterrows():
        sku = row[sku_col]
        val = row[qty_col]
        if not sku or sku == "nan":
            continue
        if pd.isna(val) or val <= 0:
            continue
        result[sku] = val

    print(f"  [OE DEMAND]  Loaded {len(result)} SKU entries from oe_demand.csv")
    return result


# ---------------------------------------------------------------------------
# CORE LOGIC
# ---------------------------------------------------------------------------

def _compute_updated_req(stage3_val: float, sku: str, market: str,
                         avg_sales: dict, oe_demand: dict) -> float:
    """
    Return the refined Updated_Requirement for one row.

    Rules:
      OE  market → max(Stage3_Updated_Req, oe_demand[SKU])
                   (avg_sales NOT used for OE; Ghost SKUs in oe_demand are
                    already corrected to OE by Stage 3)
      RE  market → max(Stage3_Updated_Req, avg_sales[SKU,RE])
      EXP market → max(Stage3_Updated_Req, avg_sales[SKU,EXP])
      All others → Stage3_Updated_Req unchanged

    market is already uppercased by the caller.
    """
    candidates = [stage3_val]

    if market == "OE":
        # OE: use oe_demand only — NOT avg_sales
        oe = oe_demand.get(sku)
        if oe is not None:
            candidates.append(oe)

    elif market == "RE":
        # RE: use avg_sales only — Ghost SKUs in oe_demand already corrected to OE by Stage 3
        avg = avg_sales.get((sku, "RE"))
        if avg is not None:
            candidates.append(avg)

    elif market == "EXP":
        avg = avg_sales.get((sku, "EXP"))
        if avg is not None:
            candidates.append(avg)

    # All other markets (ST, OTR, GHOST, etc.) → stage3_val unchanged
    return math.ceil(max(candidates))


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def run_stage4():
    print("=" * 70)
    print("  STAGE 4 — Updated_Requirement Refinement")
    print("  Sources: avg_sales.csv  +  oe_demand.csv  →  max per market rule")
    print("=" * 70)
    print()

    date_str = input("Enter date of Stage 3 output (DD.MM.YYYY): ").strip()
    try:
        date = datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        print("❌ Invalid date format. Use DD.MM.YYYY")
        return

    ddmmyyyy   = date.strftime("%d%m%Y")
    stage3_file = f"vector_frontend_running_demand_{ddmmyyyy}.xlsx"

    if not os.path.exists(stage3_file):
        print(f"❌ Stage 3 output not found: {stage3_file}")
        return

    # --- Load reference files ---
    print("\nLoading reference files...")
    if not os.path.exists(AVG_SALES_FILE):
        print(f"❌ avg_sales.csv not found at: {AVG_SALES_FILE}")
        return
    if not os.path.exists(OE_DEMAND_FILE):
        print(f"❌ oe_demand.csv not found at: {OE_DEMAND_FILE}")
        return

    avg_sales = _load_avg_sales()
    oe_demand = _load_oe_demand()

    # --- Load ALL sheets from Stage 3 Excel ---
    print(f"\nReading Stage 3 output: {stage3_file}")
    xl        = pd.ExcelFile(stage3_file)
    all_sheets = xl.sheet_names
    main_sheet = all_sheets[0]   # First sheet = Stage 3 main output

    print(f"  Main sheet : '{main_sheet}'  ({len(all_sheets)} total sheets)")

    df = xl.parse(main_sheet)

    # --- Validate required columns ---
    for req in ["SKUCode", "Market", "Updated_Requirement"]:
        if req not in df.columns:
            print(f"❌ Column '{req}' not found in Stage 3 output. Cannot proceed.")
            return

    # --- Update Updated_Requirement ---
    upd_col_idx = list(df.columns).index("Updated_Requirement")
    print(f"\n  'Updated_Requirement' is column index {upd_col_idx} "
          f"(Excel col {chr(65 + upd_col_idx) if upd_col_idx < 26 else chr(64 + upd_col_idx // 26) + chr(65 + upd_col_idx % 26)})")

    changed  = 0
    skipped_manual = 0
    for i, row in df.iterrows():
        sku        = str(row["SKUCode"]).strip()
        market     = str(row["Market"]).strip().upper()
        source     = str(row.get("Source", "Automated")).strip()
        stage3_val = pd.to_numeric(row["Updated_Requirement"], errors="coerce")

        if pd.isna(stage3_val):
            stage3_val = 0.0

        # --- Frontend (Manual) SKUs: keep Updated_Requirement exactly as Stage 3 ---
        if source.lower() == "manual":
            skipped_manual += 1
            continue

        new_val = _compute_updated_req(stage3_val, sku, market, avg_sales, oe_demand)

        if new_val != stage3_val:
            df.at[i, "Updated_Requirement"] = new_val
            changed += 1

    print(f"  Manual (frontend) SKUs — kept unchanged : {skipped_manual}")
    print(f"  Automated SKUs updated (value changed)  : {changed}")
    print(f"  Automated SKUs unchanged                : {len(df) - changed - skipped_manual}")

    # --- Add reference columns: oe_demand_qty and avg_sales_qty ---
    # These are informational columns appended at the end (AJ, AK)
    def _get_oe_qty(row):
        sku = str(row["SKUCode"]).strip().upper()
        val = oe_demand.get(sku)
        return val if val is not None else 0

    def _get_avg_sales_qty(row):
        sku = str(row["SKUCode"]).strip().upper()
        mkt = str(row["Market"]).strip().upper()
        # Try market-specific first, then any market for this SKU
        val = avg_sales.get((sku, mkt))
        return round(val, 1) if val is not None else 0

    df["oe_demand_qty"]  = df.apply(_get_oe_qty, axis=1)
    df["avg_sales_qty"]  = df.apply(_get_avg_sales_qty, axis=1)
    print(f"\n  Added columns: 'oe_demand_qty' (AJ), 'avg_sales_qty' (AK)")

    # --- Write output — same structure, same sheets ---
    out_file = f"vector_stage4_running_demand_{ddmmyyyy}.xlsx"
    print(f"\nWriting Stage 4 output: {out_file}")

    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        # Main sheet — updated
        df.to_excel(writer, sheet_name=main_sheet, index=False)

        # All history/other sheets — copied unchanged
        for sheet in all_sheets[1:]:
            hist_df = xl.parse(sheet)
            hist_df.to_excel(writer, sheet_name=sheet, index=False)
            print(f"  [Copied unchanged] Sheet: '{sheet}'")

    print(f"\n✅ Stage 4 complete: {out_file}")
    print(f"   Columns        : {len(df.columns)}  (Stage 3 cols + oe_demand_qty + avg_sales_qty)")
    print(f"   Rows           : {len(df)}")
    print(f"   Updated_Req col: index {upd_col_idx} (unchanged position)")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_stage4()
