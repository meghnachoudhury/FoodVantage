import streamlit as st
import sys
import os
import pandas as pd
import hashlib
import calendar as cal_module
import time
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from gemini_api import *
from streamlit_back_camera_input import back_camera_input

st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")

# --- SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'welcome_shown' not in st.session_state: st.session_state.welcome_shown = False
if 'welcome_start_time' not in st.session_state: st.session_state.welcome_start_time = None
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'selected_result' not in st.session_state: st.session_state.selected_result = None
if 'scanning' not in st.session_state: st.session_state.scanning = False
if 'scan_count' not in st.session_state: st.session_state.scan_count = 0

# --- CSS ---
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">', unsafe_allow_html=True)
st.markdown("""
    <style>
    .stApp { background-color: #F7F5F0; color: #1A1A1A; }
    .logo-text { font-family: 'Arial Black', sans-serif; font-size: 3rem; text-align: center; }
    .logo-dot { color: #E2725B; }
    .card { background: white; padding: 24px; border-radius: 20px; border: 1px solid #EEE; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; }
    .white-shelf { background: white; height: 35px; border-radius: 10px; border: 1px solid #EEE; margin-bottom: 25px; }
    .tomato-wrapper { width: 100%; text-align: center; padding: 30px 0; }
    .tomato-icon { font-size: 150px !important; color: tomato !important; }

    /* WELCOME SCREEN */
    .welcome-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        min-height: 70vh;
    }
    
    .welcome-text {
        font-size: 2.5rem;
        font-weight: 800;
        color: #1A1A1A;
        text-align: center;
        margin-bottom: 30px;
    }
    
    .dots {
        display: flex;
        gap: 12px;
        justify-content: center;
    }
    
    .dot {
        width: 16px;
        height: 16px;
        background: #E2725B;
        border-radius: 50%;
        animation: dotPulse 1.5s ease-in-out infinite;
    }
    
    .dot:nth-child(1) { animation-delay: 0s; }
    .dot:nth-child(2) { animation-delay: 0.3s; }
    .dot:nth-child(3) { animation-delay: 0.6s; }
    
    @keyframes dotPulse {
        0%, 60%, 100% { 
            opacity: 0.3;
            transform: scale(0.8);
        }
        30% { 
            opacity: 1;
            transform: scale(1.3);
        }
    }

    /* CAMERA CENTERING */
    [data-testid="stCameraInput"] {
        display: flex !important;
        justify-content: center !important;
    }
    
    .hud-container {
        position: relative;
        width: 100%;
        max-width: 640px;
        margin: 0 auto;
    }

    .focus-square {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 200px;
        height: 200px;
        border: 4px dashed #E2725B;
        border-radius: 30px;
        z-index: 999;
        pointer-events: none;
        animation: pulseFocus 2s ease-in-out infinite;
    }
    
    @keyframes pulseFocus {
        0%, 100% { opacity: 0.6; }
        50% { opacity: 1.0; }
    }
    
    .hud-bubble {
        position: fixed;
        top: calc(50% - 200px);
        left: 50%;
        transform: translateX(-50%);
        background: white; 
        padding: 16px 28px; 
        border-radius: 50px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.15); 
        border: 3px solid #E2725B;
        z-index: 1000;
        text-align: center;
        min-width: 220px;
    }
    
    .scanning-indicator {
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(226, 114, 91, 0.9);
        color: white;
        padding: 10px 24px;
        border-radius: 25px;
        z-index: 1000;
        font-weight: bold;
        animation: blink 1.5s infinite;
    }
    
    @keyframes blink {
        0%, 100% { opacity: 0.7; }
        50% { opacity: 1.0; }
    }
    
    .result-option {
        background: white;
        padding: 16px;
        border-radius: 12px;
        border: 2px solid #EEE;
        margin-bottom: 10px;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .result-option:hover {
        border-color: #E2725B;
        box-shadow: 0 4px 12px rgba(226, 114, 91, 0.2);
    }
    
    .result-option.selected {
        border-color: #E2725B;
        background: #FFF5F3;
    }
    
    .list-row { 
        display: flex; 
        justify-content: space-between; 
        padding: 10px; 
        background: #FFF; 
        border-radius: 12px; 
        border: 1px solid #F0F0F0; 
        margin-bottom: 8px; 
    }
    </style>
""", unsafe_allow_html=True)

