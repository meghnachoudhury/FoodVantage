import streamlit as st
import sys
import os
import pandas as pd
import hashlib
import calendar as cal_module
import time
from datetime import datetime
from collections import defaultdict
# Path resolution for local development
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from gemini_api import *
from streamlit_back_camera_input import back_camera_input

st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")

# --- SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'last_scan' not in st.session_state: st.session_state.last_scan = None
if 'scanning' not in st.session_state: st.session_state.scanning = False
if 'scan_count' not in st.session_state: st.session_state.scan_count = 0

# --- CSS ENGINE (PERFECT CENTERING + HUD) ---
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">', unsafe_allow_html=True)
st.markdown("""
    <style>
    .stApp { background-color: #F7F5F0; color: #1A1A1A; }
    .logo-text { font-family: 'Arial Black', sans-serif; font-size: 3rem; text-align: center; }
    .logo-dot { color: #E2725B; }
    .card { background: white; padding: 24px; border-radius: 20px; border: 1px solid #EEE; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; }
    .white-shelf { background: white; height: 35px; border-radius: 10px; border: 1px solid #EEE; margin-bottom: 25px; }

    /* PERFECT CENTER TOMATO */
    .tomato-wrapper { width: 100%; text-align: center; padding: 30px 0; }
    .tomato-icon { font-size: 150px !important; color: tomato !important; }

    /* === FIXED: PERFECT CAMERA WIDGET CENTERING === */
    
    /* Target Streamlit's camera widget container */
    [data-testid="stCameraInput"] {
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
    }
    
    /* Center the video element itself */
    [data-testid="stCameraInput"] video {
        display: block !important;
        margin: 0 auto !important;
    }
    
    /* HUD Container - wraps everything */
    .hud-container {
        position: relative;
        width: 100%;
        max-width: 640px;
        margin: 0 auto;
        display: flex;
        justify-content: center;
        align-items: center;
    }

    /* THE RETICLE: Mathematically locked to absolute center */
    .focus-square {
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: 180px;
        height: 180px;
        border: 4px dashed #E2725B;
        border-radius: 30px;
        z-index: 999;
        pointer-events: none;
        animation: pulse 2s ease-in-out infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 0.6; }
        50% { opacity: 1.0; }
    }
    
    /* HUD Bubble - floats above reticle */
    .hud-bubble {
        position: fixed;
        top: calc(50% - 180px);
        left: 50%;
        transform: translateX(-50%);
        background: white; 
        padding: 16px 28px; 
        border-radius: 50px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.15); 
        border: 3px solid #E2725B;
        z-index: 1000;
        text-align: center;
        font-weight: bold;
        min-width: 200px;
        animation: slideDown 0.3s ease-out;
    }
    
    @keyframes slideDown {
        from { top: calc(50% - 220px); opacity: 0; }
        to { top: calc(50% - 180px); opacity: 1; }
    }
    
    /* Scanning indicator */
    .scanning-indicator {
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(226, 114, 91, 0.9);
        color: white;
        padding: 8px 20px;
        border-radius: 20px;
        z-index: 1000;
        font-weight: bold;
        animation: blink 1.5s ease-in-out infinite;
    }
    
    @keyframes blink {
        0%, 100% { opacity: 0.7; }
        50% { opacity: 1.0; }
    }
    
    .list-row { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #FFF; border-radius: 12px; border: 1px solid #F0F0F0; margin-bottom: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- HELPERS ---
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

# --- ROUTING ---
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.write(""); st.markdown('<div class="card" style="text-align: center;">', unsafe_allow_html=True)
        render_logo(size="3.5rem")
        t1, t2 = st.tabs(["Sign In", "Create Account"])
        with t1:
            u, p = st.text_input("User ID", key="l_u"), st.text_input("Password", type="password", key="l_p")
            if st.button("Sign In", type="primary", use_container_width=True):
                if authenticate_user(u, p): 
                    st.session_state.user_id, st.session_state.logged_in = u, True
                    st.rerun()
                else: st.error("Access Denied.")
        with t2:
            u2, p2 = st.text_input("Choose ID", key="s_u"), st.text_input("Choose PWD", type="password", key="s_p")
            if st.button("Create Account", use_container_width=True):
                if create_user(u2, p2): st.success("Account Created! Sign in.")
        st.markdown("</div>", unsafe_allow_html=True)

else:
    # --- SIDEBAR ---
    with st.sidebar:
        st.write(""); st.markdown("##### 🔍 Search")
        search_q = st.text_input("Quick check score", key="sidebar_search")
        if search_q:
            res = search_vantage_db(search_q)
            if res:
                d = res[0]
                c = "#2E8B57" if d['vms_score'] < 3.0 else "#F9A825" if d['vms_score'] < 7.0 else "#D32F2F"
                st.markdown(f"<div class='card'><b>{d['name']}</b><br><span style='color:{c}; font-weight:bold; font-size:1.5rem;'>{d['vms_score']}</span></div>", unsafe_allow_html=True)
            else:
                st.warning("Item not found.")
        st.markdown("---")
        if st.button("🏠 Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Log History", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        if st.button("Log Out"): st.session_state.logged_in = False; st.rerun()

    if st.session_state.page == 'dashboard':
        render_logo(size="3.5rem")
        st.markdown("<h3 style='text-align: center;'>Active Focus Scanner</h3>", unsafe_allow_html=True)
        st.markdown('<div class="white-shelf"></div>', unsafe_allow_html=True)
        
        if not st.session_state.camera_active:
            # DASHBOARD ICON
            st.markdown('<div class="tomato-wrapper"><i class="fa fa-camera tomato-icon"></i></div>', unsafe_allow_html=True)
            if st.button("Start Live Scan", type="primary", use_container_width=True):
                st.session_state.camera_active = True
                st.session_state.scanning = True
                st.rerun()
        else:
            # === LIVE SCANNER WITH PERFECT CENTERING ===
            
            # Scanning indicator
            if st.session_state.scanning:
                st.markdown('<div class="scanning-indicator">🔍 Scanning...</div>', unsafe_allow_html=True)
            
            # Show HUD bubble if product detected
            if st.session_state.last_scan:
                ls = st.session_state.last_scan
                clr = "#2E8B57" if ls['vms_score'] < 3.0 else "#F9A825" if ls['vms_score'] < 7.0 else "#D32F2F"
                st.markdown(f"""
                    <div class="hud-bubble">
                        <div style="font-size: 0.9rem; margin-bottom: 4px;">{ls['name']}</div>
                        <div style="color:{clr}; font-size:2.2rem; font-weight:900;">{ls['vms_score']}</div>
                        <div style="font-size: 0.8rem; color: {clr};">{ls['rating']}</div>
                    </div>
                """, unsafe_allow_html=True)

            # The reticle (focus square)
            st.markdown('<div class="focus-square"></div>', unsafe_allow_html=True)
            
            # Camera widget in HUD container
            st.markdown('<div class="hud-container">', unsafe_allow_html=True)
            image = back_camera_input(key="hud_cam")
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Stop button
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("❌ Stop Scanning", use_container_width=True):
                    st.session_state.camera_active = False
                    st.session_state.last_scan = None
                    st.session_state.scanning = False
                    st.rerun()
            
            # === CONTINUOUS SCANNING LOGIC ===
            if image and st.session_state.scanning:
                # Only scan every 3rd capture to avoid overwhelming the API
                st.session_state.scan_count += 1
                
                if st.session_state.scan_count % 3 == 0:
                    with st.spinner("Analyzing..."):
                        res = vision_live_scan(image)
                        if res:
                            st.session_state.last_scan = res[0]
                            st.session_state.scanning = False  # Stop after successful scan
                            st.rerun()

        # --- DEEP DIVE SECTION ---
        if st.session_state.last_scan:
            with st.expander("📊 Metabolic Nutrient Deep Dive", expanded=True):
                ls_raw = st.session_state.last_scan['raw']
                st.markdown("#### Clinical Data (Open Food Facts)")
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
                            st.session_state.last_scan['name'], 
                            st.session_state.last_scan['vms_score']
                        )
                        st.success("✅ Added to calendar!")
                with col2:
                    if st.button("🔄 Scan Again", use_container_width=True):
                        st.session_state.last_scan = None
                        st.session_state.scanning = True
                        st.rerun()

        # === FIXED: TRENDS GRAPH ===
        st.markdown("### 📈 Your Health Trends")
        raw = get_trend_data_db(st.session_state.user_id, days=30)
        
        if raw and len(raw) > 0:
            # Convert to DataFrame
            df = pd.DataFrame(raw, columns=["date", "category", "count"])
            
            # Convert date column to string for display
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            
            # Pivot for better chart display
            df_pivot = df.pivot(index='date', columns='category', values='count').fillna(0)
            
            st.area_chart(df_pivot)
        else:
            st.info("📊 No data yet. Start logging items to see your trends!")
            
            # Add sample data button for testing
            if st.button("📝 Add Sample Data (for testing)"):
                from datetime import timedelta
                today = datetime.now()
                for i in range(7):
                    date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                    add_calendar_item_db(st.session_state.user_id, date, f"Sample Item {i}", float(i % 10))
                st.success("Sample data added! Refresh to see trends.")
                st.rerun()

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
            st.info("No history yet. Start scanning items!")
