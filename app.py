import streamlit as st
import streamlit.components.v1 as components
import sys
import os
import base64
import pandas as pd
import hashlib
import calendar as cal_module
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from gemini_api import (
    calculate_vms_science, get_scientific_db,
    search_vantage_db, search_open_food_facts, vision_live_scan_dark,
    generate_health_insights, generate_meal_plan, generate_daily_recipes,
    get_db_connection, get_trend_data_db, get_all_calendar_data_db,
    get_gemini_api_key, authenticate_user,
    add_calendar_item_db, get_calendar_items_db, delete_item_db,
    get_log_history_db, create_user, user_exists, reset_password,
    change_password, delete_account,
    vms_to_health_score, calculate_overall_health_score, calculate_day_streak,
    get_total_items_logged, get_items_today,
    get_user_allergies, save_user_allergies, check_item_allergies, ALLERGY_KEYWORDS
)
try:
    from streamlit_back_camera_input import back_camera_input
except ImportError:
    back_camera_input = None

st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")

# --- SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_id' not in st.session_state: st.session_state.user_id = None
# Migration guard: old sessions had logged_in=True with user_id="demo_user".
# Force those sessions back to the login screen.
if st.session_state.get('user_id') == 'demo_user':
    st.session_state.logged_in = False
    st.session_state.user_id = None
if 'auth_tab' not in st.session_state: st.session_state.auth_tab = 'login'   # login | signup | forgot
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'selected_result' not in st.session_state: st.session_state.selected_result = None
if 'scanning' not in st.session_state: st.session_state.scanning = False
if 'scan_count' not in st.session_state: st.session_state.scan_count = 0
if 'trends_view' not in st.session_state: st.session_state.trends_view = 'weekly'
if 'scan_status' not in st.session_state: st.session_state.scan_status = None
if 'detected_items' not in st.session_state: st.session_state.detected_items = []
if '_captured_image' not in st.session_state: st.session_state._captured_image = None
if 'scan_error' not in st.session_state: st.session_state.scan_error = None
if 'ai_insights' not in st.session_state: st.session_state.ai_insights = None
if 'meal_plan' not in st.session_state: st.session_state.meal_plan = None
if 'daily_recipes' not in st.session_state: st.session_state.daily_recipes = None
if 'recipes_date' not in st.session_state: st.session_state.recipes_date = None
if 'user_allergies' not in st.session_state: st.session_state.user_allergies = None
if 'allergy_popup_open' not in st.session_state: st.session_state.allergy_popup_open = False
if '_loading_insights' not in st.session_state: st.session_state._loading_insights = False
if '_loading_recipes' not in st.session_state: st.session_state._loading_recipes = False
if '_loading_meal_plan' not in st.session_state: st.session_state._loading_meal_plan = False
if 'cal_date' not in st.session_state: st.session_state.cal_date = datetime.now().date()
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month


# --- DARK THEME COLOR PALETTE ---
C = {
    'bg': '#101014',
    'bg_card': '#17171d',
    'bg_elevated': '#242430',
    'bg_input': '#1e1e2a',
    'sidebar_bg': '#131318',
    'teal': '#eea4b7',
    'teal_light': '#f5c5d4',
    'olive': '#7c9e38',
    'text': '#E8EAF0',
    'text_sec': '#a0a0b4',
    'text_muted': '#9090b0',
    'green': '#4CAF50',
    'yellow': '#F9A825',
    'red': '#E53935',
    'orange': '#E8967A',
    'border': '#2A2E38',
    'streak_bg': '#1e1e28',
}

# Helper: portion size label
def needs_portion_size(item_name):
    item_lower = item_name.lower()
    cooked_keywords = [
        'cooked', 'grilled', 'fried', 'baked', 'roasted', 'steamed',
        'boiled', 'sauteed', 'plate', 'meal', 'dish', 'curry', 'stew',
        'soup', 'salad', 'pasta', 'rice', 'noodle', 'stir fry', 'pizza',
        'burger', 'sandwich', 'wrap', 'taco', 'burrito', 'bowl'
    ]
    fresh_keywords = [
        'apple', 'banana', 'orange', 'grape', 'strawberry', 'avocado',
        'tomato', 'cucumber', 'carrot', 'lettuce', 'spinach', 'kale',
        'berry', 'peach', 'pear', 'plum', 'mango', 'melon', 'lemon',
        'lime', 'onion', 'garlic', 'pepper', 'broccoli', 'cauliflower',
        'fresh', 'whole', 'raw', 'fruit', 'vegetable'
    ]
    superfood_keywords = [
        'superfood', 'chia', 'flax', 'hemp', 'spirulina', 'acai',
        'goji', 'matcha', 'turmeric', 'ginger'
    ]
    for keyword in cooked_keywords + fresh_keywords + superfood_keywords:
        if keyword in item_lower:
            return False
    return True

def score_color(score, mode='vms'):
    """Return color based on score. mode='vms' for VMS scale, mode='health' for 0-100 scale."""
    if mode == 'health':
        if score >= 70: return C['green']
        if score >= 30: return C['yellow']
        return C['red']
    else:
        if score < 3.0: return C['green']
        if score < 7.0: return C['yellow']
        return C['red']

def vms_to_display_score(vms_score):
    """Convert VMS score (-2 to 10) to a 0-10 user-facing scale where 10 = healthiest."""
    return round(vms_to_health_score(vms_score) / 10, 1)

