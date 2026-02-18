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
    get_log_history_db, create_user
)
from streamlit_back_camera_input import back_camera_input

st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")

# --- SESSION STATE ---
# FIX 1: NO LOGIN PAGE - Direct to main app
if 'logged_in' not in st.session_state: st.session_state.logged_in = True
if 'user_id' not in st.session_state: st.session_state.user_id = "demo_user"
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'selected_result' not in st.session_state: st.session_state.selected_result = None
if 'scanning' not in st.session_state: st.session_state.scanning = False
if 'scan_count' not in st.session_state: st.session_state.scan_count = 0
if 'trends_view' not in st.session_state: st.session_state.trends_view = 'weekly'
# FIX 6: Status tracking for in-widget display
if 'scan_status' not in st.session_state: st.session_state.scan_status = None
if 'detected_items' not in st.session_state: st.session_state.detected_items = []
# AI Agent state
if 'ai_insights' not in st.session_state: st.session_state.ai_insights = None
if 'meal_plan' not in st.session_state: st.session_state.meal_plan = None
if 'daily_recipes' not in st.session_state: st.session_state.daily_recipes = None
if 'recipes_date' not in st.session_state: st.session_state.recipes_date = None

# --- BACKGROUND IMAGE ---
_bg_path = os.path.join(os.path.dirname(__file__), "assets", "image_1010.png")
if os.path.exists(_bg_path):
    with open(_bg_path, "rb") as _f:
        _bg_b64 = base64.b64encode(_f.read()).decode()
else:
    _bg_b64 = ""

# --- COLOR PALETTE (Grocery Template) ---
COLORS = {
    'olive': '#7BD0E7',
    'terracotta': '#7BD0E7',
    'salmon': '#A7E8F5',
    'beige': '#04060D',
    'dark_text': '#E9EEF7',
    'green': '#4CC38A',
    'yellow': '#D8A66A',
    'red': '#E87474',
    'camera_icon': '#7BD0E7',
    'toggle_button': '#8C74CC',
    'unhealthy_bar': '#6B3240',
    'card_bg': '#0C111D',
    'border': '#1B2436',
}

# FIX 2 & 5: Helper function to determine if item needs portion size
def needs_portion_size(item_name):
    """
    Returns True if item should show 'per serving' label.
    
    SHOW portion size for: Packaged goods (oils, chips, cereals, etc.)
    DON'T show for: Fresh produce, cooked meals, superfoods
    """
    item_lower = item_name.lower()
    
    # Cooked food keywords - NO portion size
    cooked_keywords = [
        'cooked', 'grilled', 'fried', 'baked', 'roasted', 'steamed', 
        'boiled', 'sauteed', 'plate', 'meal', 'dish', 'curry', 'stew',
        'soup', 'salad', 'pasta', 'rice', 'noodle', 'stir fry', 'pizza',
        'burger', 'sandwich', 'wrap', 'taco', 'burrito', 'bowl'
    ]
    
    # Fresh produce - NO portion size (whole items)
    fresh_keywords = [
        'apple', 'banana', 'orange', 'grape', 'strawberry', 'avocado',
        'tomato', 'cucumber', 'carrot', 'lettuce', 'spinach', 'kale',
        'berry', 'peach', 'pear', 'plum', 'mango', 'melon', 'lemon',
        'lime', 'onion', 'garlic', 'pepper', 'broccoli', 'cauliflower',
        'fresh', 'whole', 'raw', 'fruit', 'vegetable'
    ]
    
    # Superfoods - NO portion size
    superfood_keywords = [
        'superfood', 'chia', 'flax', 'hemp', 'spirulina', 'acai',
        'goji', 'matcha', 'turmeric', 'ginger'
    ]
    
    # Check exclusions first
    for keyword in cooked_keywords + fresh_keywords + superfood_keywords:
        if keyword in item_lower:
            return False
    
    # Everything else (packaged goods) = show portion size
    return True

