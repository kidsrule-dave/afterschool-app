import streamlit as st
import pandas as pd
import math
import io
from datetime import datetime
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas

# ADD THE LOGO HERE - It will sit at the very top of your sidebar
st.sidebar.image("kidsrule-logo.png", use_container_width=True)

# --- 1. SECURE CONNECTION ---
SUPABASE_URL = "https://wwofdtdjpprvtzjmqgbk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind3b2ZkdGRqcHBydnR6am1xZ2JrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5MTQzMTcsImV4cCI6MjA5MTQ5MDMxN30.jirzLPRXKfr1Z3slm-0CchvTU7lXgLtTWuCk1RDhmfQ"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. UTILS ---
def ncs_round(check_in, check_out):
    try:
        fmt = "%H:%M:%S"
        start = datetime.strptime(check_in, fmt)
        end = datetime.strptime(check_out, fmt)
        actual_hours = (end - start).total_seconds() / 3600
        return math.ceil(actual_hours)
    except Exception:
        return 0

def is_sunday():
    """Returns True only if today is Sunday (weekday 6)."""
    return datetime.now().weekday() == 6

# --- 3. NAVIGATION & ADMIN SIDEBAR ---
sites = ["Elphin", "Ballinameen", "Boyle", "Roscommon", "Keadue"]
page = st.sidebar.radio("Navigation", ["Dashboard", "Weekly Planner", "Quick-Tap Board", "Attendance", "NCS Compliance", "Admin Settings"])
sel_site = st.sidebar.selectbox("Current Site Location", sites)

# Add clear visual indicators directly in your navigation frame
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔐 Admin Dashboard Status")

if is_sunday():
    st.sidebar.caption("🟢 Live Status: **Sunday Maintenance Active**")
else:
    st.sidebar.caption("🔵 Live Status: **Standard Weekday Operation**")

# Set to True globally so editing is unlocked every single day
unlocked = True

# --- 4. DASHBOARD ---
if page == "Dashboard":
    st.title(f"🏫 {sel_site} Hub")
    today = str(datetime.now().date())
    
    try:
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
    
    lock_planner = False
    
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
            st.success("🔓 Open: Daily updates and submissions are fully unlocked.")
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
                    st.error(f"Failed to submit database entries: {e}")

# --- 6. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Sign-Out")
    st.caption("Tap a child's name to select who is collecting them.")
    
    try:
        children_res = supabase.table("children").select(
            "name", "emergency_name", "emergency_phone",
            "pickup_1_name", "pickup_1_phone",
            "pickup_2_name", "pickup_2_phone",
            "pickup_3_name", "pickup_3_phone"
        ).eq("location", sel_site).execute()
        child_lookup = {c['name']: c for c in children_res.data}
        
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
                if st.button(label, key=f"name_btn_{child_id}", type=b_style, use_container_width=True):
                    st.session_state[active_child_key] = child_id
                    st.rerun()

        st.divider()

        active_id = st.session_state.get("active_tap_child_id")
        
        if active_id:
            selected_log = next((l for l in site_logs if l['id'] == active_id), None)
            
            if selected_log:
                c_key = f"coll_{active_id}"
                current_collector = st.session_state.get(c_key)
                
                meta = child_lookup.get(selected_log['name'], {})
                e_name = meta.get('emergency_name', 'Not Listed')
                e_phone = meta.get('emergency_phone', 'Not Listed')
                
                p1_name = meta.get('pickup_1_name') or "Mom"
                p1_phone = meta.get('pickup_1_phone') or ""
                p2_name = meta.get('pickup_2_name') or "Slot 2 (Empty)"
                p2_phone = meta.get('pickup_2_phone') or ""
                p3_name = meta.get('pickup_3_name') or "Slot 3 (Empty)"
                p3_phone = meta.get('pickup_3_phone') or ""
                
                with st.container(border=True):
                    st.subheader(f"🔑 Sign-Out: {selected_log['name']}")
                    st.write(f"🎒 *In since {selected_log['check_in']} ({selected_log.get('session_type', 'Afterschool')})*")
                    st.warning(f"🚨 **Emergency Contact:** {e_name} — 📞 {e_phone}")
                    st.write("---")
                    st.write("**Who is collecting them?**")
                    
                    custom_collectors = [
                        f"👩 {p1_name} ({p1_phone})",
                        f"👤 {p2_name} ({p2_phone})",
                        f"👤 {p3_name} ({p3_phone})"
                    ]
                    
                    coll_cols = st.columns(3)
                    for i, p in enumerate(custom_collectors):
                        p_style = "primary" if current_collector == p else "secondary"
                        if coll_cols[i].button(p, key=f"q_tap_p_{i}_{active_id}", type=p_style, use_container_width=True):
                            st.session_state[c_key] = p
                            st.rerun()
                    
                    if current_collector:
                        st.success(f"Selected Collector: **{current_collector}**")
                        st.write("✍️ **Collector's Signature:**")
                        
                        canvas_result = st_canvas(
                            fill_color="rgba(255, 165, 0, 0.3)",
                            stroke_width=3,
                            stroke_color="#000000",
                            background_color="#eeeeee",
                            height=150,
                            key=f"canvas_{active_id}",
                            update_streamlit=True
                        )
                        
                        with st.form(f"checkout_form_{active_id}"):
                            st.caption("Please sign above before confirming.")
                            confirm_btn = st.form_submit_button("Confirm Child Sign-Out", type="primary", use_container_width=True)
                            
                            if confirm_btn:
                                now_time = datetime.now().strftime("%H:%M:%S")
                                calculated_hours = ncs_round(selected_log['check_in'], now_time)
                                
                                try:
                                    supabase.table("attendance").update({
                                        "check_out": now_time,
                                        "collected_by": current_collector,
                                        "calculated_hours": calculated_hours
                                    }).eq("id", active_id).execute()
                                    
                                    st.success(f"🎒 {selected_log['name']} successfully signed out at {now_time}!")
                                    
                                    if active_child_key in st.session_state:
                                        del st.session_state[active_child_key]
                                    if c_key in st.session_state:
                                        del st.session_state[c_key]
                                        
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to submit sign-out: {e}")
                    else:
                        st.info("💡 Please tap one of the names above to select the collector.")
