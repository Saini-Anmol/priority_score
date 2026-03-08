# ctp_demand_processor.py
# CTP Stage 1 Processing Engine — Plant 1900 (PCR + TBR)
#
# Mirrors BTP demand_processor.py logic exactly, with these differences:
#   1. Plant filter: Location Code.startswith('1900') and Plant Code == '1900'
#   2. ASP source:   CTP TYRE DESPATCH DEC 24 TO NOV 25.XLSX (Plant 1900 only)
#   3. Cure time:    PCR Curing cycle time.xlsx + TBR curing cycle time.xlsx (merged)
#   4. SKU split:    PCR SKUs from SKU_List.xlsx; TBR = everything else
#   5. Output:       Returns (pcr_df, tbr_df) tuple — two separate DataFrames

import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# PATH SETUP — allow running from project root OR from CTP/ subfolder
# ---------------------------------------------------------------------------
_CTP_DIR = os.path.dirname(os.path.abspath(__file__))
if _CTP_DIR not in sys.path:
    sys.path.insert(0, _CTP_DIR)

import ctp_config as config


# ---------------------------------------------------------------------------
# MIN-MAX NORMALISATION HELPER
# ---------------------------------------------------------------------------

def _minmax(series: pd.Series) -> pd.Series:
    """
    Min-max normalize a Series to [0, 1].
    Formula: (x - min) / (max - min)
    Returns 0.0 everywhere when max == min (avoids division by zero).
    """
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.0, index=series.index)
    return (series - mn) / (mx - mn)


# ---------------------------------------------------------------------------
# CURE TIME LOADER
# ---------------------------------------------------------------------------

def _load_cure_time() -> pd.DataFrame:
    """
    Load and merge PCR and TBR cure time files into a single DataFrame
    with columns [SKUCode, Cure Time].

    PCR file format (header row 2):
        Columns: Unnamed:0 | Curing code | GT Code | Product name | Cure time

    TBR file format (header row 1, skip row 0 which is blank):
        Columns: SL NO. | SAP CODE | PRODUCT CODE | RECIPE CODE | TYRE SIZE | TOTAL CURE TIME
    """
    frames = []

    # --- PCR ---
    try:
        pcr = pd.read_excel(config.PCR_CURE_FILE, header=2)
        # After header=2, real data starts. Columns are positional.
        # Col index 1 = Curing code, Col index 2 = GT Code (SKUCode alias),
        # Col index 4 = Cure time
        # We use GT Code (index 2) as SKUCode since it's the SAP material code.
        # Rename columns by position for robustness
        pcr.columns = ['_drop0', 'CuringCode', 'SKUCode', 'ProductName', 'Cure Time']
        pcr = pcr[['SKUCode', 'Cure Time']].dropna(subset=['SKUCode', 'Cure Time'])
        pcr['SKUCode'] = pcr['SKUCode'].astype(str).str.strip()
        pcr['Cure Time'] = pd.to_numeric(pcr['Cure Time'], errors='coerce')
        pcr['_type'] = 'PCR'
        frames.append(pcr)
        print(f"  [Cure Time] PCR: {len(pcr)} entries loaded.")
    except Exception as e:
        print(f"  [WARN] Could not load PCR cure time file: {e}")

    # --- TBR ---
    try:
        tbr = pd.read_excel(config.TBR_CURE_FILE, header=0)
        # Column positions: 0=SL NO, 1=SAP CODE (=SKUCode), 5=TOTAL CURE TIME
        tbr.columns = ['SL_NO', 'SKUCode', 'ProductCode', 'RecipeCode', 'TyreSize', 'Cure Time']
        tbr = tbr[['SKUCode', 'Cure Time']].dropna(subset=['SKUCode', 'Cure Time'])
        tbr['SKUCode'] = tbr['SKUCode'].astype(str).str.strip()
        tbr['Cure Time'] = pd.to_numeric(tbr['Cure Time'], errors='coerce')
        tbr['_type'] = 'TBR'
        frames.append(tbr)
        print(f"  [Cure Time] TBR: {len(tbr)} entries loaded.")
    except Exception as e:
        print(f"  [WARN] Could not load TBR cure time file: {e}")

    if not frames:
        print("  [WARN] No cure time data loaded. Using DEFAULT_CURE_TIME for all SKUs.")
        return pd.DataFrame(columns=['SKUCode', 'Cure Time'])

    combined = pd.concat(frames, ignore_index=True).dropna(subset=['Cure Time'])
    # If a SKU appears in both files (rare), keep the highest cure time (conservative)
    combined = combined.sort_values('Cure Time', ascending=False).drop_duplicates('SKUCode')
    return combined[['SKUCode', 'Cure Time']].reset_index(drop=True)