# --- CSS (Dark Theme) ---
st.markdown('<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">', unsafe_allow_html=True)
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">', unsafe_allow_html=True)
st.markdown(f"""
    <style>
    /* === GLOBAL === */
    .stApp {{
        background-color: {C['bg']};
        color: {C['text']};
        font-family: 'Inter', sans-serif;
    }}
    .stApp::before {{ display: none; }}

    h1, h2, h3, h4, h5, h6, p, div, label {{
        font-family: 'Inter', sans-serif !important;
        color: {C['text']};
    }}

    .stMarkdown {{ color: {C['text']}; }}

    /* === SIDEBAR === */
    section[data-testid="stSidebar"] {{
        background-color: {C['sidebar_bg']} !important;
        border-right: 1px solid {C['border']} !important;
    }}
    section[data-testid="stSidebar"] * {{
        color: {C['text']} !important;
    }}
    /* === INPUTS === */
    input[type="text"], input[type="password"], input[type="number"] {{
        background-color: {C['bg_input']} !important;
        color: {C['text']} !important;
        border: 1px solid {C['border']} !important;
        border-radius: 12px !important;
        padding: 10px 14px !important;
        font-family: 'Inter', sans-serif !important;
    }}
    input[type="text"]:focus {{
        border-color: {C['teal']} !important;
        box-shadow: 0 0 0 2px rgba(238,164,183,0.2) !important;
    }}
    .stTextInput > div > div > input {{
        background-color: {C['bg_input']} !important;
        color: {C['text']} !important;
        -webkit-text-fill-color: {C['text']} !important;
    }}
    .stTextInput label {{
        color: {C['text_sec']} !important;
    }}

    /* Date input */
    .stDateInput > div > div > input {{
        background-color: {C['bg_input']} !important;
        color: {C['text']} !important;
        border: 1px solid {C['border']} !important;
        border-radius: 12px !important;
    }}

    /* === BUTTONS === */
    .stButton > button {{
        background: rgba(238,164,183,0.07) !important;
        color: {C['teal_light']} !important;
        border: 1px solid rgba(238,164,183,0.25) !important;
        border-radius: 12px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.5rem !important;
        transition: all 0.2s ease !important;
        letter-spacing: 0.1px;
        box-shadow: 0 0 8px rgba(238,164,183,0.08) !important;
        backdrop-filter: blur(4px);
    }}
    .stButton > button:hover {{
        background: rgba(238,164,183,0.14) !important;
        border-color: rgba(238,164,183,0.5) !important;
        box-shadow: 0 0 16px rgba(238,164,183,0.22) !important;
        transform: translateY(-1px) !important;
        color: white !important;
    }}
    .stButton > button[kind="secondary"] {{
        background: rgba(36,36,48,0.45) !important;
        border: 1px solid rgba(238,164,183,0.15) !important;
        color: {C['text_sec']} !important;
    }}

    .stHorizontalBlock div[data-testid="column"] .stButton > button {{
        border-radius: 12px !important;
    }}
    /* === METRICS === */
    [data-testid="stMetricValue"] {{
        color: {C['text']} !important;
        font-weight: 700 !important;
    }}
    [data-testid="stMetricLabel"] {{
        color: {C['teal']} !important;
    }}

    /* === EXPANDERS === */
    .stExpander {{
        background: {C['bg_card']} !important;
        border: 1px solid {C['border']} !important;
        border-radius: 14px !important;
    }}
    .stExpander p, .stExpander div, .stExpander span {{
        color: {C['text']} !important;
    }}

    /* === CARDS === */
    .card {{
        background: {C['bg_card']};
        padding: 20px;
        border-radius: 16px;
        border: 1px solid {C['border']};
        margin-bottom: 16px;
    }}

    /* === HUD BUBBLE === */
    .hud-bubble {{
        position: fixed;
        top: calc(50% - 200px);
        left: 50%;
        transform: translateX(-50%);
        background: {C['bg_card']};
        padding: 16px 28px;
        border-radius: 50px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.4);
        border: 2px solid {C['teal']};
        z-index: 1000;
        text-align: center;
        min-width: 220px;
    }}

    /* === LIST ROWS === */
    .list-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px 16px;
        background: {C['bg_card']};
        border-radius: 14px;
        border: 1px solid {C['border']};
        margin-bottom: 8px;
    }}

    /* === SCROLLABLE RESULTS === */
    .results-scroll-container {{
        max-height: 400px;
        overflow-y: auto;
        padding-right: 8px;
    }}
    .results-scroll-container::-webkit-scrollbar {{ width: 6px; }}
    .results-scroll-container::-webkit-scrollbar-track {{ background: {C['bg']}; border-radius: 10px; }}
    .results-scroll-container::-webkit-scrollbar-thumb {{ background: {C['teal']}; border-radius: 10px; }}

    /* === SCANNER VIEWFINDER === */
    /* Sequential corner jitter: TL → TR → BL → BR, one at a time, 5s cycle */
    @keyframes jitter-tl {{
        0%   {{ transform: translate(0,0);       opacity: 0.4; }}
        5%   {{ transform: translate(-5px,-5px); opacity: 1;   }}
        10%  {{ transform: translate(-3px,-3px); opacity: 1;   }}
        15%  {{ transform: translate(-5px,-5px); opacity: 1;   }}
        20%  {{ transform: translate(0,0);       opacity: 0.4; }}
        100% {{ transform: translate(0,0);       opacity: 0.4; }}
    }}
    @keyframes jitter-tr {{
        0%,  25% {{ transform: translate(0,0);      opacity: 0.4; }}
        30%  {{ transform: translate(5px,-5px);  opacity: 1;   }}
        35%  {{ transform: translate(3px,-3px);  opacity: 1;   }}
        40%  {{ transform: translate(5px,-5px);  opacity: 1;   }}
        45%  {{ transform: translate(0,0);       opacity: 0.4; }}
        100% {{ transform: translate(0,0);       opacity: 0.4; }}
    }}
    @keyframes jitter-bl {{
        0%,  50% {{ transform: translate(0,0);      opacity: 0.4; }}
        55%  {{ transform: translate(-5px,5px);  opacity: 1;   }}
        60%  {{ transform: translate(-3px,3px);  opacity: 1;   }}
        65%  {{ transform: translate(-5px,5px);  opacity: 1;   }}
        70%  {{ transform: translate(0,0);       opacity: 0.4; }}
        100% {{ transform: translate(0,0);       opacity: 0.4; }}
    }}
    @keyframes jitter-br {{
        0%,  75% {{ transform: translate(0,0);     opacity: 0.4; }}
        80%  {{ transform: translate(5px,5px);  opacity: 1;   }}
        85%  {{ transform: translate(3px,3px);  opacity: 1;   }}
        90%  {{ transform: translate(5px,5px);  opacity: 1;   }}
        95%  {{ transform: translate(0,0);      opacity: 0.4; }}
        100% {{ transform: translate(0,0);      opacity: 0.4; }}
    }}
    .scanner-viewfinder {{
        background: {C['bg_card']};
        border-radius: 20px;
        position: relative;
        height: 320px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        margin: 20px auto;
        max-width: 500px;
        overflow: hidden;
    }}
    .scanner-corner {{
        position: absolute;
        width: 45px;
        height: 45px;
        border-color: {C['teal']};
        border-style: solid;
    }}
    .corner-tl {{ top: 28px; left: 28px; border-width: 3px 0 0 3px; border-radius: 6px 0 0 0;
                  animation: jitter-tl 5s ease-in-out infinite; }}
    .corner-tr {{ top: 28px; right: 28px; border-width: 3px 3px 0 0; border-radius: 0 6px 0 0;
                  animation: jitter-tr 5s ease-in-out infinite; }}
    .corner-bl {{ bottom: 28px; left: 28px; border-width: 0 0 3px 3px; border-radius: 0 0 0 6px;
                  animation: jitter-bl 5s ease-in-out infinite; }}
    .corner-br {{ bottom: 28px; right: 28px; border-width: 0 3px 3px 0; border-radius: 0 0 6px 0;
                  animation: jitter-br 5s ease-in-out infinite; }}
    .scanner-icon {{
        width: 64px; height: 64px;
        border-radius: 50%;
        background: rgba(238,164,183,0.15);
        display: flex; align-items: center; justify-content: center;
        margin-bottom: 16px;
    }}
    .scanner-icon i {{ font-size: 28px; color: {C['teal']}; }}

    /* === STAT CARDS === */
    .stat-cards {{
        display: flex;
        gap: 16px;
        margin: 20px 0;
    }}
    .stat-card {{
        flex: 1;
        background: {C['bg_card']};
        border: 1px solid {C['border']};
        border-radius: 16px;
        padding: 20px;
        position: relative;
    }}
    .stat-label {{
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 1.2px;
        color: {C['teal']};
        text-transform: uppercase;
        margin-bottom: 8px;
    }}
    .stat-value {{
        font-size: 1.8rem;
        font-weight: 800;
        color: {C['text']};
        line-height: 1;
    }}
    .stat-unit {{
        font-size: 0.85rem;
        font-weight: 500;
        color: {C['text_sec']};
    }}
    .stat-sub {{
        font-size: 0.75rem;
        color: {C['text_muted']};
        margin-top: 4px;
    }}

    /* === STREAK CARD (Sidebar) === */
    .streak-card {{
        background: {C['streak_bg']};
        border: 1px solid {C['border']};
        border-radius: 14px;
        padding: 16px;
        margin-top: 20px;
    }}
    .streak-header {{
        font-size: 1rem;
        font-weight: 700;
        color: {C['teal']};
        margin-bottom: 2px;
    }}
    .streak-sub {{
        font-size: 0.75rem;
        color: {C['text_muted']};
        margin-bottom: 10px;
    }}
    .streak-bar-bg {{
        background: {C['bg']};
        border-radius: 6px;
        height: 8px;
        overflow: hidden;
        margin-bottom: 6px;
    }}
    .streak-bar-fill {{
        background: linear-gradient(90deg, {C['orange']}, {C['teal']});
        height: 100%;
        border-radius: 6px;
        transition: width 0.5s ease;
    }}
    .streak-milestone {{
        font-size: 0.7rem;
        color: {C['text_muted']};
        margin-bottom: 12px;
    }}
    .streak-stats {{
        display: flex;
        gap: 8px;
    }}
    .streak-stat {{
        flex: 1;
        background: {C['bg']};
        border-radius: 10px;
        padding: 10px;
        text-align: center;
    }}
    .streak-stat-val {{
        font-size: 1.1rem;
        font-weight: 800;
        color: {C['teal']};
    }}
    .streak-stat-label {{
        font-size: 0.65rem;
        color: {C['text_muted']};
        margin-top: 2px;
    }}

    /* === TREND TABS (compact in right column) === */
    .trend-tabs-compact .stButton > button {{
        background: rgba(36,36,48,0.35) !important;
        border: 1px solid rgba(238,164,183,0.15) !important;
        border-radius: 8px !important;
        font-size: 0.8rem !important;
        padding: 0.3rem 0.6rem !important;
        color: {C['text_muted']} !important;
    }}
    .trend-tabs-compact .stButton > button[kind="primary"] {{
        background: rgba(238,164,183,0.1) !important;
        border: 1px solid rgba(238,164,183,0.45) !important;
        border-radius: 8px !important;
        color: {C['teal_light']} !important;
        box-shadow: 0 0 10px rgba(238,164,183,0.2) !important;
        min-height: 44px;
    }}

    /* === SCANNER RESULTS === */
    .scanner-result {{
        background: {C['bg_card']};
        padding: 14px;
        border-radius: 14px;
        margin: 10px 0;
        border-left: 3px solid {C['teal']};
    }}
    .scanner-result-title {{
        color: {C['text']};
        font-weight: 700;
        font-size: 1rem;
        margin-bottom: 6px;
    }}
    .scanner-result-text {{
        color: {C['text_sec']};
        font-weight: 500;
        font-size: 0.95rem;
    }}

    /* === FRIENDLY ERRORS === */
    .friendly-error {{
        background: {C['bg_card']};
        border-left: 3px solid {C['teal']};
        padding: 14px;
        border-radius: 12px;
        margin: 10px 0;
    }}
    .friendly-error-title {{ font-weight: 700; color: {C['teal']}; margin-bottom: 6px; }}
    .friendly-error-text {{ color: {C['text_sec']}; font-size: 0.85rem; }}

    /* Nav buttons in sidebar */
    .nav-btn {{
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 14px;
        border-radius: 10px;
        cursor: pointer;
        margin-bottom: 4px;
        font-size: 0.9rem;
        font-weight: 500;
        color: {C['text_sec']};
        transition: all 0.15s ease;
        text-decoration: none;
    }}
    .nav-btn:hover {{ background: rgba(238,164,183,0.1); color: {C['text']}; }}
    .nav-btn.active {{
        background: rgba(238,164,183,0.15);
        color: {C['teal_light']};
        font-weight: 600;
    }}
    .nav-btn i {{ width: 20px; text-align: center; font-size: 0.95rem; }}

    /* === INFO / WARNING / SUCCESS overrides === */
    .stAlert {{
        background: {C['bg_card']} !important;
        border: 1px solid {C['border']} !important;
        border-radius: 12px !important;
    }}
    .stAlert p {{ color: {C['text_sec']} !important; }}

    /* Hide Streamlit branding — do NOT hide stToolbar, the sidebar toggle lives inside it in Streamlit 1.50 */
    #MainMenu {{ display: none !important; }}
    footer {{ display: none !important; }}
    [data-testid="stDecoration"] {{ display: none !important; }}
    [data-testid="stStatusWidget"] {{ display: none !important; }}

    /* === SIDEBAR NAV BUTTONS === */
    .sidebar-nav .stButton > button {{
        background: transparent !important;
        border: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 10px 14px !important;
        color: {C['text_sec']} !important;
        font-weight: 500 !important;
        border-radius: 10px !important;
        font-size: 0.9rem !important;
        margin-bottom: 2px !important;
        box-shadow: none !important;
        letter-spacing: 0 !important;
    }}
    .sidebar-nav .stButton > button:hover {{
        background: rgba(238,164,183,0.1) !important;
        color: {C['text']} !important;
        transform: none !important;
        box-shadow: none !important;
    }}
    .sidebar-nav .stButton > button[kind="primary"] {{
        background: rgba(238,164,183,0.08) !important;
        border: 1px solid rgba(238,164,183,0.4) !important;
        color: {C['teal_light']} !important;
        font-weight: 600 !important;
        box-shadow: 0 0 12px rgba(238,164,183,0.18) !important;
    }}

    /* === AI LOADING INDICATOR === */
    @keyframes loading-pulse {{
        0%, 100% {{ opacity: 0.5; }}
        50% {{ opacity: 1; }}
    }}
    .ai-loading {{
        text-align: center;
        padding: 20px;
        animation: loading-pulse 1.5s ease-in-out infinite;
    }}
    .ai-loading-text {{
        font-size: 0.95rem;
        font-weight: 600;
        color: {C['teal']};
    }}
    .ai-loading-sub {{
        font-size: 0.75rem;
        color: {C['text_muted']};
        margin-top: 4px;
    }}

    /* === ALLERGY ALERT === */
    .allergy-alert {{
        background: rgba(229,57,53,0.1);
        border: 1px solid rgba(229,57,53,0.3);
        border-radius: 10px;
        padding: 10px 14px;
        margin-top: 8px;
        margin-bottom: 4px;
    }}
    .allergy-alert-title {{
        font-weight: 700;
        font-size: 0.8rem;
        color: {C['red']};
    }}
    .allergy-alert-text {{
        font-size: 0.75rem;
        color: {C['text_sec']};
        margin-top: 2px;
    }}

    /* === BLINKING DOT IN LOGO === */
    @keyframes blink-dot {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0; }}
    }}
    .logo-dot-blink {{
        animation: blink-dot 1.1s ease-in-out infinite;
        display: inline-block;
    }}

    /* === AUTH PAGE === */
    .auth-card {{
        background: {C['bg_card']};
        border: 1px solid {C['border']};
        border-radius: 20px;
        padding: 36px 32px;
        max-width: 420px;
        margin: 0 auto;
    }}
    .auth-tab-btn {{
        flex: 1;
        padding: 10px;
        border-radius: 10px;
        border: none;
        cursor: pointer;
        font-family: 'Inter', sans-serif;
        font-size: 0.9rem;
        font-weight: 600;
        transition: all 0.2s;
    }}
    .auth-tab-active {{
        background: {C['teal']};
        color: white;
    }}
    .auth-tab-inactive {{
        background: transparent;
        color: {C['text_muted']};
    }}

    /* === OLIVE SCAN BUTTONS === */
    .olive-btn .stButton > button {{
        background: linear-gradient(135deg, {C['olive']} 0%, #5a7a28 100%) !important;
    }}
    .olive-btn .stButton > button:hover {{
        box-shadow: 0 4px 16px rgba(124,158,56,0.35) !important;
    }}
    </style>
""", unsafe_allow_html=True)

