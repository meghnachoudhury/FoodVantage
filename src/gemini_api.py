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
import requests

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
        
        # FIXED: Detect heavily processed foods that can't be superfoods
        processed_indicators = ['biscuit', 'burger', 'sandwich', 'pizza', 'nugget', 'patty', 
                               'fried', 'breaded', 'crispy', 'wrapped', 'stuffed', 'smothered',
                               'cheesy', 'creamy', 'buttery', 'glazed', 'frosted', 'coated',
                               'melt', 'loaded', 'supreme', 'deluxe', 'combo', 'platter']
        
        is_heavily_processed = any(word in n for word in processed_indicators) or nova_val >= 3
        
        # Only mark as superfood if NOT heavily processed
        if not is_heavily_processed:
            is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'broccoli', 'egg', 'avocado', 'spinach', 'kale'])
        else:
            is_superfood = False
        
        is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
        
        # Whole fresh requires NOVA <= 2 AND not heavily processed
        is_whole_fresh = ((nova_val <= 2 and (is_superfood or is_dairy_plain or is_fruit)) 
                         and not (is_liquid or is_dried) and not is_heavily_processed)

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
        
        # If no results in local DB, try Open Food Facts API
        if not results or len(results) == 0:
            print(f"[DB] No results in local database, trying Open Food Facts...")
            return search_open_food_facts(product_name, limit)
        
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

def search_open_food_facts(product_name: str, limit=5):
    """
    Fallback: Search Open Food Facts API when product not in local database
    Returns data in same format as local database
    """
    try:
        print(f"[OPEN FOOD FACTS] Searching for: {product_name}")
        
        # Clean product name for API search
        search_term = product_name.lower().strip()
        
        # Open Food Facts API endpoint
        url = f"https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "search_terms": search_term,
            "page_size": limit,
            "json": 1,
            "fields": "product_name,brands,nutriments,nova_group"
        }
        
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code != 200:
            print(f"[OPEN FOOD FACTS] API error: {response.status_code}")
            return None
        
        data = response.json()
        products = data.get('products', [])
        
        if not products:
            print(f"[OPEN FOOD FACTS] No products found")
            return None
        
        print(f"[OPEN FOOD FACTS] Found {len(products)} products")
        
        output = []
        for p in products[:limit]:
            try:
                # Extract nutrition data
                nutriments = p.get('nutriments', {})
                
                name = p.get('product_name', 'Unknown Product')
                brand = p.get('brands', '').split(',')[0] if p.get('brands') else ''
                
                # Get per 100g values (Open Food Facts standard)
                calories = nutriments.get('energy-kcal_100g', 0) or 0
                sugar = nutriments.get('sugars_100g', 0) or 0
                fiber = nutriments.get('fiber_100g', 0) or 0
                protein = nutriments.get('proteins_100g', 0) or 0
                fat = nutriments.get('fat_100g', 0) or 0
                sodium = nutriments.get('sodium_100g', 0) * 1000 or 0  # Convert g to mg
                nova = p.get('nova_group', 3) or 3
                
                # Create row in same format as local database
                # [name, brand, calories, sugar, fiber, protein, fat, sodium, _, nova]
                row = [name, brand, calories, sugar, fiber, protein, fat, sodium, None, nova]
                
                # Calculate VMS score
                score = calculate_vms_science(row)
                rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"
                
                display_name = f"{brand.title()} {name.title()}" if brand else name.title()
                
                output.append({
                    "name": display_name,
                    "brand": brand.title() if brand else "",
                    "vms_score": score,
                    "rating": rating,
                    "raw": row
                })
                
                print(f"[OPEN FOOD FACTS] Added: {display_name} (Score: {score})")
                
            except Exception as e:
                print(f"[OPEN FOOD FACTS] Error processing product: {e}")
                continue
        
        return output if output else None
        
    except requests.Timeout:
        print("[OPEN FOOD FACTS] Request timeout")
        return None
    except Exception as e:
        print(f"[OPEN FOOD FACTS] Error: {e}")
        import traceback
        traceback.print_exc()
        return None

