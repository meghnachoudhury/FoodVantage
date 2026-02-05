import streamlit as st
from PIL import Image
from src.gemini_api import search_vantage_db, client
from streamlit_back_camera_input import back_camera_input
import os

# 1. PAGE CONFIG (Renamed for FoodVantage)
st.set_page_config(page_title="FoodVantage", page_icon="🧬", layout="centered")

# Custom Styling for a Sleek Metabolic Dashboard
st.markdown("""
    <style>
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border-left: 5px solid #4e5d6e; }
    .stAlert { border-radius: 10px; }
    /* Mobile optimization for text */
    @media (max-width: 600px) {
        .stMetric { padding: 10px; }
    }
    </style>
    """, unsafe_allow_html=True)

# 2. BRANDING & SIDEBAR
st.title("🧬 FoodVantage")
st.write("### Metabolic Vision Scanner")

with st.sidebar:
    st.header("The FoodVantage Mission")
    st.write("""
    FoodVantage uses Multimodal AI to look past marketing labels. 
    By calculating the **Food Matrix** and **Glycemic Velocity**, 
    we predict how your insulin will respond before you take a bite.
    """)
    st.divider()
    st.caption("Standard: Rayner 2024 Metabolic Calibration")

# 3. CAMERA INPUT (Optimized for Mobile Back Camera)
st.write("Point your camera at a food item or nutrition label:")
img_file_buffer = back_camera_input()

if img_file_buffer:
    img = Image.open(img_file_buffer)
    
    with st.status("🔮 Analyzing Biology...", expanded=True) as status:
        # Vision Identification (Gemini 2.0 Flash)
        prompt = "Identify this food product. Output ONLY brand and name."
        response = client.models.generate_content(model="gemini-2.0-flash", contents=[prompt, img])
        product_name = response.text.strip()
        
        # Metabolic Scoring (Your Stable Logic)
        results = search_vantage_db(product_name)
        status.update(label="Scanning Complete", state="complete", expanded=False)

    if results:
        res = results[0]
        score = res['vms_score']
        rating = res['rating']
        name_lower = res['name'].lower()
        
        st.divider()
        
        # 4. HEADER METRICS
        col1, col2 = st.columns([1, 2])
        with col1:
            if "Green" in rating:
                st.metric("VMS SCORE", score, "OPTIMAL")
            elif "Yellow" in rating:
                st.metric("VMS SCORE", score, "CAUTION", delta_color="off")
            else:
                st.metric("VMS SCORE", score, "STRESSOR", delta_color="inverse")
        
        with col2:
            st.write(f"#### {res['name']}")
            st.write(f"**Metabolic Zone:** {rating}")

        # 5. THE VISUAL BREAKDOWN
        st.write("---")
        st.subheader("📊 Metabolic Breakdown")
        
        # Stressor bar (Sugar/Cals/Processing)
        # Normalize score to 0-1.0 scale
        stress_level = min(max((score + 5) / 25, 0.1), 1.0) 
        st.write(f"**Metabolic Load (Insulin Requirement)**")
        st.progress(stress_level, text=f"Intensity: {int(stress_level * 100)}%")
        
        # Buffer bar (Fiber/Protein/Whole Matrix)
        buffer_level = 0.9 if score < 0 else 0.4
        st.write(f"**Metabolic Buffer (Fiber/Protein Protection)**")
        st.progress(buffer_level, text=f"Stability: {int(buffer_level * 100)}%")

        # 6. DYNAMIC WARNINGS (Accuracy Bridge)
        st.write("---")
        st.subheader("💡 Metabolic Insights")
        
        # Case A: The Liquid Starch (Oat Milk)
        if "oat" in name_lower and "milk" in name_lower:
            st.warning("🍯 **Maltose Alert:** Oat milk is a liquid starch. While the math is stable, it enters the blood faster than whole oats.")
            
        # Case B: The Superfood (Apple / Avocado / Salmon)
        elif score < 3.0 and any(x in name_lower for x in ['apple', 'salmon', 'avocado', 'lentil', 'egg']):
            st.success("🥗 **High Stability:** The food matrix here slows glucose absorption significantly. Optimal for insulin sensitivity.")
            
        # Case C: General Spikers
        elif score > 7.0:
            st.error("⚠️ **High Velocity:** High concentration of free sugars detected. This will trigger a rapid insulin response.")
        
        # Case D: Processed Items
        elif "bar" in name_lower or "jerky" in name_lower:
            st.info("🏭 **Processing Note:** This item has metabolic stressors balanced by protein. Fine in moderation, but watch for sodium.")

    else:
        st.error("Product detected but not found in metabolic index. Try scanning the nutrition label.")

st.divider()
st.caption("FoodVantage 2.0 • Pro-Metabolic Design")