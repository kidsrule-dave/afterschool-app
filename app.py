import streamlit as st
import pandas as pd
import math
import io
from datetime import datetime
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas

# --- 1. SECURE CONNECTION ---
SUPABASE_URL = "https://wwofdtdjpprvtzjmqgbk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind3b2ZkdGRqcHBydnR6am1xZ2JrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5MTQzMTcsImV4cCI6MjA5MTQ5MDMxN30.jirzLPRXKfr1Z3slm-0CchvTU7lXgLtTWuCk1RDhmfQ"
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
page = st.sidebar.radio("Navigation", ["Dashboard", "Weekly Planner", "Quick-Tap Board", "Attendance", "NCS Compliance", "Admin Settings"])
sel_site = st.sidebar.selectbox("Current Site Location", sites)

# --- 4. DASHBOARD ---
if page == "Dashboard":
    st.title(f"🏫 {sel_site} Hub")
    today = str(datetime.now().date())
    
    try:
        # Check headcount for both separate programs for this site location
        bc_res = supabase.table("attendance").select("id", count="exact").eq("date", today).eq("location", sel_site).eq("session_type", "Breakfast Club").is_("check_out", "null").execute()
        as_res = supabase.table("attendance").select("id", count="exact").eq("date", today).eq("location", sel_site).eq("session_type", "Afterschool").is_("check_out", "null").execute()
        
        bc_in = bc_res.count if bc_res.count else 0
        as_in = as_res.count if as_res.count else 0
    except:
        bc_in, as_in = 0, 0
        
    c1, c2 = st.columns(2)
    c1.metric("🌅 Breakfast Club Present", bc_in)
    c2.metric("👦 Afterschool Present", as_in)

# --- 5. WEEKLY PLANNER (PARENTS SUNDAY MESSAGING AREA) ---
elif page == "Weekly Planner":
    st.title("📅 Parent Weekly Planner")
    st.caption("Let us know what days your child will attend for the upcoming week.")
    
    # Lock planner input if it is NOT Sunday (6 = Sunday)
    current_time = datetime.now()
    lock_planner = current_time.weekday() != 6
    
    try:
        kids = supabase.table("children").select("name").eq("location", sel_site).execute()
        child_names = sorted([k['name'] for k in kids.data])
    except Exception as e:
        st.error(f"Error loading children roster: {e}")
        child_names = []

    if not child_names:
        st.info("No children currently registered at this site location.")
    else:
        selected_child = st.selectbox("Select Your Child", child_names)
        st.write("### 🗓️ Select Attendance Days & Clubs")
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        
        with st.form("weekly_schedule_form"):
            selections = {}
            cols = st.columns(5)
            
            for idx, day in enumerate(days):
                with cols[idx]:
                    st.markdown(f"**{day}**")
                    bc = st.checkbox("Breakfast Club", key=f"bc_{day}")
                    as_club = st.checkbox("Afterschool", key=f"as_{day}")
                    selections[day] = {"breakfast_club": bc, "afterschool": as_club}
            
            st.write("---")
            if lock_planner:
                st.error("🔒 Submissions locked! The Sunday night submission deadline has passed.")
                submit_disabled = True
            else:
                st.info("🔓 Open: Submit or update your preferences before Sunday midnight.")
                submit_disabled = False
                
            submitted = st.form_submit_button("Submit Plan for Next Week", disabled=submit_disabled)
            
            if submitted:
                try:
                    for day, clubs in selections.items():
                        supabase.table("weekly_bookings").upsert({
                            "child_name": selected_child,
                            "location": sel_site,
                            "day_of_week": day,
                            "breakfast_club": clubs["breakfast_club"],
                            "afterschool": clubs["afterschool"],
                            "updated_at": str(datetime.now())
                        }, on_conflict="child_name,day_of_week").execute()
                    st.success(f"Successfully saved schedule preferences for {selected_child}!")
                except Exception as e:
                    st.error(f"Failed to submit database layout entries: {e}")

