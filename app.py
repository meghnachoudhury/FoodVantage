import streamlit as st
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
    calculate_vms_science, get_serving_scale, get_scientific_db,
    search_vantage_db, search_open_food_facts, vision_live_scan_dark,
    generate_health_insights, generate_meal_plan, generate_daily_recipes,
    get_db_connection, get_trend_data_db, get_all_calendar_data_db,
    get_gemini_api_key, authenticate_user,
    add_calendar_item_db, get_calendar_items_db, delete_item_db,
    get_log_history_db, create_user,
    vms_to_health_score, calculate_overall_health_score, calculate_day_streak,
    get_total_items_logged, get_items_today
)
from streamlit_back_camera_input import back_camera_input

st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")

# --- SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = True
if 'user_id' not in st.session_state: st.session_state.user_id = "demo_user"
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'selected_result' not in st.session_state: st.session_state.selected_result = None
if 'scanning' not in st.session_state: st.session_state.scanning = False
if 'scan_count' not in st.session_state: st.session_state.scan_count = 0
if 'trends_view' not in st.session_state: st.session_state.trends_view = 'weekly'
if 'scan_status' not in st.session_state: st.session_state.scan_status = None
if 'detected_items' not in st.session_state: st.session_state.detected_items = []
if 'ai_insights' not in st.session_state: st.session_state.ai_insights = None
if 'meal_plan' not in st.session_state: st.session_state.meal_plan = None
if 'daily_recipes' not in st.session_state: st.session_state.daily_recipes = None
if 'recipes_date' not in st.session_state: st.session_state.recipes_date = None

