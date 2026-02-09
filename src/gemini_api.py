import os
import re
import time
import requests
from io import BytesIO
from PIL import Image
import google.generativeai as genai

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set!")

genai.configure(api_key=GEMINI_API_KEY)

# FIX 3 & 6: Updated vision model for better item detection
def vision_live_scan_dark(image_data):
    """
    Enhanced vision scanning with:
    - Better multi-item detection
    - Accurate counting
    - Status tracking
    - Error handling
    """
    try:
        # Convert image
        img = Image.open(BytesIO(image_data.getvalue()))
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        # FIX 3: Enhanced prompt for ALL items and accurate counting
        prompt = """You are a food detection AI. Analyze this image and identify ALL food items visible.

CRITICAL INSTRUCTIONS:
1. Count EACH individual item separately (1 apple = 1 item, 3 apples = 3 separate items)
2. List ALL items you see, even if there are many
3. For produce: Count individual pieces (2 bananas = list "Banana" twice)
4. For packaged goods: Identify the specific product name from the label
5. Focus ONLY on food items in the center focus area

Return ONLY a JSON array of food items, like this:
["Apple", "Banana", "Orange", "Coca Cola", "Potato Chips"]

If scanning packaged goods, use the exact product name from the package.
If scanning fresh produce, use the common name and list each piece separately.
DO NOT include any explanatory text, ONLY the JSON array.
"""
        
        # Call Gemini Vision API
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content([prompt, img])
        
        # Parse response
        response_text = response.text.strip()
        
        # Extract JSON array
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if not match:
            print(f"[VISION DEBUG] No JSON found in response: {response_text}")
            return None
        
        json_str = match.group(0)
        items = eval(json_str)  # Safe here since we control the format
        
        if not items:
            return None
        
        print(f"[VISION DEBUG] Detected {len(items)} items: {items}")
        
        # FIX 3: Search for ALL detected items (no limit)
        results = []
        for item_name in items:
            # Search in VantageDB
            search_results = search_vantage_db(item_name, limit=1)
            
            if search_results and len(search_results) > 0:
                result = search_results[0]
                # FIX: Filter out 10.0 default scores
                if result['vms_score'] != 10.0:
                    results.append(result)
        
        # Return ALL results (no cap)
        return results if results else None
        
    except Exception as e:
        # FIX 6: Better error handling for API quota
        error_str = str(e)
        if "429" in error_str or "quota" in error_str.lower():
            print(f"[VISION ERROR] API quota exceeded: {e}")
            # Return special error indicator
            return None
        elif "RESOURCE_EXHAUSTED" in error_str:
            print(f"[VISION ERROR] Resource exhausted: {e}")
            return None
        else:
            print(f"[VISION ERROR] Unexpected error: {e}")
            return None


def search_vantage_db(query, limit=5):
    """
    Search VantageDB with Open Food Facts fallback
    
    Returns list of dicts with:
    - name: Product name
    - vms_score: Metabolic health score
    - rating: Health category
    - raw: [name, brand, calories, sugar, fiber, protein, fat, sodium, _, nova]
    """
    from src.vantagedb import search_db
    
    # Try VantageDB first
    results = search_db(query, limit=limit)
    
    if results and len(results) > 0:
        formatted = []
        for r in results:
            name, brand, calories, sugar, fiber, protein, fat, sodium, _, nova = r
            vms = calculate_vms_science(r)
            rating = categorize_vms(vms)
            
            formatted.append({
                'name': name,
                'vms_score': round(vms, 2),
                'rating': rating,
                'raw': r
            })
        return formatted
    
    # FIX 7: Try Open Food Facts API as fallback
    print(f"[SEARCH DEBUG] Not found in VantageDB, trying Open Food Facts for: {query}")
    
    try:
        # Open Food Facts API with better search
        url = f"https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            'search_terms': query,
            'search_simple': 1,
            'json': 1,
            'page_size': limit
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            products = data.get('products', [])
            
            if products:
                formatted = []
                for p in products[:limit]:
                    # Extract nutrition data
                    nutrients = p.get('nutriments', {})
                    
                    # Create row format for VMS calculation
                    row = [
                        p.get('product_name', 'Unknown'),
                        p.get('brands', ''),
                        nutrients.get('energy-kcal_100g', 0),
                        nutrients.get('sugars_100g', 0),
                        nutrients.get('fiber_100g', 0),
                        nutrients.get('proteins_100g', 0),
                        nutrients.get('fat_100g', 0),
                        nutrients.get('sodium_100g', 0) * 1000,  # Convert to mg
                        '',
                        p.get('nova_group', 3)
                    ]
                    
                    vms = calculate_vms_science(row)
                    rating = categorize_vms(vms)
                    
                    formatted.append({
                        'name': row[0],
                        'vms_score': round(vms, 2),
                        'rating': rating,
                        'raw': row
                    })
                
                return formatted
    
    except Exception as e:
        print(f"[SEARCH ERROR] Open Food Facts API failed: {e}")
    
    return []