# --- Botanical Corner Illustrations ---
st.markdown(f"""
<div style="position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;overflow:hidden;">

  <!-- TOP-RIGHT corner botanical cluster -->
  <div style="position:absolute;top:0;right:0;width:240px;height:240px;opacity:0.28;">
    <svg viewBox="0 0 240 240" width="240" height="240" xmlns="http://www.w3.org/2000/svg">
      <!-- Large back leaf -->
      <path d="M228,8 C210,38 188,85 178,135 C168,178 172,208 178,235
               C186,205 190,172 198,128 C212,76 226,32 228,8 Z"
            fill="#7c9e38" opacity="0.55"/>
      <!-- Medium centre leaf -->
      <path d="M240,28 C218,58 194,108 182,158 C170,200 174,228 181,240
               C190,225 192,195 201,150 C217,97 237,52 240,28 Z"
            fill="#7c9e38" opacity="0.65"/>
      <!-- Slim front leaf -->
      <path d="M210,0 C204,22 200,58 198,94 C196,130 198,158 202,182
               C204,156 207,127 210,90 C215,54 216,22 210,0 Z"
            fill="#96b348" opacity="0.45"/>
      <!-- Horizontal accent leaf -->
      <path d="M240,96 C210,90 175,92 148,110
               C175,116 210,114 240,96 Z"
            fill="#7c9e38" opacity="0.40"/>
      <!-- Stem line -->
      <path d="M230,230 Q195,165 162,108" stroke="#7c9e38" stroke-width="1.8" fill="none" opacity="0.45"/>
      <!-- Pink accent dots -->
      <circle cx="162" cy="126" r="5.5" fill="{C['teal']}" opacity="0.55"/>
      <circle cx="178" cy="155" r="4"   fill="{C['teal']}" opacity="0.50"/>
      <circle cx="150" cy="142" r="3"   fill="{C['teal']}" opacity="0.45"/>
      <circle cx="182" cy="174" r="4.5" fill="{C['teal_light']}" opacity="0.42"/>
      <!-- Olive dots -->
      <circle cx="144" cy="110" r="3.5" fill="#7c9e38" opacity="0.45"/>
      <circle cx="166" cy="98"  r="2.5" fill="#7c9e38" opacity="0.38"/>
    </svg>
  </div>

  <!-- BOTTOM-LEFT corner botanical cluster (mirror of top-right) -->
  <div style="position:absolute;bottom:0;left:0;width:240px;height:240px;opacity:0.28;transform:rotate(180deg);">
    <svg viewBox="0 0 240 240" width="240" height="240" xmlns="http://www.w3.org/2000/svg">
      <path d="M228,8 C210,38 188,85 178,135 C168,178 172,208 178,235
               C186,205 190,172 198,128 C212,76 226,32 228,8 Z"
            fill="#7c9e38" opacity="0.55"/>
      <path d="M240,28 C218,58 194,108 182,158 C170,200 174,228 181,240
               C190,225 192,195 201,150 C217,97 237,52 240,28 Z"
            fill="#7c9e38" opacity="0.65"/>
      <path d="M210,0 C204,22 200,58 198,94 C196,130 198,158 202,182
               C204,156 207,127 210,90 C215,54 216,22 210,0 Z"
            fill="#96b348" opacity="0.45"/>
      <path d="M240,96 C210,90 175,92 148,110
               C175,116 210,114 240,96 Z"
            fill="#7c9e38" opacity="0.40"/>
      <path d="M230,230 Q195,165 162,108" stroke="#7c9e38" stroke-width="1.8" fill="none" opacity="0.45"/>
      <circle cx="162" cy="126" r="5.5" fill="{C['teal']}" opacity="0.55"/>
      <circle cx="178" cy="155" r="4"   fill="{C['teal']}" opacity="0.50"/>
      <circle cx="150" cy="142" r="3"   fill="{C['teal']}" opacity="0.45"/>
      <circle cx="182" cy="174" r="4.5" fill="{C['teal_light']}" opacity="0.42"/>
      <circle cx="144" cy="110" r="3.5" fill="#7c9e38" opacity="0.45"/>
      <circle cx="166" cy="98"  r="2.5" fill="#7c9e38" opacity="0.38"/>
    </svg>
  </div>

  <!-- TOP-LEFT corner small accent -->
  <div style="position:absolute;top:0;left:0;width:160px;height:160px;opacity:0.16;transform:scaleX(-1);">
    <svg viewBox="0 0 240 240" width="160" height="160" xmlns="http://www.w3.org/2000/svg">
      <path d="M228,8 C210,38 188,85 178,135 C168,178 172,208 178,235
               C186,205 190,172 198,128 C212,76 226,32 228,8 Z"
            fill="#7c9e38" opacity="0.7"/>
      <path d="M210,0 C204,22 200,58 198,94 C196,130 198,158 202,182
               C204,156 207,127 210,90 C215,54 216,22 210,0 Z"
            fill="#96b348" opacity="0.55"/>
      <circle cx="162" cy="126" r="5" fill="{C['teal']}" opacity="0.55"/>
      <circle cx="150" cy="108" r="3" fill="{C['teal']}" opacity="0.45"/>
    </svg>
  </div>

  <!-- BOTTOM-RIGHT corner small accent -->
  <div style="position:absolute;bottom:0;right:0;width:160px;height:160px;opacity:0.16;transform:rotate(180deg) scaleX(-1);">
    <svg viewBox="0 0 240 240" width="160" height="160" xmlns="http://www.w3.org/2000/svg">
      <path d="M228,8 C210,38 188,85 178,135 C168,178 172,208 178,235
               C186,205 190,172 198,128 C212,76 226,32 228,8 Z"
            fill="#7c9e38" opacity="0.7"/>
      <path d="M210,0 C204,22 200,58 198,94 C196,130 198,158 202,182
               C204,156 207,127 210,90 C215,54 216,22 210,0 Z"
            fill="#96b348" opacity="0.55"/>
      <circle cx="162" cy="126" r="5" fill="{C['teal']}" opacity="0.55"/>
      <circle cx="150" cy="108" r="3" fill="{C['teal']}" opacity="0.45"/>
    </svg>
  </div>

</div>
""", unsafe_allow_html=True)

def render_logo(size="1.6rem"):
    st.markdown(f"""<div style='margin-bottom: 6px;'>
        <span style='font-size: {size}; font-weight: 800; color: {C["text"]};'>foodvantage</span><span class='logo-dot-blink' style='font-size: {size}; font-weight: 800; color: {C["teal"]};'>.</span>
    </div>""", unsafe_allow_html=True)

def create_html_calendar(year, month, selected_day=None, logged_days=None):
    """Returns inner HTML for embedding inside a components.html() iframe.
    onclick='pickDate(N)' passes the integer day to JS in that iframe."""
    logged_days = logged_days or set()
    cal = cal_module.monthcalendar(year, month)
    month_name = cal_module.month_name[month]
    html = f"<div style='text-align:center; font-weight:700; font-size:0.95rem; color:{C['text']}; margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid {C['border']};'>{month_name} {year}</div>"
    html += "<table style='width:100%; text-align:center; border-collapse:separate; border-spacing:2px;'><thead><tr>"
    for day in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]:
        html += f"<th style='color:{C['text_muted']}; font-size:0.75rem; font-weight:600; padding:6px;'>{day}</th>"
    html += "</tr></thead><tbody>"
    for week in cal:
        html += "<tr>"
        for day in week:
            if day == 0:
                html += "<td style='padding:2px;'></td>"
            else:
                is_selected = day == selected_day
                is_logged = day in logged_days
                if is_selected:
                    cell_style = f"background:{C['teal']}; color:white; border-radius:10px; font-weight:700;"
                elif is_logged:
                    cell_style = f"color:{C['text']}; font-weight:600; border-radius:8px;"
                else:
                    cell_style = f"color:{C['text_sec']}; border-radius:8px;"
                dot_color = 'white' if is_selected else C['teal']
                dot = f"<div style='width:4px;height:4px;border-radius:50%;background:{dot_color};margin:1px auto 0;'></div>" if is_logged else ""
                # Pass integer day — JS in the iframe will find+click the matching hidden button
                html += (f"<td style='padding:2px; font-size:0.85rem;'>"
                         f"<div onclick='pickDate({day})' "
                         f"style='padding:7px 4px; cursor:pointer; {cell_style}'>"
                         f"{day}{dot}</div></td>")
        html += "</tr>"
    return html + "</tbody></table>"


# ============================
# SIDEBAR  (only when logged in)
# ============================
def _reset_scanner():
    st.session_state.camera_active = False
    st.session_state.scan_results = None
    st.session_state.selected_result = None
    st.session_state.scanning = False
    st.session_state.scan_status = None
    st.session_state.detected_items = []
    st.session_state._captured_image = None

