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

# === VMS ALGORITHM (UNCHANGED) ===
def calculate_vms_science(row):
    try:
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal, sug, fib = float(cal or 0), float(sug or 0), float(fib or 0)
        prot, fat, sod = float(prot or 0), float(fat or 0), float(sod or 0)
        nova_val = int(nova or 1)
        
        n = name.lower()
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'nectar', 'smoothie'])
        is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin', 'mango', 'date'])
        is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'apple', 'broccoli', 'egg', 'avocado'])
        is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
        is_whole_fresh = (nova_val <= 2 or is_superfood or is_dairy_plain) and not (is_liquid or is_dried)

        pts_energy = min(cal / 80, 10.0)
        pts_fat = min(fat / 2.0, 10.0) 
        pts_sodium = min(sod / 150, 10.0)
        
        if is_liquid: pts_sugar = min(sug / 1.5, 10.0)
        elif is_whole_fresh: pts_sugar = min((sug * 0.2) / 4.5, 10.0)
        else: pts_sugar = min(sug / 4.5, 10.0)

        c_total = 0.0 if (is_liquid or is_dried) else (min(fib / 0.5, 7.0) + min(prot / 1.2, 7.0))

        score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 2)
        if is_whole_fresh: return min(score, -1.0)
        if is_liquid and sug > 4.0: return max(score, 7.5)
        if is_dried and sug > 15.0: return max(score, 7.0)
        return max(-2.0, min(10.0, score))
    except: return 5.0

# === DATABASE ACCESS (UNCHANGED) ===
@st.cache_resource
def get_scientific_db():
    zip_path = 'data/vantage_core.zip'
    db_path = '/tmp/data/vantage_core.db'
    if not os.path.exists(db_path) and os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall('/tmp/')
    return duckdb.connect(db_path, read_only=True)

def search_vantage_db(product_name: str):
    con = get_scientific_db()
    if not con: return None
    try:
        safe_name = product_name.replace("'", "''")
        query = f"SELECT * FROM products WHERE product_name ILIKE '%{safe_name}%' LIMIT 1"
        results = con.execute(query).fetchall()
        if not results: return None
        r = results[0]
        score = calculate_vms_science(r)
        rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"
        return [{"name": r[0].title(), "brand": str(r[1]).title() if r[1] else "Generic", "vms_score": score, "rating": rating, "raw": r}]
    except: return None

# === HUD VISION BRIDGE (CENTERED CROP) ===
def vision_live_scan(image_bytes):
    api_key = os.getenv("GEMINI_API_KEY") or (st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else None)
    if not api_key: return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        # PERFECT CENTER CROP: 140px relative area
        left, top, right, bottom = w*0.35, h*0.35, w*0.65, h*0.65
        img_cropped = img.crop((left, top, right, bottom))
        buf = io.BytesIO()
        img_cropped.save(buf, format="JPEG")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model="gemini-3-flash-preview", contents=["Only return Brand and Product name from this label.", buf.getvalue()])
        return search_vantage_db(response.text.strip())
    except: return None

# === USER DATA LOGGING (UNCHANGED) ===
@st.cache_resource
def get_db_connection():
    con = duckdb.connect('/tmp/user_data.db', read_only=False)
    con.execute("CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR)")
    try: con.execute("CREATE SEQUENCE IF NOT EXISTS seq_cal_id START 1")
    except: pass
    con.execute("CREATE TABLE IF NOT EXISTS calendar (id INTEGER DEFAULT nextval('seq_cal_id'), username VARCHAR, date DATE, item_name VARCHAR, score FLOAT, category VARCHAR)")
    return con

def get_gemini_api_key():
    if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets: return st.secrets["GEMINI_API_KEY"]
    return os.getenv("GEMINI_API_KEY")

# Auth/Log helpers omitted for brevity but remain identical to your source
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
    category = 'healthy' if score < 3.0 else 'moderate' if score < 7.0 else 'unhealthy'
    con.execute("INSERT INTO calendar (username, date, item_name, score, category) VALUES (?, ?, ?, ?, ?)", [username, date_str, item_name, score, category])

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
    try: return con.execute("SELECT CAST(date AS VARCHAR), category, COUNT(*) FROM calendar WHERE username = ? AND date >= current_date - INTERVAL ? DAY GROUP BY date, category ORDER BY date ASC", [username, days]).fetchall()
    except: return []

def analyze_label_with_gemini(image):
    api_key = get_gemini_api_key()
    if not api_key: return "❌ Key not configured"
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model="gemini-3-flash-preview", contents=["Analyze ingredients for insulin sensitivity.", image])
        return response.text
    except Exception as e: return f"❌ Error: {e}"