"""
Food Knowledge Base (FKB) - Canonical food records with enrichment.

Loads from the existing DuckDB products table and enriches each record with:
- Category taxonomy (produce_fruit, dairy, protein_meat, beverage, etc.)
- Synonyms for matching
- Typical serving sizes per category
- Processing labels (from NOVA + rule-based fallback)

Every food in the system is a record in the FKB, not a hardcoded string.
"""

from dataclasses import dataclass, field
from typing import Optional


# --- Category taxonomy with serving size defaults ---
CATEGORY_TAXONOMY = {
    # Produce
    'produce_fruit': {'serving_g': 150, 'form': 'solid', 'keywords': [
        'apple', 'banana', 'orange', 'grape', 'strawberry', 'blueberry',
        'raspberry', 'mango', 'pineapple', 'watermelon', 'melon', 'kiwi',
        'peach', 'pear', 'plum', 'cherry', 'lime', 'lemon', 'grapefruit',
        'papaya', 'guava', 'passion fruit', 'dragon fruit', 'fig',
        'pomegranate', 'apricot', 'nectarine', 'tangerine', 'clementine',
        'cranberry', 'blackberry', 'gooseberry', 'lychee', 'persimmon',
        'starfruit', 'jackfruit', 'durian', 'plantain', 'date fruit',
    ]},
    'produce_vegetable': {'serving_g': 100, 'form': 'solid', 'keywords': [
        'broccoli', 'spinach', 'kale', 'lettuce', 'tomato', 'cucumber',
        'carrot', 'onion', 'garlic', 'pepper', 'cauliflower', 'cabbage',
        'celery', 'zucchini', 'eggplant', 'asparagus', 'artichoke',
        'beetroot', 'beet', 'radish', 'turnip', 'parsnip', 'squash',
        'pumpkin', 'sweet potato', 'potato', 'corn', 'peas', 'green bean',
        'mushroom', 'okra', 'leek', 'chard', 'arugula', 'watercress',
        'endive', 'fennel', 'brussels sprout', 'bok choy', 'collard',
    ]},
    # Protein
    'protein_meat': {'serving_g': 100, 'form': 'solid', 'keywords': [
        'chicken', 'beef', 'pork', 'lamb', 'turkey', 'duck', 'veal',
        'venison', 'bison', 'rabbit', 'goat', 'ham', 'bacon', 'sausage',
        'steak', 'ground beef', 'ground turkey', 'meat', 'prosciutto',
    ]},
    'protein_fish': {'serving_g': 100, 'form': 'solid', 'keywords': [
        'salmon', 'tuna', 'cod', 'tilapia', 'sardine', 'mackerel',
        'trout', 'halibut', 'swordfish', 'anchovy', 'herring', 'catfish',
        'bass', 'perch', 'snapper', 'mahi', 'shrimp', 'prawn', 'lobster',
        'crab', 'clam', 'mussel', 'oyster', 'scallop', 'squid', 'octopus',
        'fish', 'seafood',
    ]},
    'protein_legume': {'serving_g': 130, 'form': 'solid', 'keywords': [
        'lentil', 'chickpea', 'black bean', 'kidney bean', 'navy bean',
        'pinto bean', 'lima bean', 'edamame', 'soybean', 'split pea',
        'bean', 'legume', 'dal', 'dhal', 'hummus',
    ]},
    'protein_egg': {'serving_g': 50, 'form': 'solid', 'keywords': [
        'egg', 'eggs', 'omelette', 'omelet', 'frittata',
    ]},
    # Dairy
    'dairy_milk': {'serving_g': 244, 'form': 'liquid', 'keywords': [
        'milk', 'whole milk', 'skim milk', 'low-fat milk', '2% milk',
        'buttermilk', 'goat milk',
    ]},
    'dairy_yogurt': {'serving_g': 170, 'form': 'solid', 'keywords': [
        'yogurt', 'yoghurt', 'greek yogurt', 'skyr', 'kefir', 'lassi',
    ]},
    'dairy_cheese': {'serving_g': 30, 'form': 'solid', 'keywords': [
        'cheese', 'cheddar', 'mozzarella', 'parmesan', 'brie', 'gouda',
        'swiss', 'feta', 'ricotta', 'cottage cheese', 'cream cheese',
        'provolone', 'gruyere', 'camembert', 'blue cheese', 'goat cheese',
    ]},
    # Grains
    'grain_bread': {'serving_g': 30, 'form': 'solid', 'keywords': [
        'bread', 'toast', 'bagel', 'muffin', 'croissant', 'baguette',
        'pita', 'naan', 'tortilla', 'flatbread', 'roll', 'bun',
        'sourdough', 'rye bread', 'whole wheat bread',
    ]},
    'grain_cereal': {'serving_g': 40, 'form': 'solid', 'keywords': [
        'cereal', 'oat', 'oatmeal', 'granola', 'muesli', 'porridge',
        'cornflake', 'bran',
    ]},
    'grain_pasta': {'serving_g': 140, 'form': 'solid', 'keywords': [
        'pasta', 'spaghetti', 'penne', 'fusilli', 'macaroni', 'linguine',
        'fettuccine', 'noodle', 'ramen', 'udon', 'rice noodle', 'lasagna',
    ]},
    'grain_rice': {'serving_g': 150, 'form': 'solid', 'keywords': [
        'rice', 'brown rice', 'white rice', 'basmati', 'jasmine rice',
        'wild rice', 'risotto', 'quinoa', 'couscous', 'bulgur',
    ]},
    # Beverages
    'beverage_juice': {'serving_g': 250, 'form': 'liquid', 'keywords': [
        'juice', 'orange juice', 'apple juice', 'grape juice', 'cranberry juice',
        'tomato juice', 'vegetable juice', 'smoothie', 'nectar',
    ]},
    'beverage_soda': {'serving_g': 330, 'form': 'liquid', 'keywords': [
        'soda', 'cola', 'pepsi', 'coca cola', 'coke', 'sprite', 'fanta',
        'mountain dew', 'dr pepper', 'ginger ale', 'tonic', 'root beer',
        'energy drink', 'red bull', 'monster',
    ]},
    'beverage_tea_coffee': {'serving_g': 240, 'form': 'liquid', 'keywords': [
        'tea', 'coffee', 'espresso', 'latte', 'cappuccino', 'matcha',
        'green tea', 'black tea', 'herbal tea', 'iced tea', 'chai',
    ]},
    'beverage_water': {'serving_g': 250, 'form': 'liquid', 'keywords': [
        'water', 'sparkling water', 'mineral water', 'coconut water',
    ]},
    'beverage_alcohol': {'serving_g': 150, 'form': 'liquid', 'keywords': [
        'beer', 'wine', 'vodka', 'whiskey', 'rum', 'gin', 'tequila',
        'sake', 'cider', 'champagne', 'cocktail', 'ale', 'stout', 'lager',
    ]},
    'beverage_milk_alt': {'serving_g': 244, 'form': 'liquid', 'keywords': [
        'oat milk', 'almond milk', 'soy milk', 'coconut milk', 'rice milk',
        'hemp milk', 'cashew milk', 'plant milk',
    ]},
    # Snacks
    'snack': {'serving_g': 30, 'form': 'solid', 'keywords': [
        'chip', 'chips', 'crisp', 'crisps', 'cracker', 'pretzel',
        'popcorn', 'trail mix', 'granola bar', 'protein bar', 'energy bar',
        'snack bar', 'rice cake',
    ]},
    # Sweets & Desserts
    'dessert': {'serving_g': 80, 'form': 'solid', 'keywords': [
        'cake', 'cookie', 'brownie', 'pie', 'tart', 'pastry', 'donut',
        'doughnut', 'ice cream', 'gelato', 'sorbet', 'pudding', 'mousse',
        'cupcake', 'waffle', 'pancake', 'crepe', 'churro', 'eclair',
        'macaron', 'tiramisu', 'cheesecake', 'flan', 'custard',
    ]},
    'candy': {'serving_g': 30, 'form': 'solid', 'keywords': [
        'candy', 'chocolate', 'gummy', 'lollipop', 'caramel', 'fudge',
        'toffee', 'marshmallow', 'licorice', 'jelly bean', 'skittles',
        'snickers', 'mars', 'twix', 'kitkat', 'reese', 'oreo',
    ]},
    # Condiments & Oils
    'condiment': {'serving_g': 15, 'form': 'solid', 'keywords': [
        'ketchup', 'mustard', 'mayonnaise', 'mayo', 'soy sauce',
        'hot sauce', 'vinegar', 'salsa', 'guacamole', 'hummus',
        'dressing', 'bbq sauce', 'teriyaki', 'sriracha', 'tabasco',
        'worcestershire', 'pesto', 'relish', 'chutney', 'aioli',
    ]},
    'oil_fat': {'serving_g': 14, 'form': 'liquid', 'keywords': [
        'oil', 'olive oil', 'coconut oil', 'vegetable oil', 'canola oil',
        'sesame oil', 'avocado oil', 'sunflower oil', 'peanut oil',
        'butter', 'margarine', 'ghee', 'lard', 'shortening',
    ]},
    'spread': {'serving_g': 20, 'form': 'solid', 'keywords': [
        'jam', 'jelly', 'marmalade', 'peanut butter', 'almond butter',
        'nutella', 'honey', 'maple syrup', 'syrup', 'molasses', 'agave',
    ]},
    'spice': {'serving_g': 3, 'form': 'solid', 'keywords': [
        'salt', 'pepper', 'sugar', 'cinnamon', 'paprika', 'cumin',
        'turmeric', 'oregano', 'basil', 'thyme', 'rosemary', 'ginger',
        'nutmeg', 'clove', 'cardamom', 'chili powder', 'curry powder',
    ]},
    # Nuts & Seeds
    'nuts_seeds': {'serving_g': 30, 'form': 'solid', 'keywords': [
        'almond', 'walnut', 'cashew', 'peanut', 'pistachio', 'pecan',
        'macadamia', 'hazelnut', 'brazil nut', 'chestnut', 'pine nut',
        'sunflower seed', 'pumpkin seed', 'chia seed', 'flax seed',
        'hemp seed', 'sesame seed', 'nut', 'nuts', 'seed', 'seeds',
    ]},
    # Dried fruits
    'dried_fruit': {'serving_g': 30, 'form': 'solid', 'keywords': [
        'raisin', 'dried', 'dehydrated', 'prune', 'dried apricot',
        'dried fig', 'dried mango', 'dried cranberry', 'date',
    ]},
    # Prepared/Composite foods
    'prepared_meal': {'serving_g': 250, 'form': 'solid', 'keywords': [
        'pizza', 'burger', 'sandwich', 'wrap', 'taco', 'burrito', 'bowl',
        'curry', 'stew', 'soup', 'salad', 'stir fry', 'casserole',
        'lasagna', 'quiche', 'risotto', 'paella', 'biryani', 'sushi',
        'gyoza', 'dumpling', 'spring roll', 'egg roll', 'empanada',
        'meal', 'dish', 'plate', 'platter', 'combo',
    ]},
    'frozen_food': {'serving_g': 200, 'form': 'solid', 'keywords': [
        'frozen', 'tv dinner', 'frozen pizza', 'frozen meal',
        'frozen entree', 'ice pop', 'popsicle',
    ]},
    # Supplements
    'supplement': {'serving_g': 10, 'form': 'solid', 'keywords': [
        'protein powder', 'whey', 'casein', 'creatine', 'bcaa',
        'supplement', 'vitamin', 'mineral', 'spirulina', 'chlorella',
    ]},
    # Avocado specifically (high-fat produce, unique profile)
    'produce_avocado': {'serving_g': 70, 'form': 'solid', 'keywords': [
        'avocado', 'guacamole',
    ]},
}