# ---------------------------------------------------------------------------
# PCR SKU LIST LOADER
# ---------------------------------------------------------------------------

def _load_pcr_skus() -> set:
    """Load the PCR SKU master list from SKU_List.xlsx. Returns a set of strings."""
    try:
        df = pd.read_excel(config.PCR_SKU_LIST_FILE)
        # Column is 'SKU Code'
        col = df.columns[0]
        skus = set(df[col].dropna().astype(str).str.strip())
        print(f"  [SKU List] PCR SKUs loaded: {len(skus)}")
        return skus
    except Exception as e:
        print(f"  [WARN] Could not load PCR SKU list: {e}. All SKUs treated as TBR.")
        return set()


# ---------------------------------------------------------------------------
# HISTORY PENETRATION HELPER
# ---------------------------------------------------------------------------

def compute_history_penetration(today_bor: pd.DataFrame, date_str: str, n: int) -> pd.Series:
    """
    Compute HistoryPenetrationScore — discrete integer in [0, n].

    Scoring rules (identical to BTP):
      • 0  : Penetration < BLACK threshold today
      • k  : Penetration >= BLACK threshold for k consecutive days ending today
      • n  : Max streak (n days all black)

    Uses Plant-1900 BOR files only.
    """
    today = datetime.strptime(date_str, "%d%m%Y")

    def _get_penetrations(bor_df: pd.DataFrame) -> dict:
        if 'Virtual Norm' not in bor_df.columns or 'Stock' not in bor_df.columns:
            return {}
        df = bor_df.copy()
        df['SKUCode'] = df['SKUCode'].astype(str)
        df['_pen'] = np.where(
            df['Virtual Norm'] == 0, 0,
            (df['Virtual Norm'] - df['Stock']) / df['Virtual Norm'] * 100
        )
        return df.groupby('SKUCode')['_pen'].mean().to_dict()

    today_pens = _get_penetrations(today_bor)
    all_skus   = list(today_pens.keys())

    day_pens = [today_pens]

    for day_offset in range(1, n):
        past_date = today - timedelta(days=day_offset)
        bor_path  = (
            f'{config.BASE_DATA_PATH}/Vectordata/BOR/'
            f'BORColorBandwiseReport__{past_date.strftime("%d-%m-%Y")}.csv'
        )

        if not os.path.exists(bor_path):
            day_pens.append({})
            continue

        try:
            past_bor = pd.read_csv(bor_path)
            past_bor['SKUCode'] = past_bor['SKUCode'].astype(str)
            if 'Location Code' in past_bor.columns:
                past_bor = past_bor[past_bor['Location Code'].str.startswith(config.CTP_PLANT_PREFIX)]
            day_pens.append(_get_penetrations(past_bor))
        except Exception:
            day_pens.append({})

    black_threshold = config.HISTORY_PENETRATION_BLACK
    scores: dict = {}

    for sku in all_skus:
        if today_pens.get(sku, 0.0) < black_threshold:
            scores[sku] = 0
            continue

        streak = 0
        for day_idx in range(n):
            pen = day_pens[day_idx].get(sku, None)
            if pen is None:
                continue
            if pen < black_threshold:
                break
            streak += 1

        scores[sku] = streak

    return pd.Series(scores, name='HistoryPenetrationScore', dtype=int)


