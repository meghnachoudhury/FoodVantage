"""
FoodVantage - Gemini API Integration Module
============================================

This module integrates Google's Gemini 3 Flash model for food label analysis
and manages database operations for the FoodVantage application.

Gemini 3 Integration:
- Model: gemini-3-flash-preview
- Purpose: Multimodal analysis of food label images
- Features: Identifies ingredients and insulin sensitivity concerns

Database Architecture:
- vantage_core.db: Read-only scientific nutrition database
- user_data.db: Read-write user accounts and calendar data

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
# This file location: /mount/src/foodvantage/src/gemini_api.py
# Project root: /mount/src/foodvantage/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# === VMS ALGORITHM ===
def calculate_vms_science(row):
    """
    Vantage Metabolic Score (VMS) Algorithm
    
    Calculates a metabolic impact score for food items based on:
    - Energy density (calories)
    - Sugar content (with liquid/whole food adjustments)
    - Fat content (saturated fat)
    - Sodium levels
    - Protective factors (fiber, protein)
    - NOVA classification (processing level)
    
    Returns:
        float: Score from -2.0 to 10.0
            < 3.0 = Metabolic Green (Protector)
            3.0-7.0 = Metabolic Yellow (Neutral)
            > 7.0 = Metabolic Red (Disruptor)
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

        # Penalty points (higher = worse)
        pts_energy = min(cal / 80, 10.0)
        pts_fat = min(fat / 2.0, 10.0) 
        pts_sodium = min(sod / 150, 10.0)
        
        # Sugar penalty with food type adjustments
        if is_liquid:
            pts_sugar = min(sug / 1.5, 10.0)  # Liquids penalized heavily
        elif is_whole_fresh:
            pts_sugar = min((sug * 0.2) / 4.5, 10.0)  # Whole foods protected
        else:
            pts_sugar = min(sug / 4.5, 10.0)

        # Protective factors (fiber & protein)
        if is_liquid or is_dried:
            c_total = 0.0  # No credit for liquids/dried foods
        else:
            c_fiber = min(fib / 0.5, 7.0) 
            c_protein = min(prot / 1.2, 7.0)
            c_total = c_fiber + c_protein

        # Final score calculation
        score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 2)
        
        # Special case adjustments
        if is_whole_fresh: return min(score, -1.0)  # Cap at -1.0 for whole foods
        if is_liquid and sug > 4.0: return max(score, 7.5)  # Floor at 7.5 for sugary liquids
        if is_dried and sug > 15.0: return max(score, 7.0)  # Floor at 7.0 for dried fruit
        
        return max(-2.0, min(10.0, score))  # Clamp to valid range
        
    except Exception as e:
        print(f"[ERROR] VMS calculation failed: {e}")
        return 5.0  # Neutral score on error

