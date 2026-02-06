import streamlit as st
import sys
import os
import pandas as pd
import hashlib
import calendar as cal_module
import time
from datetime import datetime
from collections import defaultdict

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from gemini_api import *
from streamlit_back_camera_input import back_camera_input

st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")

# --- SESSION STATE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'transitioning' not in st.session_state: st.session_state.transitioning = False
if 'last_scan' not in st.session_state: st.session_state.last_scan = None

# --- CSS (MATH CENTERING) ---
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">', unsafe_allow_html=True)
st.markdown("""
    <style>
    .stApp { background-color: #F7F5F0; color: #1A1A1A; }
    .logo-text { font-family: 'Arial Black', sans-serif; font-size: 3rem; letter-spacing: -2px; line-height: 1.0; margin-bottom: 0; }
    .logo-dot { color: #E2725B; }
    .card { background: white; padding: 24px; border-radius: 20px; border: 1px solid #EEE; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; }
    .white-shelf { background: white; height: 35px; border-radius: 10px; border: 1px solid #EEE; margin-bottom: 25px; }

    /* PERFECT CENTERING WRAPPER */
    .centered-wrapper { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; text-align: center; }
    
    .scanner-ui-container { position: relative; display: flex; justify-content: center; align-items: center; width: 100%; max-width: 500px; margin: 0 auto; border-radius: 20px; overflow: hidden; }
    .reticle-square { position: absolute; width: 140px; height: 140px; border: 4px dashed #E2725B; border-radius: 20px; z-index: 100; pointer-events: none; }
    
    .hud-bubble { background: white; padding: 10px 20px; border-radius: 50px; box-shadow: 0 8px 24px rgba(0,0,0,0.1); margin-bottom: 10px; border: 2px solid #E2725B; text-align: center; font-weight: bold; }
    button[data-baseweb="tab"] p { color: black !important; font-weight: bold !important; }
    .welcome-subtitle { font-size: 22px; color: #2c3e50; font-weight: 600; text-align: center; }
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
if st.session_state.transitioning:
    p = st.empty()
    for dots in [".", "..", "...", ".", "..", "..."]:
        p.markdown(f"<div style='text-align:center; font-size:2.5rem; margin-top:20vh;'>Let us start your health journey{dots}</div>", unsafe_allow_html=True)
        time.sleep(0.4)
    st.session_state.transitioning = False; st.rerun()

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.write(""); st.markdown('<div class="card" style="text-align: center;">', unsafe_allow_html=True)
        render_logo(size="3.5rem")
        st.markdown('<p class="welcome-subtitle">Welcome! Ready to eat healthy?</p>', unsafe_allow_html=True)
        t1, t2 = st.tabs(["Sign In", "Create Account"])
        with t1:
            u, p = st.text_input("User ID", key="l_u"), st.text_input("Password", type="password", key="l_p")
            if st.button("Sign In", type="primary", use_container_width=True):
                if authenticate_user(u, p): st.session_state.user_id, st.session_state.logged_in, st.session_state.transitioning = u, True, True; st.rerun()
        with t2:
            u2, p2 = st.text_input("Choose ID", key="s_u"), st.text_input("Choose PWD", type="password", key="s_p")
            if st.button("Create Account", use_container_width=True):
                if create_user(u2, p2): st.success("Created! Sign In.")
        st.markdown("</div>", unsafe_allow_html=True)

else:
    with st.sidebar:
        st.write("")
        st.markdown("##### 🔍 Search")
        search_q = st.text_input("Check score", placeholder="e.g. Avocado", label_visibility="collapsed")
        if search_q:
            res = search_vantage_db(search_q)
            if res:
                d = res[0]
                c = "#2E8B57" if d['vms_score'] < 3.0 else "#F9A825" if d['vms_score'] < 7.0 else "#D32F2F"
                st.markdown(f"<div style='background:white; padding:12px; border-radius:12px; border:1px solid #EEE;'><b>{d['name']}</b><br><span style='color:{c}; font-weight:bold; font-size:1.5rem;'>{d['vms_score']}</span></div>", unsafe_allow_html=True)
        st.markdown("---")
        if st.button("🏠 Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Grocery Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Grocery Log", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        st.markdown("---")
        if st.button("Log Out"): st.session_state.logged_in = False; st.rerun()

    if st.session_state.page == 'dashboard':
        render_logo(size="3.5rem")
        st.markdown("<h3 style='text-align: center;'>Active Focus Scanner</h3>", unsafe_allow_html=True)
        st.markdown('<div class="white-shelf"></div>', unsafe_allow_html=True)
        
        # --- CENTERED CAMERA LAYOUT ---
        st.markdown('<div class="centered-wrapper">', unsafe_allow_html=True)
        if not st.session_state.camera_active:
            st.markdown('<i class="fa fa-camera" style="font-size:150px; color:tomato; margin-bottom:20px;"></i>', unsafe_allow_html=True)
            if st.button("Start Live Scan", type="primary", use_container_width=True):
                st.session_state.camera_active = True; st.rerun()
        else:
            if st.session_state.last_scan:
                ls = st.session_state.last_scan
                clr = "#2E8B57" if ls['rating']=="Metabolic Green" else "#F9A825" if ls['rating']=="Metabolic Yellow" else "#D32F2F"
                st.markdown(f"<div class='hud-bubble'><b>{ls['name']}</b> | <span style='color:{clr};'>{ls['vms_score']} {ls['rating']}</span></div>", unsafe_allow_html=True)
            
            # THE HUD WIDGET
            st.markdown('<div class="scanner-ui-container">', unsafe_allow_html=True)
            st.markdown('<div class="reticle-square"></div>', unsafe_allow_html=True)
            image = back_camera_input(key="hud_cam")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if st.button("❌ Stop Scanning", use_container_width=True):
                st.session_state.camera_active = False; st.session_state.last_scan = None; st.rerun()
            if image:
                res = vision_live_scan(image)
                if res: st.session_state.last_scan = res[0]
        st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.last_scan:
            with st.expander("📊 Metabolic Deep Dive", expanded=True):
                ls = st.session_state.last_scan['raw']
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Sugar", f"{ls[3]}g"); c2.metric("Fiber", f"{ls[4]}g"); c3.metric("Protein", f"{ls[5]}g"); c4.metric("Sodium", f"{ls[7]}mg")
                if st.button("➕ Add to My Calendar", use_container_width=True):
                    add_calendar_item_db(st.session_state.user_id, datetime.now().strftime("%Y-%m-%d"), st.session_state.last_scan['name'], st.session_state.last_scan['vms_score'])
                    st.toast("Logged!")

        st.markdown("### 📈 Your Health Trends")
        raw = get_trend_data_db(st.session_state.user_id)
        if raw:
            df = pd.DataFrame(raw, columns=["Date", "Category", "Count"])
            st.area_chart(df, x="Date", y="Count", color="Category")

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
                    add_calendar_item_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"), new_item, score); st.rerun()
            items = get_calendar_items_db(st.session_state.user_id, sel_date.strftime("%Y-%m-%d"))
            for iid, name, score, cat in items:
                col_c = "#2E8B57" if score < 3.0 else "#F9A825" if score < 7.0 else "#D32F2F"
                cr, cd = st.columns([5, 1])
                cr.markdown(f"""<div style='display:flex; justify-content:space-between; align-items:center; padding:10px; background:#FFF; border-radius:12px; border:1px solid #F0F0F0; margin-bottom:8px;'><span>{name}</span><span style='color:{col_c}; font-weight:bold;'>{score}</span></div>""", unsafe_allow_html=True)
                if cd.button("🗑️", key=f"d_{iid}"): delete_item_db(iid); st.rerun()

    elif st.session_state.page == 'log':
        st.markdown("## 📝 Grocery Log")
        history = get_log_history_db(st.session_state.user_id)
        grouped = defaultdict(list)
        for d_obj, name, score, cat in history: grouped[d_obj.strftime("%a, %b %d")].append({"n": name, "s": score, "c": cat})
        for d_lbl, items in grouped.items():
            st.markdown(f"""<div class="card"><div style="font-weight:bold; border-bottom:1px solid #EEE; padding-bottom:10px; margin-bottom:10px;">🛍️ {d_lbl}</div>""", unsafe_allow_html=True)
            for item in items:
                col = "#2E8B57" if item['c']=='healthy' else "#F9A825" if item['c']=='moderate' else "#D32F2F"
                st.markdown(f"<div style='display:flex; justify-content:space-between;'><span>{item['n']}</span><strong style='color:{col}'>{item['s']}</strong></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)