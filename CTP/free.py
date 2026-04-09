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