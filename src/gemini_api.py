import duckdb
import os
import streamlit as st
import hashlib
from google import genai
from dotenv import load_dotenv

load_dotenv()

# === CRITICAL PATH FIX ===
# On Streamlit Cloud, the app structure is:
# /mount/src/foodvantage/app.py
# /mount/src/foodvantage/src/gemini_api.py  <- we are HERE
# /mount/src/foodvantage/data/vantage_core.db
#
# We need to go UP one level from this file to get to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 1. THE SCIENTIFIC ENGINE ---
def calculate_vms_science(row):
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
    except Exception:
        return 5.0

# --- 2. DATABASE SEARCH (READ-ONLY - SCIENTIFIC DATA) ---
def search_vantage_db(product_name: str):
    """
    Searches the read-only scientific database for product information.
    Uses PROJECT_ROOT to find the database correctly on both local and Streamlit Cloud.
    """
    # CORRECT PATH: Use __file__ to find project root, then append 'data/vantage_core.db'
    db_path = os.path.join(PROJECT_ROOT, 'data', 'vantage_core.db')
    
    # Debug info (will show in Streamlit Cloud logs)
    print(f"[DEBUG] PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"[DEBUG] Looking for database at: {db_path}")
    print(f"[DEBUG] Database exists? {os.path.exists(db_path)}")
    
    # Check if database exists
    if not os.path.exists(db_path):
        # Try to list what IS in the data directory
        data_dir = os.path.join(PROJECT_ROOT, 'data')
        if os.path.exists(data_dir):
            print(f"[DEBUG] Files in data directory:")
            for f in os.listdir(data_dir):
                print(f"[DEBUG]   - {f}")
        else:
            print(f"[DEBUG] Data directory doesn't exist at: {data_dir}")
        
        st.error(f"❌ Database not found at: {db_path}")
        st.info("💡 Make sure 'data/vantage_core.db' is committed to your GitHub repository and NOT in .gitignore")
        return None
    
    try:
        # Open in read_only mode - this is ONLY for reading scientific data
        con = duckdb.connect(db_path, read_only=True)
        
        # Escape single quotes to prevent SQL injection
        safe_product_name = product_name.replace("'", "''")
        
        query = f"""
            SELECT * FROM products 
            WHERE product_name ILIKE '%{safe_product_name}%'
            ORDER BY 
                CASE WHEN LOWER(product_name) = LOWER('{safe_product_name}') THEN 0 ELSE 1 END,
                sugar DESC
            LIMIT 1
        """
        results = con.execute(query).fetchall()
        con.close()
        
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
        st.error(f"❌ Error searching database: {str(e)}")
        print(f"[ERROR] Database query failed: {str(e)}")
        return None

# --- 3. USER DATA DATABASE (READ-WRITE - SEPARATE FILE) ---
@st.cache_resource
def get_db_connection():
    """
    Gets connection to the user data database (separate from scientific data).
    This database stores user accounts, calendar items, etc.
    Uses PROJECT_ROOT to ensure correct path on Streamlit Cloud.
    """
    # Use a SEPARATE database file for user data to avoid locking issues
    db_path = os.path.join(PROJECT_ROOT, 'data', 'user_data.db')
    
    print(f"[DEBUG] User database path: {db_path}")
    
    # Create the data directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Open in read-write mode for user data
    con = duckdb.connect(db_path, read_only=False)
    
    # Create tables if they don't exist
    con.execute("CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR)")
    
    # Check if sequence exists before creating
    try:
        con.execute("CREATE SEQUENCE IF NOT EXISTS seq_cal_id START 1")
    except:
        # Sequence might already exist, that's fine
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
    if exists: 
        return False
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
    except Exception as e:
        print(f"[ERROR] Trend data query failed: {str(e)}")
        return []

# --- 4. GEMINI AI ---
def get_gemini_api_key():
    """Get API key from Streamlit secrets or environment variables"""
    try:
        # Try Streamlit secrets first (for Streamlit Cloud deployment)
        if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except:
        pass
    
    # Fall back to environment variable (for local development)
    return os.getenv("GEMINI_API_KEY")

def analyze_label_with_gemini(image):
    """
    Analyzes food label image using Gemini API.
    This is a core requirement for the Gemini 3 Hackathon.
    """
    api_key = get_gemini_api_key()
    
    if not api_key:
        return """❌ **Error: GEMINI_API_KEY not found**
        
Please add your Gemini API key:
1. Go to Streamlit Cloud dashboard
2. Click on your app → Settings → Secrets
3. Add: `GEMINI_API_KEY = "your-api-key-here"`

Or for local development, add to `.env` file:
```
GEMINI_API_KEY=your-api-key-here
```
"""
    
    try:
        client = genai.Client(api_key=api_key)
        prompt = """Analyze this food label image and identify the ingredients. 
        Return exactly 3 specific concerns related to insulin sensitivity and blood sugar impact.
        Format your response in clear Markdown with bullet points.
        Be specific about which ingredients cause concern and why."""
        
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",  # Using Gemini 2.0 as required by hackathon
            contents=[prompt, image]
        )
        return response.text
    except Exception as e: 
        return f"""❌ **Error analyzing image:** {str(e)}
        
This might be due to:
1. Invalid API key
2. API quota exceeded
3. Network issues
4. Invalid image format

Please check your Gemini API key in Streamlit secrets."""