# --- CSS (Grocery Template Theme) ---
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">', unsafe_allow_html=True)
st.markdown('<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Source+Serif+4:wght@600;700&display=swap" rel="stylesheet">', unsafe_allow_html=True)
st.markdown(f"""
    <style>
    /* === GLOBAL === */
    .stApp {{
        background: radial-gradient(circle at top right, #0B1528 0%, #05070D 45%, #03050A 100%);
        color: #E7ECF8;
        font-family: 'Inter', sans-serif;
    }}

    .stApp::before {{
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-image: url("data:image/png;base64,{_bg_b64}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        opacity: 0.08;
        pointer-events: none;
        z-index: 0;
    }}

    .block-container {{
        padding-top: 2rem;
    }}

    h1, h2, h3, h4, h5, h6, p, div, label {{
        font-family: 'Inter', sans-serif !important;
        color: #E7ECF8;
    }}

    .logo-text {{
        font-family: 'Source Serif 4', serif !important;
        font-size: 2rem;
        text-align: left;
        font-weight: 700;
        letter-spacing: -0.6px;
        color: #F6F8FF;
        white-space: nowrap;
        line-height: 1.1;
    }}

    .logo-dot {{ color: {COLORS['olive']}; }}

    .subtitle {{
        color: #627090;
        margin-top: -8px;
        margin-bottom: 14px;
        font-size: 1.35rem;
        font-weight: 500;
    }}

    .card {{
        background: linear-gradient(145deg, #0E1220 0%, #0C101B 100%);
        padding: 24px;
        border-radius: 24px;
        border: 1px solid {COLORS['border']};
        box-shadow: 0 12px 30px rgba(2, 6, 15, 0.45);
        margin-bottom: 20px;
    }}

    .white-shelf {{
        background: linear-gradient(135deg, #111626 0%, #111726 100%);
        height: 35px;
        border-radius: 14px;
        border: 1px solid {COLORS['border']};
        margin-bottom: 25px;
    }}

    .tomato-wrapper {{ width: 100%; text-align: center; padding: 30px 0; }}
    .tomato-icon {{ font-size: 150px !important; color: {COLORS['camera_icon']} !important; opacity: 0.8; }}

    /* === INPUTS === */
    input[type="text"], input[type="password"] {{
        background-color: #141A2A !important;
        color: #ECF3FF !important;
        border: 1.5px solid {COLORS['border']} !important;
        border-radius: 14px !important;
        padding: 12px 16px !important;
        font-family: 'Inter', sans-serif !important;
    }}

    input[type="text"]:focus, input[type="password"]:focus {{
        border-color: {COLORS['olive']} !important;
        box-shadow: 0 0 0 2px rgba(123,208,231,0.2) !important;
    }}

    .stTextInput > div > div > input {{
        background-color: #141A2A !important;
        color: #ECF3FF !important;
        -webkit-text-fill-color: #ECF3FF !important;
        font-family: 'Inter', sans-serif !important;
    }}

    /* === BUTTONS === */
    .stButton > button {{
        background: linear-gradient(90deg, #5E95A6 0%, #6FAEBF 100%) !important;
        color: #F5FBFF !important;
        border: 1px solid rgba(123, 208, 231, 0.35) !important;
        border-radius: 14px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        padding: 0.62rem 1rem !important;
        transition: all 0.2s ease !important;
        letter-spacing: 0.1px;
    }}

    .stButton > button:hover {{
        background: linear-gradient(90deg, #6CA7B8 0%, #7EB9C8 100%) !important;
        box-shadow: 0 6px 18px rgba(76, 150, 173, 0.35) !important;
        transform: translateY(-1px) !important;
    }}

    .stButton > button[kind="secondary"] {{
        background: #111827 !important;
        color: #A9B6D0 !important;
        border: 1px solid {COLORS['border']} !important;
    }}

    .stHorizontalBlock div[data-testid="column"] .stButton > button {{
        border-radius: 12px !important;
    }}

    /* === METRICS === */
    [data-testid="stMetricValue"] {{
        color: #EFF4FF !important;
        font-weight: 700 !important;
        font-size: 1.5rem !important;
        font-family: 'Inter', sans-serif !important;
    }}

    [data-testid="stMetricLabel"] {{
        color: #8B99B3 !important;
        font-weight: 600 !important;
        font-family: 'Inter', sans-serif !important;
    }}

    /* === EXPANDERS === */
    .stExpander {{
        background: #0F1422 !important;
        color: #E7ECF8 !important;
        border-radius: 16px !important;
        border: 1px solid {COLORS['border']} !important;
    }}

    .stExpander p, .stExpander div, .stExpander span {{
        color: #D7DEED !important;
    }}

    /* === HUD BUBBLE (Scanner Overlay) === */
    .hud-bubble {{
        position: fixed;
        top: calc(50% - 200px);
        left: 50%;
        transform: translateX(-50%);
        background: rgba(13, 19, 34, 0.96);
        padding: 16px 28px;
        border-radius: 50px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.45);
        border: 1px solid rgba(123,208,231,0.4);
        z-index: 1000;
        text-align: center;
        min-width: 220px;
        font-family: 'Inter', sans-serif;
    }}

    /* === SCROLLABLE RESULTS === */
    .results-scroll-container {{
        max-height: 400px;
        overflow-y: auto;
        padding-right: 10px;
    }}

    .results-scroll-container::-webkit-scrollbar {{
        width: 8px;
    }}

    .results-scroll-container::-webkit-scrollbar-track {{
        background: #0D1423;
        border-radius: 10px;
    }}

    .results-scroll-container::-webkit-scrollbar-thumb {{
        background: #2C3B57;
        border-radius: 10px;
    }}

    /* === SCANNER RESULTS === */
    .scanner-result {{
        background: #0F1525;
        padding: 16px;
        border-radius: 16px;
        margin: 12px 0;
        border-left: 4px solid {COLORS['olive']};
        font-family: 'Inter', sans-serif;
    }}

    .scanner-result-title {{
        color: #F1F5FF;
        font-weight: 700;
        font-size: 1.1rem;
        margin-bottom: 8px;
    }}

    .scanner-result-text {{
        color: #D9E2F5;
        font-weight: 600;
        font-size: 1.3rem;
        line-height: 1.6;
    }}

    /* === LIST ROWS === */
    .list-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px 16px;
        background: #131A2D;
        border-radius: 16px;
        border: 1px solid {COLORS['border']};
        margin-bottom: 8px;
        font-family: 'Inter', sans-serif;
    }}

    /* === TREND & INSIGHTS PANELS === */
    .trend-shell {{
        background: linear-gradient(145deg, #0C101B 0%, #0A0F1A 100%);
        border: 1px solid #1A2338;
        border-radius: 26px;
        padding: 22px 22px 12px 22px;
        margin-top: 12px;
        margin-bottom: 22px;
    }}

    .trend-title-row {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 6px;
    }}

    .trend-title {{
        font-size: 2.15rem;
        font-weight: 700;
        letter-spacing: -0.4px;
        color: #F2F6FF;
    }}

    .trend-sub {{
        color: #5F6E8D;
        font-size: 1.02rem;
        margin-bottom: 8px;
    }}

    .trend-tabs-container {{
        background: #121827;
        border: 1px solid #242F47;
        border-radius: 18px;
        padding: 6px;
        width: 100%;
    }}

    .trend-tabs-container .stButton > button {{
        background-color: transparent !important;
        color: #7D89A6 !important;
        border: none !important;
        border-radius: 14px !important;
        min-height: 44px;
    }}

    .trend-tabs-container .stButton > button[kind="primary"] {{
        background: #69AFC2 !important;
        color: #F5FBFF !important;
        font-weight: 700 !important;
    }}

    .trend-chart-note {{
        color: #5E6B88;
        font-size: 0.92rem;
        margin-bottom: 10px;
    }}

    .action-card {{
        background: linear-gradient(145deg, #0E1220 0%, #0C101A 100%);
        border: 1px solid #1A2338;
        border-radius: 26px;
        padding: 22px;
        min-height: 285px;
    }}

    .action-card-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
    }}

    .action-title {{
        color: #EEF3FF;
        font-size: 2.05rem;
        font-weight: 700;
    }}

    .action-chip {{
        color: #A998CF;
        border: 1px solid #473B65;
        background: rgba(51,40,75,0.45);
        border-radius: 999px;
        font-size: 0.9rem;
        font-weight: 600;
        padding: 4px 14px;
    }}

    .action-muted {{
        color: #667593;
        font-size: 1.02rem;
        line-height: 1.65;
        margin-bottom: 18px;
    }}

    .coach-list-item {{
        background: #121827;
        border: 1px solid #27324C;
        border-radius: 14px;
        padding: 10px 12px;
        margin-bottom: 8px;
    }}

    /* === SIDEBAR === */
    [data-testid="collapsedControl"] {{
        color: {COLORS['olive']} !important;
    }}

    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #080C16 0%, #050811 100%) !important;
        border-right: 1px solid #1A2236 !important;
    }}

    section[data-testid="stSidebar"] .stMarkdown h4,
    section[data-testid="stSidebar"] .stMarkdown h5,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label {{
        color: #8A97B3 !important;
    }}

    section[data-testid="stSidebar"] .stButton > button {{
        justify-content: flex-start;
        background: #0E1424 !important;
        color: #A4B2CD !important;
        border-radius: 16px !important;
        border: 1px solid #1E2A42 !important;
    }}

    section[data-testid="stSidebar"] .stButton > button:hover {{
        background: #101C2F !important;
    }}

    /* === FRIENDLY ERRORS === */
    .friendly-error {{
        background: #111726;
        border-left: 4px solid #476A97;
        padding: 16px;
        border-radius: 12px;
        margin: 12px 0;
        font-family: 'Inter', sans-serif;
    }}

    .friendly-error-title {{
        font-weight: 700;
        color: #BFD4F1;
        margin-bottom: 8px;
    }}

    .friendly-error-text {{
        color: #93A7C7;
        font-size: 0.9rem;
    }}

    /* === SCAN PROMPT BADGE === */
    .scan-prompt {{
        background: #101A2A;
        padding: 12px 20px;
        border-radius: 14px;
        display: inline-block;
        border: 1px solid #23304A;
        color: #C8D6ED;
    }}

    hr {{
        border-color: #1A2439;
    }}

    .stAlert {{
        background-color: #111726 !important;
        color: #C8D6ED !important;
        border: 1px solid #24324C !important;
    }}

    [data-testid="stSidebar"] [data-testid="stMetric"] {{
        background: #0D1322;
        border: 1px solid #1C2942;
        border-radius: 14px;
        padding: 8px 10px;
    }}

    .kicker {{
        color: #5C6884;
        text-transform: uppercase;
        letter-spacing: 1.6px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 6px;
    }}

    .metric-strip {{
        background: linear-gradient(160deg, #0F1526 0%, #0D1422 100%);
        border: 1px solid #1A2840;
        border-radius: 22px;
        padding: 18px;
        min-height: 120px;
    }}

    .metric-strip .metric-value {{
        font-size: 2.8rem;
        line-height: 1;
        font-weight: 700;
        color: #F3F6FF;
    }}

    .metric-strip .metric-note {{
        margin-top: 10px;
        color: #5FC696;
        font-size: 1.05rem;
        font-weight: 600;
    }}

    .sidebar-streak-card {{
        margin-top: 24px;
        padding: 14px;
        border-radius: 18px;
        border: 1px solid #1F2A42;
        background: linear-gradient(155deg, #111726 0%, #0D1321 100%);
    }}

    .sidebar-streak-title {{
        color: #EEF3FF;
        font-size: 1.55rem;
        font-weight: 700;
        margin-bottom: 2px;
    }}

    .sidebar-streak-sub {{
        color: #6F7E9E;
        font-size: 0.95rem;
        margin-bottom: 10px;
    }}

    .sidebar-progress-wrap {{
        width: 100%;
        height: 6px;
        background: #1E2840;
        border-radius: 999px;
        overflow: hidden;
    }}

    .sidebar-progress-fill {{
        height: 100%;
        background: linear-gradient(90deg, #F2B14C 0%, #E58D32 100%);
        border-radius: 999px;
    }}

    .sidebar-mini-stats {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-top: 10px;
    }}

    .stat-tile {{
        background: #0D1322;
        border: 1px solid #1E2942;
        border-radius: 14px;
        padding: 10px 8px;
        text-align: center;
    }}

    .stat-tile .v {{
        color: #EAF0FD;
        font-weight: 700;
        font-size: 1.15rem;
    }}

    .stat-tile .l {{
        color: #637290;
        font-size: 0.85rem;
        margin-top: 2px;
    }}

    </style>
""", unsafe_allow_html=True)

