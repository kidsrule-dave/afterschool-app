import streamlit as st
import pandas as pd
import math
import hashlib
from datetime import datetime, timedelta
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas

# --- CONNECT TO SUPABASE ---
# Replace these with your actual keys from Supabase Settings > API
URL = "https://wwofdtdjpprvtzjmqgbk.supabase.co"
KEY = "sb_publishable_HFSxcJjKT8c0M1_UoFLznA_J6HzGbdm"
supabase: Client = create_client(URL, KEY)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# --- APP START ---
st.set_page_config(page_title="Roscommon Afterschool", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title("Staff Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        res = supabase.table("staff").select("*").eq("username", u).eq("password", hash_pw(p)).execute()
        if res.data:
            st.session_state['logged_in'] = True
            st.session_state['user'] = u
            st.rerun()
        else: st.error("Access Denied")

else:
    sites = ["Elphin", "Ballinameen", "Boyle", "Roscommon", "Keadue"]
    page = st.sidebar.radio("Navigation", ["Dashboard", "Attendance", "Billing & Enrollment", "Audit Mode"])
    sel_site = st.sidebar.selectbox("Current Site", sites)

    # --- DASHBOARD & TUSLA RATIOS ---
    if page == "Dashboard":
        st.title(f"🏫 {sel_site} Dashboard")
        today = str(datetime.now().date())
        
        # Live Stats
        kids_in = supabase.table("attendance").select("id", count="exact").eq("date", today).is_("check_out", "NULL").execute()
        staff_in = supabase.table("staff_roster").select("id", count="exact").eq("site", sel_site).eq("date", today).is_("shift_end", "NULL").execute()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Children Present", kids_in.count)
        c2.metric("Staff on Duty", staff_in.count)
        
        req_staff = math.ceil(kids_in.count / 12) if kids_in.count > 0 else 0
        status = "✅ Compliant" if staff_in.count >= req_staff else "🚨 Understaffed (Ratio 1:12)"
        c3.metric("Tusla Status", status)

        if st.button("⏰ Clock In for Shift"):
            supabase.table("staff_roster").insert({"username": st.session_state['user'], "site": sel_site, "date": today, "shift_start": datetime.now().strftime("%H:%M:%S")}).execute()
            st.success("Clocked in!")

    # --- ATTENDANCE & NCS ROUNDING ---
    elif page == "Attendance":
        st.title("📍 Daily Attendance")
        
        # Bulk Check-In
        with st.expander("🚌 Bulk Bus Arrival"):
            kids = supabase.table("children").select("name").eq("location", sel_site).execute()
            names = [k['name'] for k in kids.data]
            sel_kids = st.multiselect("Select Children", names)
            if st.button("Check In Group"):
                for n in sel_kids:
                    supabase.table("attendance").insert({"name": n, "date": str(datetime.now().date()), "session": "Afterschool", "check_in": datetime.now().strftime("%H:%M:%S")}).execute()
                st.rerun()

        st.divider()
        # Individual Out with NCS Rounding
        active = supabase.table("attendance").select("*, children!inner(location, allergies)").is_("check_out", "NULL").execute()
        site_logs = [a for a in active.data if a['children']['location'] == sel_site]
        
        for log in site_logs:
            col_n, col_o = st.columns([3, 1])
            col_n.write(f"**{log['name']}** (In: {log['check_in']})")
            if col_o.button("OUT", key=log['id']):
                # NCS Rounding Rule (math.ceil)
                t1 = datetime.strptime(log['check_in'], "%H:%M:%S")
                t2 = datetime.now()
                actual = (t2 - t1).total_seconds() / 3600
                rounded = math.ceil(actual)
                
                supabase.table("attendance").update({"check_out": t2.strftime("%H:%M:%S"), "hours": rounded, "signature_captured": True}).eq("id", log['id']).execute()
                st.rerun()

    # --- BILLING, NCS & ENROLLMENT ---
    elif page == "Billing & Enrollment":
        st.title("📊 Enrollment & NCS")
        with st.form("enroll"):
            name = st.text_input("Full Name")
            chick = st.text_input("NCS Number (CHICK)")
            reg = st.number_input("Registered Weekly Hours", value=20)
            p_email = st.text_input("Parent Email")
            if st.form_submit_button("Enroll Child"):
                supabase.table("children").insert({"name": name, "location": sel_site, "ncs_number": chick, "registered_hours": reg, "parent_email": p_email}).execute()
                st.success("Child Added")

    # --- AUDIT MODE ---
    elif page == "Audit Mode":
        st.title("🛡️ Inspector Audit Mode")
        start = st.date_input("Start Date")
        end = st.date_input("End Date")
        if st.button("Generate Inspection Table"):
            res = supabase.table("attendance").select("*, children!inner(ncs_number)").gte("date", str(start)).lte("date", str(end)).execute()
            st.table(pd.DataFrame(res.data))
