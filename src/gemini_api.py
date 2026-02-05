"""
FoodVantage - Gemini API Integration Module
============================================

Fixed for Streamlit Cloud deployment with writable temp directory

Author: Meghna Choudhury
Hackathon: Gemini 3 Hackathon (Devpost)
"""

import duckdb
import os
import zipfile
import streamlit as st
import hashlib
from google import genai
from dotenv import load_dotenv

load_dotenv()

# === PATH CONFIGURATION ===
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# === VMS ALGORITHM (UNCHANGED) ===
def calculate_vms_science(row):
    """Vantage Metabolic Score - 100% your original algorithm"""
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
        print(f"[ERROR] VMS calculation failed: {e}")
        return 5.0

# === DATABASE EXTRACTION - FIXED FOR STREAMLIT CLOUD ===
@st.cache_resource
def ensure_database_extracted():
    """
    Extract database to WRITABLE location (/tmp/)
    
    Streamlit Cloud's /mount/src/ is READ-ONLY!
    We must extract to /tmp/ which is writable.
    """
    # Source: Read-only GitHub files
    zip_path = os.path.join(PROJECT_ROOT, 'data', 'vantage_core.zip')
    
    # Destination: Writable temp directory
    temp_db_path = '/tmp/vantage_core.db'
    
    # If already extracted in this session, return it
    if os.path.exists(temp_db_path):
        print(f"[DEBUG] Database already extracted: {temp_db_path}")
        return temp_db_path
    
    # Check if source zip exists
    if not os.path.exists(zip_path):
        print(f"[ERROR] Zip file not found: {zip_path}")
        return None
    
    # Extract to /tmp/ (writable location)
    print(f"📦 Extracting database from {zip_path} to /tmp/...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall('/tmp/')
        
        if os.path.exists(temp_db_path):
            print(f"✅ Database extracted successfully to {temp_db_path}")
            return temp_db_path
        else:
            print(f"[ERROR] Extraction completed but file not found at {temp_db_path}")
            return None
            
    except Exception as e:
        print(f"[ERROR] Failed to extract database: {e}")
        import traceback
        traceback.print_exc()
        return None

# === SCIENTIFIC DATABASE SEARCH ===
def search_vantage_db(product_name: str):
    """Search read-only scientific nutrition database"""
    db_path = ensure_database_extracted()
    
    if not db_path:
        st.error("❌ Scientific database not available")
        return None
    
    if not os.path.exists(db_path):
        st.error(f"❌ Database file not found: {db_path}")
        return None
    
    con = None
    try:
        # Open read-only connection
        con = duckdb.connect(db_path, read_only=True)
        
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
        print(f"[ERROR] Search failed: {e}")
        st.error(f"❌ Search error: {e}")
        return None
        
    finally:
        if con:
            try:
                con.close()
            except:
                pass

# === USER DATA DATABASE ===
@st.cache_resource
def get_db_connection():
    """Get connection to user data database (writable /tmp/ location)"""
    # User data also goes to /tmp/ (writable)
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
    """Create new user account"""
    con = get_db_connection()
    exists = con.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
    if exists: 
        return False
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    con.execute("INSERT INTO users VALUES (?, ?)", [username, pwd_hash])
    return True

def authenticate_user(username, password):
    """Verify user credentials"""
    con = get_db_connection()
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    result = con.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", [username, pwd_hash]).fetchone()
    return result is not None

def add_calendar_item_db(username, date_str, item_name, score):
    """Add item to user's grocery calendar"""
    con = get_db_connection()
    category = 'healthy' if score < 3.0 else 'moderate' if score < 7.0 else 'unhealthy'
    con.execute("INSERT INTO calendar (username, date, item_name, score, category) VALUES (?, ?, ?, ?, ?)", 
                [username, date_str, item_name, score, category])

def get_calendar_items_db(username, date_str):
    """Get all items for a specific date"""
    con = get_db_connection()
    return con.execute("SELECT id, item_name, score, category FROM calendar WHERE username = ? AND date = ?", [username, date_str]).fetchall()

def delete_item_db(item_id):
    """Delete item from calendar"""
    con = get_db_connection()
    con.execute("DELETE FROM calendar WHERE id = ?", [item_id])

def get_log_history_db(username):
    """Get complete grocery log history"""
    con = get_db_connection()
    return con.execute("SELECT date, item_name, score, category FROM calendar WHERE username = ? ORDER BY date DESC", [username]).fetchall()

def get_trend_data_db(username, days=7):
    """Get trend data for health charts"""
    con = get_db_connection()
    try:
        return con.execute("""
            SELECT date, category, COUNT(*) as count FROM calendar
            WHERE username = ? AND date >= current_date - INTERVAL ? DAY
            GROUP BY date, category ORDER BY date ASC
        """, [username, days]).fetchall()
    except Exception as e:
        print(f"[ERROR] Trend query failed: {str(e)}")
        return []

# === GEMINI 3 INTEGRATION ===
def get_gemini_api_key():
    """Retrieve Gemini API key"""
    try:
        if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except:
        pass
    return os.getenv("GEMINI_API_KEY")

def analyze_label_with_gemini(image):
    """Analyze food label using Gemini 3 Flash"""
    api_key = get_gemini_api_key()
    
    if not api_key:
        return """❌ **Error: GEMINI_API_KEY not found**
        
**Setup:** Add GEMINI_API_KEY to Streamlit Cloud Secrets
**Get key:** https://aistudio.google.com/app/apikey"""
    
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = """Analyze this food label image and identify the ingredients.

Return EXACTLY 3 specific concerns related to insulin sensitivity and blood sugar impact.

Format:
• Concern 1: [Ingredient] - [Why concerning for insulin/blood sugar]
• Concern 2: [Ingredient] - [Why concerning for insulin/blood sugar]  
• Concern 3: [Ingredient] - [Why concerning for insulin/blood sugar]"""
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[prompt, image]
        )
        
        return response.text
        
    except Exception as e:
        print(f"[ERROR] Gemini analysis failed: {e}")
        return f"❌ **Error analyzing image:** {e}"