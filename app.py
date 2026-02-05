import streamlit as st
from streamlit_back_camera_input import back_camera_input
import pandas as pd
import random
import time
from datetime import datetime
from collections import defaultdict
# Connect the backend functions
from src.gemini_api import (
    analyze_label_with_gemini, 
    create_user, 
    authenticate_user, 
    add_calendar_item_db, 
    get_calendar_items_db,
    delete_item_db,
    get_log_history_db
)

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")

# --- 2. SESSION STATE INIT ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'page' not in st.session_state: st.session_state.page = 'login'
if 'user_id' not in st.session_state: st.session_state.user_id = ""

# --- 3. CUSTOM CSS (Matching Your Screenshots) ---
st.markdown("""
    <style>
    /* Global Background */
    .stApp { background-color: #FDFBF7; color: #1A1A1A; }
    
    /* Tekni-Style Logo */
    .logo-text { font-family: 'Arial Black', sans-serif; font-size: 3rem; letter-spacing: -2px; line-height: 1.0; margin-bottom: 0; }
    .logo-dot { color: #E2725B; }
    
    /* Card Containers */
    .card { background: white; padding: 24px; border-radius: 20px; border: 1px solid #F0F0F0; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; }
    
    /* Camera Hero Section */
    .camera-hero { background: white; padding: 30px; border-radius: 24px; border: 1px solid #E0E0E0; margin-bottom: 30px; text-align: center; display: flex; flex-direction: column; align-items: center; box-shadow: 0 8px 20px rgba(0,0,0,0.05); }
    
    /* Buttons */
    .stButton>button { border-radius: 12px; font-weight: 600; border: none; height: 45px; }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] { background-color: white; border-right: 1px solid #F0F0F0; }
    
    /* Calendar List Items */
    .list-item { display: flex; align-items: center; justify-content: space-between; padding: 15px; border: 1px solid #EEE; border-radius: 16px; margin-bottom: 10px; background: white; }
    
    /* Scores & Badges */
    .badge { padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: bold; }
    .bg-green { background: #E8F5E9; color: #2E8B57; }
    .bg-red { background: #FFEBEE; color: #D32F2F; }
    .bg-yellow { background: #FFF8E1; color: #F9A825; }
    
    /* Remove default headers */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

def render_logo(size="3rem"):
    st.markdown(f"<div style='text-align: center; margin-bottom: 20px;'><div class='logo-text' style='font-size: {size};'>foodvantage<span class='logo-dot'>.</span></div></div>", unsafe_allow_html=True)

# --- 4. PAGE ROUTING LOGIC ---

# === PAGE: LOGIN ===
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.write(""); st.write("")
        with st.container():
            st.markdown('<div class="card" style="text-align: center;">', unsafe_allow_html=True)
            render_logo(size="3.5rem")
            st.caption("Welcome back! Ready to eat healthy?")
            
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
                    else:
                        st.error("User not found or incorrect password.")
            
            with tab2:
                u2 = st.text_input("Choose User ID", key="s_u")
                p2 = st.text_input("Choose Password", type="password", key="s_p")
                if st.button("Create Account", use_container_width=True):
                    if create_user(u2, p2):
                        st.success("Account created! Go to Sign In tab.")
                    else:
                        st.error("User ID already exists.")
            st.markdown("</div>", unsafe_allow_html=True)

# === PAGE: MAIN APP ===
else:
    # --- SIDEBAR MENU ---
    with st.sidebar:
        render_logo(size="2rem")
        
        # 1. Search (Sidebar Only)
        st.markdown("##### 🔍 Search Groceries")
        search_q = st.text_input("Find health scores", placeholder="e.g. Soda", label_visibility="collapsed")
        if search_q:
            # Simple simulation for instant feedback
            score = random.randint(30, 99)
            color = "#2E8B57" if score > 70 else "#D32F2F"
            st.markdown(f"""
            <div style="background:white; padding:12px; border-radius:12px; border:1px solid #EEE; margin-top:10px; box-shadow:0 2px 5px rgba(0,0,0,0.05);">
                <div style="font-weight:bold; font-size:1.1rem;">{search_q}</div>
                <div style="color:{color}; font-weight:bold; font-size:1.5rem;">{score}</div>
                <div style="font-size:0.8rem; color:#888;">Gemini 3 Est.</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        # Navigation Buttons
        if st.button("🏠 Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Grocery Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Grocery Log", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        
        st.markdown("---")
        if st.button("Log Out"): st.session_state.logged_in = False; st.rerun()

    # --- VIEW: DASHBOARD ---
    if st.session_state.page == 'dashboard':
        st.markdown("### 📸 Scan Your Groceries")
        # Hero Camera
        with st.container():
            st.markdown('<div class="camera-hero">', unsafe_allow_html=True)
            image = back_camera_input()
            st.markdown('</div>', unsafe_allow_html=True)
            if image:
                with st.spinner("Gemini 3 is analyzing..."):
                    st.success("Scanned!")
                    st.markdown(analyze_label_with_gemini(image))

        # Trends Graph
        st.markdown("### 📈 Your Health Trends")
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            # Fake data for visual (Phase 3: Connect this to real DB)
            dates = [f"Day {i}" for i in range(1, 8)]
            chart_data = pd.DataFrame({
                "Healthy": [random.randint(10,20) for _ in range(7)],
                "Unhealthy": [random.randint(2,8) for _ in range(7)]
            }, index=dates)
            st.line_chart(chart_data, color=["#2E8B57", "#E2725B"], height=250)
            st.markdown('</div>', unsafe_allow_html=True)
            
        # 15 Recipes Grid
        st.markdown("### 🍳 Recommended Recipes")
        recipes = [{"icon":"🥗","n":"Kale Salad","c":"150"},{"icon":"🐟","n":"Grilled Salmon","c":"450"},{"icon":"🥑","n":"Avo Toast","c":"320"}] * 5
        cols = st.columns(3)
        for i, r in enumerate(recipes):
            with cols[i%3]:
                st.markdown(f"""<div style="background:white; padding:15px; border-radius:12px; border:1px solid #EEE; margin-bottom:10px; text-align:center;">
                <div style="font-size:2rem;">{r['icon']}</div>
                <strong>{r['n']}</strong><br><span style="color:#888; font-size:0.8rem;">{r['c']} kcal</span>
                </div>""", unsafe_allow_html=True)

    # --- VIEW: GROCERY CALENDAR (DB Integrated) ---
    elif st.session_state.page == 'calendar':
        st.markdown("## 📅 Grocery Calendar")
        c1, c2 = st.columns([1, 2])
        
        with c1: # Date Picker
            st.markdown('<div class="card">', unsafe_allow_html=True)
            sel_date = st.date_input("Select Date", datetime.now())
            date_key = sel_date.strftime("%Y-%m-%d")
            st.markdown('</div>', unsafe_allow_html=True)

        with c2: # Checklist
            st.markdown(f"### List for {sel_date.strftime('%b %d, %Y')}")
            
            # Add Item Form
            col_in, col_btn = st.columns([3, 1])
            new_item = col_in.text_input("Add item...", label_visibility="collapsed", placeholder="Add grocery item...")
            if col_btn.button("➕", use_container_width=True):
                if new_item:
                    score = random.randint(35, 99) # Gemini simulation
                    add_calendar_item_db(st.session_state.user_id, date_key, new_item, score)
                    st.rerun()

            # Display Items
            items = get_calendar_items_db(st.session_state.user_id, date_key)
            if not items:
                st.info("No items planned for today.")
            
            for item_id, name, score, cat, checked in items:
                # Color Logic
                bg_class = "bg-green" if cat=='healthy' else "bg-yellow" if cat=='moderate' else "bg-red"
                
                # Render Row
                c_check, c_text, c_del = st.columns([0.5, 4, 0.5])
                c_text.markdown(f"""
                <div class="list-item">
                    <span style="font-weight:500; font-size:1.1rem;">{name}</span>
                    <span class="badge {bg_class}">{score} ✎</span>
                </div>
                """, unsafe_allow_html=True)
                
                if c_del.button("🗑️", key=f"del_{item_id}"):
                    delete_item_db(item_id)
                    st.rerun()

    # --- VIEW: GROCERY LOG (Grouped by Date) ---
    elif st.session_state.page == 'log':
        st.markdown("## 📝 Grocery Log")
        
        # 1. Fetch ALL data for this user
        history = get_log_history_db(st.session_state.user_id)
        
        if not history:
            st.info("No purchase history found.")
        
        # 2. Group by Date using Python
        grouped = defaultdict(list)
        for date_obj, name, score, cat in history:
            d_str = date_obj.strftime("%a, %b %d")
            grouped[d_str].append({"name": name, "score": score, "cat": cat})
            
        # 3. Render Cards
        for date_label, items in grouped.items():
            # Calculate stats
            n_healthy = sum(1 for i in items if i['cat'] == 'healthy')
            n_unhealthy = sum(1 for i in items if i['cat'] == 'unhealthy')
            
            st.markdown(f"""
            <div class="card" style="padding:0; overflow:hidden;">
                <div style="background:#F5F9F5; padding:15px; border-bottom:1px solid #EEE; display:flex; justify-content:space-between; align-items:center;">
                    <div style="font-weight:bold;">🛍️ {date_label}</div>
                    <div style="font-size:0.8rem; background:white; padding:5px 10px; border-radius:10px; border:1px solid #DDD;">
                        {n_healthy} healthy • {n_unhealthy} unhealthy
                    </div>
                </div>
                <div style="padding:15px;">
            """, unsafe_allow_html=True)
            
            for item in items:
                color = "#2E8B57" if item['cat']=='healthy' else "#F9A825" if item['cat']=='moderate' else "#D32F2F"
                bg = "#E8F5E9" if item['cat']=='healthy' else "#FFF8E1" if item['cat']=='moderate' else "#FFEBEE"
                
                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px solid #FAFAFA; padding-bottom:5px;">
                    <span>{item['name']}</span>
                    <span style="background:{bg}; color:{color}; padding:2px 10px; border-radius:12px; font-weight:bold; font-size:0.9rem;">
                        {item['score']}
                    </span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div></div>", unsafe_allow_html=True)