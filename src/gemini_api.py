import duckdb
import os
import zipfile
import streamlit as st
import hashlib
from google import genai
from google.genai import types
from dotenv import load_dotenv
from PIL import Image
import io
import base64

load_dotenv()

# === 1. VMS ALGORITHM ===
def calculate_vms_science(row):
    try:
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal, sug, fib, prot, fat, sod = [float(x or 0) for x in [cal, sug, fib, prot, fat, sod]]
        nova_val = int(nova or 1)
        
        n = name.lower()
        
        common_fruits = ['apple', 'banana', 'orange', 'grape', 'strawberry', 'blueberry', 
                        'raspberry', 'mango', 'pineapple', 'watermelon', 'melon', 'kiwi',
                        'peach', 'pear', 'plum', 'cherry', 'lime', 'lemon', 'grapefruit',
                        'papaya', 'guava', 'passion fruit', 'dragon fruit', 'avocado']
        
        is_fruit = any(fruit in n for fruit in common_fruits)
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'smoothie'])
        is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin'])
        
        is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'broccoli', 'egg', 'avocado', 'spinach', 'kale'])
        is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
        
        is_whole_fresh = ((nova_val <= 2 or is_superfood or is_dairy_plain or is_fruit) 
                         and not (is_liquid or is_dried))

        pts_energy = min(cal / 80, 10.0)
        pts_fat = min(fat / 2.0, 10.0) 
        pts_sodium = min(sod / 150, 10.0)
        
        if is_liquid:
            pts_sugar = min(sug / 1.5, 10.0)
        elif is_whole_fresh:
            pts_sugar = min((sug * 0.2) / 4.5, 10.0)
        else:
            pts_sugar = min(sug / 4.5, 10.0)

        c_total = 0.0 if is_liquid else (min(fib / 0.5, 7.0) + min(prot / 1.2, 7.0))
        score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 2)
        
        if is_whole_fresh: return min(score, -1.0)
        if is_liquid and sug > 4.0: return max(score, 7.5)
        if is_dried and sug > 15.0: return max(score, 7.0)
        
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