with st.sidebar:
    render_logo(size="1.5rem")
    st.markdown(f"<div style='height:12px;'></div>", unsafe_allow_html=True)

    if st.session_state.logged_in:
        # Quick Score Check
        st.markdown(f"<div style='font-size:0.7rem; font-weight:700; color:{C['text_muted']}; letter-spacing:1px; text-transform:uppercase; margin-bottom:6px;'>Quick Score Check</div>", unsafe_allow_html=True)
        search_q = st.text_input("Search any food item", key="sidebar_search", placeholder="Type a food name...", label_visibility="collapsed")
        if search_q:
            results = search_vantage_db(search_q, limit=5)
            if results:
                for d in results[:3]:
                    h_score = vms_to_health_score(d['vms_score'])
                    d_score = vms_to_display_score(d['vms_score'])
                    clr = score_color(h_score, 'health')
                    st.markdown(f"<div style='padding:4px 0; display:flex; justify-content:space-between;'><span style='font-size:0.8rem; color:{C['text_sec']};'>{d['name'][:30]}</span><strong style='color:{clr}; font-size:0.8rem;'>{d_score}/10</strong></div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='font-size:0.8rem; color:{C['text_muted']}; padding:4px 0;'>No results found.</div>", unsafe_allow_html=True)

        st.markdown(f"<div style='height:16px;'></div>", unsafe_allow_html=True)

        # Navigation
        page = st.session_state.page
        nav_items = [
            ('dashboard', '🏠', 'Dashboard'),
            ('calendar', '📅', 'Calendar'),
            ('log',       '🍳', 'Cook With It'),
        ]
        st.markdown('<div class="sidebar-nav">', unsafe_allow_html=True)
        for pg, icon, label in nav_items:
            btn_type = "primary" if page == pg else "secondary"
            if st.button(f"{icon}  {label}", key=f"nav_{pg}", use_container_width=True, type=btn_type):
                _reset_scanner()
                st.session_state.page = pg
                st.rerun()

        # Me / Account button
        me_type = "primary" if page == 'account' else "secondary"
        if st.button("👤  Me", key="nav_account", use_container_width=True, type=me_type):
            _reset_scanner()
            st.session_state.page = 'account'
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

        # Logout button at very bottom
        st.markdown(f"<div style='height:12px;'></div>", unsafe_allow_html=True)
        if st.button("🚪  Logout", key="sidebar_logout", use_container_width=True, type="secondary"):
            _reset_scanner()
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.page = 'dashboard'
            st.session_state.ai_insights = None
            st.session_state.meal_plan = None
            st.session_state.daily_recipes = None
            st.session_state.user_allergies = None
            st.rerun()

        # Streak Card
        st.markdown(f"<div style='height:20px;'></div>", unsafe_allow_html=True)
        day_streak = calculate_day_streak(st.session_state.user_id)
        overall_score = calculate_overall_health_score(st.session_state.user_id)
        total_items = get_total_items_logged(st.session_state.user_id)
        streak_pct = min(day_streak * 10, 100)
        st.markdown(f"""
            <div class='streak-card'>
                <div class='streak-header'>&#128722; {day_streak}-haul streak</div>
                <div class='streak-sub'>{'Consecutive healthy hauls!' if day_streak > 0 else 'Start a haul to build your streak!'}</div>
                <div class='streak-bar-bg'>
                    <div class='streak-bar-fill' style='width:{streak_pct}%'></div>
                </div>
                <div class='streak-milestone'>{day_streak} / 10 hauls to next milestone</div>
                <div class='streak-stats'>
                    <div class='streak-stat'>
                        <div class='streak-stat-val'>{total_items}</div>
                        <div class='streak-stat-label'>items logged</div>
                    </div>
                    <div class='streak-stat'>
                        <div class='streak-stat-val'>{overall_score}</div>
                        <div class='streak-stat-label'>health score</div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)


# ============================
# AUTH GATE — show login/signup if not logged in
# ============================
if not st.session_state.logged_in:
    # Centered auth card
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown(f"""
            <div style='text-align:center; padding:40px 0 20px;'>
                <div style='font-size:2.6rem; font-weight:800; letter-spacing:-0.5px;'>
                    <span style='color:{C["text"]};'>foodvantage</span><span class='logo-dot-blink' style='color:{C["teal"]};'>.</span>
                </div>
                <div style='font-size:0.95rem; color:{C['teal']}; margin-top:8px; font-weight:500;'>Know what's in your cart before it's in your body.</div>
            </div>
        """, unsafe_allow_html=True)

        tab = st.session_state.auth_tab

        # Tab switcher
        col_l, col_s, col_f = st.columns(3)
        with col_l:
            if st.button("Log In", use_container_width=True,
                         type="primary" if tab == 'login' else "secondary", key="auth_tab_login"):
                st.session_state.auth_tab = 'login'; st.rerun()
        with col_s:
            if st.button("Sign Up", use_container_width=True,
                         type="primary" if tab == 'signup' else "secondary", key="auth_tab_signup"):
                st.session_state.auth_tab = 'signup'; st.rerun()
        with col_f:
            if st.button("Reset Password", use_container_width=True,
                         type="primary" if tab == 'forgot' else "secondary", key="auth_tab_forgot"):
                st.session_state.auth_tab = 'forgot'; st.rerun()

        st.markdown(f"<div style='height:12px;'></div>", unsafe_allow_html=True)

        # ---- LOGIN ----
        if tab == 'login':
            st.markdown(f"<div class='card' style='padding:28px 24px;'>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-weight:700; font-size:1.2rem; margin-bottom:4px;'>Welcome back</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='color:{C['text_muted']}; font-size:0.85rem; margin-bottom:20px;'>Log in to your FoodVantage account</div>", unsafe_allow_html=True)
            login_user = st.text_input("Username", key="login_user", placeholder="Enter your username")
            login_pass = st.text_input("Password", key="login_pass", placeholder="Enter your password", type="password")
            if st.button("Log In", use_container_width=True, type="primary", key="login_submit"):
                if not login_user or not login_pass:
                    st.error("Please enter both username and password.")
                elif authenticate_user(login_user.strip(), login_pass):
                    st.session_state.logged_in = True
                    st.session_state.user_id = login_user.strip()
                    st.session_state.page = 'dashboard'
                    st.session_state.user_allergies = None
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
            st.markdown(f"<div style='height:8px;'></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='text-align:center; font-size:0.8rem; color:{C['text_muted']};'>Don't have an account? <span style='color:{C['teal']}; cursor:pointer;'>Click Sign Up above</span></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ---- SIGN UP ----
        elif tab == 'signup':
            st.markdown(f"<div class='card' style='padding:28px 24px;'>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-weight:700; font-size:1.2rem; margin-bottom:4px;'>Create your account</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='color:{C['text_muted']}; font-size:0.85rem; margin-bottom:20px;'>Start tracking your grocery health</div>", unsafe_allow_html=True)
            new_user = st.text_input("Choose a username", key="signup_user", placeholder="At least 5 characters")
            new_pass = st.text_input("Create a password", key="signup_pass", placeholder="At least 8 characters", type="password")
            new_pass2 = st.text_input("Confirm password", key="signup_pass2", placeholder="Repeat your password", type="password")
            if st.button("Create Account", use_container_width=True, type="primary", key="signup_submit"):
                u = (new_user or "").strip()
                p = new_pass or ""
                p2 = new_pass2 or ""
                if len(u) < 5:
                    st.error("Username must be at least 5 characters.")
                elif len(p) < 8:
                    st.error("Password must be at least 8 characters.")
                elif p != p2:
                    st.error("Passwords do not match.")
                elif user_exists(u):
                    st.error("That username is already taken. Please choose another.")
                else:
                    if create_user(u, p):
                        st.success("Account created! You can now log in.")
                        st.session_state.auth_tab = 'login'
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Could not create account. Please try again.")
            st.markdown("</div>", unsafe_allow_html=True)

        # ---- FORGOT / RESET ----
        elif tab == 'forgot':
            st.markdown(f"<div class='card' style='padding:28px 24px;'>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-weight:700; font-size:1.2rem; margin-bottom:4px;'>Reset Password</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='color:{C['text_muted']}; font-size:0.85rem; margin-bottom:20px;'>Enter your username and set a new password</div>", unsafe_allow_html=True)
            fp_user = st.text_input("Username", key="fp_user", placeholder="Your username")
            fp_new = st.text_input("New password", key="fp_new", placeholder="At least 8 characters", type="password")
            fp_conf = st.text_input("Confirm new password", key="fp_conf", placeholder="Repeat new password", type="password")
            if st.button("Reset Password", use_container_width=True, type="primary", key="fp_submit"):
                u = (fp_user or "").strip()
                p = fp_new or ""
                p2 = fp_conf or ""
                if not u:
                    st.error("Please enter your username.")
                elif not user_exists(u):
                    st.error("Username not found.")
                elif len(p) < 8:
                    st.error("New password must be at least 8 characters.")
                elif p != p2:
                    st.error("Passwords do not match.")
                else:
                    if reset_password(u, p):
                        st.success("Password reset successfully! You can now log in.")
                        st.session_state.auth_tab = 'login'
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Could not reset password. Please try again.")
            st.markdown("</div>", unsafe_allow_html=True)

    st.stop()   # Don't render anything else while logged out

# ============================
# DASHBOARD PAGE
# ============================
if st.session_state.page == 'dashboard':
    # Load user allergies if not cached
    if st.session_state.user_allergies is None:
        st.session_state.user_allergies = get_user_allergies(st.session_state.user_id)

    # Centred brand hero — logo + tagline
    st.markdown(f"""
        <div style='text-align:center; padding:32px 0 24px; border-bottom:1px solid {C["border"]}; margin-bottom:28px;'>
            <div style='font-size:2.4rem; font-weight:800; letter-spacing:-0.5px; line-height:1;'>
                <span style='color:{C["text"]};'>foodvantage</span><span class='logo-dot-blink' style='color:{C["teal"]};'>.</span>
            </div>
            <div style='font-size:0.95rem; font-weight:500; color:{C['teal']}; margin-top:10px; letter-spacing:0.2px;'>
                Know what's in your cart before it's in your body.
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Header
    now = datetime.now()
    st.markdown(f"""
        <div style='margin-bottom:4px;'>
            <h2 style='margin:0; font-weight:800; font-size:1.8rem;'>Dashboard</h2>
            <div style='color:{C["text_muted"]}; font-size:0.85rem;'>{now.strftime('%A, %B %d, %Y')}</div>
        </div>
    """, unsafe_allow_html=True)

    # Allergy information button
    if st.button("⚠️  Add Your Allergy Information", use_container_width=True, key="allergy_toggle_btn"):
        st.session_state.allergy_popup_open = not st.session_state.allergy_popup_open
        st.rerun()

    if st.session_state.allergy_popup_open:
        st.markdown(f"""
            <div class='card' style='border:1px solid {C["yellow"]}; padding:16px;'>
                <div style='font-weight:700; font-size:0.95rem; margin-bottom:10px;'>Select Your Allergies</div>
                <div style='font-size:0.75rem; color:{C["text_muted"]}; margin-bottom:12px;'>Check all that apply. This helps us flag potential allergens in your scans and searches.</div>
            </div>
        """, unsafe_allow_html=True)
        allergy_options = list(ALLERGY_KEYWORDS.keys())
        current_allergies = st.session_state.user_allergies or []
        selected_allergies = []
        cols = st.columns(2)
        for idx, allergy in enumerate(allergy_options):
            with cols[idx % 2]:
                checked = allergy in current_allergies
                if st.checkbox(allergy, value=checked, key=f"allergy_cb_{idx}"):
                    selected_allergies.append(allergy)
        if st.button("Add to Your Allergy List", use_container_width=True, type="primary", key="save_allergies_btn"):
            save_user_allergies(st.session_state.user_id, selected_allergies)
            st.session_state.user_allergies = selected_allergies
            st.session_state.allergy_popup_open = False
            st.success(f"Saved {len(selected_allergies)} allergy/allergies!")
            time.sleep(0.5)
            st.rerun()

    # Stat cards
    overall_score = calculate_overall_health_score(st.session_state.user_id)
    day_streak = calculate_day_streak(st.session_state.user_id)
    items_today = get_items_today(st.session_state.user_id)
    sc = score_color(overall_score, 'health')
    allergy_count = len(st.session_state.user_allergies) if st.session_state.user_allergies else 0

    st.markdown(f"""
        <div class='stat-cards'>
            <div class='stat-card'>
                <div class='stat-label'>Items Tracked</div>
                <div class='stat-value'>{items_today} <span class='stat-unit'>today</span></div>
                <div class='stat-sub'>scanned &amp; logged</div>
            </div>
            <div class='stat-card'>
                <div class='stat-label'>Health Score</div>
                <div class='stat-value' style='color:{sc};'>{overall_score} <span class='stat-unit'>/100</span></div>
                <div class='stat-sub'>overall average</div>
            </div>
            <div class='stat-card'>
                <div class='stat-label'>Haul Streak</div>
                <div class='stat-value' style='color:{C["teal"]};'>{day_streak} <span class='stat-unit'>haul{"s" if day_streak != 1 else ""}</span></div>
                <div class='stat-sub'>healthy shopping hauls</div>
            </div>
            <div class='stat-card'>
                <div class='stat-label'>Allergies</div>
                <div class='stat-value' style='color:{C["yellow"] if allergy_count > 0 else C["text_muted"]};'>{allergy_count} <span class='stat-unit'>logged</span></div>
                <div class='stat-sub'>allergens tracked</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Active Focus Scanner
    st.markdown(f"<h3 style='font-weight:700; margin-top:24px;'>&#128722; Grocery Scanner</h3>", unsafe_allow_html=True)

    if not st.session_state.camera_active:
        # Scanner viewfinder rendered in components.html() so onclick works
        # (st.markdown strips all event handlers; components.html() does not)
        components.html(f"""<!DOCTYPE html><html><head>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:{C['bg_card']};font-family:'Inter',sans-serif;overflow:hidden;}}
