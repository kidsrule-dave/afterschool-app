import streamlit as st
import pandas as pd
import math
from datetime import datetime
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas

# --- 1. SECURE CONNECTION ---
SUPABASE_URL = "https://supabase.co"
SUPABASE_KEY = "sb_publishable_HFSxcJjKT8c0M1_UoFLznA_J6HzGbdm"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. UTILS ---
def ncs_round(check_in, check_out):
    fmt = "%H:%M:%S"
    start = datetime.strptime(check_in, fmt)
    end = datetime.strptime(check_out, fmt)
    actual_hours = (end - start).total_seconds() / 3600
    return math.ceil(actual_hours)

# --- 3. NAVIGATION ---
sites = ["Elphin", "Ballinameen", "Boyle", "Roscommon", "Keadue"]
page = st.sidebar.radio("Navigation", ["Dashboard", "Quick-Tap Board", "Attendance", "NCS Compliance", "Admin Settings"])
sel_site = st.sidebar.selectbox("Current Site Location", sites)

# --- 4. DASHBOARD ---
if page == "Dashboard":
    st.title(f"🏫 {sel_site} Hub")
    today = str(datetime.now().date())
    
    try:
        # Check current headcount specifically filtered for this site location
        kids_res = supabase.table("attendance").select("id", count="exact").eq("date", today).is_("check_out", "null").execute()
        kids_in = kids_res.count if kids_res.count else 0
    except:
        kids_in = 0
        
    st.metric("Children Present Today", kids_in)

# --- 5. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Sign-Out")
    
    try:
        children_res = supabase.table("children").select("name").eq("location", sel_site).execute()
        site_child_names = [c['name'] for c in children_res.data]
        
        active_res = supabase.table("attendance").select("*").is_("check_out", "null").execute()
        site_logs = [a for a in active_res.data if a['name'] in site_child_names]
    except Exception as e:
        st.error(f"Database Error: {e}")
        site_logs = []

    if not site_logs:
        st.info(f"No children currently checked in at {sel_site}.")
    
    for log in site_logs:
        child_id = log['id']
        c_key = f"coll_{child_id}"
        current_selection = st.session_state.get(c_key)

        with st.container(border=True):
            st.subheader(f"👤 {log['name']}")
            st.caption(f"Checked In At: {log['check_in']}")
            
            collectors = ["Mom", "Dad", "Nan", "Grandad", "Aunty", "Uncle", "Brother", "Sister"]
            cols = st.columns(4)
            for i, p in enumerate(collectors):
                b_type = "primary" if current_selection == p else "secondary"
                if cols[i % 4].button(p, key=f"q_tap_{p}_{child_id}", type=b_type, use_container_width=True):
                    st.session_state[c_key] = p
                    st.rerun()
            
            if current_selection:
                if st.button(f"✅ Finalize Sign-Out ({current_selection})", key=f"fin_{child_id}", type="primary", use_container_width=True):
                    now = datetime.now().strftime("%H:%M:%S")
                    supabase.table("attendance").update({
                        "check_out": now, 
                        "collected_by": current_selection,
                        "hours": ncs_round(log['check_in'], now),
                        "notes": f"Quick-tap pickup by {current_selection}"
                    }).eq("id", child_id).execute()
                    if c_key in st.session_state: del st.session_state[c_key]
                    st.rerun()