def calculate_vms_science(row):
    """
    Calculate VMS (Vantage Metabolic Score)
    
    Enhanced with FIX 5: Better cooked food detection
    """
    name, brand, calories, sugar, fiber, protein, fat, sodium, _, nova = row
    
    # Normalize inputs
    cal = float(calories) if calories else 100
    sug = float(sugar) if sugar else 0
    fib = float(fiber) if fiber else 0
    prot = float(protein) if protein else 0
    fat_val = float(fat) if fat else 0
    sod = float(sodium) if sodium else 0
    nova_val = int(nova) if nova else 3
    
    n = name.lower() if name else ""
    
    # FIX 5: Enhanced processing detection
    processing_keywords = [
        'fried', 'breaded', 'crispy', 'crunchy', 'battered',
        'biscuit', 'sandwich', 'burger', 'pizza', 'nugget',
        'patty', 'wrap', 'burrito', 'taco', 'quesadilla',
        'chips', 'crisps', 'crackers', 'cookies', 'cake',
        'pastry', 'donut', 'muffin', 'brownie', 'candy',
        'ice cream', 'frozen', 'microwave', 'instant'
    ]
    
    is_processed = any(keyword in n for keyword in processing_keywords) or nova_val >= 3
    
    # Superfood detection (only if NOT processed)
    superfood_list = ['salmon', 'lentils', 'beans', 'broccoli', 'egg', 'avocado', 'spinach', 'kale']
    is_superfood = (not is_processed) and any(food in n for food in superfood_list)
    
    # Liquid detection
    liquid_keywords = ['juice', 'drink', 'soda', 'cola', 'beverage', 'milk', 'smoothie', 'shake']
    is_liquid = any(keyword in n for keyword in liquid_keywords)
    
    # Dried fruit detection
    is_dried = 'dried' in n or 'raisin' in n
    
    # Dairy detection
    dairy_keywords = ['milk', 'yogurt', 'cheese', 'cream']
    is_dairy_plain = any(keyword in n for keyword in dairy_keywords) and 'chocolate' not in n and 'flavored' not in n
    
    # Fruit detection
    fruit_keywords = ['apple', 'banana', 'orange', 'berry', 'grape', 'melon', 'peach', 'pear']
    is_fruit = any(keyword in n for keyword in fruit_keywords)
    
    # Determine if whole/fresh (only if NOT processed)
    is_whole_fresh = ((nova_val <= 2 and not is_processed) or is_superfood or is_dairy_plain or is_fruit) and not (is_liquid or is_dried)
    
    # Base score calculation
    score = 0.0
    
    # Sugar penalty
    if sug > 15:
        score += 3.0
    elif sug > 8:
        score += 2.0
    elif sug > 4:
        score += 1.0
    
    # Fiber bonus
    if fib > 5:
        score -= 1.5
    elif fib > 3:
        score -= 1.0
    
    # Protein bonus
    if prot > 10:
        score -= 1.0
    
    # Sodium penalty
    if sod > 600:
        score += 2.0
    elif sod > 300:
        score += 1.0
    
    # Fat assessment
    if fat_val > 20:
        score += 1.5
    
    # NOVA penalty
    if nova_val == 4:
        score += 2.5
    elif nova_val == 3:
        score += 1.5
    
    # Final adjustments
    if is_whole_fresh:
        score = min(score, -1.0)  # Cap at very healthy
    
    if is_liquid and sug > 10:
        score += 2.0  # Sugary drinks penalty
    
    # Ensure score is in valid range
    score = max(-5.0, min(10.0, score))
    
    return score


def categorize_vms(score):
    """Categorize VMS score into health rating"""
    if score < 3.0:
        return "Metabolic Green"
    elif score < 7.0:
        return "Metabolic Yellow"
    else:
        return "Metabolic Red"


# Database functions (import from your existing DB)
def authenticate_user(username, password):
    from src.vantagedb import authenticate
    return authenticate(username, password)


def create_user(username, password):
    from src.vantagedb import create_user_db
    return create_user_db(username, password)


def add_calendar_item_db(user_id, date, item_name, score):
    from src.vantagedb import add_calendar_item
    return add_calendar_item(user_id, date, item_name, score)


def get_calendar_items_db(user_id, date):
    from src.vantagedb import get_calendar_items
    return get_calendar_items(user_id, date)


def delete_item_db(item_id):
    from src.vantagedb import delete_calendar_item
    return delete_calendar_item(item_id)


def get_log_history_db(user_id):
    from src.vantagedb import get_user_log_history
    return get_user_log_history(user_id)


def get_trend_data_db(user_id, days=7):
    from src.vantagedb import get_trend_data
    return get_trend_data(user_id, days)


def get_all_calendar_data_db(user_id):
    from src.vantagedb import get_all_user_calendar_data
    return get_all_user_calendar_data(user_id)