@keyframes jitter-tl{{0%{{transform:translate(0,0);opacity:.4}}5%{{transform:translate(-5px,-5px);opacity:1}}10%{{transform:translate(-3px,-3px);opacity:1}}15%{{transform:translate(-5px,-5px);opacity:1}}20%{{transform:translate(0,0);opacity:.4}}100%{{transform:translate(0,0);opacity:.4}}}}
@keyframes jitter-tr{{0%,25%{{transform:translate(0,0);opacity:.4}}30%{{transform:translate(5px,-5px);opacity:1}}35%{{transform:translate(3px,-3px);opacity:1}}40%{{transform:translate(5px,-5px);opacity:1}}45%{{transform:translate(0,0);opacity:.4}}100%{{transform:translate(0,0);opacity:.4}}}}
@keyframes jitter-bl{{0%,50%{{transform:translate(0,0);opacity:.4}}55%{{transform:translate(-5px,5px);opacity:1}}60%{{transform:translate(-3px,3px);opacity:1}}65%{{transform:translate(-5px,5px);opacity:1}}70%{{transform:translate(0,0);opacity:.4}}100%{{transform:translate(0,0);opacity:.4}}}}
@keyframes jitter-br{{0%,75%{{transform:translate(0,0);opacity:.4}}80%{{transform:translate(5px,5px);opacity:1}}85%{{transform:translate(3px,3px);opacity:1}}90%{{transform:translate(5px,5px);opacity:1}}95%{{transform:translate(0,0);opacity:.4}}100%{{transform:translate(0,0);opacity:.4}}}}
.vf{{position:relative;height:190px;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:20px;overflow:hidden;}}
.corner{{position:absolute;width:45px;height:45px;border-color:{C['teal']};border-style:solid;}}
.tl{{top:28px;left:28px;border-width:3px 0 0 3px;border-radius:6px 0 0 0;animation:jitter-tl 5s ease-in-out infinite;}}
.tr{{top:28px;right:28px;border-width:3px 3px 0 0;border-radius:0 6px 0 0;animation:jitter-tr 5s ease-in-out infinite;}}
.bl{{bottom:28px;left:28px;border-width:0 0 3px 3px;border-radius:0 0 0 6px;animation:jitter-bl 5s ease-in-out infinite;}}
.br{{bottom:28px;right:28px;border-width:0 3px 3px 0;border-radius:0 0 6px 0;animation:jitter-br 5s ease-in-out infinite;}}
.icon-btn{{width:64px;height:64px;border-radius:50%;background:rgba(238,164,183,0.15);display:flex;align-items:center;justify-content:center;margin-bottom:14px;cursor:pointer;transition:background .2s,transform .1s;}}
.icon-btn:hover{{background:rgba(238,164,183,0.3);transform:scale(1.1);}}
.icon-btn i{{font-size:28px;color:{C['teal']};}}
.rt{{font-size:1rem;font-weight:600;color:{C['text']};margin-bottom:4px;}}
.ht{{font-size:0.8rem;color:{C['text_muted']};}}
</style></head><body>
<div class="vf">
  <div class="corner tl"></div><div class="corner tr"></div>
  <div class="corner bl"></div><div class="corner br"></div>
  <div class="icon-btn" onclick="startScan()"><i class="fa-solid fa-camera"></i></div>
  <div class="rt">Scanner ready</div>
  <div class="ht">Tap the camera icon or the button below</div>