# === 3. SCANNER WITH DARK TEXT ===
def vision_live_scan_dark(image_bytes):
    """
    FIXED: Shows DARK, BOLD text instead of light text
    """
    api_key = get_gemini_api_key()
    if not api_key: 
        # Dark error message
        st.markdown("""
            <div class="scanner-result">
                <div class="scanner-result-title">⚠️ Configuration Error</div>
                <div class="scanner-result-text">No Gemini API key configured</div>
            </div>
        """, unsafe_allow_html=True)
        return None
    
    try:
        # Handle different input types
        if isinstance(image_bytes, io.BytesIO):
            image_bytes = image_bytes.getvalue()
        elif hasattr(image_bytes, 'read'):
            image_bytes = image_bytes.read()
        
        print(f"[DEBUG] Image type: {type(image_bytes)}, size: {len(image_bytes)} bytes")
        
        # Convert to PIL Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        print(f"[DEBUG] Image dimensions: {w}x{h}, mode: {img.mode}")
        
        # Convert to RGB
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
        
        # Crop center 50%
        left = int(w * 0.25)
        top = int(h * 0.25)
        right = int(w * 0.75)
        bottom = int(h * 0.75)
        img_cropped = img.crop((left, top, right, bottom))
        
        # Enhance image
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(img_cropped)
        img_cropped = enhancer.enhance(1.5)
        enhancer = ImageEnhance.Brightness(img_cropped)
        img_cropped = enhancer.enhance(1.2)
        
        # Final RGB check
        if img_cropped.mode != 'RGB':
            img_cropped = img_cropped.convert('RGB')
        
        # Convert to base64
        buf = io.BytesIO()
        img_cropped.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        img_bytes = buf.read()
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        
        # Create prompt
        prompt = """You are a precise product identifier. Look at this image and identify the food item.

RULES:
1. For FRUITS/VEGETABLES: Return just the item name (e.g., "lime", "banana")
2. For PACKAGED products: Return "[Brand] [Product]" (e.g., "Simply Mints", "Coca Cola")
3. Be SPECIFIC and CONCISE (max 4 words)
4. Return ONLY the name, nothing else

What do you see?"""
        
        # Call Gemini with proper format
        client = genai.Client(api_key=api_key)
        
        print("[DEBUG] Calling Gemini API...")
        
        # DARK themed analyzing message
        st.markdown("""
            <div class="scanner-result">
                <div class="scanner-result-title">🔍 Analyzing Image</div>
                <div class="scanner-result-text">Processing with Gemini AI...</div>
            </div>
        """, unsafe_allow_html=True)
        
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
            
            # DARK themed detection message
            st.markdown(f"""
                <div class="scanner-result">
                    <div class="scanner-result-title">👁️ Product Detected</div>
                    <div class="scanner-result-text">{product_name}</div>
                </div>
            """, unsafe_allow_html=True)
            
        except Exception as gemini_error:
            print(f"[GEMINI ERROR] {gemini_error}")
            # Fallback format
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
            print(f"✅ [GEMINI] Identified: '{product_name}'")
            
            # DARK themed detection message
            st.markdown(f"""
                <div class="scanner-result">
                    <div class="scanner-result-title">👁️ Product Detected</div>
                    <div class="scanner-result-text">{product_name}</div>
                </div>
            """, unsafe_allow_html=True)
        
        # Search database
        results = search_vantage_db(product_name, limit=5)
        
        if results:
            print(f"✅ [DATABASE] Found {len(results)} matches:")
            for i, r in enumerate(results):
                print(f"   {i+1}. {r['name']} - Score: {r['vms_score']}")
            
            # DARK themed success message
            st.markdown(f"""
                <div class="scanner-result">
                    <div class="scanner-result-title">✅ Database Match</div>
                    <div class="scanner-result-text">Found {len(results)} option(s) in database</div>
                </div>
            """, unsafe_allow_html=True)
            
            return results
        else:
            print(f"❌ [DATABASE] No matches for: '{product_name}'")
            
            # DARK themed warning message
            st.markdown(f"""
                <div class="scanner-result" style="border-left-color: #D4765E;">
                    <div class="scanner-result-title">❌ Not Found</div>
                    <div class="scanner-result-text">'{product_name}' not in database</div>
                    <div style="font-size: 0.9rem; color: #666; margin-top: 8px;">
                        Try: Repositioning • Better lighting • Different angle
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            return None
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [SCAN ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        
        # DARK themed error message
        st.markdown(f"""
            <div class="scanner-result" style="border-left-color: #D4765E;">
                <div class="scanner-result-title">⚠️ Scan Error</div>
                <div class="scanner-result-text">{error_msg[:150]}</div>
            </div>
        """, unsafe_allow_html=True)
        
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

def get_all_calendar_data_db(username):
    """Get ALL calendar items for debugging - no date filter"""
    con = get_db_connection()
    try:
        results = con.execute("""
            SELECT date, item_name, score, category 
            FROM calendar 
            WHERE username = ? 
            ORDER BY date DESC
        """, [username]).fetchall()
        return results
    except Exception as e:
        print(f"[ALL CALENDAR ERROR] {e}")
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
