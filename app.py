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
page = st.sidebar.radio("Navigation", ["Dashboard", "Quick-Tap Board", "Attendance", "NCS Compliance", "Admin Settings"])
sel_site = st.sidebar.selectbox("Current Site Location", sites)

# --- 4. DASHBOARD & TUSLA RATIOS ---
if page == "Dashboard":
    st.title(f"🏫 {sel_site} Management Hub")
    today = str(datetime.now().date())
    
    # Live Stats & Ratios
    kids_in = supabase.table("attendance").select("id", count="exact").eq("date", today).is_("check_out", "null").execute().count
    staff_in = supabase.table("staff_roster").select("id", count="exact").eq("site", sel_site).eq("date", today).is_("shift_end", "null").execute().count
    
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
elif page == "Attendance":
    st.title("📍 Daily Log")
    # Define this at the top of the page so it's ready to use
    collector_types = ["Mom", "Dad", "Brother", "Sister", "Nan", "Grandad", "Aunty", "Uncle", "Family Friend"]
    
    tab1, tab2 = st.tabs(["🚌 Bulk Bus Arrival", "👤 Check-Out & Sign"])
    
    # ... (Keep Tab 1 as it is) ...

    with tab2:
        # (Your existing fetch logic here...)
        active_res = supabase.table("attendance").select("*").is_("check_out", "null").execute()
        children_res = supabase.table("children").select("name", "location", "allergies").eq("location", sel_site).execute()
        site_children = {c['name']: c for c in children_res.data}
        
        site_logs = []
        for a in active_res.data:
            if a['name'] in site_children:
                a['child_info'] = site_children[a['name']]
                site_logs.append(a)

        for log in site_logs:
            with st.expander(f"Sign-Out: {log['name']}"):
                # ALL LINES BELOW MUST BE INDENTED 4 SPACES FROM 'WITH'
                st.warning(f"Allergy Alert: {log['child_info'].get('allergies', 'None')}")
                
                # Use st.selectbox if st.pills isn't working on your version
                collector = st.selectbox("Who is collecting?", collector_types, key=f"coll_{log['id']}", index=None)
                
                note = st.text_input("Notes", key=f"note_{log['id']}")
                canvas_res = st_canvas(height=100, width=300, key=f"sig_{log['id']}", drawing_mode="freedraw")
                
                if st.button("Finalize Pick-Up", key=f"out_{log['id']}", type="primary"):
                    if not collector:
                        st.error("Please select a collector.")
                    else:
                        now_time = datetime.now().strftime("%H:%M:%S")
                        rounded_h = ncs_round(log['check_in'], now_time)
                        supabase.table("attendance").update({
                            "check_out": now_time, 
                            "hours": rounded_h, 
                            "notes": note,
                            "collected_by": collector,
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

# --- 8. REPORTS ---
st.header("📊 Daily Attendance Report")

report_date = st.date_input("Select Date for Report", datetime.now())

if st.button("Generate Report"):
    # 1. Fetch attendance records for that day
    att_res = supabase.table("attendance") \
        .select("name, check_in, check_out, hours") \
        .eq("date", str(report_date)) \
        .execute()
    
    # 2. Fetch list of children belonging to the current site
    kids_res = supabase.table("children") \
        .select("name") \
        .eq("location", sel_site) \
        .execute()
    
    # Create a list of names for filtering
    site_kid_names = [k['name'] for k in kids_res.data]
    
    # 3. Match attendance data with the site's children
    report_data = [row for row in att_res.data if row['name'] in site_kid_names]
    
    # Check 'report_data' (the filtered list) instead of 'res.data'
    if report_data:
        report_df = pd.DataFrame(report_data)
        
        # Select and rename columns for the final report
        report_df = report_df[["name", "check_in", "check_out", "hours"]]
        report_df.columns = ["Child Name", "Arrival", "Departure", "NCS Hours"]
        
        st.dataframe(report_df, use_container_width=True)
        
        csv = report_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV for Excel",
            data=csv,
            file_name=f"Report_{sel_site}_{report_date}.csv",
            mime="text/csv",
        )
    else:
        st.warning(f"No records found for {sel_site} on {report_date}.")


# --- 9. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Attendance")
    collector_types = ["Mom", "Dad", "Brother", "Sister", "Nan", "Grandad", "Aunty", "Uncle", "Family Friend"]

    # 1. Fetch children for site
    kids_res = supabase.table("children").select("name").eq("location", sel_site).execute()
    all_kids = sorted([k['name'] for k in kids_res.data])

    # 2. Get active attendance
    active_res = supabase.table("attendance").select("name").is_("check_out", "null").execute()
    checked_in_names = [a['name'] for a in active_res.data]

    # 3. The Grid
    cols = st.columns(4)
    for i, name in enumerate(all_kids):
        is_in = name in checked_in_names
        btn_label = f"🟢 {name.split()[0]}" if is_in else f"⚪ {name.split()[0]}"
        
        if cols[i % 4].button(btn_label, key=f"tap_{name}", use_container_width=True):
            if not is_in:
                # SIGN IN
                supabase.table("attendance").insert({
                    "name": name, "date": str(datetime.now().date()), 
                    "session": "Afterschool", "check_in": datetime.now().strftime("%H:%M:%S")
                }).execute()
                st.rerun()
            else:
                # Set session state to show collector options for this specific child
                st.session_state["signing_out_child"] = name

    # 4. Collection Flow (Triggers when a child is tapped for Sign-Out)
    if "signing_out_child" in st.session_state:
        child_name = st.session_state["signing_out_child"]
        st.divider()
        with st.container(border=True):
            st.subheader(f"Confirm Collection: {child_name}")
            col_choice = st.pills("Who is collecting?", collector_types, key="pills_coll")
            
            c1, c2 = st.columns(2)
            if c1.button("Finalize Sign-Out", type="primary", use_container_width=True):
                if col_choice:
                    # Find the record to update
                    record = supabase.table("attendance").select("id, check_in").eq("name", child_name).is_("check_out", "null").execute()
                    if record.data:
                        rec = record.data[0]
                        now_time = datetime.now().strftime("%H:%M:%S")
                        rounded_h = ncs_round(rec['check_in'], now_time)
                        supabase.table("attendance").update({
                            "check_out": now_time, 
                            "hours": rounded_h,
                            "collected_by": col_choice
                        }).eq("id", rec['id']).execute()
                        
                        del st.session_state["signing_out_child"]
                        st.success(f"{child_name} collected by {col_choice}")
                        st.rerun()
                else:
                    st.error("Please select a collector first!")
            
            if c2.button("Cancel", use_container_width=True):
                del st.session_state["signing_out_child"]
                st.rerun()
