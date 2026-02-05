import duckdb
import os
import zipfile

# 1. THE WEB-LOADER (Crucial for Streamlit Cloud)
def get_db_connection():
    """
    Connects to the database. If the .db file is missing (common on first cloud run),
    it extracts it from the .zip file first.
    """
    db_path = 'data/vantage_core.db'
    zip_path = 'data/vantage_core.zip'
    
    # Check if we need to unzip (GitHub only has the .zip due to size limits)
    if not os.path.exists(db_path):
        if os.path.exists(zip_path):
            print("📦 FoodVantage: Extracting compressed metabolic index...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Extract specifically to the 'data' folder
                zip_ref.extractall('data')
        else:
            raise FileNotFoundError(f"Missing both {db_path} and {zip_path}. Deployment failed.")

    return duckdb.connect(db_path, read_only=True)

# 2. THE LOCAL BUILDER (Your original logic, kept for your Mac)
def build_precision_db():
    path = 'data/food_data.parquet'
    db_out = 'data/vantage_core.db'
    
    if os.path.exists(db_out):
        os.remove(db_out)
        
    con = duckdb.connect(db_out)
    print("🚀 FOODVANTAGE: Rebuilding Clean Index...")

    con.execute(f"""
        CREATE OR REPLACE TABLE products AS 
        SELECT 
            TRIM(LOWER(CAST(product_name[1].text AS VARCHAR))) as product_name, 
            brands as brand,
            (list_filter(nutriments, x -> x.name = 'energy-kcal')[1]."100g") as calories,
            (list_filter(nutriments, x -> x.name = 'sugars')[1]."100g") as sugar,
            (list_filter(nutriments, x -> x.name = 'fiber')[1]."100g") as fiber,
            (list_filter(nutriments, x -> x.name = 'proteins')[1]."100g") as protein,
            (list_filter(nutriments, x -> x.name = 'saturated-fat')[1]."100g") as sat_fat,
            (list_filter(nutriments, x -> x.name = 'sodium')[1]."100g") * 1000 as sodium_mg,
            nutriscore_grade as grade,
            CAST((list_filter(nutriments, x -> x.name = 'nova-group')[1]."100g") AS INTEGER) as nova_group
        FROM read_parquet('{path}')
        WHERE product_name IS NOT NULL
          AND calories > 0
    """)
    
    count = con.execute("SELECT count(*) FROM products").fetchone()[0]
    print(f"✅ SUCCESS: {count:,} products indexed.")
    con.close()

if __name__ == "__main__":
    # Run this only locally on your Mac to generate the initial .db file
    build_precision_db()