# V1/Utilities/db_writer.py
# ---------------------------------------------------------------------------
# DATABASE UPLOAD UTILITY
# Handles cleaning and uploading Pandas DataFrames into the pre-existing
# MySQL table.  Uses DELETE + INSERT so the table schema is never dropped.
# ---------------------------------------------------------------------------

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


# ── Column mapping: DataFrame column name → DB column name ───────────────
# This maps the 37-column Stage 5 output to the btp_requirement schema.
# Only columns listed here will be uploaded. Order does not matter.
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
    "Vector_Requirement":        "vectorRequirement",
    "CPT_Requirement":           "cptRequirement",
    "Requirement":               "requirement",
    "Updated_Requirement":       "updatedRequirement",
    "avg_sales_qty":             "avgSalesQty",
    "oe_demand_qty":             "oeDemandQty",
    "Penetration":               "penetration",
    "TopSKUFlag":                "topSKUFlag",
    "HistoryPenetrationScore":   "historyPenetrationScore",
    "MachineCount":              "machineCount",
    "AvgMouldHealth":            "avgMouldHealth",
    "ProxyPenetration":          "proxyPenetration",
    "ProxyRank":                 "proxyRank",
    "CriticalGap":               "criticalGap",
    "ExcessProduction":          "excessProduction",
    "MouldAlert":                "mouldAlert",
    "IsGhostSKU":                "isGhostSKU",
    "ASP":                       "asp",
    "Cure Time":                 "cureTime",
    "PriorityScore":             "priorityScore",
    "ConsolidatedPriorityScore": "consolidatedPriorityScore",
}


def upload_dataframe_to_sql(df: pd.DataFrame, table_name: str, engine: Engine):
    """
    Uploads a DataFrame to the pre-existing MySQL table.

    Strategy:  DELETE all existing rows  →  INSERT new rows.
    The table schema is NEVER dropped or recreated.

    Args:
        df:         The pandas DataFrame to upload.
        table_name: The target table in the MySQL database.
        engine:     The active SQLAlchemy connection engine.
    """
    if engine is None:
        print(f"  [ERROR] Cannot upload to '{table_name}' — No active database connection.")
        return

    # 1. Select and rename only the columns that exist in the DB schema
    upload_df = df.copy()
    rename_map = {k: v for k, v in _COLUMN_MAP.items() if k in upload_df.columns}
    upload_df = upload_df[[c for c in _COLUMN_MAP if c in upload_df.columns]]
    upload_df = upload_df.rename(columns=rename_map)

    print(f"  [DB Upload] Preparing to upload {len(upload_df)} rows to table '{table_name}'...")
    print(f"              Columns mapped: {len(rename_map)} / {len(_COLUMN_MAP)}")

    try:
        # 2. DELETE all existing rows (preserves schema + id auto-increment)
        with engine.connect() as conn:
            conn.execute(text(f"DELETE FROM {table_name}"))
            conn.commit()
        print(f"  [DB Upload] Cleared old rows from '{table_name}'.")

        # 3. INSERT new rows using pandas to_sql with 'append' mode
        #    'append' = INSERT only, never touches the table structure
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