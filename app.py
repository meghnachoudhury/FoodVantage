import streamlit as st
if "preview_ok" not in st.session_state:
    st.session_state.preview_ok = True
    st.stop()
st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide", initial_sidebar_state="expanded")
# Initialize phase
if "phase" not in st.session_state:
    st.session_state.phase = "launch"
if st.session_state.phase == "launch":
    st.title("FoodVantage 🥗")
    st.caption("Smart food & nutrition insights")

    if st.button("Launch App"):
        st.session_state.phase = "login"
        st.rerun()

    st.stop()
import sys
import os
import pandas as pd
import hashlib
import calendar as cal_module
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from gemini_api import *
from streamlit_back_camera_input import back_camera_input
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
if 'trends_view' not in st.session_state: st.session_state.trends_view = 'weekly'

# --- COLOR PALETTE ---
COLORS = {
    'olive': '#6B7E54',
    'terracotta': '#D4765E',
    'salmon': '#E89580',
    'beige': '#F5E6D3',
    'dark_text': '#2C2C2C',
    'green': '#6B7E54',
    'yellow': '#E8B54D',
    'red': '#D4765E',
    # MVP COLORS
    'camera_icon': '#c6d9ec',  # FIX 1: Light blue
    'toggle_button': '#737373',  # FIX 2: Lighter grey
    'unhealthy_bar': '#ffb3b3'  # FINAL: Light pink for unhealthy bars
}