def search_vantage_db(product_name: str, limit=5):
    """Returns top 5 results with full product names"""
    con = get_scientific_db()
    if not con: return None
    try:
        safe_name = product_name.replace("'", "''")
        
        query = f"""
            SELECT * FROM products 
            WHERE product_name ILIKE '%{safe_name}%'
            ORDER BY 
                CASE 
                    WHEN LOWER(product_name) = LOWER('{safe_name}') THEN 0
                    WHEN product_name NOT LIKE '%,%' AND (brand IS NULL OR brand = '') THEN 1
                    WHEN LENGTH(product_name) - LENGTH(REPLACE(product_name, ' ', '')) <= 2 THEN 2
                    ELSE 3
                END,
                LENGTH(product_name),
                sugar DESC
            LIMIT {limit}
        """
        
        results = con.execute(query).fetchall()
        if not results: return None
        
        output = []
        for r in results:
            score = calculate_vms_science(r)
            rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"
            
            full_name = r[0].title()
            brand = str(r[1]).title() if r[1] and r[1].strip() else ""
            
            if brand and brand not in full_name:
                display_name = f"{brand} {full_name}"
            else:
                display_name = full_name
            
            output.append({
                "name": display_name,
                "brand": brand,
                "vms_score": score, 
                "rating": rating, 
                "raw": r
            })
        
        return output
        
    except Exception as e:
        print(f"[DB ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None

# === 3. FIXED GEMINI API CALL ===
def vision_live_scan(image_bytes):
    """
    FIXED: Proper Gemini API format with types.Content and types.Part
    """
    api_key = get_gemini_api_key()
    if not api_key: 
        st.error("⚠️ No Gemini API key configured!")
        return None
    
    try:
        # Step 1: Handle different input types
        if isinstance(image_bytes, io.BytesIO):
            image_bytes = image_bytes.getvalue()
        elif hasattr(image_bytes, 'read'):
            image_bytes = image_bytes.read()
        
        print(f"[DEBUG] Image type: {type(image_bytes)}, size: {len(image_bytes)} bytes")
        
        # Step 2: Convert to PIL Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        print(f"[DEBUG] Image dimensions: {w}x{h}, mode: {img.mode}")
        
        # Step 3: Convert to RGB
        if img.mode == 'RGBA':
            print("[DEBUG] Converting RGBA to RGB...")
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
            img = background
        elif img.mode == 'LA':
            print("[DEBUG] Converting LA to RGB...")
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[1])
            img = background
        elif img.mode != 'RGB':
            print(f"[DEBUG] Converting {img.mode} to RGB...")
            img = img.convert('RGB')
        
        print(f"[DEBUG] After conversion, mode: {img.mode}")
        
        # Step 4: Crop center 50%
        left = int(w * 0.25)
        top = int(h * 0.25)
        right = int(w * 0.75)
        bottom = int(h * 0.75)
        img_cropped = img.crop((left, top, right, bottom))
        
        # Step 5: Enhance image
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(img_cropped)
        img_cropped = enhancer.enhance(1.5)
        enhancer = ImageEnhance.Brightness(img_cropped)
        img_cropped = enhancer.enhance(1.2)
        
        # Step 6: Final RGB check
        if img_cropped.mode != 'RGB':
            img_cropped = img_cropped.convert('RGB')
        
        # Step 7: Convert to base64 (Gemini SDK expects base64 for inline_data)
        buf = io.BytesIO()
        img_cropped.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        img_bytes = buf.read()
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        
        print(f"[DEBUG] Image converted to base64, length: {len(img_b64)}")
        
        # Step 8: Create prompt
        prompt = """You are a precise product identifier. Look at this image and identify the food item.

RULES:
1. For FRUITS/VEGETABLES: Return just the item name (e.g., "lime", "banana")
2. For PACKAGED products: Return "[Brand] [Product]" (e.g., "Simply Mints", "Coca Cola")
3. Be SPECIFIC and CONCISE (max 4 words)
4. Return ONLY the name, nothing else

What do you see?"""
        
        # Step 9: FIXED - Proper Gemini API call using types.Content
        client = genai.Client(api_key=api_key)
        
        print("[DEBUG] Calling Gemini API with proper format...")
        st.info("🔍 Analyzing image with Gemini...")
        
        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=types.Content(
                    parts=[
                        types.Part(text=prompt),
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/jpeg",
                                data=img_b64
                            )
                        )
                    ]
                )
            )
            
            product_name = response.text.strip().replace('"', '').replace('*', '').replace('.', '')
            print(f"✅ [GEMINI] Identified: '{product_name}'")
            st.success(f"👁️ Gemini detected: **{product_name}**")
            
        except Exception as gemini_error:
            print(f"[GEMINI ERROR] {gemini_error}")
            # Try alternative format
            print("[DEBUG] Trying alternative API format...")
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents={
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]
                }
            )
            product_name = response.text.strip().replace('"', '').replace('*', '').replace('.', '')
            print(f"✅ [GEMINI] Identified (alt format): '{product_name}'")
            st.success(f"👁️ Gemini detected: **{product_name}**")
        
        # Step 10: Search database
        results = search_vantage_db(product_name, limit=5)
        
        if results:
            print(f"✅ [DATABASE] Found {len(results)} matches:")
            for i, r in enumerate(results):
                print(f"   {i+1}. {r['name']} - Score: {r['vms_score']}")
            st.success(f"✅ Found {len(results)} options!")
            return results
        else:
            print(f"❌ [DATABASE] No matches for: '{product_name}'")
            st.warning(f"❌ '{product_name}' not in database.\n\nTry:\n- Repositioning camera\n- Better lighting\n- Different angle")
            return None
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [SCAN ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        st.error(f"⚠️ Scan error: {error_msg[:300]}")
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

def get_trend_data_db(username, days=30):
    con = get_db_connection()
    try: 
        results = con.execute("""
            SELECT date, category, COUNT(*) as count
            FROM calendar 
            WHERE username = ? AND date >= current_date - INTERVAL ? DAY 
            GROUP BY date, category 
            ORDER BY date ASC
        """, [username, days]).fetchall()
        return results
    except Exception as e:
        print(f"[TRENDS ERROR] {e}")
        return []

# === 5. AUTH HELPERS ===
def get_gemini_api_key():
    if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets: 
        return st.secrets["GEMINI_API_KEY"]
    return os.getenv("GEMINI_API_KEY")

def authenticate_user(username, password):
    try:
        con = get_db_connection()
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        result = con.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", [username, pwd_hash]).fetchone()
        is_valid = result is not None
        print(f"[AUTH] Login attempt for '{username}': {'SUCCESS' if is_valid else 'FAILED'}")
        return is_valid
    except Exception as e:
        print(f"[AUTH ERROR] {e}")
        return False

def add_calendar_item_db(username, date_str, item_name, score):
    try:
        con = get_db_connection()
        category = 'healthy' if score < 3.0 else 'moderate' if score < 7.0 else 'unhealthy'
        con.execute("INSERT INTO calendar (username, date, item_name, score, category) VALUES (?, ?, ?, ?, ?)", 
                   [username, date_str, item_name, score, category])
        print(f"[CALENDAR] Added: {item_name} ({score}) for {username} on {date_str}")
    except Exception as e:
        print(f"[CALENDAR ERROR] {e}")

def get_calendar_items_db(username, date_str):
    try:
        con = get_db_connection()
        return con.execute("SELECT id, item_name, score, category FROM calendar WHERE username = ? AND date = ?", 
                          [username, date_str]).fetchall()
    except Exception as e:
        print(f"[CALENDAR ERROR] {e}")
        return []

def delete_item_db(item_id):
    try:
        con = get_db_connection()
        con.execute("DELETE FROM calendar WHERE id = ?", [item_id])
        print(f"[CALENDAR] Deleted item ID: {item_id}")
    except Exception as e:
        print(f"[CALENDAR ERROR] {e}")

def get_log_history_db(username):
    try:
        con = get_db_connection()
        return con.execute("SELECT date, item_name, score, category FROM calendar WHERE username = ? ORDER BY date DESC", 
                          [username]).fetchall()
    except Exception as e:
        print(f"[LOG ERROR] {e}")
        return []

def create_user(username, password):
    try:
        con = get_db_connection()
        exists = con.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
        if exists: 
            print(f"[AUTH] User '{username}' already exists")
            return False
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        con.execute("INSERT INTO users VALUES (?, ?)", [username, pwd_hash])
        print(f"[AUTH] Created new user: '{username}'")
        return True
    except Exception as e:
        print(f"[AUTH ERROR] Failed to create user '{username}': {e}")
        return False
