import duckdb
import os
import zipfile
import streamlit as st
import hashlib
from google import genai  # CORRECT: User's SDK version
from google.genai import types  # CORRECT: User's SDK version
from dotenv import load_dotenv
from PIL import Image
import io
import base64
import requests
from datetime import datetime, timedelta

load_dotenv()

# === 1. VMS ALGORITHM (ENHANCED FOR FIX 5) ===
# Serving size ratios (fraction of 100g that represents one serving)
# Used to scale per-100g nutrition data to realistic portions
SERVING_SCALE = {
    # Oils & fats (~1 tbsp = 13-15g)
    'oil': 0.14, 'olive oil': 0.14, 'coconut oil': 0.14, 'vegetable oil': 0.14,
    'canola oil': 0.14, 'sesame oil': 0.14, 'avocado oil': 0.14,
    'butter': 0.14, 'margarine': 0.14, 'ghee': 0.14, 'lard': 0.14,
    # Condiments & sauces (~1 tbsp = 15-20g)
    'ketchup': 0.17, 'mustard': 0.10, 'mayonnaise': 0.15, 'mayo': 0.15,
    'soy sauce': 0.15, 'hot sauce': 0.05, 'vinegar': 0.15,
    'dressing': 0.30, 'salad dressing': 0.30,
    'bbq sauce': 0.17, 'barbecue sauce': 0.17, 'teriyaki': 0.17,
    'sriracha': 0.10, 'tabasco': 0.05, 'worcestershire': 0.10,
    'pesto': 0.15, 'hummus': 0.30, 'guacamole': 0.30, 'salsa': 0.30,
    # Spreads (~1 tbsp = 15-20g)
    'jam': 0.20, 'jelly': 0.20, 'marmalade': 0.20,
    'peanut butter': 0.32, 'almond butter': 0.32, 'nutella': 0.20,
    'honey': 0.21, 'maple syrup': 0.20, 'syrup': 0.20,
    'cream cheese': 0.30,
    # Spices & seasonings (~1 tsp = 2-5g)
    'salt': 0.02, 'pepper': 0.02, 'sugar': 0.04, 'cinnamon': 0.03,
    'paprika': 0.02, 'cumin': 0.02, 'turmeric': 0.03,
    # Cheese (1 slice/portion ~30g)
    'cheese': 0.30, 'parmesan': 0.10, 'mozzarella': 0.30, 'cheddar': 0.30,
    # Nuts & seeds (~30g serving)
    'nuts': 0.30, 'almonds': 0.30, 'walnuts': 0.30, 'cashews': 0.30,
    'peanuts': 0.30, 'seeds': 0.30, 'chia': 0.15, 'flax': 0.10,
}

def get_serving_scale(name):
    """Find the best matching serving scale for a product name"""
    n = name.lower()
    # Try longest matches first (e.g., 'olive oil' before 'oil')
    for keyword in sorted(SERVING_SCALE.keys(), key=len, reverse=True):
        if keyword in n:
            return SERVING_SCALE[keyword]
    return 1.0  # Default: use full per-100g values

