#!/usr/bin/env python3
"""
Local testing script for VMS algorithm and Local LLM integration.
Run this in your venv to test without Streamlit.

Usage:
    cd FoodVantage/src
    python test_brain.py
"""

from gemini_api import calculate_vms_science
from local_llm import LocalLLM

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

def test_vms():
    print("\n" + "="*80)
    print("FOODVANTAGE VMS ALGORITHM TEST")
    print("Testing the Vantage Metabolic Score calculation")
    print("="*80)
    print(f"{'ITEM':<20} | {'CALORIES':<8} | {'SUGAR':<6} | {'VMS SCORE':<10} | {'RATING'}")
    print("="*80)

    for row in stress_test_items:
        name, brand, cal, sug, fib, prot, fat, sod, carbs, nova = row
        score = calculate_vms_science(row)

        # Color/Rating Logic
        if score < 3.0:
            rating = "Metabolic Green (Protector)"
        elif score < 7.0:
            rating = "Metabolic Yellow (Neutral)"
        else:
            rating = "Metabolic Red (Disruptor)"

        print(f"{name:<20} | {cal:<8.1f} | {sug:<6.1f} | {score:<10.1f} | {rating}")

    print("="*80)
    print("\nExpected results:")
    print("  GREEN  (<3.0): Salmon, Lentils, Avocado, Apple, Broccoli, Egg, Plain Yogurt")
    print("  YELLOW (3-7):  (may vary based on specific values)")
    print("  RED    (>7.0): Orange Juice, Coca Cola, Honey, Sweet Yogurt")
    print("="*80 + "\n")


def test_local_llm():
    print("\n" + "="*80)
    print("LOCAL LLM CONNECTION TEST")
    print("Testing Ollama connectivity and model availability")
    print("="*80)

    llm = LocalLLM()

    # Test 1: Connection
    print("\n[TEST 1] Checking Ollama connection...")
    if llm.is_available():
        print("  PASS: Ollama is running")
    else:
        print("  FAIL: Ollama is not reachable")
        print("  -> Start Ollama with: ollama serve")
        print("  -> Or install from: https://ollama.com")
        print("="*80 + "\n")
        return

    # Test 2: Model availability
    print("\n[TEST 2] Checking available models...")
    models = llm.list_models()
    print(f"  Available models: {models}")

    has_vision = llm.has_model(llm.vision_model)
    has_text = llm.has_model(llm.text_model)
    print(f"  Vision model ({llm.vision_model}): {'READY' if has_vision else 'NOT FOUND'}")
    print(f"  Text model ({llm.text_model}): {'READY' if has_text else 'NOT FOUND'}")

    if not has_vision:
        print(f"  -> Pull vision model: ollama pull {llm.vision_model}")
    if not has_text:
        print(f"  -> Pull text model: ollama pull {llm.text_model}")

    # Test 3: Text generation (food parsing)
    if has_text:
        print("\n[TEST 3] Testing food parsing...")
        result = llm.parse_food_input("2 cups of greek yogurt with honey")
        if result:
            print(f"  PASS: Parsed food input")
            for k, v in result.items():
                print(f"    {k}: {v}")
        else:
            print("  FAIL: Could not parse food input")

        # Test 4: Health insights
        print("\n[TEST 4] Testing health insights generation...")
        insights = llm.generate_health_insights(
            total_items=10,
            healthy_count=6,
            moderate_count=3,
            unhealthy_count=1,
            recent_items_str="- 2025-01-15: Apple (score: -1.0, healthy)\n- 2025-01-15: Coca Cola (score: 7.5, unhealthy)",
            days_range=7,
        )
        if insights and len(insights) > 0:
            print(f"  PASS: Generated {len(insights)} insights")
            for i, ins in enumerate(insights):
                print(f"    {i+1}. {ins.get('emoji', '')} {ins.get('title', 'N/A')}")
        else:
            print("  FAIL: Could not generate insights")
    else:
        print("\n[TEST 3-4] SKIPPED: Text model not available")

    print("="*80 + "\n")


if __name__ == "__main__":
    test_vms()
    test_local_llm()