# ---------------------------------------------------------------------------
# HISTORY BOR DATA EXPORT HELPER  (for future Stage 3 CTP use)
# ---------------------------------------------------------------------------

def get_history_bor_data(date_str: str, n: int) -> list:
    """
    Load raw BOR data for the last N days filtered to Plant 1900.
    Returns list of (date_label, df | None).
    """
    today  = datetime.strptime(date_str, "%d%m%Y")
    result = []

    for day_offset in range(n):
        past_date  = today - timedelta(days=day_offset)
        date_label = past_date.strftime("%d-%m-%Y")
        bor_path   = (
            f'{config.BASE_DATA_PATH}/Vectordata/BOR/'
            f'BORColorBandwiseReport__{date_label}.csv'
        )

        if not os.path.exists(bor_path):
            result.append((date_label, None))
            continue

        try:
            df = pd.read_csv(bor_path)
            df['SKUCode'] = df['SKUCode'].astype(str)
            if 'Location Code' in df.columns:
                df = df[df['Location Code'].str.startswith(config.CTP_PLANT_PREFIX)].copy()
            if 'Virtual Norm' in df.columns and 'Stock' in df.columns:
                df['Penetration'] = np.where(
                    df['Virtual Norm'] == 0, 0,
                    (df['Virtual Norm'] - df['Stock']) / df['Virtual Norm'] * 100
                )
            keep = ['SKUCode', 'Location Code', 'Norm ', 'Virtual Norm', 'Stock', 'Penetration']
            keep = [c for c in keep if c in df.columns]
            result.append((date_label, df[keep].reset_index(drop=True)))
        except Exception as exc:
            print(f"[HISTORY BOR] Could not read {bor_path}: {exc}")
            result.append((date_label, None))

    return result


# ---------------------------------------------------------------------------
# MAIN STAGE 1 PROCESSOR
# ---------------------------------------------------------------------------