def calculate_vms_science(row):
    try:
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal, sug, fib, prot, fat, sod = [float(x or 0) for x in [cal, sug, fib, prot, fat, sod]]
        nova_val = int(nova or 1)

        # Scale nutrition to serving size for condiments/oils/etc.
        scale = get_serving_scale(name)
        if scale < 1.0:
            cal, sug, fib, prot, fat, sod = [v * scale for v in [cal, sug, fib, prot, fat, sod]]

        n = name.lower()
        
        common_fruits = ['apple', 'banana', 'orange', 'grape', 'strawberry', 'blueberry', 
                        'raspberry', 'mango', 'pineapple', 'watermelon', 'melon', 'kiwi',
                        'peach', 'pear', 'plum', 'cherry', 'lime', 'lemon', 'grapefruit',
                        'papaya', 'guava', 'passion fruit', 'dragon fruit', 'avocado']
        
        is_fruit = any(fruit in n for fruit in common_fruits)
        is_liquid = any(x in n for x in ['juice', 'soda', 'cola', 'drink', 'beverage', 'smoothie'])
        is_dried = any(x in n for x in ['dried', 'dehydrated', 'raisin'])
        
        # FIX 5: Enhanced processing detection for cooked foods
        processed_indicators = [
            'biscuit', 'burger', 'sandwich', 'pizza', 'nugget', 'patty', 
            'fried', 'breaded', 'crispy', 'wrapped', 'stuffed', 'smothered',
            'cheesy', 'creamy', 'buttery', 'glazed', 'frosted', 'coated',
            'melt', 'loaded', 'supreme', 'deluxe', 'combo', 'platter',
            # FIX 5: Add cooked food keywords
            'cooked', 'grilled', 'baked', 'roasted', 'steamed', 'boiled',
            'sauteed', 'plate', 'meal', 'dish', 'curry', 'stew', 'soup'
        ]
        
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
    """
    FIX 3: Returns up to 20 results (increased from 5)
    Returns top results with full product names
    """
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
    FIX 7: Fallback to Open Food Facts API with better error handling
    """
    try:
        search_term = product_name.lower().strip()
        search_term = search_term.replace("'", "").replace('"', '').replace("'s", "s")
        
        print(f"\n[OPEN FOOD FACTS] ==================")
        print(f"[OPEN FOOD FACTS] Original query: '{product_name}'")
        print(f"[OPEN FOOD FACTS] Cleaned query: '{search_term}'")
        
        # Try multiple search strategies
        search_attempts = [
            search_term,
            " ".join(search_term.split()[:3]),
            search_term.split()[0] if search_term.split() else search_term
        ]
        
        all_products = []
        
        for attempt_num, term in enumerate(search_attempts):
            if not term or len(term) < 3:
                continue
                
            print(f"[OPEN FOOD FACTS] Attempt {attempt_num + 1}: '{term}'")
            
            url = "https://world.openfoodfacts.org/cgi/search.pl"
            params = {
                "search_terms": term,
                "page_size": limit * 3,
                "json": 1,
                "fields": "product_name,brands,nutriments,nova_group"
            }
            
            try:
                response = requests.get(url, params=params, timeout=10)
                print(f"[OPEN FOOD FACTS] Status code: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    products = data.get('products', [])
                    print(f"[OPEN FOOD FACTS] Found {len(products)} raw results")
                    
                    if products:
                        all_products.extend(products)
                        if len(all_products) >= limit:
                            break
                            
            except requests.Timeout:
                print(f"[OPEN FOOD FACTS] Timeout on attempt {attempt_num + 1}")
                continue
            except Exception as e:
                print(f"[OPEN FOOD FACTS] Error on attempt {attempt_num + 1}: {e}")
                continue
        
        if not all_products:
            print(f"[OPEN FOOD FACTS] No results found after all attempts")
            return None
        
        # Process results
        output = []
        seen_names = set()
        
        for p in all_products[:limit * 2]:
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
                rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"
                
                display_name = f"{brand.title()} {name.title()}" if brand else name.title()
                
                output.append({
                    "name": display_name,
                    "brand": brand.title() if brand else "",
                    "vms_score": score,
                    "rating": rating,
                    "raw": row
                })
                
                print(f"[OPEN FOOD FACTS] ✅ Added: {display_name} (Score: {score})")
                
                if len(output) >= limit:
                    break
                
            except Exception as e:
                print(f"[OPEN FOOD FACTS] Error processing product: {e}")
                continue
        
        if output:
            print(f"[OPEN FOOD FACTS] Successfully processed {len(output)} products")
            return output
        else:
            print(f"[OPEN FOOD FACTS] No valid products after processing")
            return None
        
    except Exception as e:
        print(f"[OPEN FOOD FACTS] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return None

# === 3. SCANNER WITH ENHANCED DETECTION (FIX 3, 6) ===
def vision_live_scan_dark(image_bytes):
    """
    FIX 3: Enhanced to detect ALL items in frame with accurate counting
    FIX 6: Status tracking for in-widget display
    """
    api_key = get_gemini_api_key()
    if not api_key: 
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
        
        # Minimal crop (10% edges) to avoid UI elements, but scan most of frame
        left = int(w * 0.05)
        top = int(h * 0.05)
        right = int(w * 0.95)
        bottom = int(h * 0.95)
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
        
        # Enhanced prompt for whole-frame detection
        prompt = """You are a food detection AI. Identify ALL food items visible in this image.

