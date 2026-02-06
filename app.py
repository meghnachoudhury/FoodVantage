import streamlit as st
import sys
import os
import pandas as pd
import time
from datetime import datetime
from collections import defaultdict

# Path Resolution
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from gemini_api import *
from streamlit_back_camera_input import back_camera_input

# --- 1. CONFIG & SESSION ---
st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'transitioning' not in st.session_state: st.session_state.transitioning = False
if 'last_scan' not in st.session_state: st.session_state.last_scan = None

# --- 2. CSS ENGINE ---
st.markdown("""
    <style>
    .stApp { background-color: #F7F5F0; }
    .logo-text { font-family: 'Arial Black', sans-serif; font-size: 3.5rem; letter-spacing: -2px; text-align: center; }
    .logo-dot { color: #E2725B; }
    .card { background: white; padding: 24px; border-radius: 20px; border: 1px solid #EEE; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; text-align: center; }
    
    /* Centered Active HUD Reticle */
    .scanner-wrapper { position: relative; width: 100%; max-width: 700px; margin: 0 auto; display: flex; flex-direction: column; align-items: center; }
    .reticle-overlay {
        position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
        width: 180px; height: 180px; border: 4px dashed #E2725B; border-radius: 24px;
        z-index: 100; pointer-events: none;
    }
    
    .hud-bubble {
        background: white; padding: 12px 24px; border-radius: 50px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.1); margin-bottom: 20px;
        border: 2px solid #E2725B; display: inline-block;
    }

    button[data-baseweb="tab"] p { color: black !important; font-weight: bold !important; }
    .welcome-subtitle { font-size: 22px; color: #2c3e50; font-weight: 600; text-align: center; }
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

# Authentication Screen
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.write(""); st.write("")
        st.markdown('<div class="card">', unsafe_allow_html=True)
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
                if create_user(u2, p2): st.success("Created! Please Sign In.")
        st.markdown("</div>", unsafe_allow_html=True)

# Main Application
else:
    with st.sidebar:
        st.markdown("<div class='logo-text' style='font-size:2rem;'>foodvantage<span class='logo-dot'>.</span></div>", unsafe_allow_html=True)
        if st.button("🏠 Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Log History", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        st.markdown("---")
        if st.button("Log Out"): st.session_state.logged_in = False; st.rerun()

    if st.session_state.page == 'dashboard':
        st.markdown("<h2 style='text-align: center;'>Active Focus Scanner</h2>", unsafe_allow_html=True)

        if not st.session_state.camera_active:
            # GATEKEEPER LAYOUT
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<i class="fa fa-camera" style="font-size:120px; color:tomato; margin-bottom:20px;"></i>', unsafe_allow_html=True)
            if st.button("Start Live Scan", type="primary", use_container_width=True):
                st.session_state.camera_active = True
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            # HUD SCANNER LAYOUT
            st.markdown('<div class="scanner-wrapper">', unsafe_allow_html=True)
            
            # HUD Bubble (Floating Score)
            if st.session_state.last_scan:
                ls = st.session_state.last_scan
                clr = "#2E8B57" if ls['rating']=="Green" else "#F9A825" if ls['rating']=="Yellow" else "#D32F2F"
                st.markdown(f"""<div class='hud-bubble'>
                    <b style='color:#1A1A1A; font-size:1.2rem;'>{ls['name']}</b> | 
                    <span style='color:{clr}; font-weight:900;'>{ls['score']} {ls['rating']}</span>
                </div>""", unsafe_allow_html=True)
            
            # Camera Viewport with Centered Reticle
            st.markdown('<div class="reticle-overlay"></div>', unsafe_allow_html=True)
            image = back_camera_input(key="hud_scanner")
            
            # Control Toggle
            if st.button("❌ Stop Scanning", use_container_width=True):
                st.session_state.camera_active = False
                st.session_state.last_scan = None
                st.rerun()
            
            if image:
                # Silent Scan Capture
                res = vision_live_scan(image)
                if res: st.session_state.last_scan = res
            st.markdown('</div>', unsafe_allow_html=True)

        # Result Details & Trends
        if st.session_state.last_scan:
            with st.expander("📊 Metabolic Deep Dive", expanded=True):
                ls = st.session_state.last_scan
                v = ls['vitals']
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Calories", f"{v['cal']}kcal")
                c2.metric("Sugar", f"{v['sug']}g")
                c3.metric("Fiber", f"{v['fib']}g")
                c4.metric("Protein", f"{v['prot']}g")
                if st.button("➕ Log to Journey", use_container_width=True):
                    add_calendar_item_db(st.session_state.user_id, datetime.now().strftime("%Y-%m-%d"), ls['name'], ls['score'])
                    st.toast("Success! Logged to Health Trends.")

        st.markdown("### 📈 Health Trends")
        raw_trends = get_trend_data_db(st.session_state.user_id)
        if raw_trends:
            df = pd.DataFrame(raw_trends, columns=["Date", "Category", "Count"])
            st.area_chart(df, x="Date", y="Count", color="Category")
        else:
            st.info("Log your first scan to see your metabolic trends.")

    elif st.session_state.page == 'calendar':
        # --- CALENDAR VIEW ---
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
            new_item = col_in.text_input("Quick Add...", label_visibility="collapsed")
            if col_btn.button("➕", use_container_width=True):
                if new_item:
                    res = search_vantage_db(new_item)
                    score = res['score'] if res else 5.0
                    add_calendar_item_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"), new_item, score)
                    st.rerun()
            
            items = get_calendar_items_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"))
            for iid, name, score, cat in items:
                col_c, col_d = ("#2E8B57", "#E8F5E9") if cat=='healthy' else ("#F9A825", "#FFF8E1") if cat=='moderate' else ("#D32F2F", "#FFEBEE")
                cr, cd = st.columns([5, 1])
                cr.markdown(f"""<div class='list-row'><span>{name}</span><span class='badge-pill' style='background:{col_d}; color:{col_c};'>{score}</span></div>""", unsafe_allow_html=True)
                if cd.button("🗑️", key=f"d_{iid}"): delete_item_db(iid); st.rerun()

    elif st.session_state.page == 'log':
        # --- HISTORY LOG ---
        st.markdown("## 📝 Log History")
        history = get_log_history_db(st.session_state.user_id)
        grouped = defaultdict(list)
        for d_obj, name, score, cat in history: grouped[d_obj.strftime("%a, %b %d")].append({"n": name, "s": score, "c": cat})
        for d_lbl, items in grouped.items():
            st.markdown(f"""<div class="card"><div style="font-weight:bold; border-bottom:1px solid #EEE; padding-bottom:10px; margin-bottom:10px;">🛍️ {d_lbl}</div>""", unsafe_allow_html=True)
            for item in items:
                col = "#2E8B57" if item['c']=='healthy' else "#F9A825" if item['c']=='moderate' else "#D32F2F"
                st.markdown(f"<div style='display:flex; justify-content:space-between;'><span>{item['n']}</span><strong style='color:{col}'>{item['s']}</strong></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)