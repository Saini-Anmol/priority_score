# V1/Utilities/db_writer.py
# ---------------------------------------------------------------------------
# DATABASE UPLOAD UTILITY
# Handles the cleaning and uploading of Pandas DataFrames directly into 
# MySQL tables. Eliminates the need to save/read from local CSVs first.
# ---------------------------------------------------------------------------

import pandas as pd
from sqlalchemy.engine import Engine

def upload_dataframe_to_sql(df: pd.DataFrame, table_name: str, engine: Engine, if_exists: str = "replace"):
    """
    Cleans DataFrame column names and uploads it to the specified MySQL table.
    
    Args:
        df: The pandas DataFrame to upload.
        table_name: The target table in the MySQL database.
        engine: The active SQLAlchemy connection engine.
        if_exists: Behavior if table exists ('replace' or 'append'). Defaults to 'replace'.
    """
    # 1. Validate active connection
    if engine is None:
        print(f"  [ERROR] Cannot upload to '{table_name}' — No active database connection.")
        return

    # 2. Create a working copy to avoid mutating the original DataFrame 
    # (which might still be needed for the Excel exporter)
    upload_df = df.copy()

    # 3. Clean column names for SQL compatibility (IMPORTANT)
    # SQL databases struggle with spaces and special characters in column names.
    # - .str.strip(): Removes leading/trailing whitespace
    # - .str.replace(" ", "_"): Converts internal spaces to underscores
    # - .str.replace(regex): Strips out anything that isn't a letter, number, or underscore
    upload_df.columns = (
        upload_df.columns
        .str.strip()
        .str.replace(" ", "_", regex=False)
        .str.replace("[^a-zA-Z0-9_]", "", regex=True)
    )

    print(f"  [DB Upload] Preparing to upload {len(upload_df)} rows to table '{table_name}'...")
    
    # 4. Execute the SQL Upload
    try:
        upload_df.to_sql(
            name=table_name,
            con=engine,
            if_exists=if_exists,   
            index=False,           # Do not upload the pandas index as a separate column
            chunksize=1000         # Uploads in chunks of 1000 to prevent memory timeout issues
        )
        print(f"  ✅ Data uploaded successfully to MySQL table '{table_name}'!")
        
    except Exception as e:
        print(f"  ❌ Database upload failed: {str(e)}")