# --- 6. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Sign-Out")
    st.caption("Tap a child's name to select who is collecting them.")
    
    try:
        # 1. Fetch children registered to this site
        children_res = supabase.table("children").select("name", "emergency_name", "emergency_phone").eq("location", sel_site).execute()
        child_lookup = {c['name']: c for c in children_res.data}
        site_child_names = list(child_lookup.keys())
        
        # 2. Fetch active logs matching location
        active_res = supabase.table("attendance").select("*").is_("check_out", "null").eq("location", sel_site).execute()
        site_logs = active_res.data
    except Exception as e:
        st.error(f"Database Error: {e}")
        site_logs = []
        child_lookup = {}

    if not site_logs:
        st.info(f"No children currently checked in at {sel_site}.")
    else:
        st.write("### 👤 Children Present")
        grid_cols = st.columns(3)
        
        for idx, log in enumerate(site_logs):
            child_id = log['id']
            child_name = log['name']
            session_type = log.get('session_type', 'Afterschool')
            
            active_child_key = "active_tap_child_id"
            is_active = st.session_state.get(active_child_key) == child_id
            b_style = "primary" if is_active else "secondary"
            
            with grid_cols[idx % 3]:
                label = f"🌅 {child_name} (BC)" if session_type == "Breakfast Club" else f"👦 {child_name} (AS)"
                if st.button(label, key=f"qt_name_btn_{child_id}_{idx}", type=b_style, use_container_width=True):
                    st.session_state[active_child_key] = child_id
                    st.rerun()

        st.divider()

        # --- STEP 2: SHOW COLLECTOR PANEL FOR THE CLICKED CHILD ---
        active_id = st.session_state.get("active_tap_child_id")
        
        if active_id:
            selected_log = next((l for l in site_logs if l['id'] == active_id), None)
            
            if selected_log:
                c_key = f"coll_{active_id}"
                current_collector = st.session_state.get(c_key)
                
                meta = child_lookup.get(selected_log['name'], {})
                e_name = meta.get('emergency_name', 'Not Listed')
                e_phone = meta.get('emergency_phone', 'Not Listed')
                
                with st.container(border=True):
                    st.subheader(f"🔑 Sign-Out: {selected_log['name']}")
                    st.write(f"🎒 *In since {selected_log['check_in']} ({selected_log.get('session_type', 'Afterschool')})*")
                    st.warning(f"🚨 **Emergency Contact:** {e_name} — 📞 {e_phone}")
                    st.write("---")
                    st.write("**Who is collecting them?**")
                    
                    collectors = ["Mom", "Dad", "Nan", "Grandad", "Aunty", "Uncle", "Brother", "Sister"]
                    coll_cols = st.columns(4)
                    
                    for i, p in enumerate(collectors):
                        p_style = "primary" if current_collector == p else "secondary"
                        if coll_cols[i % 4].button(p, key=f"q_tap_p_{p}_{active_id}_{i}", type=p_style, use_container_width=True):
                            st.session_state[c_key] = p
                            st.rerun()
                    
                    if current_collector:
                        st.write("")
                        if st.button(f"✅ Confirm: {current_collector} is picking up {selected_log['name']}", key=f"fin_qt_{active_id}", type="primary", use_container_width=True):
                            now = datetime.now().strftime("%H:%M:%S")
                            
                            supabase.table("attendance").update({
                                "check_out": now, 
                                "collected_by": current_collector,
                                "hours": ncs_round(selected_log['check_in'], now),
                                "notes": f"Quick-tap pickup by {current_collector}"
                            }).eq("id", active_id).execute()
                            
                            if c_key in st.session_state: del st.session_state[c_key]
                            if "active_tap_child_id" in st.session_state: del st.session_state["active_tap_child_id"]
                            
                            st.success(f"Successfully signed out {selected_log['name']}!")
                            st.rerun()

