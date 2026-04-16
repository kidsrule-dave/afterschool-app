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
    """NCS Rule: Round part hours per day UP to the next whole hour."""
    fmt = "%H:%M:%S"
    start = datetime.strptime(check_in, fmt)
    end = datetime.strptime(check_out, fmt)
    actual_hours = (end - start).total_seconds() / 3600
    return math.ceil(actual_hours)

# --- 3. NAVIGATION & SITE SELECTOR ---
if 'user' not in st.session_state:
    st.session_state['user'] = "Staff_User"

sites = ["Elphin", "Ballinameen", "Boyle", "Roscommon", "Keadue"]
page = st.sidebar.radio("Navigation", ["Dashboard", "Quick-Tap Board", "Attendance", "NCS Compliance", "Admin Settings"])
sel_site = st.sidebar.selectbox("Current Site Location", sites)

# --- 4. DASHBOARD ---
if page == "Dashboard":
    st.title(f"🏫 {sel_site} Management Hub")
    today = str(datetime.now().date())
    
    kids_res = supabase.table("attendance").select("id", count="exact").eq("date", today).is_("check_out", None).execute()
    kids_in = kids_res.count if kids_res.count is not None else 0
    
    staff_res = supabase.table("staff_roster").select("id", count="exact").eq("site", sel_site).eq("date", today).is_("shift_end", None).execute()
    staff_in = staff_res.count if staff_res.count is not None else 0
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

# --- 5. ATTENDANCE & QUICK-TAP ---
elif page == "Attendance" or page == "Quick-Tap Board":
    st.title("📍 Daily Log & Sign-Out")
    tab1, tab2 = st.tabs(["🚌 Arrivals", "👤 Check-Out & Sign"])
    
    with tab1:
        kids = supabase.table("children").select("name").eq("location", sel_site).execute()
        names = sorted([k['name'] for k in kids.data])
        
        st.subheader("Arrivals")
        sel_kids = st.multiselect("Select Children for Bulk In", names)
        if st.button("Process Bulk In"):
            today_str = str(datetime.now().date())
            for n in sel_kids:
                supabase.table("attendance").insert({
                    "name": n, "date": today_str, "session": "Afterschool", "check_in": datetime.now().strftime("%H:%M:%S")
                }).execute()
            st.success("Checked in!")
            st.rerun()

    with tab2:
        active_res = supabase.table("attendance").select("*").is_("check_out", "null").execute()
        children_res = supabase.table("children").select("name", "location", "allergies").eq("location", sel_site).execute()
        site_children = {c['name']: c for c in children_res.data}
        
        site_logs = [a for a in active_res.data if a['name'] in site_children]

        if not site_logs:
            st.info(f"No children currently checked in at {sel_site}.")
        
        for log in site_logs:
            with st.expander(f"Sign-Out: {log['name']}"):
                st.warning(f"Allergy Alert: {site_children[log['name']].get('allergies', 'None')}")
                
                # --- Collected By Buttons ---
                st.write("### Collected By:")
                collectors = ["Mom", "Dad", "Nan", "Grandad", "Aunty", "Uncle", "Brother", "Sister"]
                c_key = f"coll_{log['id']}"
                if c_key not in st.session_state: st.session_state[c_key] = None
                
                cols = st.columns(4)
                for i, p in enumerate(collectors):
                    if cols[i % 4].button(p, key=f"btn_{p}_{log['id']}"):
                        st.session_state[c_key] = p
                
                if st.session_state[c_key]:
                    st.info(f"Selected: {st.session_state[c_key]}")

                note = st.text_input("Notes", key=f"note_{log['id']}")
                canvas_res = st_canvas(height=100, width=300, key=f"sig_{log['id']}", drawing_mode="freedraw")
                
                if st.button("Finalize Pick-Up", key=f"out_{log['id']}", type="primary"):
                    if not st.session_state[c_key]:
                        st.error("Please tap a collector first!")
                    else:
                        now_time = datetime.now().strftime("%H:%M:%S")
                        rounded_h = ncs_round(log['check_in'], now_time)
                        full_note = f"Collected by {st.session_state[c_key]}. {note}"
                        supabase.table("attendance").update({
                            "check_out": now_time, "hours": rounded_h, "notes": full_note, "signature_captured": True
                        }).eq("id", log['id']).execute()
                        st.rerun()

# --- 6. NCS TRACKER ---
elif page == "NCS Compliance":
    st.title("⚖️ 8-Week Under-Attendance Tracker")
    st.info("Monitors consecutive weeks below registered hours.")

# --- 7. ADMIN SETTINGS (WITH LOGIN) ---
elif page == "Admin Settings":
    st.title("⚙️ System Management")
    
    if 'admin_auth' not in st.session_state:
        st.session_state['admin_auth'] = False
        
    if not st.session_state['admin_auth']:
        user_in = st.text_input("Username")
        pass_in = st.text_input("Password", type="password")
        if st.button("Login"):
            if user_in == "dave" and pass_in == "bonnie123":
                st.session_state['admin_auth'] = True
                st.rerun()
            else:
                st.error("Access Denied")
    else:
        if st.button("Logout Admin"):
            st.session_state['admin_auth'] = False
            st.rerun()
            
        with st.form("enroll"):
            st.subheader("Enroll New Child")
            n = st.text_input("Full Name")
            c = st.text_input("NCS CHICK Number")
            h = st.number_input("Registered Weekly Hours", value=20)
            if st.form_submit_button("Save Record"):
                supabase.table("children").insert({"name": n, "location": sel_site, "ncs_number": c, "registered_hours": h}).execute()
                st.success("Enrolled!")

# --- 8. REPORTS ---
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
