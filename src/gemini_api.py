"""
FoodVantage - Gemini API (FIXED - accounts for data/ folder in zip)
"""

import duckdb
import os
import zipfile
import streamlit as st
import hashlib
from google import genai
from dotenv import load_dotenv

load_dotenv()

# === VMS ALGORITHM (UNCHANGED) ===
def calculate_vms_science(row):
    """Your original VMS algorithm - 100% unchanged"""
    try:
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal = float(cal) if cal is not None else 0.0
        sug = float(sug) if sug is not None else 0.0
        fib = float(fib) if fib is not None else 0.0
        prot = float(prot) if prot is not None else 0.0
        fat = float(fat) if fat is not None else 0.0
        sod = float(sod) if sod is not None else 0.0
        nova_val = int(nova) if nova is not None else 1
        
        n = name.lower()
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'nectar', 'smoothie'])
        is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin', 'mango', 'date'])
        is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'apple', 'broccoli', 'egg', 'avocado'])
        is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
        is_whole_fresh = (nova_val <= 2 or is_superfood or is_dairy_plain) and not (is_liquid or is_dried)

        pts_energy = min(cal / 80, 10.0)
        pts_fat = min(fat / 2.0, 10.0) 
        pts_sodium = min(sod / 150, 10.0)
        
        if is_liquid:
            pts_sugar = min(sug / 1.5, 10.0)
        elif is_whole_fresh:
            pts_sugar = min((sug * 0.2) / 4.5, 10.0)
        else:
            pts_sugar = min(sug / 4.5, 10.0)

        if is_liquid or is_dried:
            c_total = 0.0
        else:
            c_fiber = min(fib / 0.5, 7.0) 
            c_protein = min(prot / 1.2, 7.0)
            c_total = c_fiber + c_protein

        score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 2)
        
        if is_whole_fresh: return min(score, -1.0)
        if is_liquid and sug > 4.0: return max(score, 7.5)
        if is_dried and sug > 15.0: return max(score, 7.0)
        
        return max(-2.0, min(10.0, score))
        
    except Exception as e:
        return 5.0

# === DATABASE - FIXED FOR data/ FOLDER IN ZIP ===
@st.cache_resource
def get_scientific_db():
    """
    Extract database - FIXED: zip contains 'data/vantage_core.db', not 'vantage_core.db'
    """
    # Find the zip file
    possible_zip_paths = [
        'data/vantage_core.zip',
        './data/vantage_core.zip',
        '/mount/src/foodvantage/data/vantage_core.zip',
    ]
    
    zip_path = None
    for path in possible_zip_paths:
        if os.path.exists(path):
            zip_path = path
            break
    
    # KEY FIX: Zip contains 'data/vantage_core.db', so extracted path is /tmp/data/vantage_core.db
    db_path = '/tmp/data/vantage_core.db'
    
    # If already extracted, use it
    if os.path.exists(db_path):
        try:
            conn = duckdb.connect(db_path, read_only=True)
            conn.execute("SELECT COUNT(*) FROM products").fetchone()
            return conn
        except:
            pass
    
    if not zip_path:
        st.error("❌ Zip file not found in any expected location")
        return None
    
    # Extract
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall('/tmp/')
        
        if not os.path.exists(db_path):
            st.error(f"❌ Database not found at {db_path} after extraction")
            return None
        
        conn = duckdb.connect(db_path, read_only=True)
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        st.success(f"✅ Database ready! {count:,} products loaded")
        return conn
        
    except Exception as e:
        st.error(f"❌ Extraction failed: {e}")
        import traceback
        st.code(traceback.format_exc())
        return None

def search_vantage_db(product_name: str):
    """Search scientific database"""
    con = get_scientific_db()
    
    if not con:
        return None
    
    try:
        safe_name = product_name.replace("'", "''")
        query = f"""
            SELECT * FROM products 
            WHERE product_name ILIKE '%{safe_name}%'
            ORDER BY 
                CASE WHEN LOWER(product_name) = LOWER('{safe_name}') THEN 0 ELSE 1 END,
                sugar DESC
            LIMIT 1
        """
        
        results = con.execute(query).fetchall()
        
        if not results:
            return None
            
        r = results[0]
        score = calculate_vms_science(r)
        rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"
            
        return [{
            "name": r[0].title(),
            "brand": str(r[1]).title() if r[1] else "Generic",
            "vms_score": score,
            "rating": rating
        }]
        
    except Exception as e:
        st.error(f"❌ Search error: {e}")
        return None

# === USER DATABASE ===
@st.cache_resource
def get_db_connection():
    """User data database"""
    db_path = '/tmp/user_data.db'
    con = duckdb.connect(db_path, read_only=False)
    
    con.execute("CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR)")
    
    try:
        con.execute("CREATE SEQUENCE IF NOT EXISTS seq_cal_id START 1")
    except:
        pass
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS calendar (
            id INTEGER DEFAULT nextval('seq_cal_id'),
            username VARCHAR, 
            date DATE, 
            item_name VARCHAR, 
            score FLOAT, 
            category VARCHAR
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
    except:
        return []

# === GEMINI 3 ===
def get_gemini_api_key():
    try:
        if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except:
        pass
    return os.getenv("GEMINI_API_KEY")

def analyze_label_with_gemini(image):
    api_key = get_gemini_api_key()
    if not api_key:
        return "❌ GEMINI_API_KEY not configured"
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = """Analyze this food label and identify 3 concerns for insulin sensitivity/blood sugar.

Format:
• Concern 1: [Ingredient] - [Impact]
• Concern 2: [Ingredient] - [Impact]
• Concern 3: [Ingredient] - [Impact]"""
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[prompt, image]
        )
        return response.text
    except Exception as e:
        return f"❌ Gemini error: {e}"