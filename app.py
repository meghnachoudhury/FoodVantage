import streamlit as st
from streamlit_back_camera_input import back_camera_input
import time
from src.gemini_api import analyze_label_with_gemini

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="FoodVantage",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. SESSION STATE (The Login Gatekeeper) ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'page' not in st.session_state:
    st.session_state.page = 'login' 

# --- 3. CUSTOM CSS (Tekni-Style Branding) ---
st.markdown("""
    <style>
    /* GLOBAL THEME: Cream/Beige Background */
    .stApp {
        background-color: #FDFBF7;
        color: #1A1A1A;
    }
    
    /* LOGO DESIGN: Matches "Tekni" (Bold, Geometric, Tight) */
    .logo-container {
        display: flex;
        justify-content: center;
        align-items: center;
        flex-direction: column;
        margin-bottom: 20px;
    }
    .logo-text {
        font-family: 'Arial Black', 'Impact', sans-serif;
        font-weight: 900;
        font-size: 3.5rem; /* Massive size */
        letter-spacing: -3px; /* Tight kerning like Tekni */
        color: #1A1A1A;
        text-transform: lowercase; 
        margin-bottom: -10px;
        line-height: 1.0;
    }
    .logo-dot {
        color: #E2725B; /* The Terracotta dot */
        display: inline-block;
    }
    .logo-sub {
        font-family: 'Helvetica Neue', sans-serif;
        font-size: 0.9rem;
        color: #666;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-top: 10px;
    }

    /* BUTTONS: Terracotta Pill Shape */
    .stButton>button {
        background-color: #E2725B;
        color: white;
        border: none;
        border-radius: 50px; /* Pill shape */
        height: 55px;
        font-weight: 700;
        font-size: 1.1rem;
        width: 100%;
        box-shadow: 0 4px 10px rgba(226, 114, 91, 0.3);
        transition: all 0.2s;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 15px rgba(226, 114, 91, 0.4);
        background-color: #D6604D;
        color: white;
    }

    /* INPUT FIELDS: Clean & Modern */
    .stTextInput>div>div>input {
        background-color: white;
        border-radius: 15px;
        border: 2px solid #EEE;
        padding: 15px;
        font-size: 1rem;
    }
    .stTextInput>div>div>input:focus {
        border-color: #E2725B;
        color: #1A1A1A;
    }

    /* CARDS (Grocery Log) */
    .grocery-card {
        background: white;
        padding: 18px;
        border-radius: 16px;
        margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        border: 1px solid #F0F0F0;
        transition: transform 0.2s;
    }
    .grocery-card:hover {
        transform: scale(1.01);
    }
    
    /* REMOVE DEFAULT STREAMLIT MENU */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 4. BRANDING FUNCTION ---
def render_header(is_login=False):
    """Renders the Big Bold Logo"""
    # Adjust size slightly for main app vs login
    size = "5rem" if is_login else "3rem"
    margin = "40px" if is_login else "10px"
    
    st.markdown(f"""
        <div class="logo-container" style="margin-bottom: {margin};">
            <div class="logo-text" style="font-size: {size};">
                foodvantage<span class="logo-dot">.</span>
            </div>
            <div class="logo-sub">Metabolic Intelligence</div>
        </div>
    """, unsafe_allow_html=True)

# --- 5. LOGIN FLOW (First Page) ---
if not st.session_state.logged_in:
    
    # Centered Column for Login
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("") 
        st.write("") 
        
        # 1. RENDER LOGO
        render_header(is_login=True)
        
        # 2. LOGIN FORM
        if st.session_state.page == 'login':
            st.markdown("<h3 style='text-align: center; color: #444; margin-bottom: 20px;'>Welcome Back</h3>", unsafe_allow_html=True)
            
            email = st.text_input("Email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            
            st.write("") # Spacer
            if st.button("Sign In"):
                st.session_state.logged_in = True
                st.rerun()
            
            st.markdown("---")
            if st.button("Create Account"):
                st.session_state.page = 'signup'
                st.rerun()

        # 3. SIGNUP FORM
        elif st.session_state.page == 'signup':
            st.markdown("<h3 style='text-align: center; color: #444;'>New Account</h3>", unsafe_allow_html=True)
            st.text_input("Full Name")
            st.text_input("Email")
            st.text_input("Password", type="password")
            
            st.write("")
            if st.button("Create Profile"):
                st.session_state.logged_in = True
                st.rerun()
            
            if st.button("← Back to Login"):
                st.session_state.page = 'login'
                st.rerun()

# --- 6. MAIN APP (After Login) ---
else:
    # 1. RENDER LOGO (Centered at top)
    render_header(is_login=False)
    
    # 2. NAVIGATION TABS
    tab1, tab2, tab3 = st.tabs(["📸 Vision Scanner", "🗓️ Grocery Log", "🔍 Search"])

    # --- TAB 1: SCANNER ---
    with tab1:
        st.info("Point camera at a label. Gemini 3 will detect metabolic blockers.")
        image = back_camera_input()
        
        if image:
            c1, c2 = st.columns([1,1])
            with c1:
                st.image(image, use_container_width=True)
            with c2:
                with st.status("🧠 Gemini 3 Processing...", expanded=True):
                    st.write("Extracting Text...")
                    time.sleep(1)
                    try:
                        analysis = analyze_label_with_gemini(image)
                        st.markdown(analysis)
                    except Exception as e:
                        st.error("Could not analyze image.")

    # --- TAB 2: GROCERY LOG (Mock Data for Testing) ---
    with tab2:
        st.markdown("### 🛒 My History")
        
        # MOCK DATA (Proof Check #1)
        history_data = [
            {"date": "Today", "item": "Avocados (Hass)", "score": 95, "status": "Excellent", "color": "#2E8B57"},
            {"date": "Today", "item": "Oat Milk (Barista)", "score": 42, "status": "Spike Risk", "color": "#E2725B"},
            {"date": "Feb 03", "item": "Sourdough Bread", "score": 68, "status": "Moderate", "color": "#F9A825"},
            {"date": "Feb 01", "item": "Wild Salmon", "score": 98, "status": "Excellent", "color": "#2E8B57"},
        ]
        
        for item in history_data:
            st.markdown(f"""
            <div class="grocery-card" style="border-left: 5px solid {item['color']};">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-weight: 800; font-size: 1.1rem; color: #333;">{item['item']}</div>
                        <div style="color: #888; font-size: 0.85rem;">{item['date']}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-weight: 900; font-size: 1.4rem; color: {item['color']};">
                            {item['score']}
                        </div>
                        <div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1px; color: #888;">
                            {item['status']}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # --- TAB 3: SEARCH ---
    with tab3:
        st.markdown("### 🔍 Pre-Shop Check")
        st.text_input("Check a product before buying...", placeholder="e.g. Chobani Zero Sugar")
        st.button("Analyze")