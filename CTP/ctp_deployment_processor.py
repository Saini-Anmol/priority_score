# CTP/ctp_deployment_processor.py
# CTP Stage 3: Mould Report Cleaner
#
# Processes CTP-specific daily mould reports for PCR and TBR.

import os
import pandas as pd
import glob

_CTP_DIR = os.path.dirname(os.path.abspath(__file__))

def clean_mould_report_ctp(tyre_type: str, date_str: str) -> pd.DataFrame:
    """
    Reads the daily mould report for the given tyre type (PCR or TBR)
    from their respective folders, specifically matching the date.
    Calculates machine count and avg mould health.
    Since target life is missing, sets default target life to 3000.

    Args:
        tyre_type: "PCR" or "TBR"
    
    Returns:
        DataFrame with columns: [Sapcode, MachineCount, AvgMouldHealth]
    """
    if tyre_type.upper() == "PCR":
        folder = os.path.join(_CTP_DIR, "data", "Daily Mould Report PCR")
    else:
        folder = os.path.join(_CTP_DIR, "data", "Daily Mould Report TBR")
    
    target_filename = f"Curing_Current_Running_moulds_{date_str}"
    
    # Find any excel or csv file matching the required name
    files = glob.glob(os.path.join(folder, f"{target_filename}.xlsx")) \
          + glob.glob(os.path.join(folder, f"{target_filename}.xls")) \
          + glob.glob(os.path.join(folder, f"{target_filename}.csv"))
    
    if not files:
        print(f"  [MOULD CTP] No mould report file found for date {date_str} in {folder}")
        return None
    
    # Process the most recently modified file if multiple exist with same name (e.g. .csv and .xlsx)
    latest_file = max(files, key=os.path.getmtime)
    
    try:
        if latest_file.lower().endswith(".csv"):
            df = pd.read_csv(latest_file)
        else:
            df = pd.read_excel(latest_file)
    except Exception as e:
        print(f"  [MOULD CTP] Error reading {os.path.basename(latest_file)}: {e}")
        return pd.DataFrame() # Return empty df instead of None so caller doesn't crash on len() if they check it incorrectly, but caller checks `is not None`
        # Actually caller does `if mould_df is not None: len(mould_df)`. I will return None on error to stick to existing behavior format.
        return None
        
    df.columns = df.columns.str.strip()
    
    required = ["Sapcode", "Mould life"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  [MOULD CTP] Missing columns in {os.path.basename(latest_file)}: {missing}")
        return None

    # Clean data
    df["Sapcode"] = df["Sapcode"].astype(str).str.strip().str.upper()
    df["Mould life"] = pd.to_numeric(df["Mould life"], errors="coerce").fillna(0)
    
    # Default Target Mould life to 3000 if empty or missing
    target_col = None
    if "Target Mould life" in df.columns:
        target_col = "Target Mould life"
    elif "Target life" in df.columns:
        target_col = "Target life"
        
    if target_col is None:
        df["Target Mould life"] = 3000.0
    else:
        df["Target Mould life"] = pd.to_numeric(df[target_col], errors="coerce").fillna(3000.0)
        # Ensure 0 is also treated as 3000 to avoid division by zero
        df.loc[df["Target Mould life"] == 0, "Target Mould life"] = 3000.0
    
    # Expand WCNAME (if it contains hashes like GC08#GC15 in BTP, here WCNAME is just 20 or 21 but MouldNo has hashes)
    # The requirement is just to count the rows, or split WCNAME if we did that.
    # We will split "Current MouldNo" by "#" and create multiple rows if they represent multiple machines.
    # WAIT: BTP splits by WCNAME. Let's split WCNAME by '#', ','. Actually, in CTP, WCNAME is single, Current MouldNo has hashes.
    # Is MachineCount = number of moulds? Yes. Let's split Current MouldNo.
    
    # Some rows might have multiple WCNAME or MouldNo. BTP code splits 'WCNAME'. 
    # To be safe, let's split 'WCNAME' just like BTP, and also 'Current MouldNo' optionally. 
    # Actually, counting rows is usually enough if it's 1 row per machine, but if WCNAME has "A#B", it means 2 machines.
    if "WCNAME" in df.columns:
        df["WCNAME"] = df["WCNAME"].astype(str)
        # expand rows where WCNAME has '#' or ','
        df["WCNAME"] = df["WCNAME"].str.replace(",", "#")
        df["WCNAME_list"] = df["WCNAME"].str.split("#")
        df = df.explode("WCNAME_list")
        
        # If Current MouldNo is present and hasn't been split, let's not worry about it unless they want us to count moulds instead of machines. 
        # MachineCount usually comes from expanding WCNAME.
    
    # Calculate Health
    df["MouldHealth"] = (df["Mould life"] / df["Target Mould life"]) * 100
    df["MouldHealth"] = df["MouldHealth"].clip(lower=0, upper=100)
    
    # Group by Sapcode
    grouped = df.groupby("Sapcode").agg({
        "Sapcode": "count",         # MachineCount
        "MouldHealth": "mean"       # AvgMouldHealth
    }).rename(columns={"Sapcode": "MachineCount", "MouldHealth": "AvgMouldHealth"}).reset_index()
    
    grouped.rename(columns={"Sapcode": "SKUCode"}, inplace=True)
    grouped["AvgMouldHealth"] = grouped["AvgMouldHealth"].round(1)
    
    return grouped
