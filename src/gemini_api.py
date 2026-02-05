import duckdb
import os
import streamlit as st
import hashlib
from google import genai
from dotenv import load_dotenv

load_dotenv()

# --- 1. THE SCIENTIFIC ENGINE (STRESS-TESTED) ---
def calculate_vms_science(row):
    """
    Advanced Metabolic Scoring Algorithm.
    Incorporates Matrix Shield, Liquid Penalties, and NOVA Processing.
    """
    try:
        # Unpack & Force Sanitize
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal = float(cal) if cal is not None else 0.0
        sug = float(sug) if sug is not None else 0.0
        fib = float(fib) if fib is not None else 0.0
        prot = float(prot) if prot is not None else 0.0
        fat = float(fat) if fat is not None else 0.0
        sod = float(sod) if sod is not None else 0.0
        nova_val = int(nova) if nova is not None else 1
        
        n = name.lower()

        # Advanced State Detection
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'nectar', 'smoothie'])
        is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin', 'mango', 'date'])
        
        # Dairy & Superfood Precision Filter
        is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'apple', 'broccoli', 'egg', 'avocado'])
        is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
        
        # Whole Food Matrix Protection
        is_whole_fresh = (nova_val <= 2 or is_superfood or is_dairy_plain) and not (is_liquid or is_dried)

        # Balanced Scoring (Rayner 2024 Standard)
        pts_energy = min(cal / 80, 10.0)
        pts_fat = min(fat / 2.0, 10.0) 
        pts_sodium = min(sod / 150, 10.0)
        
        if is_liquid:
            pts_sugar = min(sug / 1.5, 10.0) 
        elif is_whole_fresh:
            pts_sugar = min((sug * 0.2) / 4.5, 10.0) # 80% Matrix Shield
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

        # Final Clinical Overrides (The Truth)
        if is_whole_fresh: return min(score, -1.0) 
        if is_liquid and sug > 4.0: return max(score, 7.5)  
        if is_dried and sug > 15.0: return max(score, 7.0)  
        
        return max(-2.0, min(10.0, score)) # Final clamping
    except Exception:
        return 5.0

# --- 2. DATABASE SEARCH ---
def search_vantage_db(product_name: str):
    con = duckdb.connect('data/vantage_core.db', read_only=True)
    try:
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
        
        if score < 3.0: rating = "Metabolic Green"
        elif 3.0 <= score < 7.0: rating = "Metabolic Yellow"
        else: rating = "Metabolic Red"
            
        return {
            "name": r[0].title(),
            "brand": str(r[1]).title() if r[1] else "Generic",
            "vms_score": score,
            "rating": rating
        }
    finally:
        con.close()

# --- 3. UI SUPPORT FUNCTIONS ---
@st.cache_resource
def get_db_connection():
    con = duckdb.connect('data/vantage_core.db', read_only=False)
    con.execute("CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR)")
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_cal_id;
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
    category = 'healthy' if score < 3.0 else 'moderate' if score < 7.0 else 'unhealthy'
    con.execute("INSERT INTO calendar (username, date, item_name, score, category) VALUES (?, ?, ?, ?, ?)", 
                [username, date_str, item_name, score, category])

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
        return con.execute("""
            SELECT date, category, COUNT(*) as count FROM calendar
            WHERE username = ? AND date >= current_date - INTERVAL ? DAY
            GROUP BY date, category ORDER BY date ASC
        """, [username, days]).fetchall()
    except Exception: return []

# --- 4. GEMINI AI ---
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def analyze_label_with_gemini(image):
    prompt = "Identify food ingredients. Return 3 concerns for insulin in Markdown."
    try:
        response = client.models.generate_content(model="gemini-3-flash", contents=[prompt, image])
        return response.text
    except Exception as e: return f"Error: {str(e)}"