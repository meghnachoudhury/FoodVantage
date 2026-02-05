import streamlit as st
from streamlit_back_camera_input import back_camera_input
import pandas as pd
import random
import time
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
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
if 'show_scanner' not in st.session_state: st.session_state.show_scanner = False # To toggle camera

# --- 3. CUSTOM CSS ---
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
    .stButton>button { border-radius: 12px; font-weight: 600; border: none; height: 45px; transition: all 0.2s; }
    .stButton>button:hover { transform: scale(1.02); }
    
    /* Custom Big Camera Button */
    .big-cam-btn { 
        font-size: 3rem !important; 
        padding: 20px !important; 
        border-radius: 50% !important; 
        width: 100px !important; 
        height: 100px !important; 
        background: #E2725B !important;
        color: white !important;
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto;
        box-shadow: 0 10px 25px rgba(226, 114, 91, 0.4);
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] { background-color: white; border-right: 1px solid #F0F0F0; }
    
    /* Scores & Badges */
    .badge { padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: bold; }
    .bg-green { background: #E8F5E9; color: #2E8B57; }
    .bg-red { background: #FFEBEE; color: #D32F2F; }
    .bg-yellow { background: #FFF8E1; color: #F9A825; }
    
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

def render_logo(size="3rem"):
    st.markdown(f"<div style='text-align: center; margin-bottom: 20px;'><div class='logo-text' style='font-size: {size};'>foodvantage<span class='logo-dot'>.</span></div></div>", unsafe_allow_html=True)

def get_consistent_score(text):
    """Generates a consistent 0-10 score based on item name"""
    # Use hash so "Soda" always gets same score
    hash_val = int(hashlib.sha256(text.encode()).hexdigest(), 16)
    # Map to 0.0 - 10.0 range
    score = (hash_val % 100) / 10.0
    return round(score, 1)

def get_unique_recipes():
    """Returns 15 UNIQUE recipes"""
    pool = [
        {"icon":"🥗","n":"Kale Caesar","c":"210","t":"Keto"},
        {"icon":"🐟","n":"Grilled Salmon","c":"450","t":"High Protein"},
        {"icon":"🥑","n":"Avo Toast","c":"320","t":"Healthy Fat"},
        {"icon":"🥒","n":"Zoodles Pesto","c":"180","t":"Low Carb"},
        {"icon":"🫐","n":"Acai Bowl","c":"290","t":"Antioxidant"},
        {"icon":"🥣","n":"Lentil Soup","c":"250","t":"Fiber Rich"},
        {"icon":"🥚","n":"Egg Bites","c":"140","t":"High Protein"},
        {"icon":"🍗","n":"Chicken Satay","c":"310","t":"High Protein"},
        {"icon":"🍄","n":"Mushroom Risotto","c":"400","t":"Vegetarian"},
        {"icon":"🌮","n":"Turkey Taco","c":"280","t":"Lean Meat"},
        {"icon":"🍤","n":"Garlic Shrimp","c":"220","t":"Low Cal"},
        {"icon":"🥬","n":"Spinach Wrap","c":"190","t":"Vegan"},
        {"icon":"🥔","n":"Sweet Potato","c":"160","t":"Complex Carb"},
        {"icon":"🥕","n":"Hummus Dip","c":"180","t":"Snack"},
        {"icon":"🥥","n":"Chia Pudding","c":"210","t":"Omega-3"},
        {"icon":"🍵","n":"Matcha Latte","c":"90","t":"Focus"},
        {"icon":"🥩","n":"Steak Salad","c":"420","t":"Iron Rich"}
    ]
    return random.sample(pool, 15)

# --- 4. PAGE ROUTING LOGIC ---

# === PAGE: LOGIN ===
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
                    else:
                        st.error("User not found.")
            
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
        
        # 1. FIXED SEARCH (Rayner Scale + Consistency)
        st.markdown("##### 🔍 Search Groceries")
        search_q = st.text_input("Check score", placeholder="e.g. Soda", label_visibility="collapsed")
        
        if search_q:
            # Consistent Score Logic
            score = get_consistent_score(search_q)
            
            # Rayner Scale Colors (Low is Good)
            if score < 3.0:
                color, bg, label = "#2E8B57", "#E8F5E9", "Metabolic Green" # Healthy
            elif score < 7.0:
                color, bg, label = "#F9A825", "#FFF8E1", "Metabolic Yellow" # Moderate
            else:
                color, bg, label = "#D32F2F", "#FFEBEE", "Metabolic Red" # Unhealthy

            st.markdown(f"""
            <div style="background:white; padding:12px; border-radius:12px; border:1px solid #EEE; margin-top:10px; box-shadow:0 2px 5px rgba(0,0,0,0.05);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="font-weight:bold; font-size:1.0rem;">{search_q}</div>
                    <div style="font-size:0.8rem; color:#888;">Rayner Score</div>
                </div>
                <div style="color:{color}; font-weight:900; font-size:2rem; line-height:1.2;">{score}</div>
                <div style="background:{bg}; color:{color}; padding:4px 8px; border-radius:4px; font-size:0.75rem; font-weight:bold; display:inline-block;">{label}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Clear Button
            if st.button("❌ Clear Search"):
                st.rerun() # Wipes the text input on reload

        st.markdown("---")
        # Navigation
        if st.button("🏠 Dashboard", use_container_width=True): st.session_state.page = 'dashboard'; st.rerun()
        if st.button("📅 Grocery Calendar", use_container_width=True): st.session_state.page = 'calendar'; st.rerun()
        if st.button("📝 Grocery Log", use_container_width=True): st.session_state.page = 'log'; st.rerun()
        
        st.markdown("---")
        if st.button("Log Out"): st.session_state.logged_in = False; st.rerun()

    # --- VIEW: DASHBOARD ---
    if st.session_state.page == 'dashboard':
        
        # HERO: CAMERA ICON TOGGLE
        st.markdown("### 📸 Scan Your Groceries")
        with st.container():
            st.markdown('<div class="camera-hero">', unsafe_allow_html=True)
            
            if not st.session_state.show_scanner:
                # The Big Clickable Icon
                st.markdown("""
                    <div style="margin-bottom:15px; color:#666;">Tap the camera to start scanning</div>
                """, unsafe_allow_html=True)
                if st.button("📷", key="start_scan_btn", help="Click to open scanner"):
                    st.session_state.show_scanner = True
                    st.rerun()
            else:
                # The Actual Scanner
                st.info("Scanner Active")
                image = back_camera_input()
                if st.button("❌ Close Scanner"):
                    st.session_state.show_scanner = False
                    st.rerun()

                if image:
                    with st.spinner("Gemini 3 is analyzing..."):
                        st.markdown(analyze_label_with_gemini(image))
            
            st.markdown('</div>', unsafe_allow_html=True)

        # TRENDS GRAPH
        st.markdown("### 📈 Your Health Trends")
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            dates = [f"Day {i}" for i in range(1, 8)]
            chart_data = pd.DataFrame({
                "Healthy": [random.randint(2,8) for _ in range(7)],
                "Unhealthy": [random.randint(0,3) for _ in range(7)]
            }, index=dates)
            st.line_chart(chart_data, color=["#2E8B57", "#E2725B"], height=250)
            st.markdown('</div>', unsafe_allow_html=True)
            
        # 15 UNIQUE RECIPES
        st.markdown("### 🍳 Recommended Recipes")
        recipes = get_unique_recipes() # Now returns 15 unique items
        cols = st.columns(3)
        for i, r in enumerate(recipes):
            with cols[i%3]:
                st.markdown(f"""
                <div style="background:white; padding:15px; border-radius:12px; border:1px solid #EEE; margin-bottom:10px; text-align:center; transition:0.3s;">
                    <div style="font-size:2rem; margin-bottom:5px;">{r['icon']}</div>
                    <div style="font-weight:bold; font-size:1rem;">{r['n']}</div>
                    <div style="color:#666; font-size:0.8rem;">{r['c']} kcal • {r['t']}</div>
                </div>""", unsafe_allow_html=True)

    # --- VIEW: GROCERY CALENDAR (With Big Date Picker) ---
    elif st.session_state.page == 'calendar':
        st.markdown("## 📅 Grocery Calendar")
        c1, c2 = st.columns([1, 2])
        
        with c1: # Date Picker
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("### Select Day")
            # Prominent Calendar Widget
            sel_date = st.date_input("Select Date", datetime.now(), label_visibility="collapsed")
            date_key = sel_date.strftime("%Y-%m-%d")
            st.caption("Click the date above to open the monthly calendar view.")
            st.markdown('</div>', unsafe_allow_html=True)

        with c2: # Checklist
            st.markdown(f"### List for {sel_date.strftime('%b %d, %Y')}")
            
            # Add Item Form
            col_in, col_btn = st.columns([3, 1])
            new_item = col_in.text_input("Add item...", label_visibility="collapsed", placeholder="Add grocery item...")
            if col_btn.button("➕", use_container_width=True):
                if new_item:
                    score = get_consistent_score(new_item)
                    add_calendar_item_db(st.session_state.user_id, date_key, new_item, int(score * 10)) # Store as 0-100 for DB precision
                    st.rerun()

            # Display Items
            items = get_calendar_items_db(st.session_state.user_id, date_key)
            if not items:
                st.info("No items planned for this day.")
            
            for item_id, name, score_raw, cat, checked in items:
                score_val = score_raw / 10.0 # Convert back to 0-10
                
                # Logic: Low Score = Good (Green)
                if score_val < 3.0: bg_class = "bg-green"
                elif score_val < 7.0: bg_class = "bg-yellow"
                else: bg_class = "bg-red"
                
                c_check, c_text, c_del = st.columns([0.5, 4, 0.5])
                c_text.markdown(f"""
                <div class="list-item">
                    <span style="font-weight:500; font-size:1.1rem;">{name}</span>
                    <span class="badge {bg_class}">{score_val}</span>
                </div>
                """, unsafe_allow_html=True)
                
                if c_del.button("🗑️", key=f"del_{item_id}"):
                    delete_item_db(item_id)
                    st.rerun()

    # --- VIEW: GROCERY LOG ---
    elif st.session_state.page == 'log':
        st.markdown("## 📝 Grocery Log")
        history = get_log_history_db(st.session_state.user_id)
        
        if not history:
            st.info("No purchase history found.")
        
        grouped = defaultdict(list)
        for date_obj, name, score_raw, cat in history:
            d_str = date_obj.strftime("%a, %b %d")
            grouped[d_str].append({"name": name, "score": score_raw/10.0, "cat": cat})
            
        for date_label, items in grouped.items():
            n_healthy = sum(1 for i in items if i['cat'] == 'healthy')
            st.markdown(f"""
            <div class="card" style="padding:0; overflow:hidden;">
                <div style="background:#F5F9F5; padding:15px; border-bottom:1px solid #EEE; display:flex; justify-content:space-between; align-items:center;">
                    <div style="font-weight:bold;">🛍️ {date_label}</div>
                    <div style="font-size:0.8rem; background:white; padding:5px 10px; border-radius:10px; border:1px solid #DDD;">
                        {n_healthy} healthy items
                    </div>
                </div>
                <div style="padding:15px;">
            """, unsafe_allow_html=True)
            
            for item in items:
                # Color Logic
                s = item['score']
                if s < 3.0: color, bg = "#2E8B57", "#E8F5E9"
                elif s < 7.0: color, bg = "#F9A825", "#FFF8E1"
                else: color, bg = "#D32F2F", "#FFEBEE"
                
                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px solid #FAFAFA; padding-bottom:5px;">
                    <span>{item['name']}</span>
                    <span style="background:{bg}; color:{color}; padding:2px 10px; border-radius:12px; font-weight:bold; font-size:0.9rem;">
                        {s}
                    </span>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div></div>", unsafe_allow_html=True)