@dataclass
class FoodRecord:
    """A canonical food record in the knowledge base."""
    food_id: int
    canonical_name: str
    original_name: str
    brand: str
    synonyms: list = field(default_factory=list)
    category: str = 'unknown'
    nutrients_per_100g: dict = field(default_factory=dict)
    serving_size_g: float = 100.0
    typical_measures: list = field(default_factory=list)
    processing_label: str = 'unknown'
    processing_confidence: float = 0.0
    nova_group: int = 0
    form: str = 'solid'  # solid, liquid, powder, dried
    ingredients_text: str = ''
    raw_row: tuple = ()  # Original DB row for backward compat


def classify_category(name: str) -> tuple:
    """
    Classify a food name into a category from the taxonomy.
    Returns (category_key, confidence).

    Uses longest-match-first to handle multi-word keywords like
    'olive oil' before 'oil'.
    """
    n = name.lower()

    # Build a flat list of (keyword, category) sorted by keyword length desc
    all_keywords = []
    for cat_key, cat_info in CATEGORY_TAXONOMY.items():
        for kw in cat_info['keywords']:
            all_keywords.append((kw, cat_key))
    all_keywords.sort(key=lambda x: len(x[0]), reverse=True)

    for kw, cat_key in all_keywords:
        if kw in n:
            return cat_key, 0.8
    return 'unknown', 0.1