# --- 7. ATTENDANCE & SIGN-OUT ---
elif page == "Attendance":
    st.title("📍 Daily Log")
    tab1, tab2 = st.tabs(["🚌 Arrivals (Quick-Sign In)", "👤 Departures (Sign Out)"])
    
    with tab1:
        st.subheader("Quick-Tap Children to Sign In")
        today_str = str(datetime.now().date())
        
        # Session selector filter for admissions operations
        chosen_session = st.radio("Signing into which program?", ["Afterschool", "Breakfast Club"], horizontal=True)
        
        try:
            kids = supabase.table("children").select("name").eq("location", sel_site).execute()
            all_names = sorted([k['name'] for k in kids.data])
            
            active_res = supabase.table("attendance").select("name").eq("date", today_str).eq("location", sel_site).eq("session_type", chosen_session).is_("check_out", "null").execute()
            already_in = [a['name'] for a in active_res.data]
        except Exception as e:
            st.error(f"Could not load attendance roster: {e}")
            all_names = []
            already_in = []

if all_names:
    arr_cols = st.columns(3)
    for idx, child_name in enumerate(all_names):
        with arr_cols[idx % 3]:
            if child_name in already_in:
                # Added _{idx} to the end of the key string
                st.button(f"✅ {child_name} (In)", key=f"in_{child_name}_{chosen_session}_{idx}", disabled=True, use_container_width=True)
            else:
                # Added _{idx} to the end of the key string
                if st.button(f"➕ {child_name}", key=f"add_{child_name}_{chosen_session}_{idx}", use_container_width=True):
                    now = datetime.now().strftime("%H:%M:%S")
                    try:
                        supabase.table("attendance").insert({
                            "name": child_name,
                            "location": sel_site,
                            "date": today_str,
                            "check_in": now,
                            "session_type": chosen_session
                        }).execute()
                        st.success(f"Signed in {child_name} to {chosen_session}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Sign-in failed: {e}")
else:
    st.info("No children found for this location.")

    with tab2:
        st.subheader("Manual Sign Out Logs")
        st.caption("Use the Quick-Tap Board for faster daily pick-up transactions.")
