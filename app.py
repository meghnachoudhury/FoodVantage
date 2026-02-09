import streamlit as st
import sys
import os
from datetime import datetime
from streamlit_back_camera_input import back_camera_input

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from gemini_api import *

st.set_page_config(page_title="FoodVantage", page_icon="🥗", layout="wide")

# SESSION STATE
if 'logged_in' not in st.session_state: st.session_state.logged_in = True
if 'user_id' not in st.session_state: st.session_state.user_id = "demo_user"
if 'page' not in st.session_state: st.session_state.page = 'dashboard'
if 'camera_active' not in st.session_state: st.session_state.camera_active = False
if 'scanning' not in st.session_state: st.session_state.scanning = False

# COLORS
COLORS = {
    'olive': '#6B7E54',
    'terracotta': '#D4765E',
    'beige': '#F5E6D3',
}

# CSS
st.markdown(f"""
<style>
.stApp {{ background-color: #F5E6D3; }}
.card {{
    background: white;
    padding: 20px;
    border-radius: 15px;
    margin: 10px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}}
.score-card {{
    background: white;
    padding: 15px;
    border-radius: 12px;
    border-left: 4px solid {COLORS['olive']};
    margin: 10px 0;
}}
.score-card.red {{ border-left-color: {COLORS['terracotta']}; }}
.score-card.yellow {{ border-left-color: #E8B54D; }}
.big-button {{
    background: {COLORS['terracotta']};
    color: white;
    padding: 15px 30px;
    border-radius: 10px;
    border: none;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
    width: 100%;
    margin: 10px 0;
}}
</style>
""", unsafe_allow_html=True)

# HEADER
st.markdown("<h1 style='text-align: center;'>🥗 FoodVantage</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Scan food, get health scores instantly</p>", unsafe_allow_html=True)

# Helper function
def needs_portion_size(item_name):
    n = item_name.lower()
    
    # Cooked food - NO portion label
    cooked = ['cooked', 'grilled', 'fried', 'baked', 'roasted', 'steamed', 'boiled', 
              'plate', 'meal', 'dish', 'curry', 'stew', 'soup', 'salad']
    if any(word in n for word in cooked):
        return False
    
    # Fresh produce - NO portion label
    fresh = ['apple', 'banana', 'orange', 'carrot', 'tomato', 'lettuce', 'spinach', 'broccoli']
    if any(word in n for word in fresh):
        return False
    
    # Superfoods - NO portion label
    superfoods = ['salmon', 'lentils', 'beans', 'egg', 'avocado', 'kale']
    if any(word in n for word in superfoods):
        return False
    
    # Everything else (packaged) - YES portion label
    return True

# NAVIGATION
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("📸 Scanner", use_container_width=True):
        st.session_state.page = 'dashboard'
with col2:
    if st.button("📊 Trends", use_container_width=True):
        st.session_state.page = 'trends'
with col3:
    if st.button("📅 Calendar", use_container_width=True):
        st.session_state.page = 'calendar'

st.markdown("---")