def get_serving_size(category: str) -> float:
    """Get typical serving size in grams for a category."""
    if category in CATEGORY_TAXONOMY:
        return CATEGORY_TAXONOMY[category]['serving_g']
    return 100.0


def get_form(category: str) -> str:
    """Get the typical form (solid/liquid) for a category."""
    if category in CATEGORY_TAXONOMY:
        return CATEGORY_TAXONOMY[category]['form']
    return 'solid'


def build_synonyms(name: str, brand: str, category: str) -> list:
    """
    Generate synonyms for a food record to improve search matching.
    """
    synonyms = []
    n = name.lower().strip()

    # The canonical name itself
    synonyms.append(n)

    # Without brand
    if brand:
        b = brand.lower().strip()
        no_brand = n.replace(b, '').strip().strip(',').strip()
        if no_brand and no_brand != n:
            synonyms.append(no_brand)

    # Without common suffixes
    for suffix in [', raw', ', fresh', ', organic', ', natural', ', plain']:
        if n.endswith(suffix):
            synonyms.append(n[:-len(suffix)].strip())

    # Singular/plural variants
    if n.endswith('s') and not n.endswith('ss'):
        synonyms.append(n[:-1])
    elif not n.endswith('s'):
        synonyms.append(n + 's')

    return list(set(synonyms))


