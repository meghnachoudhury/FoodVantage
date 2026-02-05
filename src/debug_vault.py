import duckdb

con = duckdb.connect()
path = 'data/food_data.parquet'

print("🧬 ANALYZING VAULT STRUCTURE...")
# Check if it's a String, a Struct, or a Map
dtype = con.execute(f"DESCRIBE SELECT nutriments FROM read_parquet('{path}')").fetchall()
print(f"Data Type of 'nutriments': {dtype[0][1]}")

print("\n📡 PEEKING AT RAW VALUES...")
# Let's see the actual keys inside 'nutriments' for the first product
sample = con.execute(f"SELECT nutriments FROM read_parquet('{path}') LIMIT 1").fetchone()
print(f"Raw Sample: {sample}")