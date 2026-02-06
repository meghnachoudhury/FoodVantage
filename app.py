import streamlit as st
import sys
import os
import pandas as pd
import time
from datetime import datetime
from collections import defaultdict

# Setup paths
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from gemini_api import *
from streamlit_back_camera_input import back_camera_input

# --- 1. CONFIG & STATE ---
st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'transitioning' not in st.session_state: st.session_state.transitioning = False
if 'last_scan' not in st.session_state: st.session_state.last_scan = None

# --- 2. THE DESIGN ENGINE (CSS) ---
st.markdown("""
    <style>
    .stApp { background-color: #F7F5F0; }
    .logo-text { font-family: 'Arial Black', sans-serif; font-size: 3.5rem; letter-spacing: -2px; text-align: center; }
    .logo-dot { color: #E2725B; }
    .card { background: white; padding: 24px; border-radius: 20px; border: 1px solid #EEE; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; }
    
    /* Active Focus HUD Reticle */
    .reticle-container { position: relative; width: 100%; display: flex; justify-content: center; overflow: hidden; }
    .reticle {
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
        width: 180px; height: 180px; border: 2px dashed #E2725B; border-radius: 24px;
        z-index: 10; pointer-events: none;
    }
    
    /* HUD Score Bubble */
    .hud-bubble {
        position: absolute; top: 10%; left: 50%; transform: translateX(-50%);
        background: white; padding: 12px 24px; border-radius: 50px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.1); z-index: 20;
        text-align: center; border: 2px solid #E2725B; min-width: 200px;
    }

    button[data-baseweb="tab"] p { color: black !important; font-weight: bold !important; }
    .welcome-subtitle { font-size: 22px; color: #2c3e50; font-weight: 600; text-align: center; margin-bottom: 20px; }
    .transition-text { font-family: 'Arial Black', sans-serif; font-size: 2.5rem; color: #2c3e50; text-align: center; margin-top: 20vh; }
    </style>
""", unsafe_allow_html=True)

# --- 3. PAGE ROUTING ---

# Animation Transition
if st.session_state.transitioning:
    placeholder = st.empty()
    for dots in [".", "..", "...", ".", "..", "..."]:
        placeholder.markdown(f"<div class='transition-text'>Let us start your health journey{dots}</div>", unsafe_allow_html=True)
        time.sleep(0.4)
    st.session_state.transitioning = False
    st.rerun()

# Login Screen
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.write(""); st.write("")
        st.markdown('<div class="card" style="text-align: center;">', unsafe_allow_html=True)
        st.markdown("<div class='logo-text'>foodvantage<span class='logo-dot'>.</span></div>", unsafe_allow_html=True)
        st.markdown('<p class="welcome-subtitle">Welcome! Ready to eat healthy?</p>', unsafe_allow_html=True)
        t1, t2 = st.tabs(["Sign In", "Create Account"])
        with t1:
            u = st.text_input("User ID", key="l_u")
            p = st.text_input("Password", type="password", key="l_p")
            if st.button("Sign In", type="primary", use_container_width=True):
                if authenticate_user(u, p):
                    st.session_state.user_id, st.session_state.logged_in, st.session_state.transitioning = u, True, True
                    st.rerun()
                else: st.error("Access Denied.")
        with t2:
            u2, p2 = st.text_input("Choose ID", key="s_u"), st.text_input("Choose PWD", type="password", key="s_p")
            if st.button("Create Account", use_container_width=True):
                if create_user(u2, p2): st.success("Done! Sign In.")
        st.markdown("</div>", unsafe_allow_html=True)

# Dashboard
else:
    with st.sidebar:
        st.markdown("<div class='logo-text' style='font-size:2rem;'>foodvantage<span class='logo-dot'>.</span></div>", unsafe_allow_html=True)
        if st.button("🏠 Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Log", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        st.markdown("---")
        if st.button("Log Out"): st.session_state.logged_in = False; st.rerun()

    if st.session_state.page == 'dashboard':
        st.markdown("<h2 style='text-align: center;'>Active Focus Scanner</h2>", unsafe_allow_html=True)

        # Scanner HUD
        with st.container():
            st.markdown('<div class="card reticle-container">', unsafe_allow_html=True)
            st.markdown('<div class="reticle"></div>', unsafe_allow_html=True)
            
            if st.session_state.last_scan:
                ls = st.session_state.last_scan
                clr = "#2E8B57" if ls['rating']=="Green" else "#F9A825" if ls['rating']=="Yellow" else "#D32F2F"
                st.markdown(f"""<div class='hud-bubble'>
                    <b style='color:#1A1A1A; font-size:1.1rem;'>{ls['name']}</b><br>
                    <span style='color:{clr}; font-size:1.6rem; font-weight:900;'>{ls['score']} {ls['rating']}</span>
                </div>""", unsafe_allow_html=True)
            
            image = back_camera_input(key="hud_cam")
            if image:
                with st.spinner("Locking Focus..."):
                    res = vision_live_scan(image)
                    if res: st.session_state.last_scan = res
            st.markdown('</div>', unsafe_allow_html=True)

        # Deep Dive & Logging
        if st.session_state.last_scan:
            with st.expander("📊 Metabolic Deep Dive", expanded=True):
                ls = st.session_state.last_scan
                v = ls['vitals']
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Calories", f"{v['cal']}kcal")
                c2.metric("Sugar", f"{v['sug']}g")
                c3.metric("Fiber", f"{v['fib']}g")
                c4.metric("Protein", f"{v['prot']}g")
                if st.button("➕ Add to My Calendar", use_container_width=True):
                    add_calendar_item_db(st.session_state.user_id, datetime.now().strftime("%Y-%m-%d"), ls['name'], ls['score'])
                    st.toast("Item Added to Health Journey!")

        # Fixed Trends
        st.markdown("### 📈 Health Trends")
        raw_trends = get_trend_data_db(st.session_state.user_id)
        if raw_trends:
            df = pd.DataFrame(raw_trends, columns=["Date", "Category", "Count"])
            st.area_chart(df, x="Date", y="Count", color="Category")
        else:
            st.info("Start scanning items to see your health journey data!")

    # (Keep existing Calendar & Log pages with get_trend_data_db logic)
    elif st.session_state.page == 'calendar':
        # ... (Your verified Calendar code)
        pass