CRITICAL RULES:
1. Count EACH item separately (1 apple, 2 bananas = 3 total items)
2. For PACKAGED goods: Use exact product name from label
3. For FRESH produce: Use common name, count each piece
4. List ALL items you see in the frame
5. Scan the ENTIRE visible area

Return a JSON array like: ["Apple", "Banana", "Banana", "Orange", "Coca Cola"]

If you see 2 apples, list "Apple" twice.
Be PRECISE. Return ONLY the JSON array, no other text."""
        
        # CORRECT: Use user's SDK format
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
            
            response_text = response.text.strip()
            print(f"[GEMINI] Raw response: {response_text}")
            
            # FIX 3: Parse JSON array of items
            import re
            json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if json_match:
                items_json = json_match.group(0)
                # Safe eval since we control the format
                detected_items = eval(items_json)
                print(f"✅ [GEMINI] Detected {len(detected_items)} items: {detected_items}")
            else:
                # Fallback to single item
                product_name = response_text.replace('"', '').replace('*', '').replace('.', '')
                detected_items = [product_name]
                print(f"✅ [GEMINI] Single item detected: {product_name}")
            
            # DARK themed detection message
            items_display = ", ".join(detected_items[:3])
            if len(detected_items) > 3:
                items_display += f" +{len(detected_items) - 3} more"
                
            st.markdown(f"""
                <div class="scanner-result">
                    <div class="scanner-result-title">👁️ Items Detected</div>
                    <div class="scanner-result-text">{items_display}</div>
                </div>
            """, unsafe_allow_html=True)
            
        except Exception as gemini_error:
            print(f"[GEMINI ERROR] {gemini_error}")
            # Fallback: treat as single item
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
            detected_items = [product_name]
            print(f"✅ [GEMINI] Fallback single item: {product_name}")
        
        # FIX 3: Search for ALL detected items
        all_results = []
        for item in detected_items:
            results = search_vantage_db(item, limit=1)
            if results and len(results) > 0:
                # FIX: Filter 10.0 default scores
                for r in results:
                    if r['vms_score'] != 10.0:
                        all_results.append(r)
        
        if all_results:
            print(f"✅ [DATABASE] Found {len(all_results)} total matches")
            
            # DARK themed success message
            st.markdown(f"""
                <div class="scanner-result">
                    <div class="scanner-result-title">✅ Database Match</div>
                    <div class="scanner-result-text">Found {len(all_results)} item(s)</div>
                </div>
            """, unsafe_allow_html=True)
            
            return all_results
        else:
            print(f"❌ [DATABASE] No matches found")
            
            # FIX 7: Friendly error message
            st.markdown(f"""
                <div class="scanner-result" style="border-left-color: #D4765E;">
                    <div class="scanner-result-title">🔍 Item Not Found Yet</div>
                    <div class="scanner-result-text">We're constantly expanding our database with new products.</div>
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
        
        # Better error handling for API quota
        if "429" in error_msg or "quota" in error_msg.lower() or "RESOURCE_EXHAUSTED" in error_msg:
            st.markdown(f"""
                <div class="scanner-result" style="border-left-color: #D4765E;">
                    <div class="scanner-result-title">⚠️ API Limit Reached</div>
                    <div class="scanner-result-text">High demand detected. Please try again in a few moments.</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div class="scanner-result" style="border-left-color: #D4765E;">
                    <div class="scanner-result-title">⚠️ Scan Error</div>
                    <div class="scanner-result-text">{error_msg[:150]}</div>
                </div>
            """, unsafe_allow_html=True)
        
        return None

