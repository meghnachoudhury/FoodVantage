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
import time
from datetime import datetime, timedelta

load_dotenv()

# === VMS ALGORITHM ===
def calculate_vms_science(row):
    try:
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal, sug, fib, prot, fat, sod = [float(x or 0) for x in [cal, sug, fib, prot, fat, sod]]
        nova_val = int(nova or 1)
        
        n = name.lower()
        
        common_fruits = ['apple', 'banana', 'orange', 'grape', 'strawberry', 'blueberry', 
                        'raspberry', 'mango', 'pineapple', 'watermelon', 'melon', 'kiwi',
                        'peach', 'pear', 'plum', 'cherry', 'lime', 'lemon', 'grapefruit']
        
        is_fruit = any(fruit in n for fruit in common_fruits)
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'smoothie'])
        is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin'])
        
        processed_indicators = ['biscuit', 'burger', 'sandwich', 'pizza', 'nugget', 'patty', 
            'fried', 'breaded', 'crispy', 'wrapped', 'stuffed', 'cooked', 'grilled', 'baked']
        
        is_heavily_processed = any(word in n for word in processed_indicators) or nova_val >= 3
        
        if not is_heavily_processed:
            is_superfood = any(x in n for x in ['salmon', 'lentils', 'beans', 'broccoli', 'egg', 'avocado', 'spinach', 'kale'])
        else:
            is_superfood = False
        
        is_dairy_plain = ('milk' in n or 'yogurt' in n) and sug < 5.0
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