# === SCANNER PAGE ===
if st.session_state.page == 'dashboard':
    st.markdown("<h2 style='text-align: center;'>Food Scanner</h2>", unsafe_allow_html=True)
    
    if not st.session_state.camera_active:
        if st.button("🎥 Start Camera", key="start_cam", use_container_width=True):
            st.session_state.camera_active = True
            st.rerun()
    else:
        st.info("📸 Point camera at food item and tap to scan")
        
        image = back_camera_input(key="scanner_cam")
        
        if st.button("⏹️ Stop Camera", key="stop_cam", use_container_width=True):
            st.session_state.camera_active = False
            st.rerun()
        
        if image and not st.session_state.scanning:
            st.session_state.scanning = True
            
            with st.spinner("🔍 Analyzing..."):
                results = vision_live_scan_dark(image)
            
            st.session_state.scanning = False
            
            if results:
                st.success(f"✅ Found {len(results)} item(s)!")
                
                for result in results[:5]:
                    score = result['vms_score']
                    name = result['name']
                    
                    # Score color
                    if score < 3.0:
                        card_class = "score-card"
                        color = COLORS['olive']
                    elif score < 7.0:
                        card_class = "score-card yellow"
                        color = "#E8B54D"
                    else:
                        card_class = "score-card red"
                        color = COLORS['terracotta']
                    
                    # Portion size label
                    portion_label = " /serving" if needs_portion_size(name) else ""
                    
                    st.markdown(f"""
                    <div class="{card_class}">
                        <h3 style='margin: 0; color: {color};'>{name}</h3>
                        <p style='font-size: 24px; font-weight: bold; margin: 10px 0; color: {color};'>
                            Score: {score:.1f}{portion_label}
                        </p>
                        <p style='margin: 0; color: #666;'>{result['rating']}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Log button
                    if st.button(f"📝 Log {name}", key=f"log_{name}_{score}"):
                        today = datetime.now().strftime('%Y-%m-%d')
                        add_calendar_item_db(st.session_state.user_id, today, name, score)
                        st.success(f"✅ Logged {name}!")
            else:
                st.warning("🔍 Item not found. Try repositioning or better lighting.")

    # SIDEBAR SEARCH
    with st.sidebar:
        st.markdown("### 🔍 Search Database")
        search_query = st.text_input("Enter food name:", key="search_input")
        
        if search_query:
            with st.spinner("Searching..."):
                results = search_vantage_db(search_query, limit=5)
            
            if results:
                st.success(f"Found {len(results)} results")
                for r in results:
                    score = r['vms_score']
                    portion = " /serving" if needs_portion_size(r['name']) else ""
                    
                    if score < 3.0:
                        emoji = "🟢"
                    elif score < 7.0:
                        emoji = "🟡"
                    else:
                        emoji = "🔴"
                    
                    st.markdown(f"{emoji} **{r['name']}**")
                    st.markdown(f"Score: **{score:.1f}{portion}**")
                    st.markdown("---")
            else:
                st.info("No results found")

# === TRENDS PAGE ===
elif st.session_state.page == 'trends':
    st.markdown("<h2 style='text-align: center;'>Health Trends</h2>", unsafe_allow_html=True)
    
    period = st.radio("View:", ["Week", "Month"], horizontal=True)
    days = 7 if period == "Week" else 30
    
    data = get_trend_data_db(st.session_state.user_id, days)
    
    if data:
        from collections import defaultdict
        daily = defaultdict(lambda: {'healthy': 0, 'moderate': 0, 'unhealthy': 0})
        
        for date, category, count in data:
            daily[str(date)][category] = count
        
        dates = sorted(daily.keys())
        healthy = [daily[d]['healthy'] for d in dates]
        moderate = [daily[d]['moderate'] for d in dates]
        unhealthy = [daily[d]['unhealthy'] for d in dates]
        
        import plotly.graph_objects as go
        
        fig = go.Figure()
        fig.add_trace(go.Bar(name='Healthy', x=dates, y=healthy, marker_color=COLORS['olive']))
        fig.add_trace(go.Bar(name='Moderate', x=dates, y=moderate, marker_color='#E8B54D'))
        fig.add_trace(go.Bar(name='Unhealthy', x=dates, y=unhealthy, marker_color=COLORS['terracotta']))
        
        fig.update_layout(
            barmode='stack',
            title=f"Items Logged - Past {period}",
            xaxis_title="Date",
            yaxis_title="Items",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet. Start scanning foods!")

# === CALENDAR PAGE ===
elif st.session_state.page == 'calendar':
    st.markdown("<h2 style='text-align: center;'>Food Calendar</h2>", unsafe_allow_html=True)
    
    selected_date = st.date_input("Select date:", datetime.now())
    date_str = selected_date.strftime('%Y-%m-%d')
    
    items = get_calendar_items_db(st.session_state.user_id, date_str)
    
    if items:
        st.success(f"📅 {len(items)} items logged on {selected_date.strftime('%b %d, %Y')}")
        
        for item_id, name, score, category in items:
            if score < 3.0:
                color = COLORS['olive']
            elif score < 7.0:
                color = "#E8B54D"
            else:
                color = COLORS['terracotta']
            
            portion = " /serving" if needs_portion_size(name) else ""
            
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{name}** - Score: {score:.1f}{portion}")
            with col2:
                if st.button("🗑️", key=f"del_{item_id}"):
                    delete_item_db(item_id)
                    st.rerun()
    else:
        st.info("No items logged for this date")