</div>
<script>
function startScan(){{
  var btns=window.parent.document.querySelectorAll('button');
  for(var i=0;i<btns.length;i++){{
    if(btns[i].innerText.trim().includes('Start Live Scan')){{btns[i].click();return;}}
  }}
}}
</script></body></html>""", height=200, scrolling=False)
        st.markdown('<div class="olive-btn">', unsafe_allow_html=True)
        if st.button("Start Live Scan", type="primary", use_container_width=True):
            st.session_state.camera_active = True
            st.session_state.scanning = True
            st.session_state.scan_count = 0
            st.session_state.scan_results = None
            st.session_state.selected_result = None
            st.session_state.scan_status = None
            st.session_state.detected_items = []
            st.session_state._captured_image = None
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        # Scanner active - show HUD
        # Inline scan status indicator - auto-dismisses when items are detected
        if st.session_state.get('scan_status') == "captured":
            st.markdown(f"""
                <div style="text-align:center; padding:16px; margin:12px 0; background:{C['bg_card']}; border-radius:14px; border:1px solid {C['teal']};">
                    <div style="font-size:1.2rem; font-weight:700; color:{C['green']};">Image Captured!</div>
                    <div style="font-size:0.85rem; color:{C['teal']}; margin-top:6px;">Analyzing with Gemini...</div>
                </div>
            """, unsafe_allow_html=True)
        elif st.session_state.get('scan_status') == "analyzing":
            st.markdown(f"""
                <div style="text-align:center; padding:16px; margin:12px 0; background:{C['bg_card']}; border-radius:14px; border:1px solid {C['teal']};">
                    <div style="font-size:1.1rem; font-weight:700; color:{C['teal']};">Analyzing with Gemini...</div>
                    <div style="font-size:0.8rem; color:{C['text_muted']}; margin-top:6px;">Processing your scan</div>
                </div>
            """, unsafe_allow_html=True)

        # Show persistent scan error if one occurred
        if st.session_state.get('scan_error'):
            st.markdown(f"""
                <div style="text-align:center; padding:14px; margin:12px 0; background:rgba(229,57,53,0.08); border-radius:14px; border:1px solid rgba(229,57,53,0.3);">
                    <div style="font-size:1rem; font-weight:700; color:{C['red']};">{st.session_state.scan_error}</div>
                    <div style="font-size:0.8rem; color:{C['text_muted']}; margin-top:6px;">Tap "Scan Again" below to retry</div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown(f"""
            <div style="text-align: center; margin: 16px 0;">
                <div style='background:{C["bg_card"]}; padding:10px 20px; border-radius:12px; display:inline-block; border:1px solid {C["border"]};'>
                    <i class='fa-solid fa-camera' style='color:{C["teal"]};'></i>
                    <span style='color:{C["text_sec"]}; margin-left:8px; font-weight:500;'>Place item anywhere in frame and tap to scan</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        if st.session_state.get('detected_items') and not st.session_state.get('scan_results'):
            preview = ", ".join(st.session_state.detected_items[:3])
            st.markdown(f"""
                <div class="scanner-result">
                    <div class="scanner-result-title">👁️ Items Detected</div>
                    <div class="scanner-result-text">{preview}</div>
                </div>
            """, unsafe_allow_html=True)

        if back_camera_input is not None:
            image = back_camera_input(key=f"hud_cam_{st.session_state.scan_count}")
        else:
            image = st.camera_input("Scan item", key=f"hud_cam_{st.session_state.scan_count}")

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="olive-btn">', unsafe_allow_html=True)
            if st.session_state.get('scan_error'):
                if st.button("Scan Again", use_container_width=True):
                    st.session_state.scan_error = None
                    st.session_state.scan_status = None
                    st.session_state.scanning = True
                    st.session_state._captured_image = None
                    st.session_state.scan_count += 1
                    st.rerun()
            if st.button("Stop Scanning", use_container_width=True):
                st.session_state.camera_active = False
                st.session_state.scan_results = None
                st.session_state.selected_result = None
                st.session_state.scanning = False
                st.session_state.scan_status = None
                st.session_state.detected_items = []
                st.session_state._captured_image = None
                st.session_state.scan_error = None
                st.session_state.scan_count += 1
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # Scanning logic - two-phase: capture acknowledgement, then analyze
        # Phase 1: Image captured - show acknowledgement and prevent duplicate scans
        if image and st.session_state.scanning:
            st.session_state.scanning = False  # Prevent duplicate scans immediately
            st.session_state.scan_status = "captured"
            st.session_state._captured_image = image
            st.rerun()

        # Phase 2: Process captured image (runs on next rerun after acknowledgement shown)
        if st.session_state.get('scan_status') == "captured" and st.session_state.get('_captured_image'):
            st.session_state.scan_status = "analyzing"
            try:
                results = vision_live_scan_dark(st.session_state._captured_image)
                st.session_state._captured_image = None
                if results:
                    st.session_state.scan_results = results
                    st.session_state.selected_result = results[0]
                    st.session_state.detected_items = [r['name'] for r in results[:5]]
                    st.session_state.scan_status = None
                    st.session_state.scan_error = None
                    st.session_state.scanning = True
                    st.session_state.scan_count += 1
                else:
                    st.session_state.scan_status = None
                    st.session_state.scan_error = "Item not found in database — try a clearer angle or different wording"
                    st.session_state.scanning = True  # Allow retry on failure
                    st.session_state.scan_count += 1
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "quota" in error_msg.lower() or "RESOURCE_EXHAUSTED" in error_msg:
                    st.session_state.scan_error = "API limit reached — please try again in a moment"
                else:
                    st.session_state.scan_error = "Scan failed — please try again"
                st.session_state.scan_status = None
                st.session_state._captured_image = None
                st.session_state.scanning = True
                st.session_state.scan_count += 1
            st.rerun()

    # Scan results with full item details, nutrition, and grocery list integration
    if st.session_state.scan_results:
        # "Scan Again" at the TOP so the user can immediately go to next item
        st.markdown('<div class="olive-btn">', unsafe_allow_html=True)
        if st.button("🔄 Scan Again", use_container_width=True, key="scan_again_btn_top"):
            st.session_state.scan_results = None
            st.session_state.selected_result = None
            st.session_state.scanning = True
            st.session_state.detected_items = []
            st.session_state.scan_count += 1
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown(f"<h4 style='font-weight:700; margin-top:12px;'>Scan Results</h4>", unsafe_allow_html=True)
        st.markdown(f"<div style='color:{C['text_sec']}; font-size:0.85rem; margin-bottom:12px;'>Found {len(st.session_state.scan_results)} item(s) in frame</div>", unsafe_allow_html=True)

        for i, result in enumerate(st.session_state.scan_results):
            vms = result['vms_score']
            clr = score_color(vms)
            health_score = vms_to_health_score(vms)
            health_clr = score_color(health_score, 'health')
            display_score = vms_to_display_score(vms)
            rating = result['rating']
            portion_label = " /serving" if needs_portion_size(result['name']) else ""
            raw = result['raw']

            # If API provides serving size, scale per-100g values to that serving.
            # Otherwise, display per-100g directly (no heuristic scaling).
            if 'serving_g' in result:
                scale = result['serving_g'] / 100.0
                serving_note = f"per {int(result['serving_g'])}g serving"
            else:
                scale = 1.0
                serving_note = "per 100g"

            # Extract nutrition data (raw values are normalized to per 100g in backend)
            cal = round(float(raw[2] or 0) * scale, 1)
            sug = round(float(raw[3] or 0) * scale, 1)
            fib = round(float(raw[4] or 0) * scale, 1)
            prot = round(float(raw[5] or 0) * scale, 1)
            fat_val = round(float(raw[6] or 0) * scale, 1)
            sod = round(float(raw[7] or 0) * scale, 1)

            st.markdown(f"""
                <div class='card' style='padding:16px; margin-bottom:4px; border-left:4px solid {clr};'>
                    <div style='display:flex; justify-content:space-between; align-items:flex-start;'>
                        <div>
                            <div style='font-weight:700; font-size:1rem; margin-bottom:4px;'>{i+1}. {result['name']}</div>
                            <span style='color:{clr}; font-size:0.8rem; font-weight:600;'>{rating}</span>
                        </div>
                        <div style='text-align:right;'>
                            <div style='color:{health_clr}; font-size:1.6rem; font-weight:900;'>{display_score}<span style='font-size:0.9rem; font-weight:600;'>/10</span></div>
                            <div style='font-size:0.7rem; color:{C["text_muted"]};'>Health Score</div>
                        </div>
                    </div>
                    <div style='display:flex; align-items:center; gap:8px; margin-top:8px;'>
                        <div style='background:rgba(238,164,183,0.08); padding:4px 12px; border-radius:20px;'>
                            <span style='color:{C["text_muted"]}; font-size:0.7rem;'>Higher score = healthier choice &middot; </span>
                            <span style='color:{health_clr}; font-weight:600; font-size:0.7rem;'>{rating}</span>
                        </div>
                    </div>
                    <div style='margin-top:12px; padding-top:10px; border-top:1px solid {C["border"]};'>
                        <div style='font-size:0.7rem; font-weight:600; color:{C["text_muted"]}; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px;'>Nutrition ({serving_note})</div>
                        <div style='display:grid; grid-template-columns:repeat(3, 1fr); gap:8px;'>
                            <div style='text-align:center; padding:6px; background:{C["bg"]}; border-radius:8px;'>
                                <div style='font-weight:700; font-size:0.9rem; color:{C["text"]};'>{cal}</div>
                                <div style='font-size:0.65rem; color:{C["text_muted"]};'>Calories</div>
                            </div>
                            <div style='text-align:center; padding:6px; background:{C["bg"]}; border-radius:8px;'>
                                <div style='font-weight:700; font-size:0.9rem; color:{C["text"]};'>{sug}g</div>
                                <div style='font-size:0.65rem; color:{C["text_muted"]};'>Sugar</div>
                            </div>
                            <div style='text-align:center; padding:6px; background:{C["bg"]}; border-radius:8px;'>
                                <div style='font-weight:700; font-size:0.9rem; color:{C["text"]};'>{fib}g</div>
                                <div style='font-size:0.65rem; color:{C["text_muted"]};'>Fiber</div>
                            </div>
                            <div style='text-align:center; padding:6px; background:{C["bg"]}; border-radius:8px;'>
                                <div style='font-weight:700; font-size:0.9rem; color:{C["text"]};'>{prot}g</div>
                                <div style='font-size:0.65rem; color:{C["text_muted"]};'>Protein</div>
                            </div>
                            <div style='text-align:center; padding:6px; background:{C["bg"]}; border-radius:8px;'>
                                <div style='font-weight:700; font-size:0.9rem; color:{C["text"]};'>{fat_val}g</div>
                                <div style='font-size:0.65rem; color:{C["text_muted"]};'>Fat</div>
                            </div>
                            <div style='text-align:center; padding:6px; background:{C["bg"]}; border-radius:8px;'>
                                <div style='font-weight:700; font-size:0.9rem; color:{C["text"]};'>{sod}mg</div>
                                <div style='font-size:0.65rem; color:{C["text_muted"]};'>Sodium</div>
                            </div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # Allergy alert for scanned item
            user_allergies = st.session_state.user_allergies or []
            matched_allergies = check_item_allergies(result['name'], user_allergies)
            if matched_allergies:
                allergy_names = ", ".join(matched_allergies)
                st.markdown(f"""
                    <div class='allergy-alert'>
                        <div class='allergy-alert-title'>⚠️ Potential Allergy Detected</div>
                        <div class='allergy-alert-text'>This item may contain: <strong>{allergy_names}</strong>. Please verify ingredients.</div>
                    </div>
                """, unsafe_allow_html=True)

            # Add to Grocery List button for each scanned item
            st.markdown('<div class="olive-btn">', unsafe_allow_html=True)
            if st.button(f"+ Add to Grocery List", key=f"scan_add_{i}", use_container_width=True):
                add_calendar_item_db(
                    st.session_state.user_id,
                    datetime.now().strftime("%Y-%m-%d"),
                    result['name'],
                    round(vms, 1)
                )
                st.success(f"Added {result['name']} to today's grocery list!")
                # Auto-reset scanner for continuous scanning — no need to close & reopen
                st.session_state.scan_results = None
                st.session_state.selected_result = None
                st.session_state.scanning = True
                st.session_state.detected_items = []
                st.session_state.scan_status = None
                st.session_state._captured_image = None
                st.session_state.scan_error = None
                st.session_state.scan_count += 1
                time.sleep(0.5)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


    # Health Trends - header with tabs on the right
    col_trends_title, col_trends_tabs = st.columns([2, 1])
    with col_trends_title:
        st.markdown(f"<h3 style='font-weight:700; margin-top:28px;'>Your Health Trends</h3>", unsafe_allow_html=True)
    with col_trends_tabs:
        st.markdown(f"<div style='height:28px;'></div>", unsafe_allow_html=True)
        col_d, col_w, col_m = st.columns(3)
        with col_d:
            if st.button("Day", use_container_width=True, key="day_tab",
                          type="primary" if st.session_state.trends_view == 'daily' else "secondary"):
                st.session_state.trends_view = 'daily'; st.rerun()
        with col_w:
            if st.button("Week", use_container_width=True, key="week_tab",
                          type="primary" if st.session_state.trends_view == 'weekly' else "secondary"):
                st.session_state.trends_view = 'weekly'; st.rerun()
        with col_m:
            if st.button("Month", use_container_width=True, key="month_tab",
                          type="primary" if st.session_state.trends_view == 'monthly' else "secondary"):
                st.session_state.trends_view = 'monthly'; st.rerun()

    if st.session_state.trends_view == 'daily': days = 1
    elif st.session_state.trends_view == 'weekly': days = 7
    else: days = 30

    all_data = get_all_calendar_data_db(st.session_state.user_id)
    raw = get_trend_data_db(st.session_state.user_id, days=days)

    if raw and len(raw) > 0:
        df = pd.DataFrame(raw, columns=["date", "category", "count"])
        df['date'] = pd.to_datetime(df['date'])
        df_pivot = df.pivot_table(index='date', columns='category', values='count', aggfunc='sum', fill_value=0)

        # Build per-date health score for interactive hover tooltip
        # Fetch avg VMS per day to compute daily health score
        try:
            from gemini_api import get_db_connection as _get_db
            _con = _get_db()
            _hs_rows = _con.execute("""
                SELECT date, AVG(score) as avg_vms
                FROM calendar WHERE username = ?
                GROUP BY date ORDER BY date
            """, [st.session_state.user_id]).fetchall()
            _hs_map = {str(r[0]): vms_to_health_score(r[1]) for r in _hs_rows}
        except Exception:
            _hs_map = {}

        fig = go.Figure()
        if 'healthy' in df_pivot.columns:
            hs_vals = [_hs_map.get(str(d.date()), None) for d in df_pivot.index]
            hover_texts = [
                f"<b>{str(d.date())}</b><br>{y} healthy items<br>Health Score: <b>{hs}/100</b>" if hs is not None
                else f"<b>{str(d.date())}</b><br>{y} healthy items"
                for d, y, hs in zip(df_pivot.index, df_pivot['healthy'], hs_vals)
            ]
            fig.add_trace(go.Scatter(
                x=df_pivot.index, y=df_pivot['healthy'], name='Healthy',
                mode='lines+markers', line=dict(color=C['teal'], width=2.5, shape='spline'),
                marker=dict(size=7, color=C['teal']), fill='tozeroy',
                fillcolor='rgba(238,164,183,0.1)',
                text=hover_texts, hovertemplate='%{text}<extra></extra>'
            ))
        if 'moderate' in df_pivot.columns:
            hs_vals_m = [_hs_map.get(str(d.date()), None) for d in df_pivot.index]
            hover_texts_m = [
                f"<b>{str(d.date())}</b><br>{y} moderate items<br>Health Score: <b>{hs}/100</b>" if hs is not None
                else f"<b>{str(d.date())}</b><br>{y} moderate items"
                for d, y, hs in zip(df_pivot.index, df_pivot['moderate'], hs_vals_m)
            ]
            fig.add_trace(go.Scatter(
                x=df_pivot.index, y=df_pivot['moderate'], name='Moderate',
                mode='lines+markers', line=dict(color=C['yellow'], width=2, shape='spline'),
                marker=dict(size=6),
                text=hover_texts_m, hovertemplate='%{text}<extra></extra>'
            ))
        if 'unhealthy' in df_pivot.columns:
            hs_vals_u = [_hs_map.get(str(d.date()), None) for d in df_pivot.index]
            hover_texts_u = [
                f"<b>{str(d.date())}</b><br>{y} unhealthy items<br>Health Score: <b>{hs}/100</b>" if hs is not None
                else f"<b>{str(d.date())}</b><br>{y} unhealthy items"
                for d, y, hs in zip(df_pivot.index, df_pivot['unhealthy'], hs_vals_u)
            ]
            fig.add_trace(go.Scatter(
                x=df_pivot.index, y=df_pivot['unhealthy'], name='Unhealthy',
                mode='lines+markers', line=dict(color=C['red'], width=2, shape='spline'),
                marker=dict(size=6),
                text=hover_texts_u, hovertemplate='%{text}<extra></extra>'
            ))

        fig.update_layout(
            height=280,
            margin=dict(l=16, r=16, t=8, b=32),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, showline=False, tickfont=dict(color=C['text_muted']), color=C['text_muted']),
            yaxis=dict(showgrid=True, gridcolor=C['border'], showline=False, tickfont=dict(color=C['text_muted']), color=C['text_muted']),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(color=C['text_sec'])),
            hovermode='x unified',
            hoverlabel=dict(bgcolor=C['bg_card'], font_size=13, font_color=C['text'])
        )
        st.plotly_chart(fig, use_container_width=True)

        total_items_trend = int(df['count'].sum())
        healthy_count = int(df[df['category'] == 'healthy']['count'].sum()) if 'healthy' in df['category'].values else 0
        st.markdown(f"<div style='color:{C['text_sec']}; font-size:0.85rem;'>Total items: <strong>{total_items_trend}</strong> &middot; Healthy choices: <strong style='color:{C['green']};'>{healthy_count}</strong></div>", unsafe_allow_html=True)

    else:
        if all_data and len(all_data) > 0:
            st.markdown(f"<div style='color:{C['text_muted']}; font-size:0.85rem; padding:12px 0;'>No data in the last {days} day(s). Try a different time range above.</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='color:{C['text_muted']}; font-size:0.85rem; padding:12px 0;'>No grocery hauls yet — scan or search items to start tracking!</div>", unsafe_allow_html=True)

    # AI Health Coach & Healthy Recipes — always visible (even with 0 items)
    st.markdown(f"<div style='height:20px;'></div>", unsafe_allow_html=True)
    col_coach, col_recipes = st.columns(2)

    with col_coach:
        st.markdown(f"""
            <div class='card' style='min-height:200px;'>
                <div style='display:flex; align-items:center; gap:10px; margin-bottom:12px;'>
                    <div style='width:36px; height:36px; border-radius:10px; background:rgba(238,164,183,0.15); display:flex; align-items:center; justify-content:center;'>
                        <i class='fa-solid fa-heart-pulse' style='color:{C["teal"]}; font-size:1rem;'></i>
                    </div>
                    <div>
                        <div style='font-weight:700; font-size:0.95rem;'>Grocery Health Coach</div>
                        <div style='font-size:0.7rem; color:{C["text_muted"]};'>Score your shopping habits</div>
                    </div>
                </div>
        """, unsafe_allow_html=True)

        if st.session_state.ai_insights:
            for i, insight in enumerate(st.session_state.ai_insights[:5]):
                emoji = insight.get('emoji', '')
                title = insight.get('title', 'Insight')
                body = insight.get('insight', '')
                st.markdown(f"<div style='font-size:0.8rem; margin-bottom:8px;'><strong>{emoji} {title}</strong><br><span style='color:{C['text_sec']};'>{body}</span></div>", unsafe_allow_html=True)
            if st.button("Refresh Insights", key="refresh_insights", use_container_width=True):
                st.session_state.ai_insights = None; st.rerun()
        elif st.session_state._loading_insights:
            st.markdown(f"""<div class='ai-loading'>
                <div class='ai-loading-text'>Hold on...fetching details</div>
                <div class='ai-loading-sub'>Analyzing your shopping patterns</div>
            </div>""", unsafe_allow_html=True)
            try:
                insights = generate_health_insights(raw, all_data, days)
                if insights:
                    st.session_state.ai_insights = insights
                else: st.warning("Could not generate insights.")
            except Exception as e: st.error(f"Error: {e}")
            st.session_state._loading_insights = False
            st.rerun()
        else:
            if st.button("🧠  Get AI Insights", use_container_width=True, type="primary", key="get_insights_btn"):
                st.session_state._loading_insights = True
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    with col_recipes:
        today_str = datetime.now().strftime("%Y-%m-%d")
        if st.session_state.recipes_date != today_str:
            st.session_state.daily_recipes = None
            st.session_state.recipes_date = today_str

        st.markdown(f"""
            <div class='card' style='min-height:200px;'>
                <div style='display:flex; align-items:center; gap:10px; margin-bottom:12px;'>
                    <div style='width:36px; height:36px; border-radius:10px; background:rgba(124,158,56,0.15); display:flex; align-items:center; justify-content:center;'>
                        <i class='fa-solid fa-utensils' style='color:{C["olive"]}; font-size:1rem;'></i>
                    </div>
                    <div>
                        <div style='font-weight:700; font-size:0.95rem;'>Cook With Your Haul</div>
                        <div style='font-size:0.7rem; color:{C["text_muted"]};'>Recipe ideas from what you buy</div>
                    </div>
                </div>
        """, unsafe_allow_html=True)

        if st.session_state.daily_recipes:
            for recipe in st.session_state.daily_recipes[:2]:
                r_name = recipe.get('name', 'Recipe')
                r_type = recipe.get('meal_type', '')
                r_time = recipe.get('prep_time', '')
                r_desc = recipe.get('description', '')
                r_url = recipe.get('recipe_url', '')
                if not r_url:
                    continue
                st.markdown(f"""<div style='font-size:0.8rem; margin-bottom:10px;'>
                    <strong>{r_name}</strong><br>
                    <span style='color:{C["text_sec"]}; font-size:0.75rem;'>{r_desc}</span><br>
                    <span style='color:{C["text_muted"]}; font-size:0.7rem;'>{r_type} &middot; {r_time}</span><br>
                    <a href='{r_url}' target='_blank' style='color:{C["teal"]}; font-size:0.75rem; text-decoration:none; font-weight:600;'>View full recipe on BBC Food &rarr;</a>
                </div>""", unsafe_allow_html=True)
            if st.button("New Recipes", key="refresh_recipes", use_container_width=True):
                st.session_state.daily_recipes = None; st.rerun()
        elif st.session_state._loading_recipes:
            st.markdown(f"""<div class='ai-loading'>
                <div class='ai-loading-text'>Hold on...fetching details</div>
                <div class='ai-loading-sub'>Finding healthy BBC Food recipes</div>
            </div>""", unsafe_allow_html=True)
            try:
                recipes = generate_daily_recipes()
                if recipes:
                    st.session_state.daily_recipes = recipes
                    st.session_state.recipes_date = today_str
                else: st.warning("Could not load recipes.")
            except Exception as e: st.error(f"Error: {e}")
            st.session_state._loading_recipes = False
            st.rerun()
        else:
            if st.button("🌿  Discover Recipes", use_container_width=True, type="primary", key="discover_recipes_btn"):
                st.session_state._loading_recipes = True
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # Disclaimer at bottom of dashboard
    st.markdown(f"""
        <div style='text-align:center; padding:20px 16px 8px; margin-top:24px; border-top:1px solid {C["border"]};'>
            <div style='font-size:0.75rem; color:{C["text_muted"]}; line-height:1.5;'>
                While we are consistently and sincerely updating our algorithm, note that this is a grocery scanning app and will work best with grocery items, but approximate prepared food items.
            </div>
        </div>
    """, unsafe_allow_html=True)


