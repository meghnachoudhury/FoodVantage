import duckdb
import os

# 1. Verify Path
path = 'data/food_data.parquet'
print(f"Checking path: {os.path.abspath(path)}")
print(f"File exists: {os.path.exists(path)}")

# 2. Extract Column Names (The "Source of Truth")
try:
    con = duckdb.connect()
    # This command asks DuckDB to show the names of every column in the file
    columns = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
    print("\n--- ACTUAL COLUMN NAMES IN YOUR FILE ---")
    for col in columns:
        # We search for any variation of 'energy'
        if 'energy' in col[0].lower():
            print(f"📍 FOUND ENERGY COLUMN: '{col[0]}'")
except Exception as e:
    print(f"❌ ERROR: {e}")