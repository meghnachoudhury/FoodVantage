import duckdb
import os
import zipfile
import streamlit as st
import hashlib
import threading
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import io
import base64
import requests
import re
from datetime import datetime, timedelta

load_dotenv()

# === AI MODEL CONFIGURATION ===
# Text + vision AI via OpenAI-compatible endpoint
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_AGENT_MODEL = "gemini-2.5-flash"
GEMINI_SCANNER_MODEL = "gemini-2.5-flash"

# === DIGITALOCEAN GRADIENT AI CONFIGURATION (for hackathon integration) ===
GRADIENT_BASE_URL = "https://inference.do-ai.run/v1/"
GRADIENT_MODEL = "llama3.3-70b-instruct"

# System prompt that forces Gemini to return raw JSON without markdown wrapping
_JSON_SYSTEM = "You are a JSON API. Return ONLY valid JSON with no markdown, no code fences, no explanation. Start your response directly with { or [."

# gemini-2.5-flash has thinking ENABLED by default.
# We must explicitly set thinkingBudget=0 to disable it for fast/reliable calls,
# or a small budget for agent calls that benefit from light reasoning.
# Without this, thinking tokens consume max_tokens causing empty/400 responses.
_NO_THINKING = {"extra_body": {"google": {"thinkingConfig": {"thinkingBudget": 0}}}}
_SCANNER_LIGHT_THINKING = {"extra_body": {"google": {"thinkingConfig": {"thinkingBudget": 0}}}}
_LIGHT_THINKING = {"extra_body": {"google": {"thinkingConfig": {"thinkingBudget": 512}}}}

_MAX_TOKENS_VISION = 1536   # scanner JSON can include multiple label-heavy items
_MAX_TOKENS_TEXT = 8192     # increased to give agents room alongside light thinking


class ScannerAnalysisError(Exception):
    """Raised when scanner AI analysis fails (timeout/quota/network/model)."""

def safe_parse_json(text, expected='object'):
    """Robustly parse JSON from Gemini — strips code fences, fixes trailing commas."""
    import json, re
    if not text:
        return None
    # Remove markdown code fences (```json ... ``` or ``` ... ```)
    text = re.sub(r'```(?:json|python)?\s*', '', text)
    text = re.sub(r'```', '', text)
    text = text.strip()
    # Fix trailing commas before ] or } — common LLM mistake
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # Try full parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Extract the first complete JSON block
    pattern = r'\[[\s\S]*\]' if expected == 'array' else r'\{[\s\S]*\}'
    match = re.search(pattern, text)
    if match:
        snippet = re.sub(r',\s*([}\]])', r'\1', match.group(0))
        try:
            return json.loads(snippet)
        except Exception as e:
            print(f"[JSON] Parse still failed: {e} | Snippet: {snippet[:300]}")
    return None

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
    # Mints, gum, candy (~1-3g per piece)
    'mint': 0.02, 'mints': 0.02, 'gum': 0.03, 'lozenge': 0.03,
    'breath': 0.02, 'tic tac': 0.02,
    # Small candy/sweets (~10-15g per piece)
    'candy': 0.10, 'hard candy': 0.05, 'caramel': 0.10, 'toffee': 0.10,
    'lollipop': 0.10, 'jellybean': 0.05,
    # Chocolate bars (~40-50g serving)
    'chocolate': 0.40, 'chocolate bar': 0.40,
    # Supplements/vitamins (~1-5g per serving)
    'supplement': 0.03, 'vitamin': 0.02, 'probiotic': 0.02,
    # Tea, coffee (dry, ~2-3g per serving)
    'tea': 0.02, 'coffee': 0.08, 'espresso': 0.07,
}

def get_serving_scale(name):
    """Find the best matching serving scale for a product name"""
    n = name.lower()
    # Try longest matches first (e.g., 'olive oil' before 'oil')
    for keyword in sorted(SERVING_SCALE.keys(), key=len, reverse=True):
        if keyword in n:
            return SERVING_SCALE[keyword]
    return 1.0  # Default: use full per-100g values


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_serving_grams(product):
    """Best-effort extraction of serving size in grams from Open Food Facts product payload."""
    sq = _safe_float(product.get('serving_quantity'))
    if sq and sq > 0:
        return sq

    serving_size = str(product.get('serving_size', '') or '').lower()
    import re
    match = re.search(r'(\d+(?:\.\d+)?)\s*g\b', serving_size)
    if match:
        grams = _safe_float(match.group(1))
        if grams and grams > 0:
            return grams
    return None


def _nutrient_per_100g(nutriments, key_base, serving_g):
    """
    Normalize Open Food Facts nutrient values to a per-100g basis.
    Returns (value_per_100g, source_basis) where source_basis is one of:
    - 'per_100g' when *_100g is present
    - 'per_serving' when converted from *_serving using serving_g
    - 'missing' when neither path is usable
    """
    per_100_key = f"{key_base}_100g"
    per_serving_key = f"{key_base}_serving"

    per_100 = _safe_float(nutriments.get(per_100_key))
    if per_100 is not None:
        return per_100, 'per_100g'

    per_serving = _safe_float(nutriments.get(per_serving_key))
    if per_serving is None or not serving_g:
        return None, 'missing'

    return per_serving * (100.0 / serving_g), 'per_serving'


