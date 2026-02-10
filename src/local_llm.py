"""
Local LLM integration via Ollama.

Provides a unified interface for all LLM tasks in FoodVantage:
- Vision scanning (multimodal: image → food items)
- Structured food parsing (text → JSON schema)
- Health coaching (trend data → insights)
- Meal planning (history → 7-day plan)
- Recipe generation (date seed → 5 recipes)

Uses Ollama's OpenAI-compatible API, so the same code works with:
- Local Ollama on Mac (development)
- Dockerized Ollama (production)
- Any OpenAI-compatible endpoint (fallback)

Setup:
    1. Install Ollama: https://ollama.com
    2. Pull models (~3GB total):
        ollama pull moondream              # Vision (~1.7GB) - smallest vision model
        ollama pull llama3.2:1b            # Text (~1.3GB) - lightweight instruct
    3. Ollama runs automatically on http://localhost:11434

    For more capable (but larger) models:
        ollama pull llama3.2-vision:11b    # Vision (~7GB) - best quality
        ollama pull llama3.2:3b            # Text (~2GB) - better JSON output
"""

import os
import json
import re
import base64
import requests
from typing import Optional


# --- Configuration ---
# Override with environment variables or .env
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "moondream")
OLLAMA_TEXT_MODEL = os.getenv("OLLAMA_TEXT_MODEL", "llama3.2:1b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))


class LocalLLM:
    """
    Unified local LLM client for all FoodVantage AI tasks.

    Uses Ollama's REST API directly (no pip dependency needed beyond requests).
    Falls back gracefully if Ollama is unavailable.
    """

    def __init__(
        self,
        base_url: str = None,
        vision_model: str = None,
        text_model: str = None,
        timeout: int = None,
    ):
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.vision_model = vision_model or OLLAMA_VISION_MODEL
        self.text_model = text_model or OLLAMA_TEXT_MODEL
        self.timeout = timeout or OLLAMA_TIMEOUT
        self._available = None

    # --- Health check ---

    def is_available(self) -> bool:
        """Check if Ollama is running and reachable."""
        if self._available is not None:
            return self._available
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            self._available = r.status_code == 200
            if self._available:
                models = [m["name"] for m in r.json().get("models", [])]
                print(f"[LocalLLM] Ollama is running. Available models: {models}")
            return self._available
        except Exception:
            self._available = False
            print("[LocalLLM] Ollama is not reachable. AI features will be unavailable.")
            return False

    def list_models(self) -> list:
        """List all models available in Ollama."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []

    def has_model(self, model_name: str) -> bool:
        """Check if a specific model is pulled and ready."""
        models = self.list_models()
        # Check both exact match and prefix match (e.g., "llama3.2:3b" matches "llama3.2:3b-...")
        return any(model_name in m or m.startswith(model_name.split(":")[0]) for m in models)

    # --- Core generation ---

    def generate(
        self,
        prompt: str,
        model: str = None,
        system: str = None,
        images: list = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> Optional[str]:
        """
        Generate a response from the local LLM.

        Args:
            prompt: The user prompt
            model: Model name override (defaults to text_model or vision_model if images provided)
            system: System prompt
            images: List of base64-encoded images (triggers vision model)
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens to generate
            json_mode: If True, request JSON format output

        Returns:
            The generated text, or None on failure
        """
        if not self.is_available():
            return None

        # Auto-select model
        if model is None:
            model = self.vision_model if images else self.text_model

        # Build messages for chat API
        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        user_msg = {"role": "user", "content": prompt}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if json_mode:
            payload["format"] = "json"

        try:
            print(f"[LocalLLM] Calling {model} (temp={temperature}, max_tokens={max_tokens})")
            r = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )

            if r.status_code != 200:
                print(f"[LocalLLM] Error {r.status_code}: {r.text[:200]}")
                return None

            data = r.json()
            content = data.get("message", {}).get("content", "")
            print(f"[LocalLLM] Response ({len(content)} chars): {content[:150]}...")
            return content

        except requests.Timeout:
            print(f"[LocalLLM] Timeout after {self.timeout}s")
            return None
        except Exception as e:
            print(f"[LocalLLM] Error: {e}")
            return None

    # --- Task-specific methods ---

    def detect_food_items(self, image_b64: str) -> Optional[list]:
        """
        Vision task: detect food items in an image.
        Returns a list of food item names, or None on failure.
        """
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

        response = self.generate(
            prompt=prompt,
            images=[image_b64],
            temperature=0.1,
            max_tokens=500,
        )

        if not response:
            return None

        return self._parse_json_array(response)

    def parse_food_input(self, text: str) -> Optional[dict]:
        """
        Structured parsing: convert user food text into a structured schema.

        Returns dict with keys:
            base_food, form, prep, modifiers, brand, portion, packaged_hint
        """
        prompt = f"""Parse this food input into a structured JSON object.

Input: "{text}"

Return ONLY valid JSON with these fields:
{{
  "base_food": "the core food item name (e.g., yogurt, chicken, orange)",
  "form": "solid|juice|drink|powder|dried|frozen|unknown",
  "prep": "raw|baked|fried|grilled|boiled|steamed|roasted|sauteed|unknown",
  "modifiers": ["list", "of", "descriptors like plain, berry, sweetened, greek, organic"],
  "brand": "brand name or null",
  "portion": {{"qty": 1, "unit": "piece|cup|tbsp|g|ml|oz|slice|serving|unknown"}},
  "packaged_hint": false
}}

Rules:
- base_food should be the simplest canonical name
- If it mentions a brand (e.g., "Coca Cola"), set brand and packaged_hint=true
- If portion is not specified, use {{"qty": 1, "unit": "serving"}}
- modifiers captures flavor, style, preparation adjectives
- Be precise and consistent"""

        response = self.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=300,
            json_mode=True,
        )

        if not response:
            return None

        return self._parse_json_object(response)

    def generate_health_insights(
        self,
        total_items: int,
        healthy_count: int,
        moderate_count: int,
        unhealthy_count: int,
        recent_items_str: str,
        days_range: int,
    ) -> Optional[list]:
        """
        Health coach: analyze eating trends and generate 3 personalized insights.
        """
        prompt = f"""You are a friendly, expert nutritionist AI health coach. Analyze this user's eating data and provide exactly 3 personalized, specific, actionable insights.

USER'S EATING DATA (last {days_range} days):
- Total items logged: {total_items}
- Healthy items (score 67-100): {healthy_count}
- Moderate items (score 34-66): {moderate_count}
- Unhealthy items (score 0-33): {unhealthy_count}

RECENT ITEMS:
{recent_items_str}

SCORING SYSTEM:
- Score 67-100 = Healthy (green)
- Score 34-66 = Moderate (yellow)
- Score 0-33 = Unhealthy (red)
- Higher scores are better

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

        response = self.generate(
            prompt=prompt,
            temperature=0.7,
            max_tokens=800,
        )

        if not response:
            return None

        return self._parse_json_array(response)

    def generate_meal_plan(
        self,
        total: int,
        healthy_pct: float,
        unhealthy_pct: float,
        items_str: str,
    ) -> Optional[dict]:
        """
        Meal planner: generate a personalized 7-day meal plan.
        """
        prompt = f"""You are an expert nutritionist AI. Generate a personalized 7-day meal plan for this user.

USER PROFILE:
- Total items logged: {total}
- Healthy choices: {healthy_pct}%
- Unhealthy choices: {unhealthy_pct}%

ITEMS THEY'VE CONSUMED RECENTLY:
{items_str}

SCORING SYSTEM (Health Score 0-100):
- 67-100 = Healthy (green)
- 34-66 = Moderate (yellow)
- 0-33 = Unhealthy (red)
- Higher is better

RULES:
1. Generate 3 meals per day (Breakfast, Lunch, Dinner) for 7 days
2. Incorporate foods they already enjoy (when healthy)
3. Suggest healthier alternatives to their unhealthy choices
4. Keep estimated scores realistic (don't make everything 100)
5. Include variety - don't repeat the same meal
6. Make meals practical and easy to prepare
7. Use common grocery items

Return ONLY valid JSON, no other text:
{{
  "Monday": [
    {{"meal": "Breakfast", "name": "Meal description", "estimated_score": 75}},
    {{"meal": "Lunch", "name": "Meal description", "estimated_score": 70}},
    {{"meal": "Dinner", "name": "Meal description", "estimated_score": 80}}
  ],
  "Tuesday": [...],
  "Wednesday": [...],
  "Thursday": [...],
  "Friday": [...],
  "Saturday": [...],
  "Sunday": [...]
}}"""

        response = self.generate(
            prompt=prompt,
            temperature=0.8,
            max_tokens=2500,
        )

        if not response:
            return None

        return self._parse_json_object(response)

    def generate_daily_recipes(self, day_of_week: str, day_of_year: int, week_number: int) -> Optional[list]:
        """
        Recipe generator: generate 5 unique healthy recipes for the day.
        """
        prompt = f"""You are a healthy recipe curator. Today is {day_of_week}, day {day_of_year} of the year, week {week_number}.

Generate exactly 5 unique, healthy food recipes for today. These should be real, practical recipes.

RULES:
1. Each recipe must be DIFFERENT - no repeating ingredients or themes
2. Mix cuisines: include at least 3 different cuisine types (Mediterranean, Asian, Mexican, Indian, etc.)
3. Mix meal types: include breakfast, lunch, dinner, snack, and dessert options
4. All recipes should be genuinely healthy (low sugar, high fiber/protein, whole ingredients)
5. Use the day number ({day_of_year}) as a seed - generate DIFFERENT recipes than you would for day {day_of_year - 1} or {day_of_year + 1}
6. Include estimated prep time
7. Keep recipe names concise (max 6 words)

Return ONLY valid JSON array, no other text:
[
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Breakfast", "prep_time": "15 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}},
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Lunch", "prep_time": "20 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}},
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Dinner", "prep_time": "30 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}},
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Snack", "prep_time": "10 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}},
  {{"name": "Recipe Name", "cuisine": "Cuisine Type", "meal_type": "Dessert", "prep_time": "15 min", "description": "One sentence description", "key_ingredients": "3-4 main ingredients"}}
]"""

        response = self.generate(
            prompt=prompt,
            temperature=0.9,
            max_tokens=1000,
        )

        if not response:
            return None

        result = self._parse_json_array(response)
        return result[:5] if result else None

    # --- JSON parsing helpers ---

    def _parse_json_array(self, text: str) -> Optional[list]:
        """Extract and parse a JSON array from LLM response text."""
        try:
            # Try direct parse first
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON array in text
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        print(f"[LocalLLM] Failed to parse JSON array from: {text[:200]}")
        return None

    def _parse_json_object(self, text: str) -> Optional[dict]:
        """Extract and parse a JSON object from LLM response text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        print(f"[LocalLLM] Failed to parse JSON object from: {text[:200]}")
        return None


# --- Singleton instance ---
_llm_instance = None


def get_local_llm() -> LocalLLM:
    """Get or create the singleton LocalLLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LocalLLM()
    return _llm_instance
