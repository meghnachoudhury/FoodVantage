import duckdb
import os
import zipfile
import streamlit as st
import hashlib
from google import genai
from dotenv import load_dotenv
from PIL import Image
import io
import base64

load_dotenv()

# === 1. ACCURATE DATABASE ENGINE (UNCHANGED) ===
def calculate_vms_science(row):
    try:
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal, sug, fib, prot, fat, sod = [float(x or 0) for x in [cal, sug, fib, prot, fat, sod]]
        nova_val = int(nova or 1)
        
        n = name.lower()
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage'])
        is_whole_fresh = (nova_val <= 2) and not is_liquid

        pts_energy = min(cal / 80, 10.0)
        pts_fat = min(fat / 2.0, 10.0) 
        pts_sodium = min(sod / 150, 10.0)
        pts_sugar = min((sug * 0.2) / 4.5, 10.0) if is_whole_fresh else min(sug / 1.5, 10.0) if is_liquid else min(sug / 4.5, 10.0)

        c_total = 0.0 if is_liquid else (min(fib / 0.5, 7.0) + min(prot / 1.2, 7.0))
        score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 2)
        
        if is_whole_fresh: return min(score, -1.0)
        if is_liquid and sug > 4.0: return max(score, 7.5)
        return max(-2.0, min(10.0, score))
    except: return 5.0

# === 2. DATABASE ACCESS ===
@st.cache_resource
def get_scientific_db():
    zip_path, db_path = 'data/vantage_core.zip', '/tmp/data/vantage_core.db'
    if not os.path.exists(db_path) and os.path.exists(zip_path):
        os.makedirs('/tmp/data', exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref: 
            zip_ref.extractall('/tmp/')
    return duckdb.connect(db_path, read_only=True)

def search_vantage_db(product_name: str):
    """Search database for product"""
    con = get_scientific_db()
    if not con: return None
    try:
        safe_name = product_name.replace("'", "''")
        query = f"SELECT * FROM products WHERE product_name ILIKE '%{safe_name}%' ORDER BY sugar DESC LIMIT 1"
        
        r = con.execute(query).fetchone()
        if not r: return None
        score = calculate_vms_science(r)
        rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"
        return [{
            "name": r[0].title(), 
            "brand": str(r[1]).title() if r[1] else "Generic",
            "vms_score": score, 
            "rating": rating, 
            "raw": r
        }]
    except Exception as e:
        print(f"DB Error: {e}")
        return None

# === 3. PRECISION VISION SCAN (GEMINI 3 FLASH) ===
def vision_live_scan(image_bytes):
    """
    FIXED: Uses Gemini 3 Flash and handles image processing properly
    """
    api_key = get_gemini_api_key()
    if not api_key: 
        print("No API key found!")
        return None
    
    try:
        # Convert bytes to PIL Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        
        # MATHEMATICAL CROP: Target center 30% to match HUD reticle
        left = int(w * 0.35)
        top = int(h * 0.35)
        right = int(w * 0.65)
        bottom = int(h * 0.65)
        img_cropped = img.crop((left, top, right, bottom))
        
        # Convert to bytes for Gemini
        buf = io.BytesIO()
        img_cropped.save(buf, format="JPEG", quality=85)
        img_data = buf.getvalue()
        
        # Call Gemini 3 Flash
        client = genai.Client(api_key=api_key)
        
        prompt = """Look at this product image and identify the food product.
        
Return ONLY the product name in this format:
[Brand] [Product Name]

Examples:
- "Coca Cola"
- "Lay's Potato Chips"
- "Tropicana Orange Juice"

Be concise. Return only the product name, nothing else."""
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview",  # FIXED: Using Gemini 3
            contents=[prompt, img_data]
        )
        
        product_name = response.text.strip()
        print(f"[VISION] Gemini identified: {product_name}")
        
        # Search database
        result = search_vantage_db(product_name)
        
        if result:
            print(f"[VISION] Found in DB: {result[0]['name']} - Score: {result[0]['vms_score']}")
        else:
            print(f"[VISION] Not found in DB: {product_name}")
        
        return result
        
    except Exception as e:
        print(f"[VISION ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None

# === 4. USER DB & TRENDS ===
@st.cache_resource
def get_db_connection():
    con = duckdb.connect('/tmp/user_data.db', read_only=False)
    con.execute("CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR)")
    try: con.execute("CREATE SEQUENCE IF NOT EXISTS seq_cal_id START 1")
    except: pass
    con.execute("CREATE TABLE IF NOT EXISTS calendar (id INTEGER DEFAULT nextval('seq_cal_id'), username VARCHAR, date DATE, item_name VARCHAR, score FLOAT, category VARCHAR)")
    return con

def get_trend_data_db(username, days=7):
    """FIXED: Returns data in correct format for Streamlit charts"""
    con = get_db_connection()
    try: 
        # Simplified query that works with Streamlit area_chart
        results = con.execute("""
            SELECT 
                date,
                category,
                COUNT(*) as count
            FROM calendar 
            WHERE username = ? AND date >= current_date - INTERVAL ? DAY 
            GROUP BY date, category 
            ORDER BY date ASC
        """, [username, days]).fetchall()
        
        print(f"[TRENDS] Found {len(results)} data points for {username}")
        return results
    except Exception as e:
        print(f"[TRENDS ERROR] {e}")
        return []

# === 5. AUTH HELPERS ===
def get_gemini_api_key():
    if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets: 
        return st.secrets["GEMINI_API_KEY"]
    key = os.getenv("GEMINI_API_KEY")
    if key:
        print(f"[API KEY] Found: {key[:10]}...")
    else:
        print("[API KEY] NOT FOUND!")
    return key

def authenticate_user(username, password):
    con = get_db_connection()
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    result = con.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", [username, pwd_hash]).fetchone()
    return result is not None

def add_calendar_item_db(username, date_str, item_name, score):
    con = get_db_connection()
    category = 'healthy' if score < 3.0 else 'moderate' if score < 7.0 else 'unhealthy'
    con.execute("INSERT INTO calendar (username, date, item_name, score, category) VALUES (?, ?, ?, ?, ?)", [username, date_str, item_name, score, category])
    print(f"[CALENDAR] Added: {item_name} ({score}) for {username} on {date_str}")

def get_calendar_items_db(username, date_str):
    con = get_db_connection()
    return con.execute("SELECT id, item_name, score, category FROM calendar WHERE username = ? AND date = ?", [username, date_str]).fetchall()

def delete_item_db(item_id):
    con = get_db_connection()
    con.execute("DELETE FROM calendar WHERE id = ?", [item_id])

def get_log_history_db(username):
    con = get_db_connection()
    return con.execute("SELECT date, item_name, score, category FROM calendar WHERE username = ? ORDER BY date DESC", [username]).fetchall()

def create_user(username, password):
    con = get_db_connection()
    exists = con.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
    if exists: return False
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    con.execute("INSERT INTO users VALUES (?, ?)", [username, pwd_hash])
    return True