# --- 6. ATTENDANCE & SIGN-OUT ---
elif page == "Attendance":
    st.title("📍 Daily Log")
    tab1, tab2 = st.tabs(["🚌 Arrivals (Sign In)", "👤 Departures (Sign Out)"])
    
    with tab1:
        st.subheader("Sign In Children")
        try:
            kids = supabase.table("children").select("name").eq("location", sel_site).execute()
            names = sorted([k['name'] for k in kids.data])
        except Exception as e:
            st.error(f"Could not load children: {e}")
            names = []

        if names:
            sel_kids = st.multiselect("Select children to Check-In:", names)
            if st.button("Confirm Check In", type="primary"):
                if sel_kids:
                    for n in sel_kids:
                        supabase.table("attendance").insert({
                            "name": n, 
                            "date": str(datetime.now().date()), 
                            "check_in": datetime.now().strftime("%H:%M:%S")
                        }).execute()
                    st.success(f"Successfully checked in {len(sel_kids)} children!")
                    st.rerun()
                else:
                    st.warning("Please select at least one child.")
        else:
            st.info("No children registered at this site yet. Go to Admin Settings to register them.")

    with tab2:
        st.subheader("Sign Out Children")
        try:
            active_res = supabase.table("attendance").select("*").is_("check_out", "null").execute()
            children_res = supabase.table("children").select("name", "location").eq("location", sel_site).execute()
            site_children = {c['name']: c for c in children_res.data}
            site_logs = [a for a in active_res.data if a['name'] in site_children]
        except Exception as e:
            site_logs = []

        if not site_logs:
            st.info("No active check-ins found for this location.")

        for log in site_logs:
            child_id = log['id']
            c_key = f"coll_{child_id}"
            
            with st.expander(f"Sign-Out Profile: {log['name']} (In: {log['check_in']})"):
                current_selection = st.session_state.get(c_key)
                
                st.write("**Who is collecting the child?**")
                collectors = ["Mom", "Dad", "Nan", "Grandad", "Aunty", "Uncle", "Brother", "Sister"]
                cols = st.columns(4)
                for i, p in enumerate(collectors):
                    b_type = "primary" if current_selection == p else "secondary"
                    if cols[i % 4].button(p, key=f"btn_{p}_{child_id}", type=b_type, use_container_width=True):
                        st.session_state[c_key] = p
                        st.rerun()
                
                if current_selection:
                    st.success(f"Selected Collector: {current_selection}")
                
                note = st.text_input("Additional Notes (e.g. Medication, Mood)", key=f"note_{child_id}")
                st.write("Authorized Signature:")
                st_canvas(height=100, width=300, key=f"sig_{child_id}", drawing_mode="freedraw")
                
                if st.button("Complete Sign-Out Process", key=f"out_{child_id}", type="primary", use_container_width=True):
                    if not current_selection:
                        st.error("⚠️ System requires you to select a collector before submitting!")
                    else:
                        now = datetime.now().strftime("%H:%M:%S")
                        supabase.table("attendance").update({
                            "check_out": now, 
                            "collected_by": current_selection,
                            "hours": ncs_round(log['check_in'], now),
                            "notes": f"Collected by {current_selection}. {note}"
                        }).eq("id", child_id).execute()
                        if c_key in st.session_state: del st.session_state[c_key]
                        st.rerun()

# --- 7. ADMIN SETTINGS (ENROLLMENT) ---
elif page == "Admin Settings":
    st.title("⚙️ Administration Portal")
    if not st.session_state.get('admin_auth'):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.button("Login"):
            if u == "dave" and p == "bonnie123":
                st.session_state['admin_auth'] = True
                st.rerun()
            else:
                st.error("Invalid Credentials.")
    else:
        st.subheader("➕ Enroll New Child")
        with st.form("enrollment_form", clear_on_submit=True):
            new_name = st.text_input("Child's Full Name")
            new_loc = st.selectbox("Assigned Base Site Location", sites, index=sites.index(sel_site))
            allergies = st.text_area("Allergies / Medical Notes", value="None")
            
            submit_enrollment = st.form_submit_button("Save Child to Database")
            if submit_enrollment:
                if new_name.strip() != "":
                    try:
                        supabase.table("children").insert({
                            "name": new_name.strip(),
                            "location": new_loc,
                            "allergies": allergies
                        }).execute()
                        st.success(f"🎉 {new_name} successfully added to database at {new_loc}!")
                    except Exception as e:
                        st.error(f"Failed to save child: {e}")
                else:
                    st.error("Name field cannot be blank.")

        if st.button("Logout from Admin Panel"):
            st.session_state['admin_auth'] = False
            st.rerun()

# --- 8. GLOBAL REPORTS ---
st.divider()
st.header("📊 Daily Attendance Report")
r_date = st.date_input("Select Report Date", datetime.now().date())
if st.button("Generate Live Report Data"):
    try:
        att_data = supabase.table("attendance").select("*").eq("date", str(r_date)).execute()
        kids_at_site = supabase.table("children").select("name").eq("location", sel_site).execute()
        names_at_site = [k['name'] for k in kids_at_site.data]
        
        filtered = [r for r in att_data.data if r['name'] in names_at_site]
        if filtered:
            df = pd.DataFrame(filtered)
            # Safe fallbacks if column data fields are missing 
            if 'collected_by' not in df.columns:
                df['collected_by'] = "N/A", "Total Hours
Use code with caution.df = df[["name", "check_in", "check_out", "collected_by", "hours"]]df.columns = ["Child Name", "Sign In Time", "Sign Out Time", "Creport data: {e}")