def build_record_from_row(food_id: int, row: tuple) -> FoodRecord:
    """
    Build a FoodRecord from a database row.
    Row format: (product_name, brand, calories, sugar, fiber, protein, sat_fat, sodium_mg, grade, nova_group)
    """
    name = str(row[0] or '').strip()
    brand = str(row[1] or '').strip()
    cal = float(row[2] or 0)
    sug = float(row[3] or 0)
    fib = float(row[4] or 0)
    prot = float(row[5] or 0)
    fat = float(row[6] or 0)
    sod = float(row[7] or 0)
    nova = int(row[9] or 0) if row[9] else 0

    category, cat_conf = classify_category(name)
    serving_g = get_serving_size(category)
    form = get_form(category)
    synonyms = build_synonyms(name, brand, category)

    # Processing label from NOVA
    if nova >= 4:
        proc_label, proc_conf = 'ultra_processed', 0.9
    elif nova == 3:
        proc_label, proc_conf = 'processed', 0.85
    elif nova == 2:
        proc_label, proc_conf = 'processed_ingredient', 0.8
    elif nova == 1:
        proc_label, proc_conf = 'unprocessed', 0.9
    else:
        proc_label, proc_conf = 'unknown', 0.0

    return FoodRecord(
        food_id=food_id,
        canonical_name=name,
        original_name=name,
        brand=brand,
        synonyms=synonyms,
        category=category,
        nutrients_per_100g={
            'calories': cal,
            'sugar': sug,
            'fiber': fib,
            'protein': prot,
            'sat_fat': fat,
            'sodium': sod,
        },
        serving_size_g=serving_g,
        typical_measures=[{'name': 'serving', 'grams': serving_g}],
        processing_label=proc_label,
        processing_confidence=proc_conf,
        nova_group=nova,
        form=form,
        raw_row=row,
    )


class FoodKnowledgeBase:
    """
    The Food Knowledge Base: stores all canonical food records.
    Loads from DuckDB and enriches with taxonomy, synonyms, and serving info.
    """

    def __init__(self):
        self.records: list[FoodRecord] = []
        self._id_index: dict[int, FoodRecord] = {}
        self._name_index: dict[str, list[FoodRecord]] = {}

    def load_from_db(self, db_connection):
        """Load all products from the DuckDB database and build FoodRecords."""
        try:
            rows = db_connection.execute(
                "SELECT * FROM products WHERE product_name IS NOT NULL LIMIT 200000"
            ).fetchall()

            for i, row in enumerate(rows):
                record = build_record_from_row(i, row)
                self.records.append(record)
                self._id_index[i] = record

                key = record.canonical_name.lower()
                if key not in self._name_index:
                    self._name_index[key] = []
                self._name_index[key].append(record)

            print(f"[FKB] Loaded {len(self.records)} food records")
        except Exception as e:
            print(f"[FKB ERROR] Failed to load: {e}")
            import traceback
            traceback.print_exc()

    def get_record(self, food_id: int) -> Optional[FoodRecord]:
        return self._id_index.get(food_id)

    def get_all_texts(self) -> list[str]:
        """Get searchable text for each record (for building search index)."""
        texts = []
        for r in self.records:
            parts = [r.canonical_name]
            if r.brand:
                parts.append(r.brand)
            parts.extend(r.synonyms)
            parts.append(r.category.replace('_', ' '))
            texts.append(' '.join(parts).lower())
        return texts

    def get_all_names(self) -> list[str]:
        """Get canonical names for fuzzy matching."""
        return [r.canonical_name for r in self.records]

    def get_by_category(self, category: str) -> list[FoodRecord]:
        return [r for r in self.records if r.category == category]

    def size(self) -> int:
        return len(self.records)
