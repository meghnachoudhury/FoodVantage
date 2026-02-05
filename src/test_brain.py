from gemini_api import calculate_vms_science

# Mocking database rows: [name, brand, cal, sug, fib, prot, fat, sod, carbs, nova]
# These values are based on standard nutritional data for 100g
stress_test_items = [
    # --- THE DISRUPTORS (RED) ---
    ("Orange Juice", "Fresh", 45, 9.0, 0.2, 0.7, 0.2, 1.0, 10.0, 3), # Liquid Sugar Bomb
    ("Coca Cola", "Classic", 42, 10.6, 0.0, 0.0, 0.0, 4.0, 10.6, 4),# Ultra-processed Liquid
    ("Honey", "Pure", 304, 82.0, 0.0, 0.3, 0.0, 4.0, 82.0, 2),      # Concentrated Sugar/No Matrix
    
    # --- THE PROTECTORS (GREEN) ---
    ("Salmon", "Wild", 208, 0.0, 0.0, 20.0, 13.0, 59.0, 0.0, 1),    # Superfood / Zero Sugar
    ("Lentils", "Cooked", 116, 1.8, 7.9, 9.0, 0.4, 2.0, 20.0, 1),   # Fiber Matrix Reward
    ("Avocado", "Fresh", 160, 0.7, 7.0, 2.0, 15.0, 7.0, 8.5, 1),    # Matrix Shield + Healthy Fat
    ("Apple", "Fuji", 52, 10.0, 2.4, 0.3, 0.2, 1.0, 14.0, 1),       # Matrix Protected Sugar
    ("Broccoli", "Steamed", 35, 1.7, 3.3, 2.4, 0.4, 33.0, 7.0, 1),  # Fiber King
    ("Egg", "Boiled", 155, 1.1, 0.0, 13.0, 11.0, 124.0, 1.1, 1),    # Protein Reward
    
    # --- THE DAIRY FILTER ---
    ("Yogurt", "Plain", 61, 4.7, 0.0, 3.5, 3.3, 46.0, 4.7, 1),      # Dairy Protection Triggered (<5g sug)
    ("Yogurt Berry", "Sweet", 110, 15.0, 0.1, 3.0, 2.5, 40.0, 18.0, 3) # Dairy Protection Fails (>5g sug)
]

print("\n" + "="*60)
print(f"{'ITEM':<15} | {'VMS SCORE':<10} | {'METABOLIC RATING'}")
print("="*60)

for row in stress_test_items:
    score = calculate_vms_science(row)
    
    # Color/Rating Logic
    if score < 3.0:
        rating = "🟢 Metabolic Green (Protector)"
    elif score < 7.0:
        rating = "🟡 Metabolic Yellow (Neutral)"
    else:
        rating = "🔴 Metabolic Red (Disruptor)"
        
    print(f"{row[0]:<15} | {score:<10} | {rating}")

print("="*60 + "\n")