# ============================
# CALENDAR PAGE
# ============================
elif st.session_state.page == 'calendar':
    # Get logged days for the calendar dots
    all_items = get_all_calendar_data_db(st.session_state.user_id)
    total_logged = len(all_items) if all_items else 0
    unique_dates = set()
    if all_items:
        for item in all_items:
            try:
                d = item[0]
                if hasattr(d, 'day'):
                    unique_dates.add(d)
                else:
                    unique_dates.add(datetime.strptime(str(d), '%Y-%m-%d').date())
            except:
                pass

    st.markdown(f"""
        <div style='margin-bottom:16px;'>
            <h2 style='margin:0; font-weight:800; font-size:1.8rem;'><i class='fa-solid fa-cart-shopping' style='color:{C["teal"]}; margin-right:8px;'></i>Grocery Planner</h2>
            <div style='color:{C["teal"]}; font-size:0.9rem; font-weight:600; margin-top:2px;'>Know your health score before it hits your cart.</div>
            <div style='color:{C["text_muted"]}; font-size:0.8rem; margin-top:2px;'>{len(unique_dates)} hauls tracked &middot; {total_logged} items scanned total</div>
        </div>
    """, unsafe_allow_html=True)

    sel_date = st.session_state.cal_date

    # --- Hidden day-trigger buttons (same technique as camera icon) ---
    # 31 real Streamlit buttons, one per day. The calendar iframe JS calls
    # pickDate(N) which finds the button labelled "d0N" and .click()s it —
    # identical to how the camera icon clicks "Start Live Scan".
    # CSS moves the entire 31-column block off-screen; pointer-events:none
    # prevents accidental mouse clicks while JS .click() still works.
    st.markdown("""<style>
div.stHorizontalBlock:has(> div.stColumn:nth-child(31)){
  position:fixed!important;left:-9999px!important;
  top:0!important;opacity:0!important;pointer-events:none!important;
}
</style>""", unsafe_allow_html=True)
    _tcols = st.columns(31)
    _day_triggered = None
    for _i, _col in enumerate(_tcols):
        with _col:
            if st.button(f"d{_i+1:02d}", key=f"cal_trig_{_i+1}"):
                _day_triggered = _i + 1
    if _day_triggered is not None:
        try:
            _nd = datetime(st.session_state.cal_year, st.session_state.cal_month, _day_triggered).date()
            st.session_state.cal_date = _nd
            st.rerun()
        except ValueError:
            pass  # e.g. day 31 clicked in a 30-day month — ignore

    c1, c2 = st.columns([1, 1.5])

    with c1:
        # Month navigation
        nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
        with nav_col1:
            if st.button("‹", key="cal_prev", help="Previous month"):
                m, y = st.session_state.cal_month - 1, st.session_state.cal_year
                if m < 1: m, y = 12, y - 1
                st.session_state.cal_month, st.session_state.cal_year = m, y
                st.rerun()
        with nav_col3:
            if st.button("›", key="cal_next", help="Next month"):
                m, y = st.session_state.cal_month + 1, st.session_state.cal_year
                if m > 12: m, y = 1, y + 1
                st.session_state.cal_month, st.session_state.cal_year = m, y
                st.rerun()

        # Get logged days for displayed month
        logged_days_in_month = set()
        for d in unique_dates:
            if hasattr(d, 'year') and d.year == st.session_state.cal_year and d.month == st.session_state.cal_month:
                logged_days_in_month.add(d.day)
        # Highlight selected day only if it's in the displayed month
        shown_selected = sel_date.day if (sel_date.year == st.session_state.cal_year and sel_date.month == st.session_state.cal_month) else None
        # Render calendar inside components.html() — onclick works here.
        # pickDate(N) finds the hidden "d0N" Streamlit button in the parent
        # page and calls .click() on it, identical to how the camera icon works.
        cal_inner = create_html_calendar(
            st.session_state.cal_year, st.session_state.cal_month,
            shown_selected, logged_days_in_month)
        components.html(f"""<!DOCTYPE html><html><head><style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:{C['bg_card']};font-family:'Inter',sans-serif;padding:14px;}}
div[onclick]:hover{{opacity:0.7;}}
</style></head><body>
{cal_inner}
<script>
function pickDate(day){{
  var label='d'+(day<10?'0':'')+day;
  var btns=window.parent.document.querySelectorAll('button');
  for(var i=0;i<btns.length;i++){{
    if(btns[i].innerText.trim()===label){{btns[i].click();return;}}
  }}
}}
</script></body></html>""", height=285, scrolling=False)

    with c2:
        items = get_calendar_items_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"))
        item_count = len(items) if items else 0
        st.markdown(f"""
            <div style='margin-bottom:16px;'>
                <h4 style='font-weight:700; margin:0;'>{sel_date.strftime('%b %d, %Y')}</h4>
                <div style='color:{C["text_muted"]}; font-size:0.8rem;'>{item_count} item{"s" if item_count != 1 else ""} in haul</div>
            </div>
        """, unsafe_allow_html=True)

        # Add item — friendly onboarding text
        st.markdown(f"""
            <div style='background:rgba(238,164,183,0.08); border:1px solid rgba(238,164,183,0.2); border-radius:12px; padding:10px 14px; margin-bottom:10px;'>
                <div style='font-size:0.8rem; font-weight:600; color:{C["teal"]}; margin-bottom:3px;'>Forgot to scan before buying? No problem!</div>
                <div style='font-size:0.75rem; color:{C["text_muted"]};'>Search any item below — we'll look up its health score and log it to your haul.</div>
            </div>
        """, unsafe_allow_html=True)
        search_item = st.text_input("Search for an item", key="calendar_search", placeholder="e.g., banana, avocado...", label_visibility="collapsed")

        if search_item:
            search_results = search_vantage_db(search_item, limit=10)
            # Filter out placeholder/default 10.0 scores — these are unmatched DB entries
            valid_results = [r for r in search_results if r['vms_score'] != 10.0] if search_results else []
            if valid_results:
                st.markdown('<div class="results-scroll-container">', unsafe_allow_html=True)
                cal_user_allergies = get_user_allergies(st.session_state.user_id)
                for idx, result in enumerate(valid_results):
                    h_sc = vms_to_health_score(result['vms_score'])
                    clr = score_color(h_sc, 'health')
                    d_sc = vms_to_display_score(result['vms_score'])
                    col_a, col_b, col_c = st.columns([3, 1, 0.6])
                    with col_a:
                        st.markdown(f"<span style='font-size:0.9rem;'>{result['name']}</span>", unsafe_allow_html=True)
                        cal_matched = check_item_allergies(result['name'], cal_user_allergies)
                        if cal_matched:
                            st.markdown(f"<div style='font-size:0.7rem; color:{C['red']}; font-weight:600;'>⚠️ Potential allergy: {', '.join(cal_matched)} — verify ingredients</div>", unsafe_allow_html=True)
                    with col_b:
                        st.markdown(f"<div style='text-align:center; color:{clr}; font-weight:bold;'>{d_sc}/10</div>", unsafe_allow_html=True)
                    with col_c:
                        if st.button("+", key=f"add_cal_{idx}_{sel_date}", help=f"Add {result['name']}"):
                            add_calendar_item_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"),
                                                 result['name'], round(result['vms_score'], 1))
                            st.success("Added!")
                            time.sleep(0.5)
                            st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.markdown(f"""
                    <div class='friendly-error'>
                        <div class='friendly-error-title'>Item Not Found</div>
                        <div class='friendly-error-text'>We couldn't find reliable nutrition data for this item. Try a more specific product name or a similar alternative.</div>
                    </div>
                """, unsafe_allow_html=True)

        # Items for this day
        st.markdown(f"<div style='height:12px;'></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:0.75rem; font-weight:600; color:{C['text_muted']}; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;'>Items in This Haul</div>", unsafe_allow_html=True)
        if items:
            for iid, name, score_val, cat in items:
                h_sc_item = vms_to_health_score(score_val)
                clr = score_color(h_sc_item, 'health')
                d_sc_item = vms_to_display_score(score_val)
                col_item, col_del = st.columns([5, 1])
                with col_item:
                    st.markdown(f"""
                        <div class='list-row'>
                            <div style='display:flex; align-items:center; gap:10px;'>
                                <div style='width:8px; height:8px; border-radius:50%; background:{clr};'></div>
                                <span style='font-size:0.9rem;'>{name}</span>
                            </div>
                            <strong style='color:{clr}; font-size:0.9rem;'>{d_sc_item}/10</strong>
                        </div>
                    """, unsafe_allow_html=True)
                with col_del:
                    if st.button("🗑", key=f"del_{iid}", help="Delete"):
                        delete_item_db(iid)
                        st.rerun()
        else:
            st.markdown(f"<div style='color:{C['text_muted']}; font-size:0.85rem; padding:12px;'>No grocery haul logged for this date. Search above to add items before you shop!</div>", unsafe_allow_html=True)


