import streamlit as st
from streamlit_back_camera_input import back_camera_input
import pandas as pd
import random
import time
import hashlib
import calendar as cal_module
from datetime import datetime, timedelta
from collections import defaultdict
from src.gemini_api import (
    analyze_label_with_gemini, 
    create_user, 
    authenticate_user, 
    add_calendar_item_db, 
    get_calendar_items_db,
    delete_item_db,
    get_log_history_db,
    get_trend_data_db
)

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")

# --- 2. SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'page' not in st.session_state: st.session_state.page = 'login'
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'camera_active' not in st.session_state: st.session_state.camera_active = False

# --- 3. ASSETS ---
CAMERA_ICON_URL = "https://cdn-icons-png.flaticon.com/512/3687/3687412.png" 
# NOTE: Replace with your raw GitHub URL if you have a custom image

# --- 4. CSS ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
    <style>
    .stApp { background-color: #F7F5F0; color: #1A1A1A; }
    .logo-text { font-family: 'Arial Black', sans-serif; font-size: 3rem; letter-spacing: -2px; line-height: 1.0; margin-bottom: 0; }
    .logo-dot { color: #E2725B; }
    .card { background: white; padding: 24px; border-radius: 20px; border: 1px solid #EEE; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; }
    
    /* BIG TOMATO CAMERA BUTTON */
    div.stButton > button.big-cam {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
        color: tomato !important;
        font-size: 150px !important;
        line-height: 1 !important;
        height: auto !important;
        box-shadow: none !important;
        margin: 0 auto;
    }
    
    /* Calendar Styling */
    .cal-table { width: 100%; text-align: center; border-collapse: collapse; }
    .cal-header { font-weight: bold; color: #E2725B; padding: 10px; }
    .cal-day { padding: 10px; border: 1px solid #F0F0F0; color: #555; }
    .cal-selected { background-color: #E2725B; color: white; border-radius: 50%; font-weight: bold; box-shadow: 0 4px 8px rgba(226, 114, 91, 0.4); }
    
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 5. HELPERS ---
def render_logo(size="3rem"):
    st.markdown(f"<div style='text-align: center; margin-bottom: 20px;'><div class='logo-text' style='font-size: {size};'>foodvantage<span class='logo-dot'>.</span></div></div>", unsafe_allow_html=True)

def get_consistent_score(text):
    if not text: return 0.0
    hash_val = int(hashlib.sha256(text.lower().strip().encode()).hexdigest(), 16)
    score = (hash_val % 100) / 10.0
    return round(score, 1)

def create_html_calendar(year, month, selected_day=None):
    """Draws a calendar and highlights the selected day."""
    cal = cal_module.monthcalendar(year, month)
    
    html = "<table class='cal-table'><thead><tr>"
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        html += f"<th class='cal-header'>{day}</th>"
    html += "</tr></thead><tbody>"
    
    for week in cal:
        html += "<tr>"
        for day in week:
            if day == 0: 
                html += "<td class='cal-day'></td>"
            else:
                # HIGHLIGHT LOGIC: Match the day picked in the dropdown
                cls = "cal-selected" if day == selected_day else "cal-day"
                html += f"<td class='{cls}'>{day}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

def get_unique_recipes():
    pool = [{"icon":"🥗","n":"Kale Caesar","c":"210","t":"Keto"},{"icon":"🐟","n":"Grilled Salmon","c":"450","t":"High Protein"},{"icon":"🥑","n":"Avo Toast","c":"320","t":"Healthy Fat"},{"icon":"🥒","n":"Zoodles Pesto","c":"180","t":"Low Carb"},{"icon":"🫐","n":"Acai Bowl","c":"290","t":"Antioxidant"},{"icon":"🥣","n":"Lentil Soup","c":"250","t":"Fiber Rich"},{"icon":"🥚","n":"Egg Bites","c":"140","t":"High Protein"},{"icon":"🍗","n":"Chicken Satay","c":"310","t":"High Protein"},{"icon":"🍄","n":"Mushroom Risotto","c":"400","t":"Vegetarian"},{"icon":"🌮","n":"Turkey Taco","c":"280","t":"Lean Meat"},{"icon":"🍤","n":"Garlic Shrimp","c":"220","t":"Low Cal"},{"icon":"🥬","n":"Spinach Wrap","c":"190","t":"Vegan"},{"icon":"🥔","n":"Sweet Potato","c":"160","t":"Complex Carb"},{"icon":"🥕","n":"Hummus Dip","c":"180","t":"Snack"},{"icon":"🥥","n":"Chia Pudding","c":"210","t":"Omega-3"},{"icon":"🍵","n":"Matcha Latte","c":"90","t":"Focus"},{"icon":"🥩","n":"Steak Salad","c":"420","t":"Iron Rich"}]
    return random.sample(pool, 15)

# --- 6. PAGE LOGIC ---

# === LOGIN ===
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.write(""); st.write("")
        with st.container():
            st.markdown('<div class="card" style="text-align: center;">', unsafe_allow_html=True)
            render_logo(size="3.5rem")
            st.caption("Welcome! Ready to eat healthy?")
            tab1, tab2 = st.tabs(["Sign In", "Create Account"])
            with tab1:
                u = st.text_input("User ID", key="l_u")
                p = st.text_input("Password", type="password", key="l_p")
                if st.button("Sign In", type="primary", use_container_width=True):
                    if authenticate_user(u, p):
                        st.session_state.logged_in = True
                        st.session_state.user_id = u
                        st.session_state.page = 'dashboard'
                        st.rerun()
                    else: st.error("User not found.")
            with tab2:
                u2 = st.text_input("Choose User ID", key="s_u")
                p2 = st.text_input("Choose Password", type="password", key="s_p")
                if st.button("Create Account", use_container_width=True):
                    if create_user(u2, p2): st.success("Created! Sign In now.");
                    else: st.error("Username taken.")
            st.markdown("</div>", unsafe_allow_html=True)

# === MAIN APP ===
else:
    with st.sidebar:
        st.write("")
        st.markdown("##### 🔍 Search Groceries")
        search_q = st.text_input("Check score", placeholder="e.g. Soda", label_visibility="collapsed")
        if search_q:
            score = get_consistent_score(search_q)
            if score < 3.0: color, bg, lbl = "#2E8B57", "#E8F5E9", "Healthy"
            elif score < 7.0: color, bg, lbl = "#F9A825", "#FFF8E1", "Moderate"
            else: color, bg, lbl = "#D32F2F", "#FFEBEE", "Unhealthy"
            st.markdown(f"<div style='background:white; padding:12px; border-radius:12px; border:1px solid #EEE; margin-top:10px;'><div style='font-weight:bold;'>{search_q}</div><div style='color:{color}; font-weight:900; font-size:1.8rem;'>{score}</div><div style='background:{bg}; color:{color}; padding:2px 8px; border-radius:4px; font-size:0.8rem;'>{lbl}</div></div>", unsafe_allow_html=True)
        st.markdown("---")
        if st.button("🏠", help="Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Grocery Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Grocery Log", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        st.markdown("---")
        if st.button("Log Out"): st.session_state.logged_in = False; st.rerun()

    # === DASHBOARD ===
    if st.session_state.page == 'dashboard':
        render_logo(size="3.5rem")
        st.markdown("<h3 style='text-align: center;'>Scan Your Groceries</h3>", unsafe_allow_html=True)
        
        # CAMERA SECTION
        with st.container():
            st.markdown('<div class="card" style="text-align: center;">', unsafe_allow_html=True)
            if not st.session_state.camera_active:
                st.markdown("""<div style="display: flex; justify-content: center; margin-bottom: 20px;"><i class="fa fa-camera" style="font-size:150px; color:tomato; cursor: pointer;"></i></div>""", unsafe_allow_html=True)
                if st.button("Start Live Scan", type="primary"):
                    st.session_state.camera_active = True
                    st.rerun()
            else:
                st.info("Camera Active: If you don't see a video, check browser permissions.")
                # KEY FIX: Added unique key to camera widget
                image = back_camera_input(key="grocery_scanner")
                if st.button("❌ Stop Scanning"):
                    st.session_state.camera_active = False
                    st.rerun()
                if image:
                    with st.spinner("Gemini 3 is analyzing..."):
                        st.markdown(analyze_label_with_gemini(image))
            st.markdown('</div>', unsafe_allow_html=True)

        # SCATTER PLOT TRENDS
        st.markdown("### 📈 Your Health Trends")
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            timeframe = st.radio("Select Period", ["Week", "Month"], horizontal=True)
            days = 30 if timeframe == "Month" else 7
            
            raw_data = get_trend_data_db(st.session_state.user_id, days)
            
            if not raw_data:
                st.info("No Data Available yet. Log items in the Calendar to see your scatter plot!")
            else:
                df = pd.DataFrame(raw_data, columns=["Date", "Category", "Count"])
                color_map = {"healthy": "#2E8B57", "unhealthy": "#D32F2F", "moderate": "#F9A825"}
                df['Color'] = df['Category'].map(color_map)
                
                st.scatter_chart(
                    df,
                    x="Date",
                    y="Count",
                    color="Category", 
                    size="Count", 
                )
            st.markdown('</div>', unsafe_allow_html=True)
            
        # RECIPES
        st.markdown("### 🍳 Recommended Recipes")
        recipes = get_unique_recipes()
        cols = st.columns(3)
        for i, r in enumerate(recipes):
            with cols[i%3]:
                st.markdown(f"""<div style="background:white; padding:15px; border-radius:12px; border:1px solid #EEE; margin-bottom:10px; text-align:center;"><div style="font-size:2rem; margin-bottom:5px;">{r['icon']}</div><div style="font-weight:bold; font-size:1rem;">{r['n']}</div><div style="color:#666; font-size:0.8rem;">{r['c']} kcal • {r['t']}</div></div>""", unsafe_allow_html=True)

    # === CALENDAR (FIXED) ===
    elif st.session_state.page == 'calendar':
        st.markdown("## 📅 Grocery Calendar")
        c1, c2 = st.columns([1, 1.5])
        
        with c1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            # 1. Ask for Input FIRST
            st.markdown("### Select Day to Log")
            sel_date = st.date_input("Select Date", datetime.now(), label_visibility="collapsed")
            date_key = sel_date.strftime("%Y-%m-%d")
            
            st.markdown("---")
            
            # 2. Draw Calendar based on that input
            # We pass the selected year, month, and day to highlight it correctly
            st.markdown(f"<h3 style='text-align:center; color:#E2725B;'>{sel_date.strftime('%B %Y')}</h3>", unsafe_allow_html=True)
            st.markdown(create_html_calendar(sel_date.year, sel_date.month, sel_date.day), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with c2:
            st.markdown(f"### List for {sel_date.strftime('%b %d')}")
            col_in, col_btn = st.columns([3, 1])
            new_item = col_in.text_input("Add item...", label_visibility="collapsed")
            if col_btn.button("➕", use_container_width=True):
                if new_item:
                    score = get_consistent_score(new_item)
                    add_calendar_item_db(st.session_state.user_id, date_key, new_item, int(score * 10))
                    st.rerun()

            items = get_calendar_items_db(st.session_state.user_id, date_key)
            if not items: st.info("No items logged for this day.")
            for item_id, name, score_raw, cat, checked in items:
                score_val = score_raw / 10.0
                if score_val < 3.0: cls = "bg-green"
                elif score_val < 7.0: cls = "bg-yellow"
                else: cls = "bg-red"
                c_txt, c_del = st.columns([4, 1])
                c_txt.markdown(f"<div class='list-item'><span>{name}</span><span class='badge {cls}'>{score_val}</span></div>", unsafe_allow_html=True)
                if c_del.button("🗑️", key=f"del_{item_id}"): delete_item_db(item_id); st.rerun()

    elif st.session_state.page == 'log':
        st.markdown("## 📝 Grocery Log")
        history = get_log_history_db(st.session_state.user_id)
        if not history: st.info("Start logging items in the Calendar to see history here.")
        grouped = defaultdict(list)
        for date_obj, name, score_raw, cat in history:
            d_str = date_obj.strftime("%a, %b %d")
            grouped[d_str].append({"name": name, "score": score_raw/10.0, "cat": cat})
        for date_label, items in grouped.items():
            st.markdown(f"""<div class="card" style="padding:15px;"><div style="font-weight:bold; border-bottom:1px solid #EEE; padding-bottom:10px; margin-bottom:10px;">🛍️ {date_label}</div>""", unsafe_allow_html=True)
            for item in items:
                s = item['score']
                if s < 3.0: color="#2E8B57"
                elif s < 7.0: color="#F9A825"
                else: color="#D32F2F"
                st.markdown(f"<div style='display:flex; justify-content:space-between;'><span>{item['name']}</span><strong style='color:{color}'>{s}</strong></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)