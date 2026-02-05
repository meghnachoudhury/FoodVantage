import duckdb
import os
import streamlit as st
import hashlib
from google import genai
from dotenv import load_dotenv

load_dotenv()

# --- 1. SETUP & AUTHENTICATION ---
@st.cache_resource
def get_db_connection():
    """Connects to DB and creates secure tables if they don't exist."""
    # Connects to a persistent file 'vantage_core.db'
    con = duckdb.connect('data/vantage_core.db', read_only=False)
    
    # 1. Users Table (Secure Access)
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username VARCHAR PRIMARY KEY,
            password_hash VARCHAR
        )
    """)
    
    # 2. Calendar/Log Table (Persistent Data)
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_cal_id;
        CREATE TABLE IF NOT EXISTS calendar (
            id INTEGER DEFAULT nextval('seq_cal_id'),
            username VARCHAR,
            date DATE,
            item_name VARCHAR,
            score INTEGER,
            category VARCHAR, -- 'healthy', 'moderate', 'unhealthy'
            checked BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)
    return con

def create_user(username, password):
    """Registers a new user securely."""
    con = get_db_connection()
    exists = con.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
    if exists: return False
    
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    con.execute("INSERT INTO users VALUES (?, ?)", [username, pwd_hash])
    return True

def authenticate_user(username, password):
    """Verifies login credentials."""
    con = get_db_connection()
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    result = con.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", [username, pwd_hash]).fetchone()
    return result is not None

# --- 2. DATA MANAGEMENT FUNCTIONS ---
def add_calendar_item_db(username, date_str, item_name, score):
    """Saves a grocery item to the DB."""
    con = get_db_connection()
    # Auto-determine category based on score
    category = 'healthy' if score >= 70 else 'moderate' if score >= 40 else 'unhealthy'
    con.execute("INSERT INTO calendar (username, date, item_name, score, category, checked) VALUES (?, ?, ?, ?, ?, ?)", 
                [username, date_str, item_name, score, category, False])

def get_calendar_items_db(username, date_str):
    """Fetches items for a specific user and date."""
    con = get_db_connection()
    return con.execute("""
        SELECT id, item_name, score, category, checked 
        FROM calendar 
        WHERE username = ? AND date = ?
    """, [username, date_str]).fetchall()

def delete_item_db(item_id):
    """Removes an item."""
    con = get_db_connection()
    con.execute("DELETE FROM calendar WHERE id = ?", [item_id])

def get_log_history_db(username):
    """Fetches ALL history for the Log page, grouped by date."""
    con = get_db_connection()
    # Get recent 30 days
    data = con.execute("""
        SELECT date, item_name, score, category 
        FROM calendar 
        WHERE username = ? 
        ORDER BY date DESC
    """, [username]).fetchall()
    return data

# --- 3. GEMINI 3 VISION & ANALYSIS ---
# Initialize Gemini Client
api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def analyze_label_with_gemini(image):
    prompt = """
    Identify this food product and extract its core ingredient list.
    Focus on hidden sugars and high-GI starches.
    Return a Markdown summary with the 3 most concerning ingredients.
    """
    try:
        response = client.models.generate_content(
            model="gemini-3-flash", 
            contents=[prompt, image]
        )
        return response.text
    except Exception as e:
        return f"Gemini Error: {str(e)}"