# --- DARK THEME COLOR PALETTE ---
C = {
    'bg': '#0F1117',
    'bg_card': '#1A1D25',
    'bg_elevated': '#222630',
    'bg_input': '#1E2230',
    'sidebar_bg': '#141720',
    'teal': '#5B9B9D',
    'teal_light': '#7EC8CA',
    'olive': '#5B8C3E',
    'text': '#E8EAF0',
    'text_sec': '#9CA3B0',
    'text_muted': '#6B7280',
    'green': '#4CAF50',
    'yellow': '#F9A825',
    'red': '#E53935',
    'orange': '#E8967A',
    'border': '#2A2E38',
    'streak_bg': '#1C2030',
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
        box-shadow: 0 0 0 2px rgba(91,155,157,0.2) !important;
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
        background: linear-gradient(135deg, {C['teal']} 0%, #4A8A8C 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.5rem !important;
        transition: all 0.2s ease !important;
        letter-spacing: 0.1px;
    }}
    .stButton > button:hover {{
        box-shadow: 0 4px 16px rgba(91,155,157,0.3) !important;
        transform: translateY(-1px) !important;
    }}
    .stButton > button[kind="secondary"] {{
        background: {C['bg_elevated']} !important;
        border: 1px solid {C['border']} !important;
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
        color: {C['text_sec']} !important;
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
    @keyframes scanner-flicker {{
        0%, 100% {{ opacity: 0.35; }}
        50% {{ opacity: 1; }}
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
        animation: scanner-flicker 2.5s ease-in-out infinite;
    }}
    .corner-tl {{ top: 28px; left: 28px; border-width: 3px 0 0 3px; border-radius: 6px 0 0 0; }}
    .corner-tr {{ top: 28px; right: 28px; border-width: 3px 3px 0 0; border-radius: 0 6px 0 0; }}
    .corner-bl {{ bottom: 28px; left: 28px; border-width: 0 0 3px 3px; border-radius: 0 0 0 6px; }}
    .corner-br {{ bottom: 28px; right: 28px; border-width: 0 3px 3px 0; border-radius: 0 0 6px 0; }}
    .scanner-icon {{
        width: 64px; height: 64px;
        border-radius: 50%;
        background: rgba(91,155,157,0.15);
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
        color: {C['text_muted']};
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
        color: {C['text']};
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
        color: {C['text']};
    }}
    .streak-stat-label {{
        font-size: 0.65rem;
        color: {C['text_muted']};
        margin-top: 2px;
    }}

    /* === TREND TABS (compact in right column) === */
    .trend-tabs-compact .stButton > button {{
        background: {C['bg_elevated']} !important;
        border: 1px solid {C['border']} !important;
        border-radius: 8px !important;
        font-size: 0.8rem !important;
        padding: 0.3rem 0.6rem !important;
    }}
    .trend-tabs-compact .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {C['teal']} 0%, #4A8A8C 100%) !important;
        border: none !important;
        border-radius: 14px !important;
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
    .nav-btn:hover {{ background: rgba(91,155,157,0.1); color: {C['text']}; }}
    .nav-btn.active {{
        background: rgba(91,155,157,0.15);
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
        background: rgba(91,155,157,0.1) !important;
        color: {C['text']} !important;
        transform: none !important;
        box-shadow: none !important;
    }}
    .sidebar-nav .stButton > button[kind="primary"] {{
        background: rgba(91,155,157,0.15) !important;
        color: {C['teal_light']} !important;
        font-weight: 600 !important;
        box-shadow: none !important;
    }}
    </style>
""", unsafe_allow_html=True)

def render_logo(size="1.6rem"):
    st.markdown(f"""<div style='margin-bottom: 6px;'>
        <span style='font-size: {size}; font-weight: 800; color: {C["text"]};'>foodvantage</span><span style='font-size: {size}; font-weight: 800; color: {C["teal"]};'>.</span>
    </div>""", unsafe_allow_html=True)

def create_html_calendar(year, month, selected_day=None, logged_days=None):
    logged_days = logged_days or set()
    cal = cal_module.monthcalendar(year, month)
    html = "<table style='width:100%; text-align:center; border-collapse: separate; border-spacing: 4px;'><thead><tr>"
    for day in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]:
        html += f"<th style='color:{C['text_muted']}; font-size:0.75rem; font-weight:600; padding:6px;'>{day}</th>"
    html += "</tr></thead><tbody>"
    for week in cal:
        html += "<tr>"
        for day in week:
            if day == 0:
                html += "<td></td>"
            else:
                is_selected = day == selected_day
                is_logged = day in logged_days
                if is_selected:
                    style = f"background:{C['teal']}; color:white; border-radius:10px; font-weight:700;"
                elif is_logged:
                    style = f"color:{C['text']}; font-weight:600; position:relative;"
                else:
                    style = f"color:{C['text_sec']};"
                dot = f"<div style='width:4px;height:4px;border-radius:50%;background:{C['teal']};margin:2px auto 0;'></div>" if is_logged and not is_selected else ""
                html += f"<td style='padding:8px; font-size:0.85rem; {style}'>{day}{dot}</td>"
        html += "</tr>"
    return html + "</tbody></table>"


# ============================
# SIDEBAR
# ============================
with st.sidebar:
    render_logo(size="1.5rem")
    st.markdown(f"<div style='height:12px;'></div>", unsafe_allow_html=True)

    # Quick Score Check
    st.markdown(f"<div style='font-size:0.7rem; font-weight:700; color:{C['text_muted']}; letter-spacing:1px; text-transform:uppercase; margin-bottom:6px;'>Quick Score Check</div>", unsafe_allow_html=True)
    search_q = st.text_input("Search any food item", key="sidebar_search", placeholder="Type a food name...", label_visibility="collapsed")
    if search_q:
        results = search_vantage_db(search_q, limit=5)
        filtered_results = [r for r in results if r['vms_score'] != 10.0] if results else []
        if filtered_results:
            for d in filtered_results[:3]:
                h_score = vms_to_health_score(d['vms_score'])
                clr = score_color(h_score, 'health')
                st.markdown(f"<div style='padding:4px 0; display:flex; justify-content:space-between;'><span style='font-size:0.8rem; color:{C['text_sec']};'>{d['name'][:30]}</span><strong style='color:{clr}; font-size:0.8rem;'>{h_score}/100</strong></div>", unsafe_allow_html=True)
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
            st.session_state.page = pg
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # Streak Card at bottom
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
# DASHBOARD PAGE
# ============================
if st.session_state.page == 'dashboard':
    # Header
    now = datetime.now()
    st.markdown(f"""
        <div style='margin-bottom:4px;'>
            <h2 style='margin:0; font-weight:800; font-size:1.8rem;'>Dashboard</h2>
            <div style='color:{C["text_muted"]}; font-size:0.85rem;'>{now.strftime('%A, %B %d, %Y')}</div>
            <div style='color:{C["teal"]}; font-size:0.95rem; font-weight:600; margin-top:2px;'>Plan your food before you buy. &middot; Track smarter. Live better.</div>
        </div>
    """, unsafe_allow_html=True)

    # Stat cards
    overall_score = calculate_overall_health_score(st.session_state.user_id)
    day_streak = calculate_day_streak(st.session_state.user_id)
    items_today = get_items_today(st.session_state.user_id)
    sc = score_color(overall_score, 'health')

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
        </div>
    """, unsafe_allow_html=True)

    # Active Focus Scanner
    st.markdown(f"<h3 style='font-weight:700; margin-top:24px;'>&#128722; Grocery Scanner</h3>", unsafe_allow_html=True)

    if not st.session_state.camera_active:
        # Scanner viewfinder
        st.markdown(f"""
            <div class='scanner-viewfinder'>
                <div class='scanner-corner corner-tl'></div>
                <div class='scanner-corner corner-tr'></div>
                <div class='scanner-corner corner-bl'></div>
                <div class='scanner-corner corner-br'></div>
                <div class='scanner-icon'><i class='fa-solid fa-camera'></i></div>
                <div style='font-size:1rem; font-weight:600; color:{C["text"]}; margin-bottom:4px;'>Scanner ready</div>
                <div style='font-size:0.8rem; color:{C["text_muted"]};'>Tap below to begin live scanning</div>
            </div>
        """, unsafe_allow_html=True)
        if st.button("Start Live Scan", type="primary", use_container_width=True):
            st.session_state.camera_active = True
            st.session_state.scanning = True
            st.session_state.scan_count = 0
            st.session_state.scan_results = None
            st.session_state.selected_result = None
            st.session_state.scan_status = None
            st.session_state.detected_items = []
            st.rerun()
    else:
        # Scanner active - show HUD
        if st.session_state.selected_result:
            ls = st.session_state.selected_result
            clr = score_color(ls['vms_score'])
            portion_label = " /serving" if needs_portion_size(ls['name']) else ""
            st.markdown(f"""
                <div class="hud-bubble">
                    <div style="font-size: 0.85rem; margin-bottom: 4px; color:{C['text_sec']};">{ls['name']}</div>
                    <div style="color:{clr}; font-size:2rem; font-weight:900;">{round(ls['vms_score'], 1)}{portion_label}</div>
                    <div style="font-size: 0.75rem; color:{clr};">{ls['rating']}</div>
                </div>
            """, unsafe_allow_html=True)
        elif st.session_state.get('scan_status') == "analyzing":
            st.markdown(f"""
                <div class="hud-bubble">
                    <div style="font-size: 1.1rem; font-weight: 700; color:{C['text']};">Analyzing Image...</div>
                    <div style="font-size: 0.8rem; color:{C['text_muted']}; margin-top: 4px;">Processing with AI</div>
                </div>
            """, unsafe_allow_html=True)
        elif st.session_state.get('detected_items'):
            items_text = ", ".join(st.session_state.detected_items[:3])
            st.markdown(f"""
                <div class="hud-bubble">
                    <div style="font-size: 1.1rem; font-weight: 700; color:{C['text']};">Items Detected</div>
                    <div style="font-size: 0.9rem; color:{C['teal']}; margin-top: 4px;">{items_text}</div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown(f"""
            <div style="text-align: center; margin: 16px 0;">
                <div style='background:{C["bg_card"]}; padding:10px 20px; border-radius:12px; display:inline-block; border:1px solid {C["border"]};'>
                    <i class='fa-solid fa-camera' style='color:{C["teal"]};'></i>
                    <span style='color:{C["text_sec"]}; margin-left:8px; font-weight:500;'>Point camera at item and tap to scan</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        image = back_camera_input(key="hud_cam")

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Stop Scanning", use_container_width=True):
                st.session_state.camera_active = False
                st.session_state.scan_results = None
                st.session_state.selected_result = None
                st.session_state.scanning = False
                st.session_state.scan_status = None
                st.session_state.detected_items = []
                st.rerun()

        # Scanning logic
        if image and st.session_state.scanning:
            st.session_state.scan_count += 1
            if st.session_state.scan_count % 2 == 0:
                st.session_state.scan_status = "analyzing"
                results = vision_live_scan_dark(image)
                if results:
                    st.session_state.scan_results = results
                    st.session_state.selected_result = results[0]
                    st.session_state.detected_items = [r['name'] for r in results[:5]]
                    st.session_state.scanning = False
                    st.session_state.scan_status = None
                else:
                    st.session_state.scan_status = None
                st.rerun()

    # Scan results
    if st.session_state.scan_results:
        st.markdown(f"<h4 style='font-weight:700;'>Select Your Item</h4>", unsafe_allow_html=True)
        st.markdown(f"<div style='color:{C['text_sec']}; font-size:0.85rem; margin-bottom:8px;'>Found {len(st.session_state.scan_results)} items in frame</div>", unsafe_allow_html=True)

        st.markdown('<div class="results-scroll-container">', unsafe_allow_html=True)
        for i, result in enumerate(st.session_state.scan_results):
            clr = score_color(result['vms_score'])
            selected = st.session_state.selected_result == result
            portion_label = " /serving" if needs_portion_size(result['name']) else ""
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(f"{i+1}. {result['name']}", key=f"select_{i}",
                             type="primary" if selected else "secondary", use_container_width=True):
                    st.session_state.selected_result = result
                    st.rerun()
            with col2:
                st.markdown(f"<div style='text-align:center; color:{clr}; font-size:1.3rem; font-weight:bold; padding-top:4px;'>{round(result['vms_score'], 1)}{portion_label}</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Deep dive
    if st.session_state.selected_result:
        with st.expander("Metabolic Nutrient Deep Dive", expanded=True):
            ls_raw = st.session_state.selected_result['raw']
            item_name = st.session_state.selected_result['name']
            scale = get_serving_scale(item_name)
            if scale < 1.0:
                serving_g = int(scale * 100)
                st.markdown(f"**Clinical Data** *(per serving ~{serving_g}g)*")
            else:
                st.markdown("**Clinical Data** *(per 100g)*")

            c1, c2, c3 = st.columns(3)
            c1.metric("Calories", f"{round(float(ls_raw[2] or 0) * scale, 1)}")
            c2.metric("Sugar", f"{round(float(ls_raw[3] or 0) * scale, 1)}g")
            c3.metric("Fiber", f"{round(float(ls_raw[4] or 0) * scale, 1)}g")
            c4, c5, c6 = st.columns(3)
            c4.metric("Protein", f"{round(float(ls_raw[5] or 0) * scale, 1)}g")
            c5.metric("Fat", f"{round(float(ls_raw[6] or 0) * scale, 1)}g")
            c6.metric("Sodium", f"{round(float(ls_raw[7] or 0) * scale, 1)}mg")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Add to This Haul", use_container_width=True):
                    add_calendar_item_db(
                        st.session_state.user_id,
                        datetime.now().strftime("%Y-%m-%d"),
                        st.session_state.selected_result['name'],
                        round(st.session_state.selected_result['vms_score'], 1)
                    )
                    st.success("Added!")
            with col2:
                if st.button("Scan Again", use_container_width=True):
                    st.session_state.scan_results = None
                    st.session_state.selected_result = None
                    st.session_state.scanning = True
                    st.session_state.detected_items = []
                    st.rerun()

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

        # Line chart matching Figma design
        fig = go.Figure()
        if 'healthy' in df_pivot.columns:
            fig.add_trace(go.Scatter(x=df_pivot.index, y=df_pivot['healthy'], name='Healthy',
                                     mode='lines+markers', line=dict(color=C['teal'], width=2.5, shape='spline'),
                                     marker=dict(size=6), fill='tozeroy',
                                     fillcolor='rgba(91,155,157,0.1)',
                                     hovertemplate='%{y} healthy<extra></extra>'))
        if 'moderate' in df_pivot.columns:
            fig.add_trace(go.Scatter(x=df_pivot.index, y=df_pivot['moderate'], name='Moderate',
                                     mode='lines+markers', line=dict(color=C['yellow'], width=2, shape='spline'),
                                     marker=dict(size=5),
                                     hovertemplate='%{y} moderate<extra></extra>'))
        if 'unhealthy' in df_pivot.columns:
            fig.add_trace(go.Scatter(x=df_pivot.index, y=df_pivot['unhealthy'], name='Unhealthy',
                                     mode='lines+markers', line=dict(color=C['red'], width=2, shape='spline'),
                                     marker=dict(size=5),
                                     hovertemplate='%{y} unhealthy<extra></extra>'))

        fig.update_layout(
            height=280,
            margin=dict(l=16, r=16, t=8, b=32),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, showline=False, tickfont=dict(color=C['text_muted']), color=C['text_muted']),
            yaxis=dict(showgrid=True, gridcolor=C['border'], showline=False, tickfont=dict(color=C['text_muted']), color=C['text_muted']),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(color=C['text_sec'])),
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)

        total_items_trend = int(df['count'].sum())
        healthy_count = int(df[df['category'] == 'healthy']['count'].sum()) if 'healthy' in df['category'].values else 0
        st.markdown(f"<div style='color:{C['text_sec']}; font-size:0.85rem;'>Total items: <strong>{total_items_trend}</strong> &middot; Healthy choices: <strong style='color:{C['green']};'>{healthy_count}</strong></div>", unsafe_allow_html=True)

        # AI Health Coach & Healthy Recipes - side by side cards
        st.markdown(f"<div style='height:20px;'></div>", unsafe_allow_html=True)
        col_coach, col_recipes = st.columns(2)

        with col_coach:
            st.markdown(f"""
                <div class='card' style='min-height:200px;'>
                    <div style='display:flex; align-items:center; gap:10px; margin-bottom:12px;'>
                        <div style='width:36px; height:36px; border-radius:10px; background:rgba(91,155,157,0.15); display:flex; align-items:center; justify-content:center;'>
                            <i class='fa-solid fa-heart-pulse' style='color:{C["teal"]}; font-size:1rem;'></i>
                        </div>
                        <div>
                            <div style='font-weight:700; font-size:0.95rem;'>Grocery Health Coach</div>
                            <div style='font-size:0.7rem; color:{C["text_muted"]};'>Score your shopping habits</div>
                        </div>
                    </div>
            """, unsafe_allow_html=True)

            if st.session_state.ai_insights:
                for i, insight in enumerate(st.session_state.ai_insights[:2]):
                    emoji = insight.get('emoji', '')
                    title = insight.get('title', 'Insight')
                    body = insight.get('insight', '')
                    st.markdown(f"<div style='font-size:0.8rem; margin-bottom:8px;'><strong>{emoji} {title}</strong><br><span style='color:{C['text_sec']};'>{body[:120]}</span></div>", unsafe_allow_html=True)
                if st.button("Refresh Insights", key="refresh_insights", use_container_width=True):
                    st.session_state.ai_insights = None; st.rerun()
            else:
                if st.button("🧠  Get AI Insights", use_container_width=True, type="primary", key="get_insights_btn"):
                    with st.spinner("Analyzing your patterns..."):
                        try:
                            insights = generate_health_insights(raw, all_data, days)
                            if insights:
                                st.session_state.ai_insights = insights; st.rerun()
                            else: st.warning("Could not generate insights.")
                        except Exception as e: st.error(f"Error: {e}")

            st.markdown("</div>", unsafe_allow_html=True)

        with col_recipes:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if st.session_state.recipes_date != today_str:
                st.session_state.daily_recipes = None
                st.session_state.recipes_date = today_str

            st.markdown(f"""
                <div class='card' style='min-height:200px;'>
                    <div style='display:flex; align-items:center; gap:10px; margin-bottom:12px;'>
                        <div style='width:36px; height:36px; border-radius:10px; background:rgba(91,140,62,0.15); display:flex; align-items:center; justify-content:center;'>
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
                    st.markdown(f"<div style='font-size:0.8rem; margin-bottom:8px;'><strong>{r_name}</strong><br><span style='color:{C['text_muted']}; font-size:0.7rem;'>{r_type} &middot; {r_time}</span></div>", unsafe_allow_html=True)
                if st.button("New Recipes", key="refresh_recipes", use_container_width=True):
                    st.session_state.daily_recipes = None; st.rerun()
            else:
                if st.button("🌿  Discover Recipes", use_container_width=True, type="primary", key="discover_recipes_btn"):
                    with st.spinner("Finding healthy recipes..."):
                        try:
                            recipes = generate_daily_recipes()
                            if recipes:
                                st.session_state.daily_recipes = recipes
                                st.session_state.recipes_date = today_str
                                st.rerun()
                            else: st.warning("Could not load recipes.")
                        except Exception as e: st.error(f"Error: {e}")

            st.markdown("</div>", unsafe_allow_html=True)

    else:
        if all_data and len(all_data) > 0:
            st.info(f"You have {len(all_data)} logged items, but none in the last {days} day(s). Try a different time range.")
        else:
            st.info("No grocery hauls yet. Use the Grocery Scanner or Grocery Planner to log your first haul!")


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

    c1, c2 = st.columns([1, 1.5])

    with c1:
        sel_date = st.date_input("Select Date", datetime.now(), label_visibility="collapsed")
        # Get logged days for current month
        logged_days_in_month = set()
        for d in unique_dates:
            if hasattr(d, 'year') and d.year == sel_date.year and d.month == sel_date.month:
                logged_days_in_month.add(d.day)
        st.markdown(f"<div class='card'>{create_html_calendar(sel_date.year, sel_date.month, sel_date.day, logged_days_in_month)}</div>", unsafe_allow_html=True)

    with c2:
        items = get_calendar_items_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"))
        item_count = len(items) if items else 0
        st.markdown(f"""
            <div style='margin-bottom:16px;'>
                <h4 style='font-weight:700; margin:0;'>{sel_date.strftime('%b %d, %Y')}</h4>
                <div style='color:{C["text_muted"]}; font-size:0.8rem;'>{item_count} item{"s" if item_count != 1 else ""} in haul</div>
            </div>
        """, unsafe_allow_html=True)

        # Add item
        st.markdown(f"<div style='font-size:0.75rem; font-weight:600; color:{C['text_muted']}; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;'>Add to This Haul</div>", unsafe_allow_html=True)
        search_item = st.text_input("Search for an item", key="calendar_search", placeholder="e.g., banana, avocado...", label_visibility="collapsed")

        if search_item:
            search_results = search_vantage_db(search_item, limit=10)
            filtered_results = [r for r in search_results if r['vms_score'] != 10.0] if search_results else []
            if filtered_results:
                st.markdown('<div class="results-scroll-container">', unsafe_allow_html=True)
                for idx, result in enumerate(filtered_results):
                    clr = score_color(result['vms_score'])
                    col_a, col_b, col_c = st.columns([3, 1, 0.6])
                    with col_a:
                        st.markdown(f"<span style='font-size:0.9rem;'>{result['name']}</span>", unsafe_allow_html=True)
                    with col_b:
                        st.markdown(f"<div style='text-align:center; color:{clr}; font-weight:bold;'>{round(result['vms_score'], 1)}</div>", unsafe_allow_html=True)
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
                        <div class='friendly-error-title'>Item Not Found Yet</div>
                        <div class='friendly-error-text'>Our database is growing every day! Try a different search term.</div>
                    </div>
                """, unsafe_allow_html=True)

        # Items for this day
        st.markdown(f"<div style='height:12px;'></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:0.75rem; font-weight:600; color:{C['text_muted']}; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;'>Items in This Haul</div>", unsafe_allow_html=True)
        if items:
            for iid, name, score_val, cat in items:
                clr = score_color(score_val)
                col_item, col_del = st.columns([5, 1])
                with col_item:
                    st.markdown(f"""
                        <div class='list-row'>
                            <div style='display:flex; align-items:center; gap:10px;'>
                                <div style='width:8px; height:8px; border-radius:50%; background:{clr};'></div>
                                <span style='font-size:0.9rem;'>{name}</span>
                            </div>
                            <strong style='color:{clr}; font-size:0.9rem;'>{round(score_val, 1)}</strong>
                        </div>
                    """, unsafe_allow_html=True)
                with col_del:
                    if st.button("🗑", key=f"del_{iid}", help="Delete"):
                        delete_item_db(iid)
                        st.rerun()
        else:
            st.markdown(f"<div style='color:{C['text_muted']}; font-size:0.85rem; padding:12px;'>No grocery haul logged for this date. Search above to add items before you shop!</div>", unsafe_allow_html=True)


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
                clr = score_color(score_val)
                # Show +/- prefix for VMS scores
                score_prefix = "+" if score_val >= 0 else ""
                score_display = f"{score_prefix}{round(score_val, 1)}"
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

    if not st.session_state.meal_plan:
        st.markdown(f"<div style='color:{C['text_sec']}; font-size:0.85rem; margin-bottom:8px;'>Based on what you've been buying, get a personalized 7-day meal plan tailored to your grocery hauls.</div>", unsafe_allow_html=True)
        if st.button("Generate AI Meal Plan", use_container_width=True, type="primary"):
            with st.spinner("Crafting your personalized meal plan..."):
                try:
                    history_data = get_log_history_db(st.session_state.user_id)
                    plan = generate_meal_plan(history_data, st.session_state.user_id)
                    if plan:
                        st.session_state.meal_plan = plan; st.rerun()
                    else: st.warning("Could not generate meal plan.")
                except Exception as e: st.error(f"Error: {e}")

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