def _calories_per_100g(nutriments, serving_g):
    """Return kcal per 100g from OFF nutriments, with kJ fallback."""
    calories, basis = _nutrient_per_100g(nutriments, 'energy-kcal', serving_g)
    if calories is not None:
        return calories, basis

    energy_kj, kj_basis = _nutrient_per_100g(nutriments, 'energy', serving_g)
    if energy_kj is None:
        return None, 'missing'

    return energy_kj / 4.184, f"{kj_basis}_kj"


def _sodium_per_100g(nutriments, serving_g):
    """Return sodium (g/100g) from OFF, with salt-based fallback."""
    sodium, basis = _nutrient_per_100g(nutriments, 'sodium', serving_g)
    if sodium is not None:
        return sodium, basis

    salt, salt_basis = _nutrient_per_100g(nutriments, 'salt', serving_g)
    if salt is None:
        return None, 'missing'

    # OFF salt is grams NaCl; sodium is ~39.3% of salt by mass.
    return salt * 0.393, f"{salt_basis}_from_salt"

def calculate_vms_science(row):
    try:
        name, _, cal, sug, fib, prot, fat, sod, _, nova = row
        cal_f = _safe_float(cal)
        sug_f = _safe_float(sug)
        fat_f = _safe_float(fat)
        sod_f = _safe_float(sod)
        prot_f = _safe_float(prot)

        present_risk_fields = sum(
            _safe_float(v) is not None and _safe_float(v) > 0
            for v in [cal, sug, fat, sod]
        )

        # Guardrail: avoid over-confident "perfect" scores when OFF/local nutrition is sparse.
        if present_risk_fields < 2:
            return 5.0

        # Data-quality guardrail for packaged foods where key risk fields are zeroed/missing.
        if (cal_f or 0) >= 120 and (prot_f or 0) >= 5 and (fat_f or 0) == 0 and (sod_f or 0) == 0:
            return 5.0

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
            'lasagna', 'fries', 'frozen', 'processed',
            # FIX 5: Add cooked food keywords
            'cooked', 'grilled', 'baked', 'roasted', 'steamed', 'boiled',
            'sauteed', 'plate', 'meal', 'dish', 'curry', 'stew', 'soup'
        ]
        
        is_heavily_processed = any(word in n for word in processed_indicators) or nova_val >= 3

        # If likely processed food is missing a key risk field, avoid overly optimistic scores.
        if is_heavily_processed and (sod_f is None or fat_f is None):
            return 5.0
        
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
        score = round((pts_energy + pts_fat + pts_sodium + pts_sugar) - c_total, 1)
        
        if is_whole_fresh: return min(score, -1.0)
        if is_liquid and sug > 4.0: return max(score, 7.5)
        if is_dried and sug > 15.0: return max(score, 7.0)
        
        return max(-2.0, min(10.0, score))
    except: return 5.0

def vms_to_health_score(vms_score):
    """Convert VMS score (-2 to 10) to health score (0-100, higher is better)"""
    return max(0, min(100, round((10 - vms_score) / 12 * 100)))

def calculate_overall_health_score(username):
    """Calculate the overall health score (0-100) from all logged items"""
    con = get_db_connection()
    try:
        result = con.execute("""
            SELECT AVG(score) as avg_score
            FROM calendar
            WHERE username = ?
        """, [username]).fetchone()
        if result and result[0] is not None:
            return vms_to_health_score(result[0])
        return 0
    except Exception as e:
        print(f"[HEALTH SCORE ERROR] {e}")
        return 0

def calculate_day_streak(username):
    """
    Grocery Haul Streak: consecutive healthy shopping sessions counting back from
    the most recent haul. A 'haul' is any day where items were logged.
    Streak breaks on the first haul where avg health score < 50.
    Gaps between hauls (days with no shopping) do NOT break the streak.
    """
    con = get_db_connection()
    try:
        results = con.execute("""
            SELECT date, AVG(score) as avg_score
            FROM calendar
            WHERE username = ?
            GROUP BY date
            ORDER BY date DESC
        """, [username]).fetchall()
        streak = 0
        for date, avg_score in results:
            health_score = vms_to_health_score(avg_score)
            if health_score >= 50:
                streak += 1
            else:
                break  # Consecutive streak broken — stop counting
        return streak
    except Exception as e:
        print(f"[STREAK ERROR] {e}")
        return 0

def get_total_items_logged(username):
    """Get total number of items ever logged by user"""
    con = get_db_connection()
    try:
        result = con.execute("SELECT COUNT(*) FROM calendar WHERE username = ?", [username]).fetchone()
        return result[0] if result else 0
    except:
        return 0

def get_items_today(username):
    """Get number of items logged today"""
    con = get_db_connection()
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        result = con.execute("SELECT COUNT(*) FROM calendar WHERE username = ? AND date = ?", [username, today]).fetchone()
        return result[0] if result else 0
    except:
        return 0


def _normalized_tokens(text: str):
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', (text or '').lower())
    return [t for t in cleaned.split() if len(t) > 1]


