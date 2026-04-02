import pandas as pd
from sqlalchemy import create_engine
import os

# USER INPUT
file_path = "vector_stage5_31032026.xlsx"   # or .xlsx

server   = "35.208.174.2"   
database = "jkplanningV1"
username = "root"
password = "Dev112233"

table_name = "btp_requirement"

# READ FILE (CSV / EXCEL)
if file_path.endswith(".csv"):
    df = pd.read_csv(file_path, encoding='latin1')
elif file_path.endswith(".xlsx"):
    df = pd.read_excel(file_path)
else:
    raise ValueError("❌ Unsupported file format")

# CLEAN COLUMN NAMES (IMPORTANT)
df.columns = (
    df.columns
    .str.strip()
    .str.replace(" ", "_")
    .str.replace("[^a-zA-Z0-9_]", "", regex=True)
)

# CREATE CONNECTION (MySQL)
engine = create_engine(
    f"mysql+pymysql://{username}:{password}@{server}/{database}"
)

# If port required (uncomment below)
# engine = create_engine(
#     f"mysql+pymysql://{username}:{password}@{server}:3306/{database}"
# )

# UPLOAD TO DATABASE
df.to_sql(
    name="btp_requirement",
    con=engine,
    if_exists="replace",   # 'replace' / 'append'
    index=False,
    chunksize=1000
)

# SUCCESS MESSAGE
print(f"✅ File '{os.path.basename(file_path)}' uploaded successfully to table '{table_name}'!")