def process_single_date(date_str: str):
    """
    Process a single date for Plant 1900 (CTP).

    Args:
        date_str: Date in DDMMYYYY format.

    Returns:
        Tuple (pcr_df, tbr_df) — DataFrames with Stage 1 scores, or (None, None).
    """
    date = datetime.strptime(date_str, "%d%m%Y")

    # --- FILE PATHS (same raw files as BTP) ---
    # SPOR is optional for CTP — we include it in the check only if present
    file_bor  = (f'{config.BASE_DATA_PATH}/Vectordata/BOR/'
                 f'BORColorBandwiseReport__{date.strftime("%d-%m-%Y")}.csv')
    file_bmr  = (f'{config.BASE_DATA_PATH}/Vectordata/BMR/'
                 f'Prod_OverAll_BMReport__{date.strftime("%d_%m_%Y")}.xlsx')
    file_bpr  = (f'{config.BASE_DATA_PATH}/Vectordata/BPR/'
                 f'BufferPenetrationReport__{date.strftime("%d-%m-%Y")}.csv')

    missing = [f for f in [file_bor, file_bmr, file_bpr] if not os.path.exists(f)]
    if missing:
        print(f"  Skipping {date_str}: Missing files — {[os.path.basename(f) for f in missing]}")
        return None, None

    print(f"\n  Loading data for {date.strftime('%d-%m-%Y')} ...")

    # ── LOAD RAW FILES ──────────────────────────────────────────────────────
    bpr_raw = pd.read_csv(file_bpr)
    bor_raw = pd.read_csv(file_bor)
    bmr_raw = pd.read_excel(file_bmr)

    bpr_raw['SKUCode'] = bpr_raw['SKUCode'].astype(str)
    bor_raw['SKUCode'] = bor_raw['SKUCode'].astype(str)

    # ── FILTER TO PLANT 1900 ─────────────────────────────────────────────────
    bor_v = bor_raw[bor_raw['Location Code'].str.startswith(config.CTP_PLANT_PREFIX)].copy()
    bpr_v = bpr_raw[bpr_raw['Location Code'].str.startswith(config.CTP_PLANT_PREFIX)].copy()

    print(f"  BOR rows (Plant 1900): {len(bor_v)}")
    print(f"  BPR rows (Plant 1900): {len(bpr_v)}")

    # ── INVENTORY SCORING (BPR) ───────────────────────────────────────────────
    bpr_v['Location Type'] = bpr_v['Location Type'].replace('depot', 'Depot')
    filtered_colors = bpr_v[bpr_v['On hand Inv. Color'].isin(['Black', 'Red'])]
    pivoted = (
        filtered_colors
        .groupby(['SKUCode', 'Location Type', 'On hand Inv. Color'])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    pivoted.rename(columns={'Black': 'Black Count', 'Red': 'Red Count'}, inplace=True)
    pivoted = pivoted.pivot(
        index='SKUCode', columns='Location Type',
        values=['Black Count', 'Red Count']
    ).fillna(0)
    pivoted.columns = [f"{color}_{loc}" for color, loc in pivoted.columns]
    pivoted.reset_index(inplace=True)

    pivoted['InventoryScore'] = 0.0
    for loc, weight in config.LOCATION_WEIGHTS.items():
        b_col, r_col = f'Black Count_{loc}', f'Red Count_{loc}'
        if b_col in pivoted.columns:
            pivoted['InventoryScore'] += pivoted[b_col] * weight * config.INVENTORY_SCORE_FACTORS['black']
        if r_col in pivoted.columns:
            pivoted['InventoryScore'] += pivoted[r_col] * weight * config.INVENTORY_SCORE_FACTORS['red']

    # ── DEMAND SCORING (BOR) ─────────────────────────────────────────────────
    # Map Location Code suffix to market category
    bor_v['Market'] = bor_v['Location Code'].str.split('_').str[1].replace(
        {'FG10': 'RE', 'OE10': 'OE', 'ST10': 'ST', 'OTR10': 'OTR'}
    ).astype(str)

    # Adjusted_Target = Virtual Norm × Market Multiplier
    bor_v['Adjusted_Target'] = bor_v.apply(
        lambda row: row['Virtual Norm'] * config.NORM_MULTIPLIERS.get(row['Market'], 1.0),
        axis=1
    )
    bor_v['Requirement'] = np.maximum(bor_v['Adjusted_Target'] - bor_v['Stock'], 0)
    bor_v['Penetration']  = np.where(
        bor_v['Virtual Norm'] == 0, 0,
        (bor_v['Virtual Norm'] - bor_v['Stock']) / bor_v['Virtual Norm'] * 100
    )

    # Merge Top SKU flag from BPR
    bor_v = bor_v.merge(
        bpr_v[['SKUCode', 'Location Code', 'Top SKU']],
        on=['SKUCode', 'Location Code'], how='left'
    )

    # ── BMR (EXPORT MARKET) ───────────────────────────────────────────────────
    bmr_raw.columns = bmr_raw.iloc[0]
    bmr_raw = bmr_raw.drop(index=0).reset_index(drop=True)

    # BMR Plant Code is stored as string (e.g. '1900')
    bmr_v = bmr_raw[
        bmr_raw['Plant Code'].astype(str).str.startswith(config.CTP_PLANT_PREFIX)
    ].rename(columns={
        'Item Code': 'SKUCode',
        'Pending CCR Qty': 'Requirement',
        'BPP': 'Penetration'
    })
    bmr_v['SKUCode']         = bmr_v['SKUCode'].astype(str)
    bmr_v['Market']          = 'EXP'
    bmr_v['Top SKU']         = 'T'
    bmr_v['Adjusted_Target'] = np.nan   # BMR has no Virtual Norm

    print(f"  BMR EXP rows (Plant 1900): {len(bmr_v)}")

    # ── COMBINE BOR + BMR ────────────────────────────────────────────────────
    combined = pd.concat([bmr_v, bor_v], ignore_index=True)
    combined  = combined[combined['Requirement'] != 0].copy()

    # Force all key numeric columns to float — BMR columns (BPP, Pending CCR Qty)
    # arrive as object dtype and would break downstream calculations if not coerced.
    for _num_col in ['Penetration', 'Requirement', 'Stock', 'Virtual Norm',
                     'Norm ', 'Adjusted_Target']:
        if _num_col in combined.columns:
            combined[_num_col] = pd.to_numeric(combined[_num_col], errors='coerce').fillna(0)

    # Extract rim size from SKUCode chars [8:10]
    combined['size'] = (
        pd.to_numeric(combined['SKUCode'].str[8:10], errors='coerce')
        .fillna(0)
        .astype('Int64')
    )

    combined['MarketWeight'] = combined['Market'].map(config.MARKET_WEIGHTS).fillna(1)
    combined['TopSKUFlag']   = combined['Top SKU'].apply(lambda x: 1 if x == 'T' else 0)

    combined['NormPenetration'] = _minmax(combined['Penetration'])
    combined['NormRequirement'] = _minmax(combined['Requirement'])

    combined['priority'] = combined.apply(
        lambda row: (-row['MarketWeight'], -row['Penetration'], -row['Requirement'], -row['TopSKUFlag']),
        axis=1
    )

    combined['PriorityScore'] = (
        combined['MarketWeight'] * config.SCORING_PARAMS['market_weightage'] +
        combined['NormPenetration'] * config.SCORING_PARAMS['penetration_weightage'] +
        combined['NormRequirement'] * config.SCORING_PARAMS['requirement_weightage'] +
        combined['TopSKUFlag'] * config.SCORING_PARAMS['top_sku_weightage']
    )

    # ── INVENTORY MERGE ───────────────────────────────────────────────────────
    combined = combined.merge(pivoted[['SKUCode', 'InventoryScore']], on='SKUCode', how='left').fillna({'InventoryScore': 0})
    combined['NormInventoryScore'] = _minmax(combined['InventoryScore'])

    # ── ASP (CTP DISPATCH FILE) ───────────────────────────────────────────────
    try:
        dispatch = pd.read_excel(config.CTP_DISPATCH_FILE, header=1)
        # Column 'Qty in unit of entry' maps to Quantity for BTP equiv
        dispatch = dispatch.rename(columns={'Qty in unit of entry': 'Quantity'})
        dispatch['Amt.in loc.cur.'] = pd.to_numeric(dispatch['Amt.in loc.cur.'], errors='coerce')
        dispatch['Quantity']        = pd.to_numeric(dispatch['Quantity'], errors='coerce')
        dispatch['ASP']             = dispatch['Amt.in loc.cur.'] / dispatch['Quantity']
        dispatch['Material']        = dispatch['Material'].astype(str)

        # Market-aware ASP: OE channel vs RE channel
        combined['_mkt_grp'] = combined['Market'].apply(
            lambda m: 'OE' if m in ('OE', 'OE10') else 'RE'
        )
        sku_mkt_map = (
            combined[['SKUCode', '_mkt_grp']]
            .drop_duplicates()
            .rename(columns={'SKUCode': 'Material', '_mkt_grp': 'Market_Group'})
        )

        # CTP dispatch is already Plant 1900 only — no plant filter needed
        dispatch_merged = dispatch.merge(sku_mkt_map, on='Material', how='left')
        dispatch_merged['Market_Group'] = dispatch_merged['Market_Group'].fillna('RE')

        asp_map = dispatch_merged.groupby(['Material', 'Market_Group'])['ASP'].mean()

        combined['ASP'] = combined.apply(
            lambda row: asp_map.get((row['SKUCode'], row['_mkt_grp']), config.DEFAULT_ASP),
            axis=1
        )
        combined.drop(columns=['_mkt_grp'], inplace=True)

    except Exception as e:
        print(f"  [WARN] Could not load CTP dispatch file: {e}. Using DEFAULT_ASP.")
        combined['ASP'] = config.DEFAULT_ASP

    # ── CURE TIME ─────────────────────────────────────────────────────────────
    curing = _load_cure_time()
    combined = combined.merge(curing[['SKUCode', 'Cure Time']], on='SKUCode', how='left')
    combined['Cure Time'] = combined['Cure Time'].fillna(config.DEFAULT_CURE_TIME) + 2.5

    combined['daily_cure'] = np.ceil((1440 / combined['Cure Time']) * config.EFFICIENCY_FACTOR).astype(int)
    combined['rev_pot']    = combined['ASP'] * combined['daily_cure']
    combined['PriceScore'] = _minmax(combined['rev_pot'])

    # ── HISTORY PENETRATION SCORING ───────────────────────────────────────────
    n_days = config.HISTORY_PENETRATION_N
    history_scores = compute_history_penetration(bor_v, date_str, n_days)
    combined['HistoryPenetrationScore']     = combined['SKUCode'].map(history_scores).fillna(0).astype(int)
    combined['NormHistoryPenetrationScore'] = _minmax(combined['HistoryPenetrationScore'])

    # ── CONSOLIDATED SCORE ────────────────────────────────────────────────────
    combined['ConsolidatedPriorityScore'] = (
        combined['PriorityScore']               * config.CONSOLIDATED_WEIGHTS['demand_priority'] +
        combined['NormInventoryScore']          * config.CONSOLIDATED_WEIGHTS['inventory_priority'] +
        combined['PriceScore']                  * config.CONSOLIDATED_WEIGHTS['price_priority'] +
        combined['NormHistoryPenetrationScore'] * config.CONSOLIDATED_WEIGHTS['history_penetration']
    )

    combined['Rank_ConsolidatedPriorityScore'] = combined['ConsolidatedPriorityScore'].rank(
        ascending=False, method='min'
    )
    combined = combined.sort_values('Rank_ConsolidatedPriorityScore', ascending=True)

    # ── ROUNDING ──────────────────────────────────────────────────────────────
    # Force numeric — BMR's BPP column (renamed Penetration) may be object dtype
    combined['Penetration'] = pd.to_numeric(combined['Penetration'], errors='coerce').fillna(0).round(2)
    combined['Requirement'] = pd.to_numeric(combined['Requirement'], errors='coerce').fillna(0)
    for _col in ['PriorityScore', 'PriceScore', 'ConsolidatedPriorityScore']:
        if _col in combined.columns:
            combined[_col] = combined[_col].round(3)

    # ── OUTPUT COLUMNS (same structure as BTP Stage 1) ────────────────────────
    output_columns = [
        'SKUCode', 'SKU Description', 'size',
        'Market', 'Norm ', 'Virtual Norm', 'Adjusted_Target',
        'Stock', 'Requirement', 'Penetration',
        'TopSKUFlag',
        'InventoryScore',
        'ASP', 'Cure Time', 'PriceScore',
        'HistoryPenetrationScore',
        'PriorityScore',
        'ConsolidatedPriorityScore', 'Rank_ConsolidatedPriorityScore',
    ]
    available_cols = [c for c in output_columns if c in combined.columns]
    combined = combined[available_cols]

    # ── SPLIT INTO PCR vs TBR ─────────────────────────────────────────────────
    pcr_skus = _load_pcr_skus()
    if pcr_skus:
        pcr_df = combined[combined['SKUCode'].isin(pcr_skus)].copy()
        tbr_df = combined[~combined['SKUCode'].isin(pcr_skus)].copy()
    else:
        # Fallback: no split possible — return everything as PCR
        pcr_df = combined.copy()
        tbr_df = pd.DataFrame(columns=combined.columns)

    # Re-rank within each type individually
    for df in [pcr_df, tbr_df]:
        if not df.empty:
            df['Rank_ConsolidatedPriorityScore'] = df['ConsolidatedPriorityScore'].rank(
                ascending=False, method='min'
            ).astype(int)

    print(f"  PCR SKUs in output: {len(pcr_df)}")
    print(f"  TBR SKUs in output: {len(tbr_df)}")

    return pcr_df, tbr_df