def _token_query_terms(text: str):
    """Scanner-oriented search tokens (drop noisy packaging words)."""
    stopwords = {
        'and', 'with', 'for', 'the', 'from', 'classic', 'roast', 'blend',
        'flavor', 'flavour', 'original', 'instant', 'premium', 'natural',
        'fresh', 'food', 'item', 'items', 'pack', 'can', 'bottle', 'jar',
        'oz', 'ml', 'g', 'kg', 'lb', 'lbs'
    }
    tokens = []
    for tok in _normalized_tokens(text):
        if tok in stopwords:
            continue
        if tok.isdigit():
            continue
        if len(tok) < 3:
            continue
        tokens.append(tok)
    # Preserve order while deduplicating
    seen = set()
    out = []
    for tok in tokens:
        if tok not in seen:
            out.append(tok)
            seen.add(tok)
    return out


def _scanner_match_confidence(query: str, result: dict) -> float:
    """Heuristic confidence used to pick scanner matches from search candidates."""
    q_tokens = set(_normalized_tokens(query))
    name_tokens = set(_normalized_tokens(result.get('name', '')))
    brand_tokens = set(_normalized_tokens(result.get('brand', '')))
    all_tokens = name_tokens | brand_tokens

    if not q_tokens or not all_tokens:
        return 0.0

    overlap = len(q_tokens & all_tokens) / len(q_tokens)
    jaccard = len(q_tokens & all_tokens) / len(q_tokens | all_tokens)
    q_text = " ".join(_normalized_tokens(query))
    n_text = " ".join(_normalized_tokens(result.get('name', '')))
    exact_bonus = 0.35 if q_text and (q_text == n_text or q_text in n_text) else 0.0

    return (0.65 * overlap) + (0.35 * jaccard) + exact_bonus


def _has_minimum_nutrition(result: dict) -> bool:
    """Reject entries that are effectively empty nutrition rows."""
    raw = result.get('raw') if isinstance(result, dict) else None
    if not raw or len(raw) < 8:
        return False

    vals = [_safe_float(raw[2]), _safe_float(raw[3]), _safe_float(raw[6]), _safe_float(raw[7])]
    positive_count = sum(v is not None and v > 0 for v in vals)
    return positive_count >= 2