# ============================
# ACCOUNT PAGE
# ============================
elif st.session_state.page == 'account':
    uid = st.session_state.user_id
    st.markdown(f"""
        <div style='margin-bottom:20px;'>
            <h2 style='margin:0; font-weight:800; font-size:1.8rem;'>👤 My Account</h2>
            <div style='color:{C["text_muted"]}; font-size:0.85rem; margin-top:4px;'>Manage your FoodVantage profile</div>
        </div>
    """, unsafe_allow_html=True)

    # Profile card
    _, mid_acc, _ = st.columns([1, 2, 1])
    with mid_acc:
        st.markdown(f"""
            <div class='card' style='padding:24px; margin-bottom:16px; text-align:center;'>
                <div style='width:72px; height:72px; border-radius:50%; background:rgba(238,164,183,0.15);
                     display:flex; align-items:center; justify-content:center; margin:0 auto 12px;'>
                    <span style='font-size:2.2rem;'>👤</span>
                </div>
                <div style='font-weight:700; font-size:1.2rem; color:{C["text"]};'>{uid}</div>
                <div style='font-size:0.8rem; color:{C["text_muted"]}; margin-top:4px;'>FoodVantage Member</div>
            </div>
        """, unsafe_allow_html=True)

        # --- Change Password ---
        with st.expander("🔑 Change Password", expanded=False):
            old_p = st.text_input("Current password", type="password", key="acc_old_pass")
            new_p = st.text_input("New password (min 8 chars)", type="password", key="acc_new_pass")
            new_p2 = st.text_input("Confirm new password", type="password", key="acc_new_pass2")
            if st.button("Update Password", use_container_width=True, type="primary", key="acc_change_pass"):
                if not old_p or not new_p or not new_p2:
                    st.error("Please fill in all fields.")
                elif len(new_p) < 8:
                    st.error("New password must be at least 8 characters.")
                elif new_p != new_p2:
                    st.error("New passwords do not match.")
                else:
                    if change_password(uid, old_p, new_p):
                        st.success("Password changed successfully!")
                    else:
                        st.error("Current password is incorrect.")

        # --- Logout ---
        st.markdown(f"<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("🚪  Logout", use_container_width=True, key="acc_logout"):
            _reset_scanner()
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.page = 'dashboard'
            st.session_state.ai_insights = None
            st.session_state.meal_plan = None
            st.session_state.daily_recipes = None
            st.session_state.user_allergies = None
            st.rerun()

        # --- Delete Account ---
        st.markdown(f"<div style='height:8px;'></div>", unsafe_allow_html=True)
        with st.expander("⚠️ Delete Account", expanded=False):
            st.markdown(f"<div style='font-size:0.85rem; color:{C['red']}; margin-bottom:10px;'>This will permanently delete your account and all your data. This cannot be undone.</div>", unsafe_allow_html=True)
            del_confirm = st.text_input("Type your username to confirm deletion", key="acc_del_confirm", placeholder=uid)
            del_pass = st.text_input("Enter your password", type="password", key="acc_del_pass")
            if st.button("Delete My Account", use_container_width=True, key="acc_delete_btn"):
                if del_confirm.strip() != uid:
                    st.error("Username does not match.")
                elif not authenticate_user(uid, del_pass):
                    st.error("Incorrect password.")
                else:
                    delete_account(uid)
                    st.session_state.logged_in = False
                    st.session_state.user_id = None
                    st.session_state.page = 'dashboard'
                    st.session_state.ai_insights = None
                    st.session_state.meal_plan = None
                    st.session_state.daily_recipes = None
                    st.session_state.user_allergies = None
                    st.success("Account deleted.")
                    time.sleep(1)
                    st.rerun()


# ============================
# MEAL PLAN PAGE
# ============================
elif st.session_state.page == 'log':
    history_raw = get_log_history_db(st.session_state.user_id)
    # Also get items with IDs for delete functionality
    all_items_with_ids = []
    try:
        con = get_db_connection()
        all_items_with_ids = con.execute(
            "SELECT id, date, item_name, score, category FROM calendar WHERE username = ? ORDER BY date DESC",
            [st.session_state.user_id]
        ).fetchall()
    except:
        pass
    history = history_raw

    # Count summaries
    healthy_count = sum(1 for _, _, s, _ in history if s < 3.0) if history else 0
    watch_count = sum(1 for _, _, s, _ in history if s >= 3.0) if history else 0
    unique_days = len(set(str(d) for d, _, _, _ in history)) if history else 0

    st.markdown(f"""
        <div style='margin-bottom:8px;'>
            <h2 style='margin:0; font-weight:800; font-size:1.8rem;'><i class='fa-solid fa-bowl-food' style='color:{C["teal"]}; margin-right:8px;'></i>Cook With Your Groceries</h2>
            <div style='display:flex; gap:8px; margin-top:6px;'>
                <span style='background:rgba(76,175,80,0.15); color:{C["green"]}; padding:3px 10px; border-radius:8px; font-size:0.75rem; font-weight:600;'>{healthy_count} healthy</span>
                <span style='background:rgba(249,168,37,0.15); color:{C["yellow"]}; padding:3px 10px; border-radius:8px; font-size:0.75rem; font-weight:600;'>{watch_count} to watch</span>
            </div>
            <div style='color:{C["teal"]}; font-size:0.85rem; font-weight:600; margin-top:4px;'>Turn your grocery hauls into a week of healthy meals.</div>
            <div style='color:{C["text_muted"]}; font-size:0.8rem; margin-top:2px;'>{len(history) if history else 0} items scanned &middot; {unique_days} hauls</div>
        </div>
    """, unsafe_allow_html=True)

    # Display user allergies at top of meal plan
    mp_allergies = get_user_allergies(st.session_state.user_id)
    if mp_allergies:
        allergy_names = ", ".join(mp_allergies)
        st.markdown(f"""
            <div class='card' style='padding:12px 16px; margin-bottom:12px; border-left:4px solid {C["yellow"]};'>
                <div style='font-size:0.7rem; font-weight:600; color:{C["text_muted"]}; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;'>Allergies</div>
                <div style='font-size:0.85rem; color:{C["yellow"]}; font-weight:600;'>{allergy_names}</div>
            </div>
        """, unsafe_allow_html=True)

    if history:
        # Group items by date (with IDs for delete)
        from collections import OrderedDict
        grouped = OrderedDict()
        for row in all_items_with_ids:
            iid, d, name, score_val, cat = row
            date_str = str(d)
            if date_str not in grouped:
                grouped[date_str] = []
            grouped[date_str].append((iid, name, score_val, cat))

        for date_str, items_list in grouped.items():
            # Calculate total estimated calories for the date group
            total_cal = len(items_list) * 180  # rough estimate per item
            st.markdown(f"""
                <div class='card' style='padding:16px; margin-bottom:12px;'>
                    <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;'>
                        <div style='display:flex; align-items:center; gap:8px;'>
                            <i class='fa-regular fa-calendar' style='color:{C["teal"]}; font-size:0.85rem;'></i>
                            <span style='font-weight:700; font-size:0.9rem; color:{C["text"]};'>{date_str}</span>
                            <span style='color:{C["text_muted"]}; font-size:0.75rem;'>{len(items_list)} items</span>
                        </div>
                        <span style='color:{C["text_muted"]}; font-size:0.75rem;'>~{total_cal} cal</span>
                    </div>
            """, unsafe_allow_html=True)
            for iid, name, score_val, cat in items_list:
                h_sc_log = vms_to_health_score(score_val)
                clr = score_color(h_sc_log, 'health')
                score_display = f"{vms_to_display_score(score_val)}/10"
                # Estimate calories per item based on score category
                item_cal = 89 if score_val < 3.0 else 220 if score_val < 7.0 else 320
                col_item, col_del = st.columns([6, 0.5])
                with col_item:
                    st.markdown(f"""
                        <div style='display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid {C["border"]};'>
                            <div style='display:flex; align-items:center; gap:10px;'>
                                <div style='width:8px; height:8px; border-radius:50%; background:{clr};'></div>
                                <div>
                                    <span style='font-size:0.9rem;'>{name}</span>
                                    <span style='font-size:0.7rem; color:{C["text_muted"]}; margin-left:8px;'>~{item_cal} cal</span>
                                </div>
                            </div>
                            <strong style='color:{clr}; font-size:0.9rem;'>{score_display}</strong>
                        </div>
                    """, unsafe_allow_html=True)
                with col_del:
                    if st.button("🗑", key=f"mp_del_{iid}", help="Delete"):
                        delete_item_db(iid)
                        st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='color:{C['text_muted']}; font-size:0.9rem; padding:20px;'>No grocery hauls yet. Scan items in the Grocery Planner to get started!</div>", unsafe_allow_html=True)

    # AI Meal Planning Agent
    st.markdown(f"<div style='height:16px;'></div>", unsafe_allow_html=True)
    col_mp1, col_mp2 = st.columns([3, 1])
    with col_mp1:
        st.markdown(f"<h4 style='font-weight:700;'>AI Meal Planning</h4>", unsafe_allow_html=True)
    with col_mp2:
        if st.session_state.meal_plan:
            if st.button("Clear", key="clear_meal_plan", use_container_width=True):
                st.session_state.meal_plan = None; st.rerun()

    if st.session_state._loading_meal_plan:
        st.markdown(f"""<div class='ai-loading' style='padding:24px;'>
            <div class='ai-loading-text'>Hold on...fetching details</div>
            <div class='ai-loading-sub'>Crafting your personalized 7-day meal plan</div>
        </div>""", unsafe_allow_html=True)
        try:
            history_data = get_log_history_db(st.session_state.user_id)
            plan = generate_meal_plan(history_data, st.session_state.user_id)
            if plan:
                st.session_state.meal_plan = plan
            else: st.warning("Could not generate meal plan.")
        except Exception as e: st.error(f"Error: {e}")
        st.session_state._loading_meal_plan = False
        st.rerun()
    elif not st.session_state.meal_plan:
        st.markdown(f"<div style='color:{C['text_sec']}; font-size:0.85rem; margin-bottom:8px;'>Based on what you've been buying, get a personalized 7-day meal plan tailored to your grocery hauls.</div>", unsafe_allow_html=True)
        if st.button("Generate AI Meal Plan", use_container_width=True, type="primary"):
            st.session_state._loading_meal_plan = True
            st.rerun()

    if st.session_state.meal_plan:
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        plan = st.session_state.meal_plan
        today_str = datetime.now().strftime("%Y-%m-%d")

        for day_name in day_order:
            meals = plan.get(day_name, [])
            if not meals: continue
            with st.expander(f"{day_name}", expanded=False):
                for midx, meal in enumerate(meals):
                    meal_type = meal.get('meal', 'Meal')
                    meal_name = meal.get('name', 'Unknown')
                    est_score = round(meal.get('estimated_score', 5.0), 1)
                    clr = score_color(est_score)
                    col_meal, col_score, col_add = st.columns([3, 1, 0.6])
                    with col_meal:
                        st.markdown(f"**{meal_type}:** {meal_name}")
                    with col_score:
                        st.markdown(f"<div style='text-align:center; color:{clr}; font-weight:bold;'>{est_score}</div>", unsafe_allow_html=True)
                    with col_add:
                        if st.button("+", key=f"mp_{day_name}_{midx}", help=f"Add {meal_name} to today"):
                            add_calendar_item_db(st.session_state.user_id, today_str, meal_name, est_score)
                            st.success("Added!")
                            time.sleep(0.5)
                            st.rerun()