def render_logo(size="3rem"):
    st.markdown(f"<div style='text-align: center; margin-bottom: 10px;'><div class='logo-text' style='font-size: {size};'>foodvantage<span class='logo-dot'>.</span></div></div>", unsafe_allow_html=True)

def create_html_calendar(year, month, selected_day=None):
    cal = cal_module.monthcalendar(year, month)
    html = "<table style='width:100%; text-align:center;'><thead><tr>"
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]: html += f"<th style='color:#E2725B;'>{day}</th>"
    html += "</tr></thead><tbody>"
    for week in cal:
        html += "<tr>"
        for day in week:
            if day == 0: html += "<td></td>"
            else:
                style = "background:#E2725B; color:white; border-radius:50%;" if day == selected_day else ""
                html += f"<td style='padding:10px; {style}'>{day}</td>"
        html += "</tr>"
    return html + "</tbody></table>"

# === ROUTING ===
if not st.session_state.logged_in:
    # LOGIN PAGE
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.write("")
        st.markdown('<div class="card" style="text-align: center;">', unsafe_allow_html=True)
        render_logo(size="3.5rem")
        t1, t2 = st.tabs(["Sign In", "Create Account"])
        with t1:
            u = st.text_input("User ID", key="l_u")
            p = st.text_input("Password", type="password", key="l_p")
            if st.button("Sign In", type="primary", use_container_width=True):
                if authenticate_user(u, p): 
                    st.session_state.user_id = u
                    st.session_state.logged_in = True
                    st.session_state.welcome_shown = False
                    st.session_state.welcome_start_time = time.time()
                    st.rerun()
                else: 
                    st.error("Access Denied.")
        with t2:
            u2 = st.text_input("Choose ID", key="s_u")
            p2 = st.text_input("Choose PWD", type="password", key="s_p")
            if st.button("Create Account", use_container_width=True):
                if create_user(u2, p2): 
                    st.success("✅ Account Created! Please sign in.")
        st.markdown("</div>", unsafe_allow_html=True)

