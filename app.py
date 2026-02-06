import streamlit as st
import sys
import os
import pandas as pd
import hashlib
import calendar as cal_module
import time  # For the animated transition
from datetime import datetime
from collections import defaultdict

# --- 1. PATH FIX FOR DEPLOYMENT ---
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from gemini_api import (
    analyze_label_with_gemini, 
    create_user, 
    authenticate_user, 
    add_calendar_item_db, 
    get_calendar_items_db,
    delete_item_db,
    get_log_history_db,
    get_trend_data_db,
    search_vantage_db
)
from streamlit_back_camera_input import back_camera_input

# --- 2. CONFIGURATION ---
st.set_page_config(
    page_title="FoodVantage", 
    page_icon="🥗", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- 3. SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'transitioning' not in st.session_state: st.session_state.transitioning = False

# --- 4. CSS & FONTAWESOME ---
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">', unsafe_allow_html=True)

st.markdown("""
    <style>
    .stApp { background-color: #F7F5F0; color: #1A1A1A; }
    .logo-text { font-family: 'Arial Black', sans-serif; font-size: 3rem; letter-spacing: -2px; line-height: 1.0; margin-bottom: 0; }
    .logo-dot { color: #E2725B; }
    .card { background: white; padding: 24px; border-radius: 20px; border: 1px solid #EEE; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; }
    
    /* Login Tab Design Fix */
    button[data-baseweb="tab"] p {
        color: black !important;
        font-weight: bold !important;
    }

    /* Subtitle Styling */
    .welcome-subtitle {
        font-size: 22px !important;
        color: #2c3e50 !important;
        font-weight: 600;
        margin-bottom: 20px;
    }

    /* Transition Message Styling */
    .transition-text {
        font-family: 'Arial Black', sans-serif;
        font-size: 2.5rem;
        color: #2c3e50;
        text-align: center;
        margin-top: 20vh;
    }

    .cal-table { width: 100%; text-align: center; border-collapse: collapse; }
    .cal-header { font-weight: bold; color: #E2725B; padding: 10px; }
    .cal-day { padding: 10px; border: 1px solid #F0F0F0; color: #555; }
    .cal-selected { background-color: #E2725B; color: white; border-radius: 50%; font-weight: bold; box-shadow: 0 4px 8px rgba(226, 114, 91, 0.4); }
    
    .list-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 15px;
        background: #FFF;
        border-radius: 12px;
        border: 1px solid #F0F0F0;
        margin-bottom: 8px;
        width: 100%;
    }
    .badge-pill {
        padding: 2px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.9rem;
    }

    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 5. HELPERS ---
def render_logo(size="3rem"):
    st.markdown(f"<div style='text-align: center; margin-bottom: 10px;'><div class='logo-text' style='font-size: {size};'>foodvantage<span class='logo-dot'>.</span></div></div>", unsafe_allow_html=True)

def create_html_calendar(year, month, selected_day=None):
    cal = cal_module.monthcalendar(year, month)
    html = "<table class='cal-table'><thead><tr>"
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        html += f"<th class='cal-header'>{day}</th>"
    html += "</tr></thead><tbody>"
    for week in cal:
        html += "<tr>"
        for day in week:
            if day == 0: html += "<td class='cal-day'></td>"
            else:
                cls = "cal-selected" if day == selected_day else "cal-day"
                html += f"<td class='{cls}'>{day}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

# --- 6. PAGE ROUTING ---

# Animated Transition Screen
if st.session_state.transitioning:
    placeholder = st.empty()
    for i in range(2): # Repeat animation twice
        for dots in [".", "..", "..."]:
            placeholder.markdown(f"<div class='transition-text'>Let us start your health journey{dots}</div>", unsafe_allow_html=True)
            time.sleep(0.5)
    st.session_state.transitioning = False
    st.rerun()

# Login Logic
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.write(""); st.write("")
        with st.container():
            st.markdown('<div class="card" style="text-align: center;">', unsafe_allow_html=True)
            render_logo(size="3.5rem")
            st.markdown('<p class="welcome-subtitle">Welcome! Ready to eat healthy?</p>', unsafe_allow_html=True)
            
            tab1, tab2 = st.tabs(["Sign In", "Create Account"])
            with tab1:
                u = st.text_input("User ID", key="l_u")
                p = st.text_input("Password", type="password", key="l_p")
                if st.button("Sign In", type="primary", use_container_width=True):
                    if authenticate_user(u, p):
                        st.session_state.user_id = u
                        st.session_state.logged_in = True
                        st.session_state.transitioning = True # Trigger Animation
                        st.rerun()
                    else: st.error("User not found.")
            with tab2:
                u2, p2 = st.text_input("Choose User ID", key="s_u"), st.text_input("Choose Password", type="password", key="s_p")
                if st.button("Create Account", use_container_width=True):
                    if create_user(u2, p2): st.success("Created! Sign In now.")
                    else: st.error("Username taken.")
            st.markdown("</div>", unsafe_allow_html=True)

# Main App Logic
else:
    with st.sidebar:
        st.write("")
        st.markdown("##### 🔍 Search")
        search_q = st.text_input("Check score", placeholder="e.g. Avocado", label_visibility="collapsed")
        
        if search_q:
            res = search_vantage_db(search_q)
            if res:
                data = res[0]
                s = data['vms_score']
                label = data['rating']
                
                if s < 3.0: c, b = "#2E8B57", "#E8F5E9"
                elif s < 7.0: c, b = "#F9A825", "#FFF8E1"
                else: c, b = "#D32F2F", "#FFEBEE"
                
                st.markdown(f"""
                <div style='background:white; padding:12px; border-radius:12px; border:1px solid #EEE; margin-top:10px;'>
                    <div style='font-weight:bold;'>{data['name']}</div>
                    <div style='color:{c}; font-weight:900; font-size:1.8rem;'>{s}</div>
                    <div style='background:{b}; color:{c}; padding:2px 8px; border-radius:4px; font-size:0.8rem; font-weight:bold;'>{label}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("Item not found.")

        st.markdown("---")
        if st.button("🏠", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Grocery Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Grocery Log", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        st.markdown("---")
        if st.button("Log Out"): st.session_state.logged_in = False; st.rerun()

    if st.session_state.page == 'dashboard':
        render_logo(size="3.5rem")
        st.markdown("<h3 style='text-align: center;'>Scan Your Groceries</h3>", unsafe_allow_html=True)
        
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            cam_col1, cam_col2, cam_col3 = st.columns([1, 2, 1])
            with cam_col2:
                if not st.session_state.camera_active:
                    st.markdown('<div style="text-align: center;"><i class="fa fa-camera" style="font-size:150px; color:tomato; margin-bottom:20px;"></i></div>', unsafe_allow_html=True)
                    if st.button("Start Live Scan", type="primary", use_container_width=True):
                        st.session_state.camera_active = True
                        st.rerun()
                else:
                    image = back_camera_input(key="grocery_scanner")
                    if st.button("❌ Stop Scanning", use_container_width=True):
                        st.session_state.camera_active = False
                        st.rerun()
                    if image:
                        with st.spinner("Analyzing..."): st.markdown(analyze_label_with_gemini(image))
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("### 📈 Your Health Trends")
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            tf = st.radio("Period", ["Week", "Month"], horizontal=True, label_visibility="collapsed")
            raw_data = get_trend_data_db(st.session_state.user_id, 30 if tf == "Month" else 7)
            if not raw_data: st.info("No Data Available yet.")
            else:
                df = pd.DataFrame(raw_data, columns=["Date", "Category", "Count"])
                st.scatter_chart(df, x="Date", y="Count", color="Category", size="Count")
            st.markdown('</div>', unsafe_allow_html=True)

    elif st.session_state.page == 'calendar':
        st.markdown("## 📅 Grocery Calendar")
        c1, c2 = st.columns([1, 1.5])
        with c1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            sel_date = st.date_input("Select Date", datetime.now(), label_visibility="collapsed")
            st.markdown(f"<h3 style='text-align:center; color:#E2725B;'>{sel_date.strftime('%B %Y')}</h3>", unsafe_allow_html=True)
            st.markdown(create_html_calendar(sel_date.year, sel_date.month, sel_date.day), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f"### List for {sel_date.strftime('%b %d')}")
            col_in, col_btn = st.columns([3, 1])
            new_item = col_in.text_input("Add item...", label_visibility="collapsed")
            if col_btn.button("➕", use_container_width=True):
                if new_item:
                    res = search_vantage_db(new_item)
                    score = res[0]['vms_score'] if res else 5.0
                    add_calendar_item_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"), new_item, score)
                    st.rerun()
            
            items = get_calendar_items_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"))
            for iid, name, score, cat in items:
                col_c, col_d = ("#2E8B57", "#E8F5E9") if cat=='healthy' else ("#F9A825", "#FFF8E1") if cat=='moderate' else ("#D32F2F", "#FFEBEE")
                c_row, c_del = st.columns([5, 1])
                c_row.markdown(f"""<div class='list-row'><span>{name}</span><span class='badge-pill' style='background:{col_d}; color:{col_c};'>{score}</span></div>""", unsafe_allow_html=True)
                if c_del.button("🗑️", key=f"d_{iid}"): 
                    delete_item_db(iid)
                    st.rerun()

    elif st.session_state.page == 'log':
        st.markdown("## 📝 Grocery Log")
        history = get_log_history_db(st.session_state.user_id)
        grouped = defaultdict(list)
        for d_obj, name, score, cat in history: 
            grouped[d_obj.strftime("%a, %b %d")].append({"n": name, "s": score, "c": cat})
        
        for d_lbl, items in grouped.items():
            st.markdown(f"""<div class="card"><div style="font-weight:bold; border-bottom:1px solid #EEE; padding-bottom:10px; margin-bottom:10px;">🛍️ {d_lbl}</div>""", unsafe_allow_html=True)
            for item in items:
                col = "#2E8B57" if item['c']=='healthy' else "#F9A825" if item['c']=='moderate' else "#D32F2F"
                st.markdown(f"<div style='display:flex; justify-content:space-between;'><span>{item['n']}</span><strong style='color:{col}'>{item['s']}</strong></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