# --- 7. ATTENDANCE ---
elif page == "Attendance":
    st.title("📋 Live Site Attendance Feed")
    st.caption(f"Showing all historical and active daily logs registered for {sel_site}.")
    
    try:
        all_logs_res = supabase.table("attendance").select("*").eq("location", sel_site).order("date", desc=True).execute()
        logs_data = all_logs_res.data
    except Exception as e:
        st.error(f"Failed to load attendance logs: {e}")
        logs_data = []
        
    if not logs_data:
        st.info(f"No attendance logs have been recorded for {sel_site} yet.")
    else:
        df_logs = pd.DataFrame(logs_data)
        
        df_logs_display = df_logs.rename(columns={
            "date": "Date",
            "name": "Child Name",
            "session_type": "Session Type",
            "check_in": "Sign-In",
            "check_out": "Sign-Out",
            "collected_by": "Collected By",
            "calculated_hours": "NCS Hours"
        })
        
        st.dataframe(
            df_logs_display,
            use_container_width=True,
            column_order=["Date", "Child Name", "Session Type", "Sign-In", "Sign-Out", "Collected By", "NCS Hours"]
        )

# --- 8. NCS COMPLIANCE ---
elif page == "NCS Compliance":
    st.title("📊 NCS Compliance Dashboard")
    st.caption(f"Reviewing calculated attendance hours for compliance mapping at {sel_site}.")
    
    try:
        compliance_res = (
            supabase.table("attendance")
            .select("date", "name", "session_type", "check_in", "check_out", "collected_by", "calculated_hours")
            .eq("location", sel_site)
            .not_.is_("check_out", "null")
            .order("date", desc=True)
            .execute()
        )
        compliance_data = compliance_res.data
    except Exception as e:
        st.error(f"Failed to fetch compliance logs: {e}")
        compliance_data = []
        
    if not compliance_data:
        st.info(f"No completed checkout logs available for {sel_site} to display.")
    else:
        df = pd.DataFrame(compliance_data)
        df["calculated_hours"] = df["calculated_hours"].fillna(0).astype(int)
        total_hours_sum = int(df["calculated_hours"].sum())
        
        col_metric, _ = st.columns()
        with col_metric:
            st.metric(label="⏳ Total Rounded NCS Hours (Site)", value=f"{total_hours_sum} hrs")
            
        st.write("---")
        st.subheader("📋 NCS Attendance & Claim Log")
        
        df_clean = df.rename(columns={
            "date": "Date",
            "name": "Child Name",
            "session_type": "Session",
            "check_in": "Sign-In Time",
            "check_out": "Sign-Out Time",
            "collected_by": "Collected By",
            "calculated_hours": "NCS Claim Hours (Rounded)"
        })
        
        st.dataframe(
            df_clean,
            use_container_width=True,
            column_order=["Date", "Child Name", "Session", "Sign-In Time", "Sign-Out Time", "Collected By", "NCS Claim Hours (Rounded)"]
        )
        
        # Fixed: Verified all string conversion and string format brackets close safely
        csv_buffer = io.StringIO()
        df_clean.to_csv(csv_buffer, index=False)
        csv_bytes = csv_buffer.getvalue().encode('utf-8')
        
        # Cleaned up download button configuration layout
        st.download_button(
            label="📥 Export Compliance Logs to CSV",
            data=csv_bytes,
            file_name=f"ncs_compliance_{sel_site.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
# --- 9. ADMIN SETTINGS ---
elif page == "Admin Settings":
    st.title("⚙️ Admin Settings")
    st.subheader("Register a New Child")
    
    with st.form("register_child_form", clear_on_submit=True):
        new_name = st.text_input("Child's Full Name")
        new_location = st.selectbox("Assign Site Location", sites)
        
        ncs_chit = st.text_input("NCS CHIT / CHN Number (Optional)", placeholder="e.g., CHN1234567")
        em_name = st.text_input("Primary Emergency Contact Name")
        em_phone = st.text_input("Primary Emergency Contact Phone")
        
        st.markdown("### 🚗 Authorized Pickups Configuration")
        st.caption("Provide up to three individuals cleared to sign out this student.")
        
        col1, col2 = st.columns(2)
        with col1:
            p1_n = st.text_input("Slot 1 - Full Name", value="Mom")
            p2_n = st.text_input("Slot 2 - Full Name")
            p3_n = st.text_input("Slot 3 - Full Name")
        with col2:
            p1_p = st.text_input("Slot 1 - Contact Phone")
            p2_p = st.text_input("Slot 2 - Contact Phone")
            p3_p = st.text_input("Slot 3 - Contact Phone")
            
        submitted_child = st.form_submit_button("Register Child into System")
        
        if submitted_child:
            if new_name and em_name and em_phone:
                try:
                    supabase.table("children").insert({
                        "name": new_name,
                        "location": new_location,
                        "ncs_chit_number": ncs_chit,
                        "emergency_name": em_name,
                        "emergency_phone": em_phone,
                        "pickup_1_name": p1_n,
                        "pickup_1_phone": p1_p,
                        "pickup_2_name": p2_n,
                        "pickup_2_phone": p2_p,
                        "pickup_3_name": p3_n,
                        "pickup_3_phone": p3_p
                    }).execute()
                    st.success(f"🎉 Successfully registered {new_name} at {new_location} with pickup slots!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add child profile: {e}")
            else:
                st.error("Please fill in Name, Emergency Contact Name, and Phone details.")

    # --- 9B. REMOVE A CHILD SECTION ---
    st.markdown("---")
    st.subheader("🗑️ Remove a Child from System")
    st.caption(f"Select a child registered at {sel_site} to remove their profile.")
    
    try:
        kids_to_delete_res = supabase.table("children").select("name").eq("location", sel_site).execute()
        delete_roster = sorted([k['name'] for k in kids_to_delete_res.data])
    except Exception as e:
        st.error(f"Error loading deletion roster: {e}")
        delete_roster = []
        
    if not delete_roster:
        st.info(f"No children currently registered at {sel_site} to delete.")
    else:
        with st.form("delete_child_form"):
            child_to_remove = st.selectbox("Select Child to Delete", delete_roster)
            st.warning(f"⚠️ Warning: This will permanently remove {child_to_remove} from the registry.")
            confirm_delete = st.checkbox(f"I confirm that I want to delete {child_to_remove} permanently.")
            delete_submitted = st.form_submit_button("Delete Child Profile")
            
            if delete_submitted:
                if confirm_delete:
                    try:
                        supabase.table("children").delete().eq("name", child_to_remove).eq("location", sel_site).execute()
                        st.success(f"💥 Successfully removed {child_to_remove} from the database.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete record: {e}")
                else:
                    st.error("Please check the confirmation box before attempting to delete.")

# --- 10. GLOBAL FALLBACK ---
else:
    st.title(f"📄 {page}")