def render_logo(size="3rem"):
    st.markdown(f"<div style='margin-bottom: 8px;'><div class='logo-text' style='font-size: {size};'>foodvantage<span class='logo-dot'>.</span></div></div>", unsafe_allow_html=True)

def create_html_calendar(year, month, selected_day=None):
    cal = cal_module.monthcalendar(year, month)
    html = "<table style='width:100%; text-align:center;'><thead><tr>"
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]: html += f"<th style='color:{COLORS['terracotta']};'>{day}</th>"
    html += "</tr></thead><tbody>"
    for week in cal:
        html += "<tr>"
        for day in week:
            if day == 0: html += "<td></td>"
            else:
                style = f"background:{COLORS['terracotta']}; color:white; border-radius:50%;" if day == selected_day else ""
                html += f"<td style='padding:10px; {style}'>{day}</td>"
        html += "</tr>"
    return html + "</tbody></table>"


def get_daily_streak_metrics(history_rows):
    if not history_rows:
        return {
            "total_items": 0,
            "days_logged": 0,
            "healthy_streak_days": 0,
            "avg_health_score": 0,
        }

    by_date = {}
    for d, _, score, _ in history_rows:
        date_key = str(d)
        by_date.setdefault(date_key, []).append(float(score))

    # Requested behavior: compute average score per day, convert to /100, and
    # count healthy days where daily average health score is > 50.
    daily_health_scores = {}
    for date_key, scores in by_date.items():
        avg_score_for_date = sum(scores) / len(scores)
        daily_health_scores[date_key] = int(round(max(0, min(100, avg_score_for_date * 10))))

    healthy_streak_days = sum(1 for s in daily_health_scores.values() if s > 50)
    avg_health_score = int(round(sum(daily_health_scores.values()) / len(daily_health_scores))) if daily_health_scores else 0

    return {
        "total_items": len(history_rows),
        "days_logged": len(by_date),
        "healthy_streak_days": healthy_streak_days,
        "avg_health_score": avg_health_score,
    }

