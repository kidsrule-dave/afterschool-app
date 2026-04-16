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
        kids_res = supabase.table("attendance").select("id", count="exact").eq("date", today).is_("check_out", "null").execute()
        kids_in = kids_res.count if kids_res.count else 0
    except:
        kids_in = 0
        
    st.metric("Children Present", kids_in)
# --- NEW: 4b. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Sign-Out")
    
    # 1. Fetch active kids at this site
active_res = supabase.table("attendance").select("*").is_("check_out", None).execute()
    children_res = supabase.table("children").select("name", "location").eq("location", sel_site).execute()
    site_child_names = [c['name'] for c in children_res.data]
    site_logs = [a for a in active_res.data if a['name'] in site_child_names]

    if not site_logs:
        st.info(f"No children currently checked in at {sel_site}.")
    
    for log in site_logs:
        child_id = log['id']
        c_key = f"coll_{child_id}"
        current_selection = st.session_state.get(c_key)

        # Creates a nice visual box for each child
        with st.container(border=True):
            st.subheader(f"👤 {log['name']}")
            
            collectors = ["Mom", "Dad", "Nan", "Grandad", "Aunty", "Uncle", "Brother", "Sister"]
            cols = st.columns(4)
            for i, p in enumerate(collectors):
                b_type = "primary" if current_selection == p else "secondary"
                # use_container_width=True makes the buttons big and easy to tap
                if cols[i % 4].button(p, key=f"q_tap_{p}_{child_id}", type=b_type, use_container_width=True):
                    st.session_state[c_key] = p
                    st.rerun()
            
            if current_selection:
                if st.button(f"✅ Finalize: {current_selection} is collecting", key=f"fin_{child_id}", type="primary", use_container_width=True):
                    now = datetime.now().strftime("%H:%M:%S")
                    supabase.table("attendance").update({
                        "check_out": now, 
                        "notes": f"Quick-tap by {current_selection}"
                    }).eq("id", child_id).execute()
                    if c_key in st.session_state: del st.session_state[c_key]
                    st.rerun()

# --- 5. ATTENDANCE & SIGN-OUT ---
elif page == "Attendance":
    st.title("📍 Daily Log")
    tab1, tab2 = st.tabs(["🚌 Arrivals", "👤 Sign-Out"])
    
    with tab1:
        kids = supabase.table("children").select("name").eq("location", sel_site).execute()
        names = sorted([k['name'] for k in kids.data])
        sel_kids = st.multiselect("Bulk Check-In", names)
        if st.button("Check In"):
            for n in sel_kids:
                supabase.table("attendance").insert({"name": n, "date": str(datetime.now().date()), "check_in": datetime.now().strftime("%H:%M:%S")}).execute()
            st.rerun()

    with tab2:
        active_res = supabase.table("attendance").select("*").is_("check_out", "null").execute()
        children_res = supabase.table("children").select("name", "location", "allergies").eq("location", sel_site).execute()
        site_children = {c['name']: c for c in children_res.data}
        site_logs = [a for a in active_res.data if a['name'] in site_children]

        for log in site_logs:
            child_id = log['id']
            c_key = f"coll_{child_id}"
            
            with st.expander(f"Sign-Out: {log['name']}"):
                # SAFE CHECK: Use .get() to avoid the KeyError
                current_selection = st.session_state.get(c_key)
                
                st.write("### Collected By:")
                collectors = ["Mom", "Dad", "Nan", "Grandad", "Aunty", "Uncle", "Brother", "Sister"]
                cols = st.columns(4)
                for i, p in enumerate(collectors):
                    b_type = "primary" if current_selection == p else "secondary"
                    if cols[i % 4].button(p, key=f"btn_{p}_{child_id}", type=b_type):
                        st.session_state[c_key] = p
                        st.rerun()
                
                if current_selection:
                    st.success(f"Selected: {current_selection}")
                
                note = st.text_input("Notes", key=f"note_{child_id}")
                st_canvas(height=100, width=300, key=f"sig_{child_id}", drawing_mode="freedraw")
                
                if st.button("Finalize", key=f"out_{child_id}", type="primary"):
                    if not current_selection:
                        st.error("Select a collector!")
                    else:
                        now = datetime.now().strftime("%H:%M:%S")
                        supabase.table("attendance").update({
                            "check_out": now, 
                            "hours": ncs_round(log['check_in'], now),
                            "notes": f"By {current_selection}. {note}"
                        }).eq("id", child_id).execute()
                        if c_key in st.session_state: del st.session_state[c_key]
                        st.rerun()

# --- 7. ADMIN ---
elif page == "Admin Settings":
    if not st.session_state.get('admin_auth'):
        u, p = st.text_input("User"), st.text_input("Pass", type="password")
        if st.button("Login") and u == "dave" and p == "bonnie123":
            st.session_state['admin_auth'] = True
            st.rerun()
    else:
        st.subheader("Enroll Child")
        # Enrollment form code here...
        if st.button("Logout"):
            st.session_state['admin_auth'] = False
            st.rerun()# --- 8. REPORTS ---
st.divider()
st.header("📊 Daily Attendance Report")
r_date = st.date_input("Report Date", datetime.now())
if st.button("Generate Report"):
    att_data = supabase.table("attendance").select("*").eq("date", str(r_date)).execute()
    kids_at_site = supabase.table("children").select("name").eq("location", sel_site).execute()
    names_at_site = [k['name'] for k in kids_at_site.data]
    
    filtered = [r for r in att_data.data if r['name'] in names_at_site]
    if filtered:
        df = pd.DataFrame(filtered)[["name", "check_in", "check_out", "hours"]]
        df.columns = ["Child", "In", "Out", "Hours"]
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No records found.")
# --- 9. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Attendance")
    st.info(f"Showing children for: **{sel_site}**")

    # 1. Fetch all children for this site
    kids_res = supabase.table("children").select("name").eq("location", sel_site).execute()
    all_kids = sorted([k['name'] for k in kids_res.data])

    # 2. Get currently checked-in children to know who is 'IN'
    active_res = supabase.table("attendance").select("name").is_("check_out", "null").execute()
    checked_in_names = [a['name'] for a in active_res.data]

    # 3. Create the Grid (4 children per row)
    cols = st.columns(4)
    for i, name in enumerate(all_kids):
        first_name = name.split()[0] # Get just the first name for the button
        is_in = name in checked_in_names
        
        # Style: Green for present, Grey for absent
        btn_label = f"🟢 {first_name}" if is_in else f"⚪ {first_name}"
        
        if cols[i % 4].button(btn_label, key=f"tap_{name}", use_container_width=True):
            if not is_in:
                # SIGN IN
                supabase.table("attendance").insert({
                    "name": name, 
                    "date": str(datetime.now().date()), 
                    "session": "Afterschool", 
                    "check_in": datetime.now().strftime("%H:%M:%S")
                }).execute()
                st.toast(f"{first_name} Checked In!")
                st.rerun()
            else:
                # SIGN OUT
                # Find the record to update
                record = supabase.table("attendance").select("id, check_in").eq("name", name).is_("check_out", "null").execute()
                if record.data:
                    rec = record.data[0]
                    now_time = datetime.now().strftime("%H:%M:%S")
                    rounded_h = ncs_round(rec['check_in'], now_time)
                    supabase.table("attendance").update({
                        "check_out": now_time, 
                        "hours": rounded_h
                    }).eq("id", rec['id']).execute()
                    st.toast(f"{first_name} Checked Out!")
                    st.rerun()