elif not st.session_state.welcome_shown:
    # WELCOME SCREEN
    st.markdown("""
        <div class="welcome-container">
            <div class="welcome-text">Let's start your health journey</div>
            <div class="dots">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Auto-transition after 3 seconds
    if st.session_state.welcome_start_time:
        elapsed = time.time() - st.session_state.welcome_start_time
        if elapsed >= 3:
            st.session_state.welcome_shown = True
            st.rerun()
    
    time.sleep(0.1)
    st.rerun()

else:
    # MAIN APP
    with st.sidebar:
        st.write("")
        st.markdown("##### 🔍 Search")
        search_q = st.text_input("Quick check score", key="sidebar_search")
        if search_q:
            results = search_vantage_db(search_q, limit=5)
            if results:
                st.markdown("**Top Results:**")
                for i, d in enumerate(results):
                    c = "#2E8B57" if d['vms_score'] < 3.0 else "#F9A825" if d['vms_score'] < 7.0 else "#D32F2F"
                    st.markdown(f"""
                        <div class='card' style='padding:12px; margin-bottom:8px;'>
                            <div style='font-size:0.9rem; font-weight:bold;'>{i+1}. {d['name']}</div>
                            <div style='color:{c}; font-weight:bold; font-size:1.3rem;'>{d['vms_score']}</div>
                            <div style='font-size:0.8rem; color:{c};'>{d['rating']}</div>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("Item not found.")
        st.markdown("---")
        if st.button("🏠 Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Log History", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        if st.button("Log Out"): 
            st.session_state.logged_in = False
            st.session_state.welcome_shown = False
            st.rerun()

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
                st.rerun()
        else:
            # SCANNER ACTIVE
            if st.session_state.scanning:
                st.markdown('<div class="scanning-indicator">🔍 Scanning...</div>', unsafe_allow_html=True)
            
            # Show primary result bubble
            if st.session_state.selected_result:
                ls = st.session_state.selected_result
                clr = "#2E8B57" if ls['vms_score'] < 3.0 else "#F9A825" if ls['vms_score'] < 7.0 else "#D32F2F"
                st.markdown(f"""
                    <div class="hud-bubble">
                        <div style="font-size: 0.9rem; margin-bottom: 4px;">{ls['name']}</div>
                        <div style="color:{clr}; font-size:2.2rem; font-weight:900;">{ls['vms_score']}</div>
                        <div style="font-size: 0.8rem; color: {clr};">{ls['rating']}</div>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown('<div class="focus-square"></div>', unsafe_allow_html=True)
            
            st.markdown('<div class="hud-container">', unsafe_allow_html=True)
            image = back_camera_input(key="hud_cam")
            st.markdown('</div>', unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("❌ Stop Scanning", use_container_width=True):
                    st.session_state.camera_active = False
                    st.session_state.scan_results = None
                    st.session_state.selected_result = None
                    st.session_state.scanning = False
                    st.rerun()
            
            # SCANNING LOGIC
            if image and st.session_state.scanning:
                st.session_state.scan_count += 1
                
                if st.session_state.scan_count % 2 == 0:
                    results = vision_live_scan(image)
                    if results:
                        st.session_state.scan_results = results
                        st.session_state.selected_result = results[0]  # Auto-select first (best match)
                        st.session_state.scanning = False
                        st.rerun()

        # SHOW TOP 5 RESULTS
        if st.session_state.scan_results:
            st.markdown("### 📋 Select Your Option")
            st.markdown(f"Found **{len(st.session_state.scan_results)}** matches. Select one:")
            
            for i, result in enumerate(st.session_state.scan_results):
                clr = "#2E8B57" if result['vms_score'] < 3.0 else "#F9A825" if result['vms_score'] < 7.0 else "#D32F2F"
                selected = st.session_state.selected_result == result
                
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
                    st.markdown(f"<div style='text-align:center; color:{clr}; font-size:1.5rem; font-weight:bold;'>{result['vms_score']}</div>", unsafe_allow_html=True)

        # DEEP DIVE
        if st.session_state.selected_result:
            with st.expander("📊 Metabolic Nutrient Deep Dive", expanded=True):
                ls_raw = st.session_state.selected_result['raw']
                st.markdown("#### Clinical Data")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Sugar", f"{ls_raw[3]}g")
                c2.metric("Fiber", f"{ls_raw[4]}g")
                c3.metric("Protein", f"{ls_raw[5]}g")
                c4.metric("Sodium", f"{ls_raw[7]}mg")
                
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
                        st.rerun()

        # TRENDS
        st.markdown("### 📈 Your Health Trends")
        raw = get_trend_data_db(st.session_state.user_id)
        if raw:
            df = pd.DataFrame(raw, columns=["date", "category", "count"])
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            df_pivot = df.pivot(index='date', columns='category', values='count').fillna(0)
            st.area_chart(df_pivot)
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
            st.markdown(f"### List for {sel_date.strftime('%b %d')}")
            items = get_calendar_items_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"))
            if items:
                for iid, name, score, cat in items:
                    clr = "#2E8B57" if score < 3.0 else "#F9A825" if score < 7.0 else "#D32F2F"
                    st.markdown(f"<div class='list-row'><span>{name}</span><strong style='color:{clr}'>{score}</strong></div>", unsafe_allow_html=True)
            else:
                st.info("No items for this date.")

    elif st.session_state.page == 'log':
        st.markdown("## 📝 Log History")
        history = get_log_history_db(st.session_state.user_id)
        if history:
            for d, name, score, cat in history:
                clr = "#2E8B57" if score < 3.0 else "#F9A825" if score < 7.0 else "#D32F2F"
                st.markdown(f"<div class='list-row'><span><b>{d}</b>: {name}</span><strong style='color:{clr}'>{score}</strong></div>", unsafe_allow_html=True)
        else:
            st.info("No history yet.")
