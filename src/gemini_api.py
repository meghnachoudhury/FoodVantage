import duckdb
import os
import zipfile
import streamlit as st
import hashlib
from google import genai
from dotenv import load_dotenv
from PIL import Image
import io

load_dotenv()

# --- 1. THE SCIENTIFIC ENGINE (RAYNER 2024 / NOVA HYBRID) ---
def calculate_vms_science(row):
    """Calculates the Metabolic Score based on 10 parameters."""
    try:
        # Expected: [name, brand, cal, sug, fib, prot, fat, sod, carbs, nova]
        name, _, cal, sug, fib, prot, fat, sod, carbs, nova = row
        cal, sug, fib = float(cal or 0), float(sug or 0), float(fib or 0)
        prot, fat, sod, carbs = float(prot or 0), float(fat or 0), float(sod or 0), float(carbs or 0)
        nova_val = int(nova or 1)
        
        n = name.lower()
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'nectar', 'smoothie'])
        is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin', 'mango', 'date'])
        is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'apple', 'broccoli', 'egg', 'avocado'])
        is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
        is_whole_fresh = (nova_val <= 2 or is_superfood or is_dairy_plain) and not (is_liquid or is_dried)

        # Penalties
        pts_energy = min(cal / 80, 10.0)
        pts_fat = min(fat / 2.0, 10.0) 
        pts_sodium = min(sod / 150, 10.0)
        
        if is_liquid:
            pts_sugar = min(sug / 1.5, 10.0)
        elif is_whole_fresh:
            pts_sugar = min((sug * 0.2) / 4.5, 10.0) # 80% Metabolic Discount
        else:
            pts_sugar = min(sug / 4.5, 10.0)

        # Rewards
        if is_liquid or is_dried:
            c_total = 0.0
        else:
            c_fiber = min(fib / 0.5, 7.0) 
            c_protein = min(prot / 1.2, 7.0)
            c_total = c_fiber + c_protein

        score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 2)
        
        # Clinical Overrides
        if is_whole_fresh: score = min(score, -1.0)
        if is_liquid and sug > 4.0: score = max(score, 7.5)
        
        return max(-2.0, min(10.0, score))
    except:
        return 5.0

# --- 2. DATABASE MANAGEMENT ---
@st.cache_resource
def get_scientific_db():
    """Extracts and connects to the 1M+ product database."""
    zip_path = 'data/vantage_core.zip'
    db_path = '/tmp/data/vantage_core.db'
    
    if not os.path.exists(db_path):
        if os.path.exists(zip_path):
            os.makedirs('/tmp/data', exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall('/tmp/')
    
    return duckdb.connect(db_path, read_only=True)

def search_vantage_db(product_name: str):
    """Searches local database to prevent AI hallucinations."""
    con = get_scientific_db()
    if not con: return None
    try:
        safe_name = product_name.replace("'", "''")
        query = f"""
            SELECT * FROM products 
            WHERE product_name ILIKE '%{safe_name}%' 
            ORDER BY CASE WHEN LOWER(product_name) = LOWER('{safe_name}') THEN 0 ELSE 1 END, sugar DESC 
            LIMIT 1
        """
        r = con.execute(query).fetchone()
        if not r: return None
        
        score = calculate_vms_science(r)
        return {
            "name": r[0].title(),
            "brand": r[1].title() if r[1] else "Generic",
            "score": score,
            "rating": "Green" if score < 3 else "Yellow" if score < 7 else "Red",
            "vitals": {"cal": r[2], "sug": r[3], "fib": r[4], "prot": r[5], "fat": r[6], "sod": r[7], "carb": r[8]}
        }
    except: return None

# --- 3. LIVE HUD VISION PIPELINE ---
def get_gemini_api_key():
    if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    return os.getenv("GEMINI_API_KEY")

def vision_live_scan(image_bytes):
    """The Active Focus Engine: Crops image -> OCR -> Local DB Search."""
    api_key = get_gemini_api_key()
    if not api_key: return None
    
    try:
        # Center-crop image for Active Focus
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        img_cropped = img.crop((w/4, h/4, 3*w/4, 3*h/4))
        
        # Save cropped to buffer
        buf = io.BytesIO()
        img_cropped.save(buf, format="JPEG")
        
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=["Identify the Brand and Product Name on this label. Output ONLY 'Brand Product'", buf.getvalue()]
        )
        return search_vantage_db(response.text.strip())
    except: return None

# --- 4. USER DATABASE & LOGGING ---
@st.cache_resource
def get_db_connection():
    db_path = '/tmp/user_data.db'
    con = duckdb.connect(db_path, read_only=False)
    con.execute("CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR)")
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_cal_id START 1")
    con.execute("""
        CREATE TABLE IF NOT EXISTS calendar (
            id INTEGER DEFAULT nextval('seq_cal_id'),
            username VARCHAR, date DATE, item_name VARCHAR, score FLOAT, category VARCHAR
        )
    """)
    return con

def create_user(username, password):
    con = get_db_connection()
    exists = con.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
    if exists: return False
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    con.execute("INSERT INTO users VALUES (?, ?)", [username, pwd_hash])
    return True

def authenticate_user(username, password):
    con = get_db_connection()
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    result = con.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", [username, pwd_hash]).fetchone()
    return result is not None

def add_calendar_item_db(username, date_str, item_name, score):
    con = get_db_connection()
    cat = 'healthy' if score < 3.0 else 'moderate' if score < 7.0 else 'unhealthy'
    con.execute("INSERT INTO calendar (username, date, item_name, score, category) VALUES (?, ?, ?, ?, ?)", 
                [username, date_str, item_name, score, cat])

def get_calendar_items_db(username, date_str):
    con = get_db_connection()
    return con.execute("SELECT id, item_name, score, category FROM calendar WHERE username = ? AND date = ?", [username, date_str]).fetchall()

def delete_item_db(item_id):
    con = get_db_connection()
    con.execute("DELETE FROM calendar WHERE id = ?", [item_id])

def get_log_history_db(username):
    con = get_db_connection()
    return con.execute("SELECT date, item_name, score, category FROM calendar WHERE username = ? ORDER BY date DESC", [username]).fetchall()

def get_trend_data_db(username, days=7):
    con = get_db_connection()
    try:
        # CAST to VARCHAR fixes the st.scatter_chart error
        return con.execute("""
            SELECT CAST(date AS VARCHAR), category, COUNT(*) FROM calendar
            WHERE username = ? AND date >= current_date - INTERVAL ? DAY
            GROUP BY date, category ORDER BY date ASC
        """, [username, days]).fetchall()
    except: return []

def analyze_label_with_gemini(image):
    api_key = get_gemini_api_key()
    if not api_key: return "❌ API Key Missing"
    try:
        client = genai.Client(api_key=api_key)
        prompt = "Identify 3 metabolic concerns from this ingredient list."
        response = client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt, image])
        return response.text
    except Exception as e: return f"❌ Error: {e}"