# === DATABASE ===
@st.cache_resource
def get_scientific_db():
    zip_path, db_path = 'data/vantage_core.zip', '/tmp/data/vantage_core.db'
    if not os.path.exists(db_path) and os.path.exists(zip_path):
        os.makedirs('/tmp/data', exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref: 
            zip_ref.extractall('/tmp/')
    return duckdb.connect(db_path, read_only=True)

def search_vantage_db(product_name: str, limit=20):
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
                    ELSE 2
                END,
                LENGTH(product_name)
            LIMIT {limit}
        """
        
        results = con.execute(query).fetchall()
        
        if not results:
            print(f"[DB] No results, trying Open Food Facts...")
            return search_open_food_facts(product_name, limit)
        
        output = []
        for r in results:
            score = calculate_vms_science(r)
            if score == 10.0:  # Skip default scores
                continue
                
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
        
        return output if output else None
        
    except Exception as e:
        print(f"[DB ERROR] {e}")
        return None

def search_open_food_facts(product_name: str, limit=5):
    try:
        search_term = product_name.lower().strip().replace("'", "")
        
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "search_terms": search_term,
            "page_size": limit * 2,
            "json": 1,
            "fields": "product_name,brands,nutriments,nova_group"
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        products = data.get('products', [])
        
        if not products:
            return None
        
        output = []
        seen_names = set()
        
        for p in products[:limit * 2]:
            try:
                nutriments = p.get('nutriments', {})
                name = p.get('product_name', '').strip()
                
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                
                brand = p.get('brands', '').split(',')[0].strip() if p.get('brands') else ''
                
                calories = float(nutriments.get('energy-kcal_100g', 0) or 0)
                sugar = float(nutriments.get('sugars_100g', 0) or 0)
                fiber = float(nutriments.get('fiber_100g', 0) or 0)
                protein = float(nutriments.get('proteins_100g', 0) or 0)
                fat = float(nutriments.get('fat_100g', 0) or 0)
                sodium = float(nutriments.get('sodium_100g', 0) or 0) * 1000
                nova = int(p.get('nova_group', 3) or 3)
                
                row = [name, brand, calories, sugar, fiber, protein, fat, sodium, None, nova]
                score = calculate_vms_science(row)
                
                if score == 10.0:
                    continue
                
                rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"
                display_name = f"{brand.title()} {name.title()}" if brand else name.title()
                
                output.append({
                    "name": display_name,
                    "brand": brand.title() if brand else "",
                    "vms_score": score,
                    "rating": rating,
                    "raw": row
                })
                
                if len(output) >= limit:
                    break
                
            except:
                continue
        
        return output if output else None
        
    except:
        return None

# === FIXED SCANNER WITH TIMEOUT ===
def vision_live_scan_dark(image_bytes):
    """FIXED VERSION - Added timeout and better error handling"""
    import time
    
    api_key = get_gemini_api_key()
    if not api_key: 
        st.error("⚠️ No API key configured")
        return None
    
    try:
        # Convert to PIL Image
        if isinstance(image_bytes, io.BytesIO):
            image_bytes = image_bytes.getvalue()
        elif hasattr(image_bytes, 'read'):
            image_bytes = image_bytes.read()
        
        print(f"[DEBUG] Image size: {len(image_bytes)} bytes")
        
        img = Image.open(io.BytesIO(image_bytes))
        print(f"[DEBUG] Image dimensions: {img.size}, mode: {img.mode}")
        
        # Convert to RGB
        if img.mode != 'RGB':
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            else:
                img = img.convert('RGB')
        
        # Resize if too large (helps with speed)
        max_size = 1024
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            print(f"[DEBUG] Resized to: {img.size}")
        
        # Convert to base64
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')
        print(f"[DEBUG] Base64 size: {len(img_b64)} chars")
        
        # SIMPLE prompt
        prompt = "What food item is in this image? Reply with just the name."
        
        # Call Gemini with timeout handling
        client = genai.Client(api_key=api_key)
        
        print("[DEBUG] Calling Gemini API...")
        start_time = time.time()
        
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
                ),
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=50
                )
            )
            
            elapsed = time.time() - start_time
            print(f"[DEBUG] Gemini responded in {elapsed:.2f}s")
            
        except Exception as api_error:
            print(f"[API ERROR] {api_error}")
            st.error(f"⚠️ API Error: {str(api_error)[:100]}")
            
            # Check for quota errors
            if "429" in str(api_error) or "quota" in str(api_error).lower():
                st.warning("🔥 API quota limit reached. Please wait a moment and try again.")
            
            return None
        
        product_name = response.text.strip().replace('"', '').replace('*', '').replace('.', '')
        print(f"[GEMINI] Detected: {product_name}")
        
        if not product_name or len(product_name) < 2:
            st.warning("⚠️ Could not identify item. Try repositioning.")
            return None
        
        # Search database
        print(f"[DATABASE] Searching for: {product_name}")
        results = search_vantage_db(product_name, limit=5)
        
        if results:
            print(f"[DATABASE] Found {len(results)} matches")
            return results
        else:
            print(f"[DATABASE] No matches found")
            st.warning(f"🔍 '{product_name}' not in database yet. Try a different item!")
            return None
        
    except Exception as e:
        error_msg = str(e)
        print(f"[SCAN ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        
        # Show helpful error to user
        if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            st.error("⚠️ Network error. Check your internet connection.")
        elif "invalid" in error_msg.lower() or "format" in error_msg.lower():
            st.error("⚠️ Image format error. Try taking a new photo.")
        else:
            st.error(f"⚠️ Error: {error_msg[:150]}")
        
        return None

# === USER DB ===
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
        threshold_date = datetime.now().date() - timedelta(days=days - 1)
        threshold_str = threshold_date.strftime('%Y-%m-%d')
        
        results = con.execute("""
            SELECT date, category, COUNT(*) as count
            FROM calendar 
            WHERE username = ? AND date >= ?
            GROUP BY date, category 
            ORDER BY date ASC
        """, [username, threshold_str]).fetchall()
        
        return results
    except:
        return []

def get_all_calendar_data_db(username):
    """Get ALL calendar items for debugging"""
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

def get_gemini_api_key():
    if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets: 
        return st.secrets["GEMINI_API_KEY"]
    return os.getenv("GEMINI_API_KEY")

def authenticate_user(username, password):
    try:
        con = get_db_connection()
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        result = con.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", [username, pwd_hash]).fetchone()
        return result is not None
    except:
        return False

def add_calendar_item_db(username, date_str, item_name, score):
    try:
        con = get_db_connection()
        category = 'healthy' if score < 3.0 else 'moderate' if score < 7.0 else 'unhealthy'
        con.execute("INSERT INTO calendar (username, date, item_name, score, category) VALUES (?, ?, ?, ?, ?)", 
                   [username, date_str, item_name, score, category])
    except Exception as e:
        print(f"[CALENDAR ERROR] {e}")

def get_calendar_items_db(username, date_str):
    try:
        con = get_db_connection()
        return con.execute("SELECT id, item_name, score, category FROM calendar WHERE username = ? AND date = ?", 
                          [username, date_str]).fetchall()
    except:
        return []

def delete_item_db(item_id):
    try:
        con = get_db_connection()
        con.execute("DELETE FROM calendar WHERE id = ?", [item_id])
    except Exception as e:
        print(f"[DELETE ERROR] {e}")

def get_log_history_db(username):
    try:
        con = get_db_connection()
        return con.execute("SELECT date, item_name, score, category FROM calendar WHERE username = ? ORDER BY date DESC", 
                          [username]).fetchall()
    except:
        return []

def create_user(username, password):
    try:
        con = get_db_connection()
        exists = con.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
        if exists: 
            return False
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        con.execute("INSERT INTO users VALUES (?, ?)", [username, pwd_hash])
        return True
    except:
        return False
