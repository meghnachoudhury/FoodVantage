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
    con = duckdb.connect('data/vantage_core.db', read_only=False)
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username VARCHAR PRIMARY KEY,
            password_hash VARCHAR
        )
    """)
    
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_cal_id;
        CREATE TABLE IF NOT EXISTS calendar (
            id INTEGER DEFAULT nextval('seq_cal_id'),
            username VARCHAR,
            date DATE,
            item_name VARCHAR,
            score INTEGER,
            category VARCHAR,
            checked BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)
    return con

def create_user(username, password):
    con = get_db_connection()
    exists = con.execute("SELECT * FROM users WHERE username = ?", [username]).fetchone()
    if exists: return False
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    con.execute("INSERT INTO users VALUES (?, ?)", [username, pwd_hash])
    return True

def authenticate_user(username, password):
    con = get_db_connection()
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    result = con.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", [username, pwd_hash]).fetchone()
    return result is not None

# --- 2. DATA MANAGEMENT ---
def add_calendar_item_db(username, date_str, item_name, score):
    con = get_db_connection()
    # Logic: Score < 3 (Green/Healthy), > 7 (Red/Unhealthy) based on Rayner Scale 0-10
    if score < 3.0: category = 'healthy'
    elif score < 7.0: category = 'moderate' 
    else: category = 'unhealthy'
    
    con.execute("INSERT INTO calendar (username, date, item_name, score, category, checked) VALUES (?, ?, ?, ?, ?, ?)", 
                [username, date_str, item_name, score, category, False])

def get_calendar_items_db(username, date_str):
    con = get_db_connection()
    return con.execute("""
        SELECT id, item_name, score, category, checked 
        FROM calendar 
        WHERE username = ? AND date = ?
    """, [username, date_str]).fetchall()

def delete_item_db(item_id):
    con = get_db_connection()
    con.execute("DELETE FROM calendar WHERE id = ?", [item_id])

def get_log_history_db(username):
    con = get_db_connection()
    return con.execute("""
        SELECT date, item_name, score, category 
        FROM calendar 
        WHERE username = ? 
        ORDER BY date DESC
    """, [username]).fetchall()

def get_trend_data_db(username, days=7):
    """SAFE Function: Returns [] if no data, never None."""
    con = get_db_connection()
    try:
        data = con.execute("""
            SELECT date, category, COUNT(*) as count
            FROM calendar
            WHERE username = ? 
            AND date >= current_date - INTERVAL ? DAY
            GROUP BY date, category
            ORDER BY date ASC
        """, [username, days]).fetchall()
        return data if data else []
    except Exception:
        return []

# --- 3. GEMINI AI ---
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