# === 2. DATABASE ACCESS ===
@st.cache_resource
def get_scientific_db():
    zip_path, db_path = 'data/vantage_core.zip', '/tmp/data/vantage_core.db'
    if not os.path.exists(db_path) and os.path.exists(zip_path):
        os.makedirs('/tmp/data', exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref: 
            zip_ref.extractall('/tmp/')
    return duckdb.connect(db_path, read_only=True)

def search_vantage_db(product_name: str, limit=5, fast_mode=False):
    """
    FIX 3: Returns up to 20 results (increased from 5)
    Returns top results with full product names
    """
    con = get_scientific_db()
    if not con: return None
    try:
        safe_name = product_name.replace("'", "''")
        search_terms = _token_query_terms(product_name)
        
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

        # Tokenized fallback for long/noisy scanner labels.
        # Example: "illy instant classico classic roast" should still find
        # products containing "illy" + "classico" even if the full phrase is absent.
        if (not results or len(results) == 0) and search_terms:
            token_clauses = [
                f"(product_name ILIKE '%{t}%' OR COALESCE(brand, '') ILIKE '%{t}%')"
                for t in search_terms[:5]
            ]
            if token_clauses:
                fallback_query = f"""
                    SELECT * FROM products
                    WHERE {' AND '.join(token_clauses)}
                    ORDER BY
                        LENGTH(product_name),
                        sugar DESC
                    LIMIT {limit}
                """
                results = con.execute(fallback_query).fetchall()
        
        # If no results in local DB, try Open Food Facts API
        if not results or len(results) == 0:
            print(f"[DB] No results in local database, trying Open Food Facts...")
            return search_open_food_facts(product_name, limit, fast_mode=fast_mode)
        
        output = []
        for r in results:
            score = round(calculate_vms_science(r), 1)
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

def search_open_food_facts(product_name: str, limit=5, fast_mode=False):
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
        attempts_to_try = search_attempts[:1] if fast_mode else search_attempts
        request_timeout_s = 4 if fast_mode else 10

        for attempt_num, term in enumerate(attempts_to_try):
            if not term or len(term) < 3:
                continue
                
            print(f"[OPEN FOOD FACTS] Attempt {attempt_num + 1}: '{term}'")
            
            url = "https://world.openfoodfacts.org/cgi/search.pl"
            params = {
                "search_terms": term,
                "page_size": limit * 3,
                "json": 1,
                "fields": "product_name,brands,nutriments,nova_group,serving_quantity,serving_size"
            }
            
            try:
                response = requests.get(url, params=params, timeout=request_timeout_s)
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
                
                # Extract actual serving size from Open Food Facts (in grams)
                serving_g = _extract_serving_grams(p)

                calories, calories_basis = _calories_per_100g(nutriments, serving_g)
                sugar, sugar_basis = _nutrient_per_100g(nutriments, 'sugars', serving_g)
                fiber, fiber_basis = _nutrient_per_100g(nutriments, 'fiber', serving_g)
                protein, protein_basis = _nutrient_per_100g(nutriments, 'proteins', serving_g)
                fat, fat_basis = _nutrient_per_100g(nutriments, 'fat', serving_g)
                sodium_per_100g, sodium_basis = _sodium_per_100g(nutriments, serving_g)
                sodium = (sodium_per_100g or 0) * 1000
                nova = int(p.get('nova_group', 3) or 3)

                row = [name, brand, calories, sugar, fiber, protein, fat, sodium, None, nova]

                score = round(calculate_vms_science(row), 1)
                rating = "Metabolic Green" if score < 3.0 else "Metabolic Yellow" if score < 7.0 else "Metabolic Red"

                display_name = f"{brand.title()} {name.title()}" if brand else name.title()

                result_entry = {
                    "name": display_name,
                    "brand": brand.title() if brand else "",
                    "vms_score": score,
                    "rating": rating,
                    "raw": row
                }
                # Include actual serving size when available from the API
                if serving_g:
                    result_entry["serving_g"] = serving_g
                result_entry["nutrition_basis"] = {
                    "calories": calories_basis,
                    "sugar": sugar_basis,
                    "fiber": fiber_basis,
                    "protein": protein_basis,
                    "fat": fat_basis,
                    "sodium": sodium_basis,
                }
                output.append(result_entry)
                
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

        # Downscale very large mobile images to reduce latency/timeouts.
        max_dim = 1600
        longest = max(img.size)
        if longest > max_dim:
            scale = max_dim / float(longest)
            resized = (max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale)))
            print(f"[DEBUG] Resizing image from {img.size} to {resized}")
            img = img.resize(resized, Image.LANCZOS)
            w, h = img.size

        # Minimal crop (10% edges) to avoid UI elements, but scan most of frame
        left = int(w * 0.05)
        top = int(h * 0.05)
        right = int(w * 0.95)
        bottom = int(h * 0.95)
        img_cropped = img.crop((left, top, right, bottom))

        # Final RGB check
        if img_cropped.mode != 'RGB':
            img_cropped = img_cropped.convert('RGB')

        # Convert to base64
        buf = io.BytesIO()
        img_cropped.save(buf, format="JPEG", quality=80)
        buf.seek(0)
        img_bytes = buf.read()
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')

        # Enhanced prompt for item detection + nutrition lookup intent
        prompt = """You are a grocery item detection ai. You have to recognize the item captured in the image using identification metrics like shape, color, container, brand of item if visible, and product name if caught in the image, and fetch nutrition data related to it if it has been posted by the brand for that product to finally display the results for "item detected"
CRITICAL RULES:
1. Count EACH item separately (1 apple, 2 bananas = 3 total items)
2. For PACKAGED goods: Use exact product name from label or try to identify and recognize the shape, color, extra text in the packaging (when brand and main face side of product not captured), and type of product and container if not directly visible.
3. For FRESH produce: Use common name, count each piece. Remember even though some packaged items may contain fruit in it, does not mean it is healthy. (For example, orange juice)
4. List ALL items you see in the frame
5. Scan the ENTIRE visible area

Return a JSON array like: ["Apple", "Banana", "Banana", "Orange", "Coca Cola"]

If you see 2 apples, list "Apple" twice.
Be PRECISE. Return ONLY the JSON array, no other text."""

        client = get_gemini_client()
        if not client:
            raise ScannerAnalysisError("No AI client configured")

        use_gemini = _using_gemini_key()
        print(f"[DEBUG] Calling {_active_model('scanner')} Vision API (provider={'gemini' if use_gemini else 'openai'})...")
        print(f"[DEBUG] Encoded payload size: {len(img_bytes)} bytes")

        try:
            request_kwargs = {
                "model": _active_model('scanner'),
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_b64}",
                                    "detail": "low"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": _MAX_TOKENS_VISION,
                "timeout": 35,
            }
            # Gemini endpoint supports thinkingConfig; OpenAI endpoint does not.
            if use_gemini:
                request_kwargs.update(_SCANNER_LIGHT_THINKING)

            response = client.chat.completions.create(**request_kwargs)

            response_text = (response.choices[0].message.content or "").strip()
            finish_reason = getattr(response.choices[0], 'finish_reason', None)
            print(f"[Gemini] finish_reason={finish_reason}, response length={len(response_text)}")
            if not response_text:
                print(f"[Gemini] WARNING: Empty response (finish_reason={finish_reason}).")
                raise ScannerAnalysisError(f"AI returned empty response (finish_reason={finish_reason}).")
            print(f"[Gemini] Raw response: {response_text}")

            detected_items = safe_parse_json(response_text, expected='array')
            if detected_items and isinstance(detected_items, list):
                print(f"✅ [Gemini] Detected {len(detected_items)} items: {detected_items}")
            else:
                # Fallback: treat whole response as single item name
                product_name = response_text.replace('"', '').replace('`', '').replace('*', '').strip()
                detected_items = [product_name] if product_name else ['food item']
                print(f"✅ [Gemini] Single item detected: {product_name}")

        except Exception as api_error:
            print(f"[GEMINI SCANNER ERROR] {api_error}")
            raise ScannerAnalysisError(str(api_error)) from api_error
        
        # FIX 3: Search for ALL detected items
        all_results = []
        for item in detected_items:
            results = search_vantage_db(item, limit=8, fast_mode=True)
            if results and len(results) > 0:
                nutritionally_valid = [r for r in results if _has_minimum_nutrition(r)]
                if not nutritionally_valid:
                    continue
                scored = sorted(
                    nutritionally_valid,
                    key=lambda r: _scanner_match_confidence(item, r),
                    reverse=True
                )
                best = scored[0]
                conf = _scanner_match_confidence(item, best)
                # 0.6 is too strict for label-heavy OCR/vision strings
                # (e.g. includes roast/blend/size descriptors).
                if conf >= 0.38:
                    all_results.append(best)
                elif conf >= 0.25 and len(detected_items) == 1:
                    # Single-item scans should degrade gracefully instead of hard-failing.
                    all_results.append(best)
        
        if all_results:
            print(f"✅ [DATABASE] Found {len(all_results)} total matches")
            
            return all_results
        else:
            print(f"❌ [DATABASE] No matches found")
            
            return None
        
    except ScannerAnalysisError:
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"❌ [SCAN ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        raise ScannerAnalysisError(error_msg) from e

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
    client = get_gemini_client()
    if not client:
        raise Exception("No API key found. Add GEMINI_API_KEY to Streamlit secrets (Settings → Secrets).")

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

        prompt = f"""You are a friendly, expert nutritionist AI health coach. Analyze this user's eating data and provide exactly 5 personalized, specific, actionable insights.

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
4. Write complete, thorough insights — do not cut off mid-sentence
5. If they have few items logged, encourage them to log more

Return ONLY valid JSON array, no other text:
[
  {{"emoji": "🥗", "title": "Short Title", "insight": "Your personalized observation...", "action": "Specific action step..."}},
  {{"emoji": "💪", "title": "Short Title", "insight": "Your personalized observation...", "action": "Specific action step..."}},
  {{"emoji": "🎯", "title": "Short Title", "insight": "Your personalized observation...", "action": "Specific action step..."}},
  {{"emoji": "🌱", "title": "Short Title", "insight": "Your personalized observation...", "action": "Specific action step..."}},
  {{"emoji": "✨", "title": "Short Title", "insight": "Your personalized observation...", "action": "Specific action step..."}}
]"""

        print(f"[INSIGHTS] Calling {_active_model('agent')} with {total_items} items over {days_range} days...")

        response = client.chat.completions.create(
            model=_active_model('agent'),
            messages=[
                {"role": "system", "content": _JSON_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            max_tokens=_MAX_TOKENS_TEXT,
            **_LIGHT_THINKING
        )

        response_text = (response.choices[0].message.content or "").strip()
        finish_reason = getattr(response.choices[0], 'finish_reason', None)
        print(f"[INSIGHTS] finish_reason={finish_reason}, response length={len(response_text)}")
        if not response_text:
            print(f"[INSIGHTS] WARNING: Empty response — thinking may have consumed token budget")
            raise Exception(f"AI returned empty response (finish_reason={finish_reason}). Try again.")
        print(f"[INSIGHTS] Raw response: {response_text[:200]}...")

        insights = safe_parse_json(response_text, expected='array')
        if insights:
            print(f"✅ [INSIGHTS] Generated {len(insights)} insights")
            return insights
        raise Exception(f"AI returned non-JSON response: {response_text[:300]}")

    except Exception as e:
        print(f"❌ [INSIGHTS ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise  # Re-raise so the UI can display the actual error


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
    client = get_gemini_client()
    if not client:
        raise Exception("No API key found. Add GEMINI_API_KEY to Streamlit secrets (Settings → Secrets).")

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

        print(f"[MEAL PLAN] Calling {_active_model('agent')} for user {user_id}...")

        response = client.chat.completions.create(
            model=_active_model('agent'),
            messages=[
                {"role": "system", "content": _JSON_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            max_tokens=_MAX_TOKENS_TEXT,
            **_LIGHT_THINKING
        )

        response_text = (response.choices[0].message.content or "").strip()
        finish_reason = getattr(response.choices[0], 'finish_reason', None)
        print(f"[MEAL PLAN] finish_reason={finish_reason}, response length={len(response_text)}")
        if not response_text:
            print(f"[MEAL PLAN] WARNING: Empty response — thinking may have consumed token budget")
            raise Exception(f"AI returned empty response (finish_reason={finish_reason}). Try again.")
        print(f"[MEAL PLAN] Raw response: {response_text[:200]}...")

        meal_plan = safe_parse_json(response_text, expected='object')
        if meal_plan:
            total_meals = sum(len(v) for v in meal_plan.values() if isinstance(v, list))
            print(f"✅ [MEAL PLAN] Generated plan with {total_meals} meals across {len(meal_plan)} days")
            return meal_plan
        raise Exception(f"AI returned non-JSON response: {response_text[:300]}")

    except Exception as e:
        print(f"❌ [MEAL PLAN ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise  # Re-raise so the UI can display the actual error


# === 3D. DAILY HEALTHY RECIPES AGENT ===

def fetch_bbc_food_url(recipe_name):
    """
    Search BBC Food for a real recipe matching the given name.
    Returns the direct recipe URL if found, otherwise None (recipe doesn't exist).
    """
    import re
    try:
        query = recipe_name.replace(' ', '+')
        search_url = f"https://www.bbc.co.uk/food/search?q={query}"
        response = requests.get(search_url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; FoodVantage/1.0)'
        })
        if response.status_code == 200:
            # Extract the first recipe link from BBC Food search results
            matches = re.findall(r'href="(/food/recipes/[^"]+)"', response.text)
            if matches:
                url = f"https://www.bbc.co.uk{matches[0]}"
                print(f"[BBC FOOD] Found recipe URL for '{recipe_name}': {url}")
                return url
        print(f"[BBC FOOD] No match for '{recipe_name}' — skipping (no BBC Food page)")
        return None
    except Exception as e:
        print(f"[BBC FOOD] Error fetching URL for '{recipe_name}': {e}")
        return None


def generate_daily_recipes():
    """
    Generates 5 unique healthy recipe tiles for the day using Gemini 2.5 Flash.
    Each recipe is matched to a real BBC Food page with a clickable link.
    Returns list of 5 recipe dicts or None on error.
    """
    client = get_gemini_client()
    if not client:
        raise Exception("No API key found. Add GEMINI_API_KEY to Streamlit secrets (Settings → Secrets).")

    try:
        today = datetime.now()
        day_of_week = today.strftime("%A")
        day_of_year = today.timetuple().tm_yday
        week_number = today.isocalendar()[1]

        prompt = f"""You are a healthy recipe curator. Today is {day_of_week}, day {day_of_year} of the year, week {week_number}.

Suggest exactly 5 REAL recipes that exist on BBC Food (bbc.co.uk/food). Use actual recipe names as they appear on the BBC Food website so we can link to them.

RULES:
1. Each recipe must be DIFFERENT - no repeating ingredients or themes
2. Mix cuisines: include at least 3 different cuisine types (Mediterranean, Asian, Mexican, Indian, etc.)
3. Mix meal types: include breakfast, lunch, dinner, snack, and dessert options
4. All recipes should be genuinely healthy (low sugar, high fiber/protein, whole ingredients)
5. Use the day number ({day_of_year}) as a seed - generate DIFFERENT recipes than you would for day {day_of_year - 1} or {day_of_year + 1}
6. Include estimated prep time
7. Keep recipe names concise (max 6 words)
8. Use REAL BBC Food recipe names that actually exist on their website

Return ONLY valid JSON array, no other text:
[
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Breakfast", "prep_time": "15 min", "description": "One sentence description of the dish", "key_ingredients": "3-4 main ingredients"}},
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Lunch", "prep_time": "20 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}},
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Dinner", "prep_time": "30 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}},
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Snack", "prep_time": "10 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}},
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Dessert", "prep_time": "15 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}}
]"""

        print(f"[RECIPES] Calling {_active_model('agent')} for daily recipes (day {day_of_year})...")

        response = client.chat.completions.create(
            model=_active_model('agent'),
            messages=[
                {"role": "system", "content": _JSON_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            max_tokens=_MAX_TOKENS_TEXT,
            **_LIGHT_THINKING
        )

        response_text = (response.choices[0].message.content or "").strip()
        finish_reason = getattr(response.choices[0], 'finish_reason', None)
        print(f"[RECIPES] finish_reason={finish_reason}, response length={len(response_text)}")
        if not response_text:
            print(f"[RECIPES] WARNING: Empty response — thinking may have consumed token budget")
            raise Exception(f"AI returned empty response (finish_reason={finish_reason}). Try again.")
        print(f"[RECIPES] Raw response: {response_text[:200]}...")

        recipes = safe_parse_json(response_text, expected='array')
        if recipes:
            recipes = recipes[:5]
            # Enrich each recipe with a real BBC Food URL and filter out missing ones
            validated = []
            for recipe in recipes:
                url = fetch_bbc_food_url(recipe.get('name', ''))
                if url:
                    recipe['recipe_url'] = url
                    validated.append(recipe)
                else:
                    print(f"[RECIPES] Dropped '{recipe.get('name', '')}' — no BBC Food page found")
            if validated:
                print(f"✅ [RECIPES] {len(validated)} of {len(recipes)} recipes validated with BBC Food links")
                return validated
            print(f"[RECIPES] No recipes had valid BBC Food links, returning None")
            return None
        raise Exception(f"AI returned non-JSON response: {response_text[:300]}")

    except Exception as e:
        print(f"❌ [RECIPES ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise


# === 4. USER DB & TRENDS ===
# Thread-local storage: each Streamlit worker thread gets its own DuckDB connection.
# A single shared connection (e.g. @st.cache_resource) is NOT thread-safe — concurrent
# writes from two simultaneous users cause race conditions and silent data corruption.
_db_thread_local = threading.local()


def _init_user_db_schema(con):
    """Ensure required auth/calendar/allergy tables exist."""
    con.execute("CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR)")
    try:
        con.execute("CREATE SEQUENCE IF NOT EXISTS seq_cal_id START 1")
    except Exception:
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
    con.execute("CREATE TABLE IF NOT EXISTS allergies (username VARCHAR, allergy_name VARCHAR)")

def get_db_connection():
    """Return a per-thread DuckDB connection to the user data store."""
    if not getattr(_db_thread_local, 'con', None):
        db_path = 'data/user_data.db'
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Recover from zero-byte database files (common after failed deploy/startup).
        if os.path.exists(db_path) and os.path.getsize(db_path) == 0:
            os.remove(db_path)

        try:
            con = duckdb.connect(db_path, read_only=False)
        except duckdb.IOException as e:
            # Last-resort recovery for corrupted/non-duckdb files.
            if "not a valid DuckDB database file" in str(e):
                backup_path = f"{db_path}.corrupt"
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                if os.path.exists(db_path):
                    os.replace(db_path, backup_path)
                con = duckdb.connect(db_path, read_only=False)
                print(f"[AUTH] Rebuilt invalid user DB. Backup saved to {backup_path}")
            else:
                raise

        _init_user_db_schema(con)
        _db_thread_local.con = con
    return _db_thread_local.con

def _ensure_allergies_table():
    """Create allergies table if it doesn't exist (called outside cache)"""
    con = get_db_connection()
    try:
        con.execute("CREATE TABLE IF NOT EXISTS allergies (username VARCHAR, allergy_name VARCHAR)")
    except:
        pass

# --- Allergy DB Functions ---
ALLERGY_KEYWORDS = {
    "Peanuts": ["peanut", "groundnut", "arachis"],
    "Tree Nuts": ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut", "macadamia", "brazil nut", "chestnut"],
    "Milk / Dairy": ["milk", "cheese", "yogurt", "yoghurt", "butter", "cream", "dairy", "whey", "casein", "lactose", "ghee", "paneer", "curd"],
    "Eggs": ["egg"],
    "Wheat / Gluten": ["wheat", "bread", "pasta", "flour", "gluten", "cereal", "biscuit", "cookie", "cake", "cracker", "noodle", "couscous"],
    "Soy": ["soy", "soya", "tofu", "edamame", "tempeh", "miso"],
    "Fish": ["fish", "cod", "salmon", "tuna", "haddock", "sardine", "anchovy", "mackerel", "trout", "bass", "tilapia"],
    "Shellfish": ["shrimp", "prawn", "crab", "lobster", "oyster", "mussel", "clam", "scallop", "crawfish", "crayfish"],
    "Sesame": ["sesame", "tahini"],
    "Celery": ["celery", "celeriac"],
    "Mustard": ["mustard"],
    "Lupin": ["lupin", "lupini"],
    "Molluscs": ["mollusc", "squid", "octopus", "snail", "calamari"],
    "Sulphites": ["sulphite", "sulfite"],
    "Corn": ["corn", "maize", "polenta", "cornmeal", "cornstarch"],
}

def get_user_allergies(username):
    """Get list of allergy names for a user"""
    _ensure_allergies_table()
    con = get_db_connection()
    try:
        result = con.execute("SELECT allergy_name FROM allergies WHERE username = ?", [username]).fetchall()
        return [r[0] for r in result]
    except:
        return []

def save_user_allergies(username, allergy_list):
    """Save user's allergies (replaces existing)"""
    _ensure_allergies_table()
    con = get_db_connection()
    try:
        con.execute("DELETE FROM allergies WHERE username = ?", [username])
        for allergy in allergy_list:
            con.execute("INSERT INTO allergies VALUES (?, ?)", [username, allergy])
    except Exception as e:
        print(f"[ALLERGY DB] Error saving allergies: {e}")

def check_item_allergies(item_name, user_allergies):
    """Check if an item name matches any of the user's allergies.
    Returns list of matched allergy names."""
    if not user_allergies or not item_name:
        return []
    item_lower = item_name.lower()
    matched = []
    for allergy in user_allergies:
        keywords = ALLERGY_KEYWORDS.get(allergy, [allergy.lower()])
        for kw in keywords:
            if kw in item_lower:
                matched.append(allergy)
                break
    return matched

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
def _find_secret(names):
    """
    Flexibly search st.secrets for any of the given key names.
    Handles: flat keys, case-insensitive matches, and one level of TOML nesting.
    Logs every secret key name found (not values) for debugging.
    """
    try:
        # This line will raise FileNotFoundError locally if no secrets.toml exists
        top_level = list(st.secrets.keys())
        print(f"[AUTH] st.secrets top-level keys: {top_level}")
    except Exception as e:
        print(f"[AUTH] st.secrets not accessible: {e}")
        return None

    # Try exact match at top level
    for name in names:
        if name in st.secrets:
            val = st.secrets[name]
            if val:
                print(f"[AUTH] Found '{name}' in st.secrets (exact)")
                return val

    # Try case-insensitive match at top level
    secrets_lower = {k.lower(): k for k in top_level}
    for name in names:
        canonical = secrets_lower.get(name.lower())
        if canonical:
            val = st.secrets[canonical]
            if val:
                print(f"[AUTH] Found '{canonical}' (case-insensitive match for '{name}')")
                return val

    # Try one level of nesting (e.g. [api_keys] section in TOML)
    for section_key in top_level:
        try:
            section = st.secrets[section_key]
            if not isinstance(section, dict):
                continue
            section_lower = {k.lower(): k for k in section.keys()}
            for name in names:
                canonical = section_lower.get(name.lower())
                if canonical:
                    val = section[canonical]
                    if val:
                        print(f"[AUTH] Found '{name}' in st.secrets['{section_key}']['{canonical}'] (nested)")
                        return val
        except Exception:
            continue

    print(f"[AUTH] None of {names} found anywhere in st.secrets")
    return None


def get_gemini_api_key():
    """
    Returns AI API key with flexible lookup — handles any casing, naming
    variant, or TOML nesting the user may have used in Streamlit secrets.
    Falls back to env vars and then to OPENAI_API_KEY for backward compat.
    """
    # 1. Gemini key — try all common name variants
    gemini_names = ["GEMINI_API_KEY", "gemini_api_key", "GOOGLE_API_KEY", "google_api_key",
                    "GOOGLE_GEMINI_API_KEY", "google_gemini_api_key", "GeminiApiKey",
                    "GEMINI_KEY", "gemini_key"]
    val = _find_secret(gemini_names)
    if val:
        return val

    # 2. Env vars for Gemini
    for name in gemini_names:
        val = os.getenv(name)
        if val:
            print(f"[AUTH] Found '{name}' in environment")
            return val

    # 3. Fallback — OpenAI key (for environments not yet migrated)
    openai_names = ["OPENAI_API_KEY", "openai_api_key", "OpenAiApiKey"]
    val = _find_secret(openai_names)
    if val:
        print("[AUTH] Using OPENAI_API_KEY as fallback")
        return val
    for name in openai_names:
        val = os.getenv(name)
        if val:
            print(f"[AUTH] Using '{name}' from env as fallback")
            return val

    print("[AUTH] ERROR: No API key found in secrets or environment")
    return None


def _using_gemini_key():
    """True when a Gemini/Google key is available (not the OpenAI fallback)."""
    gemini_names = ["GEMINI_API_KEY", "gemini_api_key", "GOOGLE_API_KEY", "google_api_key",
                    "GOOGLE_GEMINI_API_KEY", "google_gemini_api_key", "GeminiApiKey",
                    "GEMINI_KEY", "gemini_key"]
    # Use the same flexible lookup as get_gemini_api_key to stay in sync
    if _find_secret(gemini_names):
        return True
    return any(os.getenv(n) for n in gemini_names)


def _active_model(mode='agent'):
    """Return model name for the requested mode and configured provider."""
    if not _using_gemini_key():
        return "gpt-4o"
    return GEMINI_SCANNER_MODEL if mode == 'scanner' else GEMINI_AGENT_MODEL


def get_gemini_client():
    """OpenAI-compatible client — auto-detects Gemini or OpenAI key."""
    api_key = get_gemini_api_key()
    if not api_key:
        print("[CLIENT] ERROR: No API key available — all AI agents will be disabled")
        return None
    if _using_gemini_key():
        print(f"[CLIENT] Gemini endpoint active: agent={GEMINI_AGENT_MODEL}, scanner={GEMINI_SCANNER_MODEL}")
        return OpenAI(base_url=GEMINI_BASE_URL, api_key=api_key)
    print("[CLIENT] OpenAI fallback active: model=gpt-4o")
    return OpenAI(api_key=api_key)


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

def user_exists(username):
    """Check if a username exists in the DB."""
    try:
        con = get_db_connection()
        result = con.execute("SELECT 1 FROM users WHERE username = ?", [username]).fetchone()
        return result is not None
    except Exception as e:
        print(f"[AUTH ERROR] user_exists: {e}")
        return False

def reset_password(username, new_password):
    """Reset the password for an existing user. Returns True on success."""
    try:
        con = get_db_connection()
        exists = con.execute("SELECT 1 FROM users WHERE username = ?", [username]).fetchone()
        if not exists:
            print(f"[AUTH] reset_password: user '{username}' not found")
            return False
        pwd_hash = hashlib.sha256(new_password.encode()).hexdigest()
        con.execute("UPDATE users SET password_hash = ? WHERE username = ?", [pwd_hash, username])
        print(f"[AUTH] Password reset for '{username}'")
        return True
    except Exception as e:
        print(f"[AUTH ERROR] reset_password: {e}")
        return False

def change_password(username, old_password, new_password):
    """Change password after verifying the old one. Returns True on success."""
    if not authenticate_user(username, old_password):
        return False
    return reset_password(username, new_password)

def delete_account(username):
    """Delete a user account and all their data."""
    try:
        con = get_db_connection()
        con.execute("DELETE FROM users WHERE username = ?", [username])
        con.execute("DELETE FROM calendar WHERE username = ?", [username])
        _ensure_allergies_table()
        con.execute("DELETE FROM allergies WHERE username = ?", [username])
        print(f"[AUTH] Deleted account and all data for '{username}'")
        return True
    except Exception as e:
        print(f"[AUTH ERROR] delete_account: {e}")
        return False