# === MAIN APP (NO LOGIN PAGE) ===
with st.sidebar:
    st.write("")
    render_logo(size="1.85rem")

    st.markdown("<div class='kicker'>Search foods</div>", unsafe_allow_html=True)
    sidebar_food_search = st.text_input("Food search", key="sidebar_food_search", placeholder="Search foods...", label_visibility="collapsed")

    st.markdown("<div class='kicker' style='margin-top:8px;'>Quick score check</div>", unsafe_allow_html=True)
    search_q = st.text_input("Quick score search", key="sidebar_search", placeholder="e.g. banana...", label_visibility="collapsed")
    active_search = (search_q or sidebar_food_search or "").strip()
    if active_search:
        results = search_vantage_db(active_search, limit=20)
        filtered_results = [r for r in results if r['vms_score'] != 10.0] if results else []

        if filtered_results:
            st.markdown("**Top Results:**")
            st.markdown('<div class="results-scroll-container">', unsafe_allow_html=True)
            for d in filtered_results:
                c = COLORS['green'] if d['vms_score'] < 3.0 else COLORS['yellow'] if d['vms_score'] < 7.0 else COLORS['red']
                portion_label = " /serving" if needs_portion_size(d['name']) else ""

                st.markdown(f"""
                    <div class='list-row'>
                        <span style='font-size:0.9rem; font-weight:700;'>{d['name']}</span>
                        <strong style='color:{c}; font-size:1.05rem;'>{d['vms_score']}{portion_label}</strong>
                    </div>
                """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class='friendly-error'>
                    <div class='friendly-error-title'>🔍 Item Not Found Yet</div>
                    <div class='friendly-error-text'>
                        We're constantly expanding our database with new products.<br>
                        Try searching for similar items or check back soon!
                    </div>
                </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    if st.button("▦ Dashboard", use_container_width=True, type="primary" if st.session_state.page == 'dashboard' else "secondary"):
        st.session_state.page = 'dashboard'
        st.rerun()
    if st.button("🗓 Calendar", use_container_width=True, type="primary" if st.session_state.page == 'calendar' else "secondary"):
        st.session_state.page = 'calendar'
        st.rerun()
    if st.button("↺ Meal Plan", use_container_width=True, type="primary" if st.session_state.page == 'log' else "secondary"):
        st.session_state.page = 'log'
        st.rerun()

    history_sidebar = get_log_history_db(st.session_state.user_id) or []
    streak_metrics_sidebar = get_daily_streak_metrics(history_sidebar)
    total_logged_sidebar = streak_metrics_sidebar["total_items"]
    health_score_sidebar = streak_metrics_sidebar["avg_health_score"]
    healthy_streak_days_sidebar = streak_metrics_sidebar["healthy_streak_days"]
    days_logged_sidebar = streak_metrics_sidebar["days_logged"]
    streak_pct = int((min(days_logged_sidebar, 10) / 10) * 100)

    st.markdown(f"""
        <div class='sidebar-streak-card'>
            <div class='sidebar-streak-title'>🔥 {healthy_streak_days_sidebar}-day streak</div>
            <div class='sidebar-streak-sub'>Keep it going!</div>
            <div class='sidebar-progress-wrap'>
                <div class='sidebar-progress-fill' style='width:{streak_pct}%;'></div>
            </div>
            <div style='margin-top:8px; color:#556582; font-size:0.82rem;'>{days_logged_sidebar} / 10 days logged</div>
            <div class='sidebar-mini-stats'>
                <div class='stat-tile'>
                    <div class='v'>{total_logged_sidebar:,}</div>
                    <div class='l'>items logged</div>
                </div>
                <div class='stat-tile'>
                    <div class='v'>{health_score_sidebar}</div>
                    <div class='l'>health score</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

if st.session_state.page == 'dashboard':
    st.markdown("<h1 style='margin-bottom:4px;'>Dashboard</h1>", unsafe_allow_html=True)
    st.markdown(f"<div class='subtitle'>{datetime.now().strftime('%A, %B %d, %Y')} · Track smarter. Live better.</div>", unsafe_allow_html=True)
    history_dashboard = get_log_history_db(st.session_state.user_id) or []
    today_key = datetime.now().strftime("%Y-%m-%d")
    items_today = sum(1 for d, *_ in history_dashboard if str(d) == today_key)
    streak_metrics_dashboard = get_daily_streak_metrics(history_dashboard)
    total_items_dashboard = streak_metrics_dashboard["total_items"]
    healthy_items_dashboard = sum(1 for _, _, score, _ in history_dashboard if float(score) < 3.0)
    health_score_dashboard = int(round((healthy_items_dashboard / total_items_dashboard) * 100)) if total_items_dashboard else 78
    day_streak_dashboard = streak_metrics_dashboard["healthy_streak_days"]

    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f"""
            <div class='metric-strip'>
                <div class='kicker'>Items tracked</div>
                <div class='metric-value'>{items_today}</div>
                <div class='metric-note'>↗ Start scanning more</div>
            </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown(f"""
            <div class='metric-strip'>
                <div class='kicker'>Health score</div>
                <div class='metric-value'>{health_score_dashboard}<span style='font-size:1.5rem; color:#7D8CAC;'>/100</span></div>
                <div class='metric-note'>↗ ↑ {max(1, healthy_items_dashboard)} pts this week</div>
            </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
            <div class='metric-strip'>
                <div class='kicker'>Day streak</div>
                <div class='metric-value'>{day_streak_dashboard}<span style='font-size:1.5rem; color:#7D8CAC;'> days</span></div>
                <div class='metric-note'>↗ Personal best!</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<h3 style='margin-top:6px;'>Active Focus Scanner</h3>", unsafe_allow_html=True)
    st.markdown('<div class="white-shelf"></div>', unsafe_allow_html=True)
    
    if not st.session_state.camera_active:
        st.markdown('<div class="tomato-wrapper"><i class="fa fa-camera tomato-icon"></i></div>', unsafe_allow_html=True)
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
        # SCANNER ACTIVE
        # Show status ABOVE camera as overlay bubble (same style as metabolic score)
        if st.session_state.selected_result:
            ls = st.session_state.selected_result
            clr = COLORS['green'] if ls['vms_score'] < 3.0 else COLORS['yellow'] if ls['vms_score'] < 7.0 else COLORS['red']

            # FIX 2: Add portion size label
            portion_label = " /serving" if needs_portion_size(ls['name']) else ""

            st.markdown(f"""
                <div class="hud-bubble">
                    <div style="font-size: 0.9rem; margin-bottom: 4px;">{ls['name']}</div>
                    <div style="color:{clr}; font-size:2.2rem; font-weight:900;">{ls['vms_score']}{portion_label}</div>
                    <div style="font-size: 0.8rem; color: {clr};">{ls['rating']}</div>
                </div>
            """, unsafe_allow_html=True)
        elif st.session_state.get('scan_status') == "analyzing":
            st.markdown(f"""
                <div class="hud-bubble">
                    <div style="font-size: 1.2rem; font-weight: 700;">🔍 Analyzing Image...</div>
                    <div style="font-size: 0.85rem; color: #666; margin-top: 4px;">Processing with Gemini AI</div>
                </div>
            """, unsafe_allow_html=True)
        elif st.session_state.get('detected_items'):
            items_text = ", ".join(st.session_state.detected_items[:3])
            st.markdown(f"""
                <div class="hud-bubble">
                    <div style="font-size: 1.2rem; font-weight: 700;">👁️ Items Detected</div>
                    <div style="font-size: 0.95rem; color: {COLORS['olive']}; margin-top: 4px;">{items_text}</div>
                </div>
            """, unsafe_allow_html=True)

            # Simple camera - NO focus square needed
        st.markdown("""
            <div style="text-align: center; margin: 20px 0;">
                <div class="scan-prompt">
                    📸 <strong>Point camera at item and tap to scan</strong>
                </div>
            </div>
        """, unsafe_allow_html=True)

        image = back_camera_input(key="hud_cam")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("❌ Stop Scanning", use_container_width=True):
                st.session_state.camera_active = False
                st.session_state.scan_results = None
                st.session_state.selected_result = None
                st.session_state.scanning = False
                st.session_state.scan_status = None
                st.session_state.detected_items = []
                st.rerun()
        
        # SCANNING LOGIC
        if image and st.session_state.scanning:
            st.session_state.scan_count += 1
            
            if st.session_state.scan_count % 2 == 0:
                # Set analyzing status (displayed on next rerun after processing)
                st.session_state.scan_status = "analyzing"

                # Run the scan (no st.rerun() before this - it would kill execution)
                results = vision_live_scan_dark(image)

                if results:
                    st.session_state.scan_results = results
                    st.session_state.selected_result = results[0]
                    st.session_state.detected_items = [r['name'] for r in results[:5]]
                    st.session_state.scanning = False
                    st.session_state.scan_status = None
                else:
                    # Clear analyzing status so it doesn't stick on failure
                    st.session_state.scan_status = None
                st.rerun()

    # FIX 3: Show ALL results with scroll
    if st.session_state.scan_results:
        st.markdown("### 📋 Select Your Item")
        st.markdown(f"Found **{len(st.session_state.scan_results)}** items in frame:")
        
        # FIX 7: Verification reminder
        st.info("💡 Always verify your selection matches what you scanned!")
        
        # FIX 3: Scrollable results (NO 5-item cap)
        st.markdown('<div class="results-scroll-container">', unsafe_allow_html=True)
        for i, result in enumerate(st.session_state.scan_results):
            clr = COLORS['green'] if result['vms_score'] < 3.0 else COLORS['yellow'] if result['vms_score'] < 7.0 else COLORS['red']
            selected = st.session_state.selected_result == result
            
            # FIX 2: Add portion size label
            portion_label = " /serving" if needs_portion_size(result['name']) else ""
            
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    f"{i+1}. {result['name']}", 
                    key=f"select_{i}",
                    type="primary" if selected else "secondary",
                    use_container_width=True
                ):
                    st.session_state.selected_result = result
                    st.rerun()
            with col2:
                st.markdown(f"<div style='text-align:center; color:{clr}; font-size:1.5rem; font-weight:bold;'>{result['vms_score']}{portion_label}</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # DEEP DIVE
    if st.session_state.selected_result:
        with st.expander("📊 Metabolic Nutrient Deep Dive", expanded=True):
            ls_raw = st.session_state.selected_result['raw']
            item_name = st.session_state.selected_result['name']
            scale = get_serving_scale(item_name)

            if scale < 1.0:
                serving_g = int(scale * 100)
                st.markdown(f"#### Clinical Data *(per serving ~{serving_g}g)*")
            else:
                st.markdown("#### Clinical Data *(per 100g)*")

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
                if st.button("➕ Log to My Journey", use_container_width=True):
                    add_calendar_item_db(
                        st.session_state.user_id, 
                        datetime.now().strftime("%Y-%m-%d"), 
                        st.session_state.selected_result['name'], 
                        st.session_state.selected_result['vms_score']
                    )
                    st.success("✅ Added!")
            with col2:
                if st.button("🔄 Scan Again", use_container_width=True):
                    st.session_state.scan_results = None
                    st.session_state.selected_result = None
                    st.session_state.scanning = True
                    st.session_state.detected_items = []
                    st.rerun()

    # TRENDS
    st.markdown('<div class="trend-shell">', unsafe_allow_html=True)
    head_left, head_right = st.columns([3.2, 1])
    with head_left:
        st.markdown("""
            <div class='trend-title-row'>
                <div style='color:#66B8CC; font-size:1.6rem;'>↗</div>
                <div class='trend-title'>Your Health Trends</div>
            </div>
        """, unsafe_allow_html=True)
    
    if st.session_state.trends_view == 'daily':
        days = 1
    elif st.session_state.trends_view == 'weekly':
        days = 7
    else:
        days = 30

    all_data = get_all_calendar_data_db(st.session_state.user_id)
    raw = get_trend_data_db(st.session_state.user_id, days=days)

    total_items = 0
    healthy_count = 0
    if raw and len(raw) > 0:
        df = pd.DataFrame(raw, columns=["date", "category", "count"])
        df['date'] = pd.to_datetime(df['date'])
        total_items = int(df['count'].sum())
        healthy_count = int(df[df['category'] == 'healthy']['count'].sum()) if 'healthy' in df['category'].values else 0
        trend_source = df.groupby('date', as_index=False)['count'].sum().sort_values('date')

        if st.session_state.trends_view == 'daily':
            labels = ['6AM', '8AM', '10AM', '12PM', '2PM', '4PM', '6PM', '8PM']
            slot_vals = [0] * len(labels)
            for _, row in trend_source.iterrows():
                h = row['date'].hour
                idx = min(range(len(labels)), key=lambda i: abs((6 + i * 2) - h))
                slot_vals[idx] += int(row['count'])
            y_vals = []
            running = 0
            for v in slot_vals:
                running += v
                y_vals.append(running)
            x_vals = labels
            hover_suffix = 'items tracked'
            hover_prefix = ''
        else:
            trend_source['label'] = trend_source['date'].dt.strftime('%b %d')
            trend_source['cum'] = trend_source['count'].cumsum()
            x_vals = trend_source['label'].tolist()
            y_vals = trend_source['cum'].astype(int).tolist()
            hover_suffix = 'items tracked'
            hover_prefix = ''

        with head_left:
            st.markdown(f"<div class='trend-sub'>Total items: {total_items} · Healthy choices: {healthy_count} · Based on your logged data</div>", unsafe_allow_html=True)
    else:
        x_vals = ['6AM', '8AM', '10AM', '12PM', '2PM', '4PM', '6PM', '8PM']
        y_vals = [0, 0, 1, 1, 1, 2, 2, 3]
        hover_suffix = 'items tracked'
        hover_prefix = ''
        with head_left:
            st.markdown("<div class='trend-sub'>Total items: 0 · Healthy choices: 0 · Based on your logged data</div>", unsafe_allow_html=True)

    with head_right:
        st.markdown('<div class="trend-tabs-container">', unsafe_allow_html=True)
        col_d, col_w, col_m = st.columns(3)
        with col_d:
            if st.button("Day", use_container_width=True, key="day_tab", type="primary" if st.session_state.trends_view == 'daily' else "secondary"):
                st.session_state.trends_view = 'daily'
                st.rerun()
        with col_w:
            if st.button("Week", use_container_width=True, key="week_tab", type="primary" if st.session_state.trends_view == 'weekly' else "secondary"):
                st.session_state.trends_view = 'weekly'
                st.rerun()
        with col_m:
            if st.button("Month", use_container_width=True, key="month_tab", type="primary" if st.session_state.trends_view == 'monthly' else "secondary"):
                st.session_state.trends_view = 'monthly'
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode='lines+markers',
        line=dict(color='#67AEC3', width=4, shape='spline', smoothing=0.6),
        marker=dict(color='#67AEC3', size=8, line=dict(color='#081018', width=2)),
        fill='tozeroy',
        fillcolor='rgba(103,174,195,0.12)',
        hovertemplate=f"%{{x}}<br>{hover_prefix}%{{y}} {hover_suffix}<extra></extra>"
    ))

    ymax = max(4, max(y_vals) if y_vals else 4)
    fig.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=10, b=25),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, showline=False, title=None, tickfont=dict(color='#394560', size=16)),
        yaxis=dict(showgrid=True, gridcolor='rgba(57,69,96,0.25)', griddash='dot', showline=False, title=None,
                   tickfont=dict(color='#394560', size=16), rangemode='tozero', range=[0, ymax * 1.15]),
        hovermode='x unified',
        showlegend=False,
        hoverlabel=dict(bgcolor='#1A2133', bordercolor='#2B3650', font=dict(color='#CFE4F2', size=16))
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if not raw or len(raw) == 0:
        if all_data and len(all_data) > 0:
            st.warning(f"⚠️ You have {len(all_data)} logged items, but none in the last {days} day(s). Try selecting a different time range.")
        else:
            st.info("📊 No data yet. Start logging items!")

    # === AI HEALTH COACH + RECIPES (FIGMA-STYLE PANELS) ===
    today_str = datetime.now().strftime("%Y-%m-%d")

    if st.session_state.recipes_date != today_str:
        st.session_state.daily_recipes = None
        st.session_state.recipes_date = today_str

    coach_col, recipe_col = st.columns(2)

    with coach_col:
        insights_ready = len(st.session_state.ai_insights) if st.session_state.ai_insights else 3
        st.markdown(f"""
            <div class='action-card'>
                <div class='action-card-header'>
                    <div class='action-title'>🧠 AI Health Coach</div>
                    <div class='action-chip'>{insights_ready} insights ready</div>
                </div>
                <div class='action-muted'>Your AI coach has analyzed food entries and found personalized insights to improve your health outcomes.</div>
            </div>
        """, unsafe_allow_html=True)

        if not st.session_state.ai_insights:
            if st.button("✨ Get AI Insights", key="figma_get_insights", use_container_width=True, type="primary"):
                with st.spinner("🧠 Your AI Health Coach is analyzing your patterns..."):
                    try:
                        insights = generate_health_insights(raw or [], all_data or [], days)
                        if insights:
                            st.session_state.ai_insights = insights
                            st.rerun()
                        else:
                            st.warning("Could not generate insights. Please try again.")
                    except Exception as e:
                        st.error(f"AI Insights error: {e}")
        else:
            if st.button("🔄 Refresh Insights", key="figma_refresh_insights", use_container_width=True):
                st.session_state.ai_insights = None
                st.rerun()

            for insight in st.session_state.ai_insights[:3]:
                emoji = insight.get('emoji', '💡')
                title = insight.get('title', 'Insight')
                body = insight.get('insight', '')
                st.markdown(f"""
                    <div class='coach-list-item'>
                        <div style='font-weight:700; color:#DDE7FA; margin-bottom:2px;'>{emoji} {title}</div>
                        <div style='font-size:0.9rem; color:#7F8DAB;'>{body}</div>
                    </div>
                """, unsafe_allow_html=True)

    with recipe_col:
        st.markdown("""
            <div class='action-card'>
                <div class='action-card-header'>
                    <div class='action-title'>👨‍🍳 Healthy Recipes</div>
                    <div style='color:#5E6685; font-size:0.95rem; font-weight:600;'>Matched to your goals</div>
                </div>
                <div class='action-muted'>Discover today's recipes curated around your nutrition targets and most-tracked foods.</div>
            </div>
        """, unsafe_allow_html=True)

        if not st.session_state.daily_recipes:
            if st.button("🍳 Discover Today's Recipes", key="figma_discover_recipes", use_container_width=True, type="primary"):
                with st.spinner("🍳 Finding healthy recipes for you..."):
                    try:
                        recipes = generate_daily_recipes()
                        if recipes:
                            st.session_state.daily_recipes = recipes
                            st.session_state.recipes_date = today_str
                            st.rerun()
                        else:
                            st.warning("Could not load recipes. Please try again.")
                    except Exception as e:
                        st.error(f"Recipe error: {e}")
        else:
            if st.button("🔄 New Recipes", key="figma_refresh_recipes", use_container_width=True):
                st.session_state.daily_recipes = None
                st.rerun()

            for recipe in st.session_state.daily_recipes[:3]:
                r_name = recipe.get('name', 'Recipe')
                r_type = recipe.get('meal_type', 'Meal')
                r_time = recipe.get('prep_time', '?')
                st.markdown(f"""
                    <div class='coach-list-item' style='border-color:#3A3341;'>
                        <div style='font-weight:700; color:#E5DBBD; margin-bottom:2px;'>🍽️ {r_name}</div>
                        <div style='font-size:0.9rem; color:#938A72;'>{r_type} · {r_time}</div>
                    </div>
                """, unsafe_allow_html=True)

elif st.session_state.page == 'calendar':
    st.markdown("## 📅 Grocery Calendar")
    calendar_all = get_all_calendar_data_db(st.session_state.user_id) or []
    tracked_days = len({d for d, *_ in calendar_all}) if calendar_all else 0
    st.markdown(f"<div class='subtitle'>{tracked_days} days tracked · {len(calendar_all)} items logged total</div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1.5])
    
    with c1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        sel_date = st.date_input("Select Date", datetime.now(), label_visibility="collapsed")
        st.markdown(create_html_calendar(sel_date.year, sel_date.month, sel_date.day), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with c2:
        st.markdown(f"### 🗓️ {sel_date.strftime('%b %d, %Y')}")
        
        st.markdown("#### ➕ Add Item to This Day")
        search_item = st.text_input("Search for an item", key="calendar_search", placeholder="e.g., banana, coca cola, avocado...")
        
        if search_item:
            search_results = search_vantage_db(search_item, limit=20)  # FIX 3: Increased limit
            filtered_results = [r for r in search_results if r['vms_score'] != 10.0] if search_results else []
            
            if filtered_results:
                # FIX 3: Scrollable container
                st.markdown('<div class="results-scroll-container">', unsafe_allow_html=True)
                for idx, result in enumerate(filtered_results):
                    clr = COLORS['green'] if result['vms_score'] < 3.0 else COLORS['yellow'] if result['vms_score'] < 7.0 else COLORS['red']
                    
                    # FIX 2: Add portion size label
                    portion_label = " /serving" if needs_portion_size(result['name']) else ""
                    
                    col_a, col_b, col_c = st.columns([3, 1, 0.6])
                    with col_a:
                        st.markdown(f"**{result['name']}**")
                    with col_b:
                        st.markdown(f"<div style='text-align:center; color:{clr}; font-weight:bold; font-size:1.2rem;'>{result['vms_score']}{portion_label}</div>", unsafe_allow_html=True)
                    with col_c:
                        if st.button("➕", key=f"add_cal_{idx}_{sel_date}", help=f"Add {result['name']}"):
                            add_calendar_item_db(
                                st.session_state.user_id,
                                sel_date.strftime("%Y-%m-%d"),
                                result['name'],
                                result['vms_score']
                            )
                            st.success(f"✅ Added!")
                            time.sleep(0.5)
                            st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                # FIX 7: Friendly error
                st.markdown("""
                    <div class='friendly-error'>
                        <div class='friendly-error-title'>🔍 Item Not Found Yet</div>
                        <div class='friendly-error-text'>
                            Our database is growing every day!<br>
                            Try a different search term or check back soon.
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("#### 📝 Items for This Day")
        
        items = get_calendar_items_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"))
        if items:
            for iid, name, score, cat in items:
                clr = COLORS['green'] if score < 3.0 else COLORS['yellow'] if score < 7.0 else COLORS['red']
                col_item, col_del = st.columns([5, 1])
                with col_item:
                    st.markdown(f"<div class='list-row'><span>{name}</span><strong style='color:{clr}'>{score}</strong></div>", unsafe_allow_html=True)
                with col_del:
                    if st.button("🗑️", key=f"del_{iid}", help="Delete this item"):
                        delete_item_db(iid)
                        st.rerun()
        else:
            st.info("📭 No items for this date. Add items above!")

elif st.session_state.page == 'log':
    st.markdown("## 🕒 Meal Plan")
    meal_hist = get_log_history_db(st.session_state.user_id) or []
    healthy_meal = sum(1 for _, _, score, _ in meal_hist if float(score) < 3.0)
    watch_meal = max(0, len(meal_hist) - healthy_meal)
    st.markdown(f"<div class='subtitle'>{len(meal_hist)} items · {healthy_meal} healthy · {watch_meal} to watch</div>", unsafe_allow_html=True)
    history = get_log_history_db(st.session_state.user_id)
    if history:
        for d, name, score, cat in history:
            clr = COLORS['green'] if score < 3.0 else COLORS['yellow'] if score < 7.0 else COLORS['red']
            st.markdown(f"<div class='list-row'><span><b>{d}</b>: {name}</span><strong style='color:{clr}'>{score}</strong></div>", unsafe_allow_html=True)
    else:
        st.info("📭 No history yet. Start logging items!")

    # === AI MEAL PLANNING AGENT ===
    st.markdown("---")
    col_mp1, col_mp2 = st.columns([3, 1])
    with col_mp1:
        st.markdown("#### 🤖 AI Meal Planning")
    with col_mp2:
        if st.session_state.meal_plan:
            if st.button("🗑️ Clear", key="clear_meal_plan", use_container_width=True):
                st.session_state.meal_plan = None
                st.rerun()

    if not st.session_state.meal_plan:
        st.markdown("Get a personalized 7-day meal plan based on your eating history.")
        if st.button("🤖 Generate AI Meal Plan", use_container_width=True, type="primary"):
            with st.spinner("🤖 Your AI nutritionist is crafting your personalized meal plan..."):
                try:
                    history = get_log_history_db(st.session_state.user_id)
                    plan = generate_meal_plan(history, st.session_state.user_id)
                    if plan:
                        st.session_state.meal_plan = plan
                        st.rerun()
                    else:
                        st.warning("Could not generate meal plan. Please try again.")
                except Exception as e:
                    st.error(f"Meal Plan error: {e}")

    if st.session_state.meal_plan:
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        plan = st.session_state.meal_plan
        today_str = datetime.now().strftime("%Y-%m-%d")

        for day_name in day_order:
            meals = plan.get(day_name, [])
            if not meals:
                continue

            with st.expander(f"📅 {day_name}", expanded=False):
                for midx, meal in enumerate(meals):
                    meal_type = meal.get('meal', 'Meal')
                    meal_name = meal.get('name', 'Unknown')
                    est_score = meal.get('estimated_score', 5.0)

                    clr = COLORS['green'] if est_score < 3.0 else COLORS['yellow'] if est_score < 7.0 else COLORS['red']

                    col_meal, col_score, col_add = st.columns([3, 1, 0.6])
                    with col_meal:
                        st.markdown(f"**{meal_type}:** {meal_name}")
                    with col_score:
                        st.markdown(f"<div style='text-align:center; color:{clr}; font-weight:bold;'>{est_score}</div>", unsafe_allow_html=True)
                    with col_add:
                        if st.button("➕", key=f"mp_{day_name}_{midx}", help=f"Add {meal_name} to today"):
                            add_calendar_item_db(
                                st.session_state.user_id,
                                today_str,
                                meal_name,
                                est_score
                            )
                            st.success(f"✅ Added!")
                            time.sleep(0.5)
                            st.rerun()
