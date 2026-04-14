import streamlit as st
import pandas as pd
import math
from datetime import datetime, timedelta
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas

# --- 1. SECURE CONNECTION ---
SUPABASE_URL = "https://wwofdtdjpprvtzjmqgbk.supabase.co"
SUPABASE_KEY = "sb_publishable_HFSxcJjKT8c0M1_UoFLznA_J6HzGbdm"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. UTILS ---
def ncs_round(check_in, check_out):
    """NCS Rule: Round part hours per day UP to the next whole hour."""
    fmt = "%H:%M:%S"
    start = datetime.strptime(check_in, fmt)
    end = datetime.strptime(check_out, fmt)
    actual_hours = (end - start).total_seconds() / 3600
    return math.ceil(actual_hours)

# --- 3. NAVIGATION & SITE SELECTOR ---
# Note: Since login is removed, we default 'user' to a generic 'Staff' or 'Admin'
if 'user' not in st.session_state:
    st.session_state['user'] = "Staff_User"

sites = ["Elphin", "Ballinameen", "Boyle", "Roscommon", "Keadue"]
page = st.sidebar.radio("Navigation", ["Dashboard", "Attendance", "NCS Compliance", "Admin Settings"])
sel_site = st.sidebar.selectbox("Current Site Location", sites)

# --- 4. DASHBOARD & TUSLA RATIOS ---
if page == "Dashboard":
    st.title(f"🏫 {sel_site} Management Hub")
    today = str(datetime.now().date())
    
    # Live Stats & Ratios
    kids_in = supabase.table("attendance").select("id", count="exact").eq("date", today).is_("check_out", "NULL").execute().count
    staff_in = supabase.table("staff_roster").select("id", count="exact").eq("site", sel_site).eq("date", today).is_("shift_end", "NULL").execute().count
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Children Present", kids_in)
    c2.metric("Staff on Duty", staff_in)
    
    req_staff = math.ceil(kids_in / 12) if kids_in > 0 else 0
    status = "✅ Compliant" if staff_in >= req_staff else "🚨 UNDERSTAFFED"
    c3.metric("Tusla 1:12 Status", status)

    if st.sidebar.button("⏰ Clock In for Shift"):
        supabase.table("staff_roster").insert({
            "username": st.session_state['user'], 
            "site": sel_site, 
            "date": today, 
            "shift_start": datetime.now().strftime("%H:%M:%S")
        }).execute()
        st.sidebar.success("Shift started!")

# --- 5. ATTENDANCE & SIGNATURES ---
  st.title("📍 Daily Log")
    tab1, tab2 = st.tabs(["🚌 Bulk Bus Arrival", "👤 Check-Out & Sign"])
    with tab1:
        kids = supabase.table("children").select("name").eq("location", sel_site).execute()
        names = [k['name'] for k in kids.data]
        sel_kids = st.multiselect("Select Children for Bulk In", names)
        if st.button("Process Bulk In"):
            for n in sel_kids:
                supabase.table("attendance").insert({
                    "name": n, 
                    "date": str(datetime.now().date()), 
                    "session": "Afterschool", 
                    "check_in": datetime.now().strftime("%H:%M:%S")
                }).execute()
            st.rerun()

    with tab2:
        active = supabase.table("attendance") \
            .select("*, children!inner(location, allergies)") \
            .is_("check_out", "null") \
            .execute()
        site_logs = [a for a in active.data if a['children']['location'] == sel_site]
        
        for log in site_logs:
             site_logs = [a for a in active.data if a['children']['location'] == sel_site]
        
        for log in site_logs:
            with st.expander(f"Sign-Out: {log['name']}"):
                # Accessing joined data: log['children']['allergies']
                st.warning(f"Allergy Alert: {log['children'].get('allergies', 'None')}")
                note = st.text_input("Notes", key=f"note_{log['id']}")
                canvas_res = st_canvas(height=100, width=300, key=f"sig_{log['id']}", drawing_mode="freedraw")
                
                if st.button("Finalize Pick-Up", key=f"out_{log['id']}", type="primary"):
                    now_time = datetime.now().strftime("%H:%M:%S")
                    rounded_h = ncs_round(log['check_in'], now_time)
                    supabase.table("attendance").update({
                        "check_out": now_time, 
                        "hours": rounded_h, 
                        "notes": note, 
                        "signature_captured": True
                    }).eq("id", log['id']).execute()
                    st.rerun()

# --- 6. NCS 8-WEEK TRACKER ---
elif page == "NCS Compliance":
    st.title("⚖️ 8-Week Under-Attendance Tracker")
    st.info("Monitors consecutive weeks below registered hours.")

# --- 7. ADMIN & EXEMPTIONS ---
elif page == "Admin Settings":
    st.title("⚙️ System Management")
    with st.form("enroll"):
        st.subheader("Enroll New Child")
        n = st.text_input("Full Name")
        c = st.text_input("NCS CHICK Number")
        h = st.number_input("Registered Weekly Hours", value=20)
        if st.form_submit_button("Save Record"):
            supabase.table("children").insert({
                "name": n, 
                "location": sel_site, 
                "ncs_number": c, 
                "registered_hours": h
            }).execute()
            st.success("Enrolled Successfully")
