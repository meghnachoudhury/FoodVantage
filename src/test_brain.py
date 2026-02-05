from gemini_api import search_vantage_db

def run_vantage_stress_test():

    items = [
        # --- THE GREEN GOLD STANDARDS ---
        "Apple", 
        "Salmon",
        
        # --- THE YELLOW MID-GROUND (New Stress Test) ---
        "Oat Milk",          # High liquid starch/maltose
        "Hummus",            # Healthy but calorie-dense
        "Beef Jerky",        # High protein vs. high sodium
        "Protein Bar",       # Processed nutrients
        "Almond Milk",       # Low sugar but processed
        
        # --- THE RED STRESSORS ---
        "Honey",
        "Orange Juice",
        "Coca Cola"
    ]
    
    print("🧬 VANTAGE:STRESS TEST")
    print("=" * 60)
    print(f"{'PRODUCT':<25} | {'SCORE':<7} | {'RATING'}")
    print("-" * 60)
    
    for item in items:
        results = search_vantage_db(item)
        if results:
            res = results[0]
            score = res['vms_score']
            rating = res['rating']
            print(f"{item:<25} | {score:>7} | {rating}")
        else:
            print(f"❌ {item:<25} | NOT FOUND")

if __name__ == "__main__":
    run_vantage_stress_test()