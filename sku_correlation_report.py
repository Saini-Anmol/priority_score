# sku_correlation_report.py
# Temporary one-off analysis script for BTP Stage 4 output.
# Calculates Pearson correlation (on Updated_Requirement) 
# and Spearman correlation (on Final Rank) across 3 consecutive days.

import os
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')

PROJECT_DIR = "/Users/anmolsaini/Documents/Vector_Project"

FILES = {
    "11_Mar": os.path.join(PROJECT_DIR, "vector_stage4_running_demand_11032026.xlsx"),
    "12_Mar": os.path.join(PROJECT_DIR, "vector_stage4_running_demand_12032026.xlsx"),
    "13_Mar": os.path.join(PROJECT_DIR, "vector_stage4_running_demand_13032026.xlsx"),
}

OUTPUT_FILE = os.path.join(PROJECT_DIR, "sku_correlation_report_v2.xlsx")

# ---------------------------------------------------------------------------
# 1. LOAD DATA
# ---------------------------------------------------------------------------
day_dfs = []
max_rank_observed = 0

for label, path in FILES.items():
    if not os.path.exists(path):
        print(f"❌ File not found: {path}")
        continue
        
    df = pd.read_excel(path, sheet_name=0)
    df['SKUCode'] = df['SKUCode'].astype(str).str.strip()
    df['Market']  = df['Market'].astype(str).str.strip()
    
    # We need Updated_Requirement, Final Rank, and SKU Description
    rank_col = 'Final Rank' if 'Final Rank' in df.columns else 'Rank_ConsolidationPriorityScore'
    desc_col = 'SKU Description' if 'SKU Description' in df.columns else 'Description'
    
    # In case a file is missing the description column completely
    if desc_col not in df.columns:
        df[desc_col] = ''
        
    subset = df[['SKUCode', 'Market', desc_col, 'Updated_Requirement', rank_col]].copy()
    subset.rename(columns={
        desc_col: 'SKU Description',
        'Updated_Requirement': f'Req_{label}',
        rank_col: f'Rank_{label}'
    }, inplace=True)
    
    # Ensure numeric
    subset[f'Req_{label}'] = pd.to_numeric(subset[f'Req_{label}'], errors='coerce').fillna(0)
    subset[f'Rank_{label}'] = pd.to_numeric(subset[f'Rank_{label}'], errors='coerce')
    
    # Track the worst rank across all days to use as a fill value for missing SKUs
    current_max_rank = subset[f'Rank_{label}'].max()
    if pd.notna(current_max_rank) and current_max_rank > max_rank_observed:
        max_rank_observed = current_max_rank
        
    # Group by SKU+Market just in case of duplicates (shouldn't be, but safe)
    # The first() aggregation will correctly keep the string description
    subset = subset.groupby(['SKUCode', 'Market']).first().reset_index()
    day_dfs.append(subset)

# ---------------------------------------------------------------------------
# 2. MERGE DATA
# ---------------------------------------------------------------------------
# Start with union of all SKU/Market/Description pairs
merged = day_dfs[0]
for df in day_dfs[1:]:
    # Merge on SKU Description as well so it doesn't create _x and _y columns
    merged = pd.merge(merged, df, on=['SKUCode', 'Market', 'SKU Description'], how='outer')

# ---------------------------------------------------------------------------
# 3. FILL MISSING VALUES
# ---------------------------------------------------------------------------
# For Requirement, absent means 0 demand
req_cols = [c for c in merged.columns if c.startswith('Req_')]
merged[req_cols] = merged[req_cols].fillna(0)

# For Rank, absent means they dropped to the bottom of the priority list
# We use max_rank_observed + 10 (e.g., if max rank is 104, absent SKUs get rank 114)
FILL_RANK = int(max_rank_observed + 10)
rank_cols = [c for c in merged.columns if c.startswith('Rank_')]
merged[rank_cols] = merged[rank_cols].fillna(FILL_RANK)

# ---------------------------------------------------------------------------
# 4. CALCULATE CORRELATIONS
# ---------------------------------------------------------------------------
# Pearson on Volume (Updated_Requirement)
pearson_matrix = merged[req_cols].corr(method='pearson').round(4)
# Rename index/columns to just dates for cleaner output
pearson_matrix.columns = [c.replace('Req_', '') for c in pearson_matrix.columns]
pearson_matrix.index = pearson_matrix.columns

# Spearman on Priority (Final Rank)
spearman_matrix = merged[rank_cols].corr(method='spearman').round(4)
spearman_matrix.columns = [c.replace('Rank_', '') for c in spearman_matrix.columns]
spearman_matrix.index = spearman_matrix.columns

# ---------------------------------------------------------------------------
# 5. SORT EXACTLY HOW YOU WANT IT FOR THE MAIN SHEET
# ---------------------------------------------------------------------------
# Let's sort by Average Requirement so the biggest hitters are at the top
merged['Avg_Req'] = merged[req_cols].mean(axis=1).round(1)
merged = merged.sort_values('Avg_Req', ascending=False).reset_index(drop=True)

# ---------------------------------------------------------------------------
# 6. WRITE TO EXCEL
# ---------------------------------------------------------------------------
with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
    # 1. Main Sheet
    merged.to_excel(writer, sheet_name='SKU_Correlation', index=False)
    
    # 2. Pearson (Volume Stability)
    pearson_matrix.to_excel(writer, sheet_name='Pearson_Requirement')
    
    # 3. Spearman (Priority Stability)
    spearman_matrix.to_excel(writer, sheet_name='Spearman_Rank')

print(f"\n✅ Report written: {OUTPUT_FILE}")
print(f"   Sheets generated: SKU_Correlation, Pearson_Requirement, Spearman_Rank")
print("\n--- Pearson Correlation (Volume Stability) ---")
print(pearson_matrix.to_string())
print("\n--- Spearman Correlation (Priority Stability) ---")
print(spearman_matrix.to_string())
