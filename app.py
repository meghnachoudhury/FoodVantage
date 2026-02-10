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
    generate_health_insights, generate_meal_plan,
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

# --- BACKGROUND IMAGE ---
_bg_path = os.path.join(os.path.dirname(__file__), "assets", "image_1010.png")
if os.path.exists(_bg_path):
    with open(_bg_path, "rb") as _f:
        _bg_b64 = base64.b64encode(_f.read()).decode()
else:
    _bg_b64 = ""

# --- COLOR PALETTE (Grocery Template) ---
COLORS = {
    'olive': '#5B8C3E',          # Primary green from template
    'terracotta': '#5B8C3E',     # Buttons now green (was terracotta)
    'salmon': '#8BC34A',         # Light green accent
    'beige': '#F5F0E8',          # Warm cream background from template
    'dark_text': '#2C2C2C',
    'green': '#4CAF50',          # Healthy score green
    'yellow': '#F9A825',         # Moderate score amber
    'red': '#E53935',            # Unhealthy score red
    'camera_icon': '#444444',    # Dark grey camera icon
    'toggle_button': '#5B8C3E',  # Green toggle buttons
    'unhealthy_bar': '#EF9A9A',  # Softer red for chart bars
    'card_bg': '#FFFFFF',
    'border': '#E8E0D4',         # Warm border tone
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
st.markdown('<link href="https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">', unsafe_allow_html=True)
st.markdown(f"""
    <style>
    /* === GLOBAL === */
    .stApp {{
        background-color: {COLORS['beige']};
        color: #1A1A1A;
        font-family: 'Josefin Sans', sans-serif;
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
        opacity: 0.20;
        pointer-events: none;
        z-index: 0;
    }}

    h1, h2, h3, h4, h5, h6, p, div, label {{
        font-family: 'Josefin Sans', sans-serif !important;
    }}

    .logo-text {{ font-family: 'Josefin Sans', sans-serif; font-size: 3rem; text-align: center; font-weight: 700; }}
    .logo-dot {{ color: {COLORS['olive']}; }}

    .card {{
        background: white;
        padding: 24px;
        border-radius: 24px;
        border: 1px solid {COLORS['border']};
        box-shadow: 0 4px 16px rgba(91,140,62,0.06);
        margin-bottom: 20px;
    }}

    .white-shelf {{
        background: linear-gradient(135deg, #E8F5E9 0%, #F1F8E9 100%);
        height: 35px;
        border-radius: 14px;
        border: 1px solid #C8E6C9;
        margin-bottom: 25px;
    }}

    .tomato-wrapper {{ width: 100%; text-align: center; padding: 30px 0; }}
    .tomato-icon {{ font-size: 150px !important; color: {COLORS['camera_icon']} !important; }}

    /* === INPUTS === */
    input[type="text"], input[type="password"] {{
        background-color: white !important;
        color: #1A1A1A !important;
        border: 1.5px solid {COLORS['border']} !important;
        border-radius: 14px !important;
        padding: 12px 16px !important;
        font-family: 'Josefin Sans', sans-serif !important;
    }}

    input[type="text"]:focus, input[type="password"]:focus {{
        border-color: {COLORS['olive']} !important;
        box-shadow: 0 0 0 2px rgba(91,140,62,0.15) !important;
    }}

    .stTextInput > div > div > input {{
        background-color: white !important;
        color: #1A1A1A !important;
        -webkit-text-fill-color: #1A1A1A !important;
        font-family: 'Josefin Sans', sans-serif !important;
    }}

    /* === BUTTONS === */
    .stButton > button {{
        background-color: {COLORS['olive']} !important;
        color: white !important;
        border: none !important;
        border-radius: 50px !important;
        font-family: 'Josefin Sans', sans-serif !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.5rem !important;
        transition: all 0.2s ease !important;
    }}

    .stButton > button:hover {{
        background-color: #4A7A2E !important;
        box-shadow: 0 4px 12px rgba(91,140,62,0.3) !important;
        transform: translateY(-1px) !important;
    }}

    /* === METRICS === */
    [data-testid="stMetricValue"] {{
        color: #1A1A1A !important;
        font-weight: 700 !important;
        font-size: 1.5rem !important;
        font-family: 'Josefin Sans', sans-serif !important;
    }}

    [data-testid="stMetricLabel"] {{
        color: #2C2C2C !important;
        font-weight: 600 !important;
        font-family: 'Josefin Sans', sans-serif !important;
    }}

    /* === EXPANDERS === */
    .stExpander {{
        background: white !important;
        color: #1A1A1A !important;
        border-radius: 16px !important;
        border: 1px solid {COLORS['border']} !important;
    }}

    .stExpander p, .stExpander div, .stExpander span {{
        color: #1A1A1A !important;
    }}

    /* === HUD BUBBLE (Scanner Overlay) === */
    .hud-bubble {{
        position: fixed;
        top: calc(50% - 200px);
        left: 50%;
        transform: translateX(-50%);
        background: white;
        padding: 16px 28px;
        border-radius: 50px;
        box-shadow: 0 10px 30px rgba(91,140,62,0.2);
        border: 3px solid {COLORS['olive']};
        z-index: 1000;
        text-align: center;
        min-width: 220px;
        font-family: 'Josefin Sans', sans-serif;
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
        background: #E8F5E9;
        border-radius: 10px;
    }}

    .results-scroll-container::-webkit-scrollbar-thumb {{
        background: {COLORS['olive']};
        border-radius: 10px;
    }}

    /* === SCANNER RESULTS === */
    .scanner-result {{
        background: white;
        padding: 16px;
        border-radius: 16px;
        margin: 12px 0;
        border-left: 4px solid {COLORS['olive']};
        font-family: 'Josefin Sans', sans-serif;
    }}

    .scanner-result-title {{
        color: {COLORS['dark_text']};
        font-weight: 700;
        font-size: 1.1rem;
        margin-bottom: 8px;
    }}

    .scanner-result-text {{
        color: {COLORS['dark_text']};
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
        background: #FFF;
        border-radius: 16px;
        border: 1px solid {COLORS['border']};
        margin-bottom: 8px;
        font-family: 'Josefin Sans', sans-serif;
    }}

    /* === TREND TABS === */
    .trend-tabs-container {{
        max-width: 400px;
        margin: 0 auto 20px auto;
    }}

    .trend-tabs-container .stButton > button {{
        background-color: {COLORS['toggle_button']} !important;
        color: white !important;
        border: none !important;
    }}

    .trend-tabs-container .stButton > button[kind="primary"] {{
        background-color: {COLORS['toggle_button']} !important;
        color: white !important;
        font-weight: bold !important;
    }}

    /* === SIDEBAR === */
    [data-testid="collapsedControl"] {{
        color: {COLORS['olive']} !important;
    }}

    section[data-testid="stSidebar"] {{
        background-color: #FAFAF5 !important;
        border-right: 1px solid {COLORS['border']} !important;
    }}

    /* === FRIENDLY ERRORS === */
    .friendly-error {{
        background: #F1F8E9;
        border-left: 4px solid {COLORS['olive']};
        padding: 16px;
        border-radius: 12px;
        margin: 12px 0;
        font-family: 'Josefin Sans', sans-serif;
    }}

    .friendly-error-title {{
        font-weight: 700;
        color: #33691E;
        margin-bottom: 8px;
    }}

    .friendly-error-text {{
        color: #558B2F;
        font-size: 0.9rem;
    }}

    /* === SCAN PROMPT BADGE === */
    .scan-prompt {{
        background: linear-gradient(135deg, #E8F5E9 0%, #F1F8E9 100%);
        padding: 12px 20px;
        border-radius: 14px;
        display: inline-block;
        border: 1px solid #C8E6C9;
    }}
    </style>
""", unsafe_allow_html=True)

def render_logo(size="3rem"):
    st.markdown(f"<div style='text-align: center; margin-bottom: 10px;'><div class='logo-text' style='font-size: {size}; font-family: Josefin Sans, sans-serif;'>foodvantage<span class='logo-dot'>.</span></div></div>", unsafe_allow_html=True)

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

# === MAIN APP (NO LOGIN PAGE) ===
with st.sidebar:
    st.write("")
    st.markdown("##### 🔍 Search")
    search_q = st.text_input("Quick check score", key="sidebar_search")
    if search_q:
        results = search_vantage_db(search_q, limit=20)  # FIX 3: Increased from 5 to 20
        filtered_results = [r for r in results if r['vms_score'] != 10.0] if results else []
        
        if filtered_results:
            st.markdown("**Top Results:**")
            # FIX 3: Add scrollable container
            st.markdown('<div class="results-scroll-container">', unsafe_allow_html=True)
            for i, d in enumerate(filtered_results):
                c = COLORS['green'] if d['vms_score'] < 3.0 else COLORS['yellow'] if d['vms_score'] < 7.0 else COLORS['red']
                
                # FIX 2: Add portion size label if needed
                portion_label = " per serving" if needs_portion_size(d['name']) else ""
                
                st.markdown(f"""
                    <div class='card' style='padding:12px; margin-bottom:8px;'>
                        <div style='font-size:0.9rem; font-weight:bold;'>{i+1}. {d['name']}</div>
                        <div style='color:{c}; font-weight:bold; font-size:1.3rem;'>{d['vms_score']}{portion_label}</div>
                        <div style='font-size:0.8rem; color:{c};'>{d['rating']}</div>
                    </div>
                """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            # FIX 7: Friendly error message
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
    if st.button("🏠 Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
    if st.button("📅 Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
    if st.button("📝 Log History", use_container_width=True): st.session_state.page = 'log'; st.rerun()

if st.session_state.page == 'dashboard':
    render_logo(size="3.5rem")
    st.markdown("<h3 style='text-align: center;'>Active Focus Scanner</h3>", unsafe_allow_html=True)
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
    st.markdown("### 📈 Your Health Trends")
    
    st.markdown('<div class="trend-tabs-container">', unsafe_allow_html=True)
    col_d, col_w, col_m = st.columns(3)
    with col_d:
        if st.button("Day", use_container_width=True, key="day_tab",
                    type="primary" if st.session_state.trends_view == 'daily' else "secondary"):
            st.session_state.trends_view = 'daily'
            st.rerun()
    with col_w:
        if st.button("Week", use_container_width=True, key="week_tab",
                    type="primary" if st.session_state.trends_view == 'weekly' else "secondary"):
            st.session_state.trends_view = 'weekly'
            st.rerun()
    with col_m:
        if st.button("Month", use_container_width=True, key="month_tab",
                    type="primary" if st.session_state.trends_view == 'monthly' else "secondary"):
            st.session_state.trends_view = 'monthly'
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state.trends_view == 'daily':
        days = 1
    elif st.session_state.trends_view == 'weekly':
        days = 7
    else:
        days = 30
    
    all_data = get_all_calendar_data_db(st.session_state.user_id)
    raw = get_trend_data_db(st.session_state.user_id, days=days)
    
    if raw and len(raw) > 0:
        df = pd.DataFrame(raw, columns=["date", "category", "count"])
        df['date'] = pd.to_datetime(df['date'])
        df_pivot = df.pivot_table(index='date', columns='category', values='count', aggfunc='sum', fill_value=0)
        
        fig = go.Figure()
        
        if 'healthy' in df_pivot.columns:
            fig.add_trace(go.Bar(
                x=df_pivot.index,
                y=df_pivot['healthy'],
                name='Healthy',
                marker_color='rgba(217,217,217,0.7)',
                hovertemplate='%{y} healthy items<extra></extra>'
            ))
        
        if 'moderate' in df_pivot.columns:
            fig.add_trace(go.Bar(
                x=df_pivot.index,
                y=df_pivot['moderate'],
                name='Moderate',
                marker_color='rgba(139,195,74,0.7)',
                hovertemplate='%{y} moderate items<extra></extra>'
            ))
        
        if 'unhealthy' in df_pivot.columns:
            fig.add_trace(go.Bar(
                x=df_pivot.index,
                y=df_pivot['unhealthy'],
                name='Unhealthy',
                marker_color='rgba(51,51,51,0.7)',
                hovertemplate='%{y} unhealthy items<extra></extra>'
            ))
        
        fig.update_layout(
            barmode='stack',
            height=300,
            margin=dict(l=20, r=20, t=20, b=40),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False, showline=False, title=None, tickfont=dict(color='#1A1A1A'), color='#1A1A1A'),
            yaxis=dict(showgrid=True, gridcolor='#E0E0E0', showline=False, title=None, tickfont=dict(color='#1A1A1A'), color='#1A1A1A'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(color='#1A1A1A')),
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        total_items = int(df['count'].sum())
        healthy_count = int(df[df['category'] == 'healthy']['count'].sum()) if 'healthy' in df['category'].values else 0
        st.markdown(f"**Total items:** {total_items} | **Healthy choices:** {healthy_count}")

        # === AI HEALTH COACH ===
        st.markdown("---")
        col_ins1, col_ins2 = st.columns([3, 1])
        with col_ins1:
            st.markdown("#### 🧠 AI Health Coach")
        with col_ins2:
            if st.session_state.ai_insights:
                if st.button("🔄 Refresh", key="refresh_insights", use_container_width=True):
                    st.session_state.ai_insights = None
                    st.rerun()

        if not st.session_state.ai_insights:
            if st.button("🧠 Get AI Insights", use_container_width=True, type="primary"):
                with st.spinner("🧠 Your AI Health Coach is analyzing your patterns..."):
                    try:
                        insights = generate_health_insights(raw, all_data, days)
                        if insights:
                            st.session_state.ai_insights = insights
                            st.rerun()
                        else:
                            st.warning("Could not generate insights. Please try again.")
                    except Exception as e:
                        st.error(f"AI Insights error: {e}")

        if st.session_state.ai_insights:
            for i, insight in enumerate(st.session_state.ai_insights):
                emoji = insight.get('emoji', '💡')
                title = insight.get('title', 'Insight')
                body = insight.get('insight', '')
                action = insight.get('action', '')
                border_colors = [COLORS['olive'], COLORS['yellow'], COLORS['terracotta']]
                bc = border_colors[i % len(border_colors)]
                st.markdown(f"""
                    <div class='card' style='border-left: 4px solid {bc}; padding: 16px;'>
                        <div style='font-size: 1.1rem; font-weight: 800; margin-bottom: 6px;'>{emoji} {title}</div>
                        <div style='color: #444; font-size: 0.95rem; margin-bottom: 8px;'>{body}</div>
                        <div style='color: {COLORS["olive"]}; font-weight: 600; font-size: 0.9rem;'>→ {action}</div>
                    </div>
                """, unsafe_allow_html=True)

    else:
        if all_data and len(all_data) > 0:
            st.warning(f"⚠️ You have {len(all_data)} logged items, but none in the last {days} day(s). Try selecting a different time range.")
        else:
            st.info("📊 No data yet. Start logging items!")

elif st.session_state.page == 'calendar':
    st.markdown("## 📅 Grocery Calendar")
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
    st.markdown("## 📝 Log History")
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

