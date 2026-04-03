# V1/Utilities/db_writer.py
# ---------------------------------------------------------------------------
# DATABASE UPLOAD UTILITY
# Handles cleaning and uploading Pandas DataFrames into the pre-existing
# MySQL table.  Uses TRUNCATE + INSERT so the table schema is never dropped.
# ---------------------------------------------------------------------------

import pandas as pd
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.engine import Engine


# ── Column mapping: DataFrame column name → DB column name ───────────────
# Matches the jkplanningV1.btp_requirement schema EXACTLY.
_COLUMN_MAP = {
    "Final Rank":                "finalRank",
    "SKUCode":                   "skuCode",
    "SKU Description":           "skuDescription",
    "size":                      "size",
    "Source":                    "source",
    "Market":                    "market",
    "HighestPriority":           "highestPriority",
    "Target Date":               "targetDate",
    "Quantity":                  "quantity",
    "weighted_score":            "weightedScore",
    "modified_priority_score":   "modifiedPriorityScore",
    "manual_rank":               "manualRank",
    "Norm ":                     "norm",
    "Virtual Norm":              "virtualNorm",
    "Adjusted_Target":           "adjustedTarget",
    "Stock":                     "stock",
    "avg_sales_qty":             "avgSalesQty",
    "oe_demand_qty":             "oePlanQty",
    "Vector_Requirement":        "vectorRequirement",
    "CPT_Requirement":           "cptRequirement",
    "Requirement":               "requirement",
    "Updated_Requirement":       "finalRequirement",
    "Penetration":               "penetration",
    "TopSKUFlag":                "topSkuFlag",
    "HistoryPenetrationScore":   "historyPenetrationScore",
    "MachineCount":              "machineCount",
    "AvgMouldHealth":            "avgMouldHealth",
    "ProxyPenetration":          "proxyMachineScore",
    "ProxyRank":                 "proxyRank",
    "CriticalGap":               "criticalGap",
    "ExcessProduction":          "excessProduction",
    "MouldAlert":                "mouldAlert",
    "IsGhostSKU":                "isGhostSku",
    "ASP":                       "avgSellingPrice",
    "Cure Time":                 "cureTime",
    "PriorityScore":             "priorityScore",
    "ConsolidatedPriorityScore": "consolidatedPriorityScore",
}


def upload_dataframe_to_sql(df: pd.DataFrame, table_name: str, engine: Engine):
    """
    Uploads a DataFrame to the pre-existing MySQL table.

    Strategy:  TRUNCATE (clear all rows + reset id)  →  INSERT new rows.
    The table schema is NEVER dropped or recreated.
    """
    if engine is None:
        print(f"  [ERROR] Cannot upload to '{table_name}' — No active database connection.")
        return

    # 1. Select and rename only the columns that exist in the DB schema
    upload_df = df.copy()
    rename_map = {k: v for k, v in _COLUMN_MAP.items() if k in upload_df.columns}
    upload_df = upload_df[[c for c in _COLUMN_MAP if c in upload_df.columns]]
    upload_df = upload_df.rename(columns=rename_map)

    # 2. Drop 'id' column if it exists — id is auto-increment primary key in DB
    if 'id' in upload_df.columns:
        upload_df.drop(columns=['id'], inplace=True)

    # 3. Data type cleaning for MySQL compatibility
    #    targetDate: empty string '' → None (DB expects DATE or NULL, not '')
    if 'targetDate' in upload_df.columns:
        upload_df['targetDate'] = upload_df['targetDate'].apply(
            lambda x: None if (pd.isna(x) or str(x).strip() == '') else x
        )

    #    BIT columns: True/False → 1/0 (MySQL BIT doesn't accept Python booleans)
    for bit_col in ['criticalGap', 'excessProduction', 'mouldAlert', 'isGhostSku', 'topSkuFlag']:
        if bit_col in upload_df.columns:
            upload_df[bit_col] = upload_df[bit_col].apply(
                lambda x: int(bool(x)) if pd.notna(x) else 0
            )

    # 4. Add createdAt (full date + time) and createdBy ("AI Plan")
    upload_df["createdAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    upload_df["createdBy"] = "AI Plan"

    print(f"  [DB Upload] Preparing to upload {len(upload_df)} rows to table '{table_name}'...")
    print(f"              Columns mapped: {len(rename_map)} / {len(_COLUMN_MAP)}")

    try:
        # 4. TRUNCATE table — clears all rows and resets auto-increment id
        with engine.connect() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_name}"))
            conn.commit()
        print(f"  [DB Upload] Truncated table '{table_name}' (old rows cleared, id reset).")

        # 5. INSERT new rows using pandas to_sql with 'append' mode
        upload_df.to_sql(
            name=table_name,
            con=engine,
            if_exists="append",
            index=False,
            chunksize=1000
        )
        print(f"  ✅ Data uploaded successfully to MySQL table '{table_name}'! ({len(upload_df)} rows)")

    except Exception as e:
        print(f"  ❌ Database upload failed: {str(e)}")