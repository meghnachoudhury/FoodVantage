import duckdb

con = duckdb.connect()
path = 'data/food_data.parquet'

print("🕵️ VANTAGE: Deep-scanning for rows with ACTUAL nutrient data...")

# We search for the first row where nutriments is NOT NULL and NOT EMPTY
query = f"""
    SELECT product_name[1].text, nutriments 
    FROM read_parquet('{path}') 
    WHERE (product_name[1].text ILIKE '%Coca-Cola%' OR product_name[1].text ILIKE '%Apple%')
      AND nutriments IS NOT NULL
      AND list_count(nutriments) > 0
    LIMIT 2
"""
results = con.execute(query).fetchall()

if results:
    for row in results:
        name, nutriments = row
        print(f"\n✅ DATA FOUND FOR: {name}")
        print("-" * 30)
        for item in nutriments:
            # We print the name and the 100g value
            print(f"🔹 Label: '{item['name']}' | Value: {item['100g']}")
else:
    print("❌ No rows found with populated nutrient lists.")