# --- CSS ---
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">', unsafe_allow_html=True)
st.markdown(f"""
    <style>
    .stApp {{ background-color: #F7F5F0; color: #1A1A1A; }}
    .logo-text {{ font-family: 'Arial Black', sans-serif; font-size: 3rem; text-align: center; }}
    .logo-dot {{ color: {COLORS['terracotta']}; }}
    .card {{ background: white; padding: 24px; border-radius: 20px; border: 1px solid #EEE; box-shadow: 0 4px 12px rgba(0,0,0,0.04); margin-bottom: 20px; }}
    .white-shelf {{ background: white; height: 35px; border-radius: 10px; border: 1px solid #EEE; margin-bottom: 25px; }}
    .tomato-wrapper {{ width: 100%; text-align: center; padding: 30px 0; }}
    
    /* FIX 1: CAMERA ICON - LIGHT BLUE COLOR (ONLY COLOR CHANGED) */
    .tomato-icon {{ font-size: 150px !important; color: {COLORS['camera_icon']} !important; }}

    /* MOBILE FIX */
    input[type="text"], input[type="password"] {{
        background-color: white !important;
        color: #1A1A1A !important;
        border: 1px solid #DDD !important;
        border-radius: 8px !important;
        padding: 12px !important;
    }}
    
    .stTextInput > div > div > input {{
        background-color: white !important;
        color: #1A1A1A !important;
        -webkit-text-fill-color: #1A1A1A !important;
    }}
    
    /* FINAL FIX: LOGIN TABS BLACK TEXT ON DESKTOP AND MOBILE */
    .stTabs [data-baseweb="tab-list"] button {{
        color: #000000 !important;
    }}
    
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {{
        color: #000000 !important;
    }}
    
    .stTabs [data-baseweb="tab-list"] button div {{
        color: #000000 !important;
    }}
    
    .stTabs [data-baseweb="tab-list"] button p {{
        color: #000000 !important;
    }}
    
    /* FIX 3: ALL BUTTONS TERRACOTTA (INCLUDING STOP SCANNING) */
    .stButton > button {{
        background-color: {COLORS['terracotta']} !important;
        color: white !important;
        border: none !important;
    }}

    /* CRITICAL FIX: DARK TEXT FOR CLINICAL DATA */
    [data-testid="stMetricValue"] {{
        color: #1A1A1A !important;
        font-weight: 700 !important;
        font-size: 1.5rem !important;
    }}
    
    [data-testid="stMetricLabel"] {{
        color: #2C2C2C !important;
        font-weight: 600 !important;
    }}
    
    .stExpander {{
        background: white !important;
        color: #1A1A1A !important;
    }}
    
    .stExpander p, .stExpander div, .stExpander span {{
        color: #1A1A1A !important;
    }}

    /* WELCOME SCREEN */
    .welcome-container {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        min-height: 70vh;
    }}
    
    .welcome-text {{
        font-size: 2.5rem;
        font-weight: 800;
        color: #1A1A1A;
        text-align: center;
        margin-bottom: 30px;
    }}
    
    .dots {{
        display: flex;
        gap: 12px;
        justify-content: center;
    }}
    
    .dot {{
        width: 16px;
        height: 16px;
        background: {COLORS['terracotta']};
        border-radius: 50%;
        animation: dotPulse 1.5s ease-in-out infinite;
    }}
    
    .dot:nth-child(1) {{ animation-delay: 0s; }}
    .dot:nth-child(2) {{ animation-delay: 0.3s; }}
    .dot:nth-child(3) {{ animation-delay: 0.6s; }}
    
    @keyframes dotPulse {{
        0%, 60%, 100% {{ 
            opacity: 0.3;
            transform: scale(0.8);
        }}
        30% {{ 
            opacity: 1;
            transform: scale(1.3);
        }}
    }}

    /* CAMERA CENTERING */
    [data-testid="stCameraInput"] {{
        display: flex !important;
        justify-content: center !important;
    }}
    
    .hud-container {{
        position: relative;
        width: 100%;
        max-width: 640px;
        margin: 0 auto;
    }}

    /* TAP INSTRUCTION */
    .tap-instruction {{
        position: absolute;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(212, 118, 94, 0.95);
        color: white;
        padding: 12px 24px;
        border-radius: 25px;
        font-weight: 600;
        z-index: 1000;
        animation: pulse 2s ease-in-out infinite;
    }}
    
    @keyframes pulse {{
        0%, 100% {{ opacity: 0.8; transform: translateX(-50%) scale(1); }}
        50% {{ opacity: 1.0; transform: translateX(-50%) scale(1.05); }}
    }}
    
    .hud-bubble {{
        position: fixed;
        top: calc(50% - 200px);
        left: 50%;
        transform: translateX(-50%);
        background: white; 
        padding: 16px 28px; 
        border-radius: 50px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.15); 
        border: 3px solid {COLORS['terracotta']};
        z-index: 1000;
        text-align: center;
        min-width: 220px;
    }}
    
    .scanning-indicator {{
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(212, 118, 94, 0.95);
        color: white;
        padding: 10px 24px;
        border-radius: 25px;
        z-index: 1000;
        font-weight: bold;
        animation: blink 1.5s infinite;
    }}
    
    @keyframes blink {{
        0%, 100% {{ opacity: 0.7; }}
        50% {{ opacity: 1.0; }}
    }}
    
    /* DARK SCANNER RESULT TEXT */
    .scanner-result {{
        background: white;
        padding: 16px;
        border-radius: 12px;
        margin: 12px 0;
        border-left: 4px solid {COLORS['olive']};
    }}
    
    .scanner-result-title {{
        color: {COLORS['dark_text']};
        font-weight: 800;
        font-size: 1.1rem;
        margin-bottom: 8px;
    }}
    
    .scanner-result-text {{
        color: {COLORS['dark_text']};
        font-weight: 700;
        font-size: 1.3rem;
        line-height: 1.6;
    }}
    
    .list-row {{ 
        display: flex; 
        justify-content: space-between; 
        align-items: center;
        padding: 12px; 
        background: #FFF; 
        border-radius: 12px; 
        border: 1px solid #F0F0F0; 
        margin-bottom: 8px; 
    }}
    
    /* FIX 2: DAY/WEEK/MONTH TOGGLE BUTTONS - LIGHTER GREY WITH WHITE TEXT */
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
    
    /* FIX 5: HIDE KEYBOARD TEXT FROM SIDEBAR ARROW */
    [data-testid="collapsedControl"] {{
        color: transparent !important;
        font-size: 0 !important;
    }}
    
    [data-testid="collapsedControl"]::before {{
        content: "»";
        font-size: 1.5rem;
        color: white;
    }}
    </style>
""", unsafe_allow_html=True)

