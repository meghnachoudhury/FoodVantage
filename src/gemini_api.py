"""
FoodVantage - Gemini API Integration Module (DEBUGGING VERSION)
================================================================

This module integrates Google's Gemini 3 Flash model for food label analysis
and manages database operations for the FoodVantage application.

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

# === PATH CONFIGURATION WITH DEBUGGING ===
def get_project_root():
    """Get project root with detailed debugging"""
    # Try multiple methods to find project root
    
    # Method 1: Based on this file's location
    current_file = os.path.abspath(__file__)
    method1_root = os.path.dirname(os.path.dirname(current_file))
    
    # Method 2: Based on current working directory
    cwd = os.getcwd()
    method2_root = cwd
    
    # Method 3: Check if we're in src/ subdirectory
    if os.path.basename(cwd) == 'src':
        method3_root = os.path.dirname(cwd)
    else:
        method3_root = cwd
    
    # Print debugging info (will show in terminal)
    print("[DEBUG] PATH RESOLUTION:")
    print(f"  __file__: {current_file}")
    print(f"  Method 1 (from __file__): {method1_root}")
    print(f"  Method 2 (from cwd): {method2_root}")
    print(f"  Method 3 (adjusted): {method3_root}")
    
    # Use method 1 by default, but fall back if needed
    for root in [method1_root, method3_root, method2_root]:
        data_dir = os.path.join(root, 'data')
        if os.path.exists(data_dir):
            print(f"  ✅ Using: {root}")
            return root
    
    print(f"  ⚠️  Falling back to: {method1_root}")
    return method1_root

PROJECT_ROOT = get_project_root()

# === VMS ALGORITHM (UNCHANGED) ===
def calculate_vms_science(row):
    """
    Vantage Metabolic Score (VMS) Algorithm
    
    NO CHANGES - This algorithm is 100% your original code
    """
    try:
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal = float(cal) if cal is not None else 0.0
        sug = float(sug) if sug is not None else 0.0
        fib = float(fib) if fib is not None else 0.0
        prot = float(prot) if prot is not None else 0.0
        fat = float(fat) if fat is not None else 0.0
        sod = float(sod) if sod is not None else 0.0
        nova_val = int(nova) if nova is not None else 1
        
        # Food classification
        n = name.lower()
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'nectar', 'smoothie'])
        is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin', 'mango', 'date'])
        is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'apple', 'broccoli', 'egg', 'avocado'])
        is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
        is_whole_fresh = (nova_val <= 2 or is_superfood or is_dairy_plain) and not (is_liquid or is_dried)

        # Penalty points
        pts_energy = min(cal / 80, 10.0)
        pts_fat = min(fat / 2.0, 10.0) 
        pts_sodium = min(sod / 150, 10.0)
        
        # Sugar penalty with adjustments
        if is_liquid:
            pts_sugar = min(sug / 1.5, 10.0)
        elif is_whole_fresh:
            pts_sugar = min((sug * 0.2) / 4.5, 10.0)
        else:
            pts_sugar = min(sug / 4.5, 10.0)

        # Protective factors
        if is_liquid or is_dried:
            c_total = 0.0
        else:
            c_fiber = min(fib / 0.5, 7.0) 
            c_protein = min(prot / 1.2, 7.0)
            c_total = c_fiber + c_protein

        # Final score
        score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 2)
        
        # Special case adjustments
        if is_whole_fresh: return min(score, -1.0)
        if is_liquid and sug > 4.0: return max(score, 7.5)
        if is_dried and sug > 15.0: return max(score, 7.0)
        
        return max(-2.0, min(10.0, score))
        
    except Exception as e:
        print(f"[ERROR] VMS calculation failed: {e}")
        return 5.0

# === DATABASE EXTRACTION WITH BETTER DEBUGGING ===
def ensure_database_extracted():
    """
    Ensures database is available - with extensive debugging
    """
    db_path = os.path.join(PROJECT_ROOT, 'data', 'vantage_core.db')
    zip_path = os.path.join(PROJECT_ROOT, 'data', 'vantage_core.zip')
    
    print(f"[DEBUG] ensure_database_extracted() called")
    print(f"  Looking for DB: {db_path}")
    print(f"  Looking for ZIP: {zip_path}")
    print(f"  DB exists: {os.path.exists(db_path)}")
    print(f"  ZIP exists: {os.path.exists(zip_path)}")
    
    # Check if data directory exists
    data_dir = os.path.join(PROJECT_ROOT, 'data')
    if not os.path.exists(data_dir):
        print(f"  ❌ Data directory doesn't exist: {data_dir}")
        return None
    
    # List what's in data directory
    print(f"  Files in data/:")
    try:
        for f in os.listdir(data_dir):
            print(f"    - {f}")
    except Exception as e:
        print(f"    Error listing: {e}")
    
    # Database already extracted
    if os.path.exists(db_path):
        print(f"  ✅ Database file found")
        return db_path
    
    # Extract from zip file
    if os.path.exists(zip_path):
        print("📦 FoodVantage: Extracting compressed metabolic index...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(os.path.join(PROJECT_ROOT, 'data'))
            print("✅ Database extracted successfully")
            
            # Verify extraction worked
            if os.path.exists(db_path):
                print(f"  ✅ Verified: {db_path} now exists")
                return db_path
            else:
                print(f"  ❌ Extraction seemed to work but file not found")
                return None
                
        except Exception as e:
            print(f"❌ Error extracting database: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # Neither file exists
    print(f"❌ Neither database nor zip file found!")
    print(f"   Expected DB: {db_path}")
    print(f"   Expected ZIP: {zip_path}")
    return None

# === SCIENTIFIC DATABASE SEARCH ===
def search_vantage_db(product_name: str):
    """
    Searches the read-only scientific nutrition database.
    """
    print(f"\n[DEBUG] search_vantage_db() called for: {product_name}")
    
    # Ensure database is available
    db_path = ensure_database_extracted()
    
    if not db_path:
        print(f"[ERROR] ensure_database_extracted() returned None")
        st.error("❌ Scientific database not available")
        return None
    
    if not os.path.exists(db_path):
        print(f"[ERROR] Database path doesn't exist: {db_path}")
        st.error(f"❌ Database file not found: {db_path}")
        return None
    
    print(f"[DEBUG] Database path: {db_path}")
    print(f"[DEBUG] File size: {os.path.getsize(db_path):,} bytes")
    
    con = None
    try:
        print(f"[DEBUG] Opening database in read-only mode...")
        # Open NEW read-only connection
        con = duckdb.connect(db_path, read_only=True)
        print(f"[DEBUG] Connection opened successfully")
        
        # Sanitize input
        safe_name = product_name.replace("'", "''")
        
        # Search query
        query = f"""
            SELECT * FROM products 
            WHERE product_name ILIKE '%{safe_name}%'
            ORDER BY 
                CASE WHEN LOWER(product_name) = LOWER('{safe_name}') THEN 0 ELSE 1 END,
                sugar DESC
            LIMIT 1
        """
        
        print(f"[DEBUG] Executing query...")
        results = con.execute(query).fetchall()
        print(f"[DEBUG] Query returned {len(results)} results")
        
        if not results:
            print(f"[DEBUG] No results found for '{product_name}'")
            return None
            
        # Calculate VMS score
        r = results[0]
        score = calculate_vms_science(r)
        
        print(f"[DEBUG] Found: {r[0]} | Score: {score}")
        
        # Determine rating
        rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"
            
        return [{
            "name": r[0].title(),
            "brand": str(r[1]).title() if r[1] else "Generic",
            "vms_score": score,
            "rating": rating
        }]
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Search failed: {error_msg}")
        import traceback
        traceback.print_exc()
        st.error(f"❌ Search error: {error_msg}")
        return None
        
    finally:
        if con:
            try:
                con.close()
                print("[DEBUG] Connection closed")
            except:
                pass

# === USER DATA DATABASE ===
@st.cache_resource
def get_db_connection():
    """
    Gets connection to user data database (SEPARATE from scientific data)
    """
    db_path = os.path.join(PROJECT_ROOT, 'data', 'user_data.db')
    
    print(f"[DEBUG] get_db_connection() - User DB path: {db_path}")
    
    # Create data directory if needed
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Open in read-write mode (this is user_data.db, NOT vantage_core.db!)
    con = duckdb.connect(db_path, read_only=False)
    
    # Initialize schema
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
    """Retrieve Gemini API key from Streamlit secrets or environment"""
    try:
        if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except:
        pass
    
    return os.getenv("GEMINI_API_KEY")

def analyze_label_with_gemini(image):
    """
    Analyze food label image using Gemini 3 Flash
    
    Model: gemini-3-flash-preview (Gemini 3 for hackathon)
    """
    api_key = get_gemini_api_key()
    
    if not api_key:
        return """❌ **Error: GEMINI_API_KEY not found**
        
**Setup Instructions:**
1. Streamlit Cloud: Settings → Secrets → Add GEMINI_API_KEY
2. Local: Add to .env file
3. Get key: https://aistudio.google.com/app/apikey
"""
    
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = """Analyze this food label image and identify the ingredients.

Return EXACTLY 3 specific concerns related to insulin sensitivity and blood sugar impact.

Format your response as:
• Concern 1: [Ingredient name] - [Why it's concerning for insulin/blood sugar]
• Concern 2: [Ingredient name] - [Why it's concerning for insulin/blood sugar]  
• Concern 3: [Ingredient name] - [Why it's concerning for insulin/blood sugar]

Be specific about which ingredients cause concern and explain the metabolic impact."""
        
        # Call Gemini 3 Flash model
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[prompt, image]
        )
        
        return response.text
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] Gemini analysis failed: {error_msg}")
        
        return f"""❌ **Error analyzing image:** {error_msg}

**Possible causes:**
1. Invalid or expired API key
2. API quota exceeded
3. Network connectivity issue
4. Unsupported image format
5. Gemini 3 API access not enabled

**Solutions:**
- Verify API key in Streamlit secrets
- Check API quota at: https://aistudio.google.com/
- Ensure image is JPG/PNG format
- Try again in a few moments"""