# === DATABASE EXTRACTION ===
def ensure_database_extracted():
    """
    Ensures the scientific database is extracted from zip file if needed.
    
    On Streamlit Cloud, the repository only contains vantage_core.zip.
    This function extracts it to vantage_core.db on first run.
    
    Returns:
        str: Path to extracted database, or None if unavailable
    """
    db_path = os.path.join(PROJECT_ROOT, 'data', 'vantage_core.db')
    zip_path = os.path.join(PROJECT_ROOT, 'data', 'vantage_core.zip')
    
    # Database already extracted
    if os.path.exists(db_path):
        return db_path
    
    # Extract from zip file
    if os.path.exists(zip_path):
        print("📦 FoodVantage: Extracting compressed metabolic index...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(os.path.join(PROJECT_ROOT, 'data'))
            print("✅ Database extracted successfully")
            return db_path
        except Exception as e:
            print(f"❌ Error extracting database: {e}")
            return None
    
    # Neither file exists
    print(f"❌ Database files not found:")
    print(f"   - {db_path}")
    print(f"   - {zip_path}")
    return None

# === SCIENTIFIC DATABASE SEARCH ===
def search_vantage_db(product_name: str):
    """
    Searches the read-only scientific nutrition database.
    
    This function:
    1. Ensures database is extracted from zip
    2. Opens a NEW read-only connection
    3. Searches for product by name
    4. Calculates VMS score using scientific algorithm
    5. Closes connection immediately
    
    Args:
        product_name: Name of product to search for
        
    Returns:
        list: [{name, brand, vms_score, rating}] or None if not found
    """
    # Ensure database is available
    db_path = ensure_database_extracted()
    
    if not db_path or not os.path.exists(db_path):
        st.error("❌ Scientific database not available")
        return None
    
    print(f"[DEBUG] Searching for: {product_name}")
    print(f"[DEBUG] Database: {db_path}")
    
    con = None
    try:
        # Open NEW read-only connection (prevents locking conflicts)
        con = duckdb.connect(db_path, read_only=True)
        
        # Sanitize input to prevent SQL injection
        safe_name = product_name.replace("'", "''")
        
        # Search query with fuzzy matching and prioritization
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
            print(f"[DEBUG] No results found")
            return None
            
        # Calculate VMS score
        r = results[0]
        score = calculate_vms_science(r)
        
        print(f"[DEBUG] Found: {r[0]} | Score: {score}")
        
        # Determine rating category
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
        st.error(f"❌ Search error: {error_msg}")
        return None
        
    finally:
        # ALWAYS close the connection
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
    Gets connection to user data database (separate from scientific data).
    
    This database stores:
    - User accounts (username, password hash)
    - Calendar items (grocery list entries)
    - Activity logs
    
    Returns:
        duckdb.Connection: Persistent connection (cached by Streamlit)
    """
    db_path = os.path.join(PROJECT_ROOT, 'data', 'user_data.db')
    
    print(f"[DEBUG] User DB: {db_path}")
    
    # Create data directory if needed
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Open in read-write mode
    con = duckdb.connect(db_path, read_only=False)
    
    # Initialize schema
    con.execute("CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR)")
    
    try:
        con.execute("CREATE SEQUENCE IF NOT EXISTS seq_cal_id START 1")
    except:
        pass  # Sequence already exists
    
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
    """
    Retrieve Gemini API key from Streamlit secrets or environment.
    
    Priority:
    1. Streamlit Cloud secrets (production)
    2. .env file (local development)
    """
    try:
        if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except:
        pass
    
    return os.getenv("GEMINI_API_KEY")

def analyze_label_with_gemini(image):
    """
    Analyze food label image using Gemini 3 Flash.
    
    This is the core Gemini 3 integration for the hackathon.
    
    Model: gemini-3-flash-preview
    Capabilities:
    - Multimodal analysis (image + text)
    - Ingredient identification
    - Health impact assessment
    - Insulin sensitivity analysis
    
    Args:
        image: PIL Image or bytes of food label
        
    Returns:
        str: Markdown-formatted analysis with 3 insulin concerns
    """
    api_key = get_gemini_api_key()
    
    if not api_key:
        return """❌ **Error: GEMINI_API_KEY not found**
        
**Setup Instructions:**

1. **Streamlit Cloud (Production):**
   - Go to app Settings → Secrets
   - Add: `GEMINI_API_KEY = "your-key-here"`

2. **Local Development:**
   - Add to `.env` file: `GEMINI_API_KEY=your-key-here`

3. **Get API Key:**
   - Visit: https://aistudio.google.com/app/apikey
   - Create new API key for Gemini 3
"""
    
    try:
        client = genai.Client(api_key=api_key)
        
        # Optimized prompt for Gemini 3 Flash
        prompt = """Analyze this food label image and identify the ingredients.

Return EXACTLY 3 specific concerns related to insulin sensitivity and blood sugar impact.

Format your response as:
• Concern 1: [Ingredient name] - [Why it's concerning for insulin/blood sugar]
• Concern 2: [Ingredient name] - [Why it's concerning for insulin/blood sugar]  
• Concern 3: [Ingredient name] - [Why it's concerning for insulin/blood sugar]

Be specific about which ingredients cause concern and explain the metabolic impact."""
        
        # Call Gemini 3 Flash model
        response = client.models.generate_content(
            model="gemini-3-flash-preview",  # Gemini 3 Flash (for hackathon)
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