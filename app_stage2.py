# app_stage2.py
# BTP Stage 2: Add Current Running Moulds to Stage 1 Vector Output
#
# Pipeline:
#   Reads:  combined_vector_demand_DDMMYYYY.xlsx  (Stage 1 output)
#           data/Vectordata/Daily Mould Report/DDMMYYYY MouldDetails.csv
#           data/oe_demand.csv  (for Ghost SKU market correction)
#   Writes: vector_stage2_DDMMYYYY.xlsx
#
# Output columns = ALL Stage 1 scoring/demand cols + mould deployment cols.
# NO Updated_Requirement here (set in Stage 3).
# NO frontend cols (Source, CPT_Requirement, etc.) — those come in Stage 4.

import os
import numpy as np
import pandas as pd
from datetime import datetime

import config
from demand_processor import get_history_bor_data
from deployment_processor import process_deployment_analysis

# ---------------------------------------------------------------------------
# STAGE 2 COLUMN ORDER
# All Stage 1 scoring cols preserved + mould deployment cols appended.
# ---------------------------------------------------------------------------
STAGE1_COLS = [
    'SKUCode', 'SKU Description', 'size', 'Market',
    'Norm ', 'Virtual Norm', 'Adjusted_Target', 'Stock',
    'Requirement', 'Penetration', 'TopSKUFlag',
    'InventoryScore', 'ASP', 'Cure Time', 'PriceScore',
    'HistoryPenetrationScore', 'PriorityScore', 'ConsolidatedPriorityScore',
]
MOULD_COLS = [
    'MachineCount', 'AvgMouldHealth', 'ProxyPenetration', 'ProxyRank',
    'CriticalGap', 'ExcessProduction', 'MouldAlert', 'IsGhostSKU',
]
STAGE2_COLUMNS = ['Final Rank'] + STAGE1_COLS + MOULD_COLS


def _ghost_sku_oe_correction(df: pd.DataFrame, oe_demand_path: str) -> pd.DataFrame:
    """Correct Ghost SKU market from RE → OE if SKU present in oe_demand.csv."""
    if not os.path.exists(oe_demand_path):
        return df
    if 'IsGhostSKU' not in df.columns:
        return df
    try:
        oe_df   = pd.read_csv(oe_demand_path, skiprows=2, header=0, encoding='latin1')
        oe_skus = set(oe_df['PRODUCT CODE'].astype(str).str.strip().str.upper())
        mask = (
            df['IsGhostSKU'].fillna(False).astype(bool) &
            df['SKUCode'].astype(str).str.strip().str.upper().isin(oe_skus)
        )
        n = mask.sum()
        if n > 0:
            df.loc[mask, 'Market'] = 'OE'
            print(f'  [Stage 2] Ghost SKU market RE→OE corrected: {n} SKU(s)')
    except Exception as e:
        print(f'  [WARN] Ghost SKU OE correction failed: {e}')
    return df


def _enforce_stage2_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only Stage 2 columns in the right order; add missing as NaN."""
    for col in STAGE2_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df[STAGE2_COLUMNS]


def _assign_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Assign Final Rank based on ConsolidatedPriorityScore (descending)."""
    df = df.sort_values('ConsolidatedPriorityScore', ascending=False).reset_index(drop=True)
    df['Final Rank'] = df.index + 1
    return df


def run_stage2():
    print('=' * 70)
    print('  BTP STAGE 2 — Add Current Running Moulds')
    print('  Source: Stage 1 vector output + Daily Mould Report')
    print('=' * 70)
    print()

    date_str = input('Enter date (DD.MM.YYYY): ').strip()
    try:
        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
    except ValueError:
        print('❌ Invalid date format. Use DD.MM.YYYY')
        return

    ddmmyyyy    = date_obj.strftime('%d%m%Y')
    stage1_file = f'combined_vector_demand_{ddmmyyyy}.xlsx'
    output_file = f'vector_stage2_{ddmmyyyy}.xlsx'

    if not os.path.exists(stage1_file):
        print(f'❌ Stage 1 output not found: {stage1_file}')
        return

    # ── Load Stage 1 output ─────────────────────────────────────────────────
    print(f'\nLoading Stage 1 output: {stage1_file}')
    xl         = pd.ExcelFile(stage1_file)
    main_sheet = xl.sheet_names[0]
    df         = xl.parse(main_sheet)
    print(f'  Loaded {len(df)} SKUs from Stage 1')

    # ── Merge mould report via existing deployment_processor ─────────────────
    print(f'\n[Stage 2] Running mould deployment analysis for {ddmmyyyy}...')
    stage2_df = process_deployment_analysis(df, ddmmyyyy)

    # ── Ensure Requirement is preserved (re-assert from Stage 1 if ghost reset it) ─
    # Ghost rows get Requirement=0 from _build_ghost_sku_rows — that is correct.
    # Demand rows should already have Requirement from Stage 1 df passed in.

    # ── Ghost SKU OE market correction ───────────────────────────────────────
    oe_path = os.path.join(config.BASE_DATA_PATH, 'oe_demand.csv')
    stage2_df = _ghost_sku_oe_correction(stage2_df, oe_path)

    # ── Assign rank ───────────────────────────────────────────────────────────
    if 'ConsolidatedPriorityScore' in stage2_df.columns:
        stage2_df = _assign_rank(stage2_df)

    # ── Enforce Stage 2 column order ─────────────────────────────────────────
    stage2_df = _enforce_stage2_columns(stage2_df)

    # ── SKU Description lookup (Stage 1 data — non-ghost rows already have it) ──
    desc_lookup: dict = {}
    if 'SKU Description' in stage2_df.columns:
        # seed from Stage 1 demand rows (ghost rows won't have descriptions yet)
        for _, row in stage2_df.iterrows():
            sku  = str(row['SKUCode']).strip()
            desc = str(row.get('SKU Description', '')).strip()
            if desc and desc not in ('nan', '0', ''):
                desc_lookup[sku] = desc

    # ── History BOR tabs ─────────────────────────────────────────────────────
    n_days = config.HISTORY_PENETRATION_N
    print(f'\n[Stage 2] Loading BOR history for last {n_days} days...')
    history_bor = get_history_bor_data(ddmmyyyy, n_days)

    # Supplement desc_lookup from BOR history (catches Ghost SKUs seen in past demand)
    for _date_label, bor_df in history_bor:
        if bor_df is None or bor_df.empty or 'SKU Description' not in bor_df.columns:
            continue
        for _, row in bor_df.iterrows():
            sku  = str(row['SKUCode']).strip()
            desc = str(row.get('SKU Description', '')).strip()
            if sku and sku not in desc_lookup and desc and desc not in ('nan', '0', ''):
                desc_lookup[sku] = desc

    # Also scan broader monthly BOR files for Ghost SKUs not in recent daily history
    missing_ghost_skus = set()
    if 'IsGhostSKU' in stage2_df.columns and 'SKU Description' in stage2_df.columns:
        ghost_mask_pre = stage2_df['IsGhostSKU'].fillna(False).astype(bool)
        missing_ghost_skus = set(
            stage2_df.loc[
                ghost_mask_pre &
                stage2_df['SKU Description'].astype(str).str.strip().isin(['nan', '0', '']),
                'SKUCode'
            ].astype(str).str.strip()
        )
    if missing_ghost_skus:
        import glob as _glob
        bor_root = config.BASE_DATA_PATH  # data/Vectordata/ or similar
        bor_files = sorted(
            _glob.glob(os.path.join(bor_root, '**', 'BOR*.csv'), recursive=True) +
            _glob.glob(os.path.join(bor_root, '**', '*BOR*.csv'), recursive=True),
            reverse=True          # most-recent first
        )
        _still_missing = set(missing_ghost_skus)
        for bf in bor_files:
            if not _still_missing:
                break
            try:
                bdf = pd.read_csv(bf, encoding='latin1', low_memory=False)
                bdf.columns = bdf.columns.str.strip()
                if 'SKUCode' not in bdf.columns or 'SKU Description' not in bdf.columns:
                    continue
                bdf['SKUCode'] = bdf['SKUCode'].astype(str).str.strip()
                hits = bdf[bdf['SKUCode'].isin(_still_missing)]
                for _, row in hits.iterrows():
                    sku  = row['SKUCode']
                    desc = str(row['SKU Description']).strip()
                    if sku and desc and desc not in ('nan', '0', ''):
                        desc_lookup[sku] = desc
                        _still_missing.discard(sku)
            except Exception:
                continue
        found_extra = len(missing_ghost_skus) - len(_still_missing)
        if found_extra > 0:
            print(f'  [Stage 2] Ghost SKU descriptions from monthly BOR files: {found_extra}')


    # Backfill Ghost SKU descriptions from the combined lookup
    ghost_mask = stage2_df['IsGhostSKU'].fillna(False).astype(bool)
    missing_desc = ghost_mask & (
        stage2_df['SKU Description'].isna() |
        stage2_df['SKU Description'].astype(str).str.strip().isin(['nan', '0', ''])
    )
    if missing_desc.sum() > 0:
        stage2_df.loc[missing_desc, 'SKU Description'] = (
            stage2_df.loc[missing_desc, 'SKUCode']
            .astype(str).str.strip()
            .map(desc_lookup)
        )
        filled = missing_desc.sum() - stage2_df.loc[missing_desc, 'SKU Description'].isna().sum()
        print(f'  [Stage 2] Ghost SKU descriptions backfilled from BOR history: {int(filled)}')

    # ── Write output ──────────────────────────────────────────────────────────
    print(f'\nWriting Stage 2 output: {output_file}')
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        stage2_df.to_excel(writer, sheet_name=ddmmyyyy, index=False)
        print(f'  [Tab 1] {ddmmyyyy} — {len(stage2_df)} rows, {len(stage2_df.columns)} columns')

        tabs_written = 0
        for date_label, bor_df in history_bor:
            if bor_df is None or bor_df.empty:
                print(f'  [History Tab] {date_label} — skipped (no BOR file)')
                continue
            bor_df = bor_df.copy()
            bor_df['SKU Description'] = bor_df['SKUCode'].astype(str).str.strip().map(desc_lookup).fillna('')
            priority_cols = ['SKUCode', 'SKU Description', 'Location Code',
                             'Norm ', 'Virtual Norm', 'Stock', 'Penetration']
            ordered   = [c for c in priority_cols if c in bor_df.columns]
            remaining = [c for c in bor_df.columns if c not in ordered]
            bor_df    = bor_df[ordered + remaining]
            bor_df.to_excel(writer, sheet_name=date_label, index=False)
            tabs_written += 1
            print(f'  [History Tab] {date_label} — {len(bor_df)} rows')

    ghost_count = int(stage2_df['IsGhostSKU'].fillna(False).sum()) if 'IsGhostSKU' in stage2_df.columns else 0
    print(f'\n✅ Stage 2 complete: {output_file}')
    print(f'   Total SKUs      : {len(stage2_df)}')
    print(f'   Ghost SKUs added: {ghost_count}')
    print(f'   History tabs    : {tabs_written} of {n_days}')
    print(f'   Columns         : {list(stage2_df.columns)}')



if __name__ == '__main__':
    run_stage2()