def render_logo(size="3rem"):
    st.markdown(f"<div style='text-align: center; margin-bottom: 10px;'><div class='logo-text' style='font-size: {size};'>foodvantage<span class='logo-dot'>.</span></div></div>", unsafe_allow_html=True)

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
            u = st.text_input("User ID", key="l_u", placeholder="Enter username")
            p = st.text_input("Password", type="password", key="l_p", placeholder="Enter password")
            if st.button("Sign In", type="primary", use_container_width=True):
                if u and p:
                    if authenticate_user(u, p): 
                        st.session_state.user_id = u
                        st.session_state.logged_in = True
                        st.session_state.welcome_shown = False
                        st.session_state.welcome_start_time = time.time()
                        st.rerun()
                    else: 
                        st.error("❌ Access Denied. Check username and password.")
                else:
                    st.warning("⚠️ Please enter both username and password.")
        with t2:
            u2 = st.text_input("Choose ID", key="s_u", placeholder="Username")
            p2 = st.text_input("Choose PWD", type="password", key="s_p", placeholder="Password (min 4 chars)")
            if st.button("Create Account", use_container_width=True):
                if u2 and p2:
                    if len(p2) < 4:
                        st.error("❌ Password must be at least 4 characters.")
                    else:
                        success = create_user(u2, p2)
                        if success:
                            st.success("✅ Account Created! Please sign in above.")
                        else:
                            st.error("❌ Username already exists. Try a different one.")
                else:
                    st.warning("⚠️ Please enter both username and password.")
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
            # FIX 4: Filter out vague 10.0 default scores
            filtered_results = [r for r in results if r['vms_score'] != 10.0] if results else []
            
            if filtered_results:
                st.markdown("**Top Results:**")
                for i, d in enumerate(filtered_results):
                    c = COLORS['green'] if d['vms_score'] < 3.0 else COLORS['yellow'] if d['vms_score'] < 7.0 else COLORS['red']
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
            # FIX 1: CAMERA ICON WITH LIGHT BLUE COLOR
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
            
            if st.session_state.selected_result:
                ls = st.session_state.selected_result
                clr = COLORS['green'] if ls['vms_score'] < 3.0 else COLORS['yellow'] if ls['vms_score'] < 7.0 else COLORS['red']
                st.markdown(f"""
                    <div class="hud-bubble">
                        <div style="font-size: 0.9rem; margin-bottom: 4px;">{ls['name']}</div>
                        <div style="color:{clr}; font-size:2.2rem; font-weight:900;">{ls['vms_score']}</div>
                        <div style="font-size: 0.8rem; color: {clr};">{ls['rating']}</div>
                    </div>
                """, unsafe_allow_html=True)

            # TAP INSTRUCTION
            st.markdown('<div class="hud-container">', unsafe_allow_html=True)
            st.markdown("""
                <div class="tap-instruction">
                    👆 Tap anywhere on camera to scan
                </div>
            """, unsafe_allow_html=True)
            image = back_camera_input(key="hud_cam")
            st.markdown('</div>', unsafe_allow_html=True)
            
            # FIX 3: STOP BUTTON ALREADY TERRACOTTA (DEFAULT BUTTON COLOR)
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
                    results = vision_live_scan_dark(image)
                    if results:
                        st.session_state.scan_results = results
                        st.session_state.selected_result = results[0]
                        st.session_state.scanning = False
                        st.rerun()

        # SHOW TOP 5 RESULTS
        if st.session_state.scan_results:
            st.markdown("### 📋 Select Your Option")
            st.markdown(f"Found **{len(st.session_state.scan_results)}** matches. Select one:")
            
            for i, result in enumerate(st.session_state.scan_results):
                clr = COLORS['green'] if result['vms_score'] < 3.0 else COLORS['yellow'] if result['vms_score'] < 7.0 else COLORS['red']
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

        # DEEP DIVE WITH DARK TEXT
        if st.session_state.selected_result:
            with st.expander("📊 Metabolic Nutrient Deep Dive", expanded=True):
                ls_raw = st.session_state.selected_result['raw']
                st.markdown("#### Clinical Data")
                
                # First row: Calories, Sugar, Fiber
                c1, c2, c3 = st.columns(3)
                c1.metric("Calories", f"{ls_raw[2]}")
                c2.metric("Sugar", f"{ls_raw[3]}g")
                c3.metric("Fiber", f"{ls_raw[4]}g")
                
                # Second row: Protein, Fat, Sodium
                c4, c5, c6 = st.columns(3)
                c4.metric("Protein", f"{ls_raw[5]}g")
                c5.metric("Fat", f"{ls_raw[6]}g")
                c6.metric("Sodium", f"{ls_raw[7]}mg")
                
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

        # TRENDS WITH FIX 2 APPLIED
        st.markdown("### 📈 Your Health Trends")
        
        # FIX 2: Lighter grey toggle buttons with white text
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
        
        # Get data based on view
        if st.session_state.trends_view == 'daily':
            days = 1
        elif st.session_state.trends_view == 'weekly':
            days = 7
        else:
            days = 30
        
        # Get trend data
        all_data = get_all_calendar_data_db(st.session_state.user_id)
        raw = get_trend_data_db(st.session_state.user_id, days=days)
        
        if raw and len(raw) > 0:
            # Create bar chart with Plotly
            df = pd.DataFrame(raw, columns=["date", "category", "count"])
            df['date'] = pd.to_datetime(df['date'])
            
            # Prepare data for bar chart
            df_pivot = df.pivot_table(index='date', columns='category', values='count', aggfunc='sum', fill_value=0)
            
            # Create stacked bar chart
            fig = go.Figure()
            
            # Add bars for each category with color palette
            if 'healthy' in df_pivot.columns:
                fig.add_trace(go.Bar(
                    x=df_pivot.index,
                    y=df_pivot['healthy'],
                    name='Healthy',
                    marker_color=COLORS['olive'],
                    hovertemplate='%{y} healthy items<extra></extra>'
                ))
            
            if 'moderate' in df_pivot.columns:
                fig.add_trace(go.Bar(
                    x=df_pivot.index,
                    y=df_pivot['moderate'],
                    name='Moderate',
                    marker_color=COLORS['salmon'],
                    hovertemplate='%{y} moderate items<extra></extra>'
                ))
            
            if 'unhealthy' in df_pivot.columns:
                fig.add_trace(go.Bar(
                    x=df_pivot.index,
                    y=df_pivot['unhealthy'],
                    name='Unhealthy',
                    marker_color=COLORS['unhealthy_bar'],  # FINAL: Light pink
                    hovertemplate='%{y} unhealthy items<extra></extra>'
                ))
            
            # Update layout
            fig.update_layout(
                barmode='stack',
                height=300,
                margin=dict(l=20, r=20, t=20, b=40),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(
                    showgrid=False,
                    showline=False,
                    title=None
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='#E0E0E0',
                    showline=False,
                    title=None
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5
                ),
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Summary stats
            total_items = int(df['count'].sum())
            healthy_count = int(df[df['category'] == 'healthy']['count'].sum()) if 'healthy' in df['category'].values else 0
            st.markdown(f"**Total items:** {total_items} | **Healthy choices:** {healthy_count}")
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
            
            # ADD ITEM FEATURE
            st.markdown("#### ➕ Add Item to This Day")
            search_item = st.text_input("Search for an item", key="calendar_search", placeholder="e.g., banana, coca cola, avocado...")
            
            if search_item:
                search_results = search_vantage_db(search_item, limit=5)
                # FIX 4: Filter out vague 10.0 default scores
                filtered_results = [r for r in search_results if r['vms_score'] != 10.0] if search_results else []
                
                if filtered_results:
                    for idx, result in enumerate(filtered_results):
                        clr = COLORS['green'] if result['vms_score'] < 3.0 else COLORS['yellow'] if result['vms_score'] < 7.0 else COLORS['red']
                        
                        col_a, col_b, col_c = st.columns([3, 1, 0.6])
                        with col_a:
                            st.markdown(f"**{result['name']}**")
                        with col_b:
                            st.markdown(f"<div style='text-align:center; color:{clr}; font-weight:bold; font-size:1.2rem;'>{result['vms_score']}</div>", unsafe_allow_html=True)
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
                else:
                    st.info("No items found. Try a different search term.")
            
            st.markdown("---")
            st.markdown("#### 📝 Items for This Day")
            
            # SHOW ITEMS FOR SELECTED DATE
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