# --- 8. NCS COMPLIANCE & PRINTABLE REPORTS ---
elif page == "NCS Compliance":
    st.title("📋 Operational & NCS Reporting")
    
    rep_tab1, rep_tab2, rep_tab3 = st.tabs([
        "📅 Weekly Booking Sheets", 
        "📝 Today's Sign-In Manifest", 
        "📊 Raw NCS System Export"
    ])
    
    # REPORT 1: SHOW WHO IS BOOKED IN ADVANCE FOR EACH DAY AT THIS SITE
    with rep_tab1:
        st.subheader(f"🗓️ Upcoming Weekly Bookings: {sel_site}")
        st.caption("This report aggregates what parents chose on their Sunday planners.")
        
        try:
            bk_res = supabase.table("weekly_bookings").select("*").eq("location", sel_site).execute()
            if bk_res.data:
                bk_df = pd.DataFrame(bk_res.data)
                
                # Format true/false fields into visual checkmarks
                bk_df["Breakfast Club"] = bk_df["breakfast_club"].apply(lambda x: "✅ Yes" if x else "❌ No")
                bk_df["Afterschool"] = bk_df["afterschool"].apply(lambda x: "✅ Yes" if x else "❌ No")
                
                # Clean columns to show
                clean_bk = bk_df[["child_name", "day_of_week", "Breakfast Club", "Afterschool"]].rename(columns={"child_name": "Child Name", "day_of_week": "Scheduled Day"})
                st.dataframe(clean_bk, use_container_width=True)
                
                # Excel Generation
                buf_bk = io.BytesIO()
                with pd.ExcelWriter(buf_bk, engine='xlsxwriter') as wr:
                    clean_bk.to_excel(wr, sheet_name='Weekly Bookings', index=False)
                
                st.download_button(
                    label="📥 Print/Download Weekly Booking Roster",
                    data=buf_bk.getvalue(),
                    file_name=f"weekly_bookings_{sel_site}_{datetime.now().date()}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.info("No parents have logged weekly schedules for this site yet.")
        except Exception as e:
            st.error(f"Error compiling weekly bookings: {e}")

    # REPORT 2: TODAY'S LIVE SIGN-IN MANIFEST (TIMES, COLLECTORS)
    with rep_tab2:
        today_date = str(datetime.now().date())
        st.subheader(f"⏱️ Live Daily Manifest: {sel_site} ({today_date})")
        st.caption("Real-time list of tracking entries logged today.")
        
        try:
            today_res = supabase.table("attendance").select("*").eq("location", sel_site).eq("date", today_date).execute()
            if today_res.data:
                td_df = pd.DataFrame(today_res.data)
                
                # Fill empty cells with placeholder markers nicely
                td_df["check_out"] = td_df["check_out"].fillna("Still Present")
                td_df["collected_by"] = td_df["collected_by"].fillna("—")
                
                clean_td = td_df[["name", "session_type", "check_in", "check_out", "collected_by"]].rename(columns={
                    "name": "Child Name",
                    "session_type": "Program",
                    "check_in": "Time In",
                    "check_out": "Time Out",
                    "collected_by": "Collected By"
                })
                
                st.dataframe(clean_td, use_container_width=True)
                
                # Excel Generation
                buf_td = io.BytesIO()
                with pd.ExcelWriter(buf_td, engine='xlsxwriter') as wr:
                    clean_td.to_excel(wr, sheet_name='Today Logs', index=False)
                
                st.download_button(
                    label="📥 Print/Download Today's Roster Manifest",
                    data=buf_td.getvalue(),
                    file_name=f"daily_manifest_{sel_site}_{today_date}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.info("No attendance entries have been checked in today.")
        except Exception as e:
            st.error(f"Error fetching daily logs: {e}")

    # REPORT 3: HISTORICAL EXPORTS
    with rep_tab3:
        st.subheader("📋 Complete Historical Compliance Database")
        try:
            att_data = supabase.table("attendance").select("*").eq("location", sel_site).execute()
            if att_data.data:
                df = pd.DataFrame(att_data.data)
                st.dataframe(df)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, sheet_name='Attendance', index=False)
                
                st.download_button(
                    label="📥 Download Historical Compliance Excel Report",
                    data=buffer.getvalue(),
                    file_name=f"ncs_report_{sel_site}_{datetime.now().date()}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.info("No logs saved yet for reporting operations pipelines.")
        except Exception as e:
            st.error(f"Report configuration failure: {e}")

# --- 9. ADMIN SETTINGS & SECURITY ---
elif page == "Admin Settings":
    st.title("🛠️ Admin Configuration Settings")
    
    # Safety password entry verification field check
    password_input = st.text_input("Enter Admin Access Password Key", type="password")
    
    if password_input:
        if password_input == "manager123":  # Password set to manager123
            st.success("Access Granted.")
            st.write("---")
            st.subheader("👨‍💻 Register New Child Profile")
            
            with st.form("register_child_form"):
                new_name = st.text_input("Child Name")
                e_name = st.text_input("Emergency Contact Person Name")
                e_phone = st.text_input("Emergency Contact Phone Number")
                
                reg_submitted = st.form_submit_button("Save New Registration Profile")
                if reg_submitted and new_name:
                    try:
                        supabase.table("children").insert({
                            "name": new_name,
                            "location": sel_site,
                            "emergency_name": e_name,
                            "emergency_phone": e_phone
                        }).execute()
                        st.success(f"Successfully registered child profile record for {new_name}!")
                    except Exception as e:
                        st.error(f"Failed to submit profile layout parameters: {e}")
        else:
            st.error("Incorrect password. Access denied.")