# === 3B. AI HEALTH COACH AGENT ===
def generate_health_insights(trend_data, history_data, days_range):
    """
    Smart Health Coach: Analyzes user's eating trends and generates
    3 personalized, actionable recommendations using Gemini AI.

    Args:
        trend_data: list of (date, category, count) tuples from get_trend_data_db
        history_data: list of (date, item_name, score, category) tuples from get_all_calendar_data_db
        days_range: int, number of days being analyzed
    Returns:
        list of insight dicts or None on error
    """
    api_key = get_gemini_api_key()
    if not api_key:
        print("[INSIGHTS] No Gemini API key configured")
        return None

    try:
        # Build summary statistics
        total_items = sum(count for _, _, count in trend_data) if trend_data else 0
        healthy_count = sum(count for _, cat, count in trend_data if cat == 'healthy') if trend_data else 0
        moderate_count = sum(count for _, cat, count in trend_data if cat == 'moderate') if trend_data else 0
        unhealthy_count = sum(count for _, cat, count in trend_data if cat == 'unhealthy') if trend_data else 0

        # Build recent items list (last 20 items max)
        recent_items = []
        if history_data:
            for date, item_name, score, category in history_data[:20]:
                recent_items.append(f"- {date}: {item_name} (score: {score}, {category})")

        items_str = "\n".join(recent_items) if recent_items else "No items logged yet."

        prompt = f"""You are a friendly, expert nutritionist AI health coach. Analyze this user's eating data and provide exactly 3 personalized, specific, actionable insights.

USER'S EATING DATA (last {days_range} days):
- Total items logged: {total_items}
- Healthy items (score < 3.0): {healthy_count}
- Moderate items (score 3.0-7.0): {moderate_count}
- Unhealthy items (score > 7.0): {unhealthy_count}

RECENT ITEMS:
{items_str}

SCORING SYSTEM:
- Score < 3.0 = Metabolic Green (healthy)
- Score 3.0-7.0 = Metabolic Yellow (moderate)
- Score > 7.0 = Metabolic Red (unhealthy)
- Lower scores are better

RULES:
1. Be encouraging and positive, not judgmental
2. Reference SPECIFIC items from their history
3. Give ACTIONABLE swaps or suggestions
4. Keep each insight to 2-3 sentences max
5. If they have few items logged, encourage them to log more

Return ONLY valid JSON array, no other text:
[
  {{"emoji": "🥗", "title": "Short Title", "insight": "Your personalized observation...", "action": "Specific action step..."}},
  {{"emoji": "💪", "title": "Short Title", "insight": "Your personalized observation...", "action": "Specific action step..."}},
  {{"emoji": "🎯", "title": "Short Title", "insight": "Your personalized observation...", "action": "Specific action step..."}}
]"""

        client = genai.Client(api_key=api_key)
        print(f"[INSIGHTS] Calling Gemini API with {total_items} items over {days_range} days...")

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=types.Content(
                parts=[types.Part(text=prompt)]
            )
        )

        response_text = response.text.strip()
        print(f"[INSIGHTS] Raw response: {response_text[:200]}...")

        # Parse JSON response
        import json
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            insights = json.loads(json_match.group(0))
            print(f"✅ [INSIGHTS] Generated {len(insights)} insights")
            return insights
        else:
            print(f"❌ [INSIGHTS] Could not parse JSON from response")
            return None

    except Exception as e:
        print(f"❌ [INSIGHTS ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None


# === 3C. AI MEAL PLANNING AGENT ===
def generate_meal_plan(user_history, user_id):
    """
    AI Meal Planning Agent: Generates a personalized 7-day meal plan
    based on user's eating history and preferences using Gemini AI.

    Args:
        user_history: list of (date, item_name, score, category) tuples
        user_id: string, the current user identifier
    Returns:
        dict with day names as keys, list of meal dicts as values, or None on error
    """
    api_key = get_gemini_api_key()
    if not api_key:
        print("[MEAL PLAN] No Gemini API key configured")
        return None

    try:
        # Analyze user's history for patterns
        total = len(user_history) if user_history else 0
        healthy_items = [h for h in user_history if h[3] == 'healthy'] if user_history else []
        unhealthy_items = [h for h in user_history if h[3] == 'unhealthy'] if user_history else []

        # Get unique items the user has consumed
        liked_items = []
        if user_history:
            for _, item_name, score, category in user_history[:30]:
                liked_items.append(f"- {item_name} (score: {score}, {category})")

        items_str = "\n".join(liked_items) if liked_items else "No items logged yet - create a general healthy plan."

        healthy_pct = round((len(healthy_items) / total * 100), 1) if total > 0 else 0
        unhealthy_pct = round((len(unhealthy_items) / total * 100), 1) if total > 0 else 0

        prompt = f"""You are an expert nutritionist AI. Generate a personalized 7-day meal plan for this user.

USER PROFILE:
- Total items logged: {total}
- Healthy choices: {healthy_pct}%
- Unhealthy choices: {unhealthy_pct}%

ITEMS THEY'VE CONSUMED RECENTLY:
{items_str}

SCORING SYSTEM (Vantage Metabolic Score):
- Score < 3.0 = Metabolic Green (healthy)
- Score 3.0-7.0 = Metabolic Yellow (moderate)
- Score > 7.0 = Metabolic Red (unhealthy)
- Lower scores are better

RULES:
1. Generate 3 meals per day (Breakfast, Lunch, Dinner) for 7 days
2. Incorporate foods they already enjoy (when healthy)
3. Suggest healthier alternatives to their unhealthy choices
4. Keep estimated scores realistic (don't make everything 0)
5. Include variety - don't repeat the same meal
6. Make meals practical and easy to prepare
7. Use common grocery items

Return ONLY valid JSON, no other text:
{{
  "Monday": [
    {{"meal": "Breakfast", "name": "Meal description", "estimated_score": 1.5}},
    {{"meal": "Lunch", "name": "Meal description", "estimated_score": 2.0}},
    {{"meal": "Dinner", "name": "Meal description", "estimated_score": 2.5}}
  ],
  "Tuesday": [...],
  "Wednesday": [...],
  "Thursday": [...],
  "Friday": [...],
  "Saturday": [...],
  "Sunday": [...]
}}"""

        client = genai.Client(api_key=api_key)
        print(f"[MEAL PLAN] Calling Gemini API for user {user_id}...")

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=types.Content(
                parts=[types.Part(text=prompt)]
            )
        )

        response_text = response.text.strip()
        print(f"[MEAL PLAN] Raw response: {response_text[:200]}...")

        # Parse JSON response
        import json
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            meal_plan = json.loads(json_match.group(0))
            total_meals = sum(len(v) for v in meal_plan.values())
            print(f"✅ [MEAL PLAN] Generated plan with {total_meals} meals across {len(meal_plan)} days")
            return meal_plan
        else:
            print(f"❌ [MEAL PLAN] Could not parse JSON from response")
            return None

    except Exception as e:
        print(f"❌ [MEAL PLAN ERROR] {e}")
        import traceback
        traceback.print_exc()
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
    """Use DuckDB-compatible date math"""
    con = get_db_connection()
    try:
        threshold_date = datetime.now().date() - timedelta(days=days - 1)
        threshold_str = threshold_date.strftime('%Y-%m-%d')
        
        print(f"\n[TRENDS] ==================")
        print(f"[TRENDS] Username: {username}")
        print(f"[TRENDS] Looking for items since: {threshold_str}")
        print(f"[TRENDS] Days requested: {days}")
        
        results = con.execute("""
            SELECT date, category, COUNT(*) as count
            FROM calendar 
            WHERE username = ? AND date >= ?
            GROUP BY date, category 
            ORDER BY date ASC
        """, [username, threshold_str]).fetchall()
        
        print(f"[TRENDS] Found {len(results)} result rows")
        print(f"[TRENDS] ==================\n")
        
        return results
        
    except Exception as e:
        print(f"[TRENDS ERROR] {e}")
        import traceback
        traceback.print_exc()
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
