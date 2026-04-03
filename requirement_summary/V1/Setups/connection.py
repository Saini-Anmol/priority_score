# V1/Setups/connection.py
# ---------------------------------------------------------------------------
# DATABASE CONNECTION MANAGER
# Securely initializes and returns a connection to the primary MySQL database.
# Reads credentials from the root .env file to prevent hardcoding passwords.
# ---------------------------------------------------------------------------

import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

def get_database_connection() -> Engine:
    """
    Initializes the SQLAlchemy engine for MySQL database operations.
    
    Returns:
        SQLAlchemy Engine object if successful, None if credentials 
        are missing or connection fails.
    """
    # 1. Fetch credentials securely from environment variables (.env file)
    server   = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE")
    username = os.getenv("DB_USERNAME")
    password = os.getenv("DB_PASSWORD")

    # 2. Safety Check: Ensure all required credentials exist
    if not all([server, database, username, password]):
        print("  [WARN] Database credentials missing or incomplete in .env file.")
        print("         Skipping database connection.")
        return None

    try:
        # 3. Create the connection engine
        # Using mysql+pymysql driver as standard for pandas-to-mysql operations
        connection_string = f"mysql+pymysql://{username}:{password}@{server}/{database}"
        engine = create_engine(connection_string)
        
        return engine
        
    except Exception as e:
        print(f"  [ERROR] Could not create database engine. Details: {e}")
        return None