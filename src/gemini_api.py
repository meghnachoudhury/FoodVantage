import duckdb
import os
import streamlit as st
from google import genai
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

# --- 1. SECURE API INITIALIZATION ---
# This ensures it works on both your Mac (local) and Streamlit Cloud (secrets)
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

if not api_key:
    print("Warning: API Key not found. Please check .env or Streamlit Secrets.")

client = genai.Client(api_key=api_key)

# --- 2. GEMINI 3 VISION FUNCTION (New Feature) ---
def analyze_label_with_gemini(image):
    """
    The Brain: Uses Gemini 3 Flash to read labels and detect metabolic triggers.
    """
    prompt = """
    Identify this food product and extract its core ingredient list.
    Focus on:
    1. Hidden sugars (Maltodextrin, syrups, concentrated juices).
    2. High-GI refined starches.
    3. Additives that impact gut-health or insulin.
    
    Return a metabolic summary: List the 3 most concerning ingredients 
    and give a 'Gemini Insight' on why they matter for blood sugar.
    Format using Markdown bullets.
    """
    
    try:
        # Calling the Gemini 3 Flash model
        response = client.models.generate_content(
            model="gemini-3-flash", # Or 'gemini-2.0-flash' / 'gemini-3-flash' depending on availability
            contents=[prompt, image]
        )
        return response.text
    except Exception as e:
        return f"Gemini Analysis Error: {str(e)}"

# --- 3. DATABASE OPTIMIZATION (Your Existing Logic) ---
@st.cache_resource
def get_db_connection():
    """Keeps the database connection open in the background for instant lookups."""
    # Ensure the path is correct relative to where app.py runs
    return duckdb.connect('data/vantage_core.db', read_only=True)

def calculate_vms_science(row):
    # 1. Unpack & Force Sanitize
    # Structure: name, brand, cal, sug, fib, prot, fat, sod, carbs, nova
    name, _, cal, sug, fib, prot, fat, sod, _, nova = row
    cal = float(cal) if cal is not None else 0.0
    sug = float(sug) if sug is not None else 0.0
    fib = float(fib) if fib is not None else 0.0
    prot = float(prot) if prot is not None else 0.0
    fat = float(fat) if fat is not None else 0.0
    sod = float(sod) if sod is not None else 0.0
    nova_val = int(nova) if nova is not None else 1
    
    n = name.lower()

    # 2. Advanced State Detection
    is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'nectar', 'smoothie'])
    is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin', 'mango', 'date'])
    
    # 3. The "Dairy & Superfood" Precision Filter
    is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'apple', 'broccoli', 'egg', 'avocado'])
    
    # Only protect dairy if it isn't a sugar-bomb
    is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
    
    # The Matrix Shield
    is_whole_fresh = (nova_val <= 2 or is_superfood or is_dairy_plain) and not (is_liquid or is_dried)

    # 4. Balanced Scoring (Rayner 2024 Standard)
    # Penalties (A-Points)
    pts_energy = min(cal / 80, 10.0)
    pts_fat = min(fat / 2.0, 10.0) 
    pts_sodium = min(sod / 150, 10.0)
    
    if is_liquid:
        pts_sugar = min(sug / 1.5, 10.0) 
    elif is_whole_fresh:
        pts_sugar = min((sug * 0.2) / 4.5, 10.0) # 80% Matrix Discount
    else:
        pts_sugar = min(sug / 4.5, 10.0)

    # Rewards (C-Points)
    if is_liquid or is_dried:
        c_total = 0.0 
    else:
        c_fiber = min(fib / 0.5, 7.0) 
        c_protein = min(prot / 1.2, 7.0)
        c_total = c_fiber + c_protein

    score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 2)

    # 5. Final Clinical Overrides (The Truth)
    if is_whole_fresh: 
        return min(score, -1.0) 
    
    if is_liquid and sug > 4.0: 
        return max(score, 7.5)  
        
    if is_dried and sug > 15.0: 
        return max(score, 7.0)  
    
    return score

def search_vantage_db(product_name: str):
    con = get_db_connection()
    try:
        # Prioritize exact matches and lower processed versions
        query = f"""
            SELECT * FROM products 
            WHERE product_name ILIKE '%{product_name}%'
            ORDER BY 
                CASE WHEN product_name = '{product_name.lower()}' THEN 0 ELSE 1 END,
                sugar DESC
            LIMIT 1
        """
        results = con.execute(query).fetchall()
        if not results: return None
        r = results[0]
        score = calculate_vms_science(r)
        
        # --- YELLOW CRITERIA ---
        if score < 3.0:
            rating = "Metabolic Green"
        elif 3.0 <= score < 7.0:
            rating = "Metabolic Yellow"
        else:
            rating = "Metabolic Red"
            
        return [{
            "name": r[0].title(),
            "brand": str(r[1]).title() if r[1] else "Generic",
            "vms_score": score,
            "rating": rating
        }]
    except Exception as e:
        print(f"Database error: {e}")
        return None