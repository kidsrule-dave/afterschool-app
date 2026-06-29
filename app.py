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

# FIXED: Set to True globally so editing is unlocked every single day
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
    
    # FIXED: The planner form submission remains fully unlocked on any day
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
        children_res = supabase.table("children").select("name", "emergency_name", "emergency_phone").eq("location", sel_site).execute()
        child_lookup = {c['name']: c for c in children_res.data}
        site_child_names = list(child_lookup.keys())
        
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
                        if coll_cols[i % 4].button(p, key=f"q_tap_p_{p}_{active_id}", type=p_style, use_container_width=True):
                            st.session_state[c_key] = p
                            st.rerun()

# --- 7. NCS COMPLIANCE & PRINTABLE REPORTS ---
elif page == "NCS Compliance":
    st.title("📋 Operational & NCS Reporting")
    
    rep_tab1, rep_tab2, rep_tab3, rep_tab4, rep_tab5 = st.tabs([
        "📅 Weekly Booking Sheets", 
        "📝 Today's Sign-In Manifest",
        "📊 Weekly Attendance Totals",
        "⚠️ Unused NCS Hours Audit",
        "📦 Raw NCS System Export"
    ])
    
    # --- REPORT 1: UPCOMING WEEKLY BOOKINGS ---
    with rep_tab1:
        st.subheader(f"🗓️ Upcoming Weekly Bookings: {sel_site}")
        st.caption("This report aggregates what parents chose on their Sunday planners.")
        
        try:
            bk_res = supabase.table("weekly_bookings").select("*").eq("location", sel_site).execute()
            if bk_res.data:
                bk_df = pd.DataFrame(bk_res.data)
                
                bk_df["Breakfast Club"] = bk_df["breakfast_club"].apply(lambda x: "✅ Yes" if x else "❌ No")
                bk_df["Afterschool"] = bk_df["afterschool"].apply(lambda x: "✅ Yes" if x else "❌ No")
                
                clean_bk = bk_df[["child_name", "day_of_week", "Breakfast Club", "Afterschool"]].rename(columns={"child_name": "Child Name", "day_of_week": "Scheduled Day"})
                st.dataframe(clean_bk, use_container_width=True)
                
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

    # --- REPORT 2: TODAY'S LIVE SIGN-IN MANIFEST ---
    with rep_tab2:
        today_date = str(datetime.now().date())
        st.subheader(f"⏱️ Live Daily Manifest: {sel_site} ({today_date})")
        st.caption("Real-time list of tracking entries logged today.")
        
        try:
            today_res = supabase.table("attendance").select("*").eq("location", sel_site).eq("date", today_date).execute()
            if today_res.data:
                td_df = pd.DataFrame(today_res.data)
                
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

    # --- NEW REPORT 3: WEEKLY ATTENDANCE SUMMARY ---
    with rep_tab3:
        st.subheader(f"📊 Total Attended Hours by Week: {sel_site}")
        st.caption("Calculates total completed hours attended per individual child grouped by calendar week numbers.")
        
        try:
            raw_att = supabase.table("attendance").select("*").eq("location", sel_site).is_not("check_out", "null").execute()
            
            if raw_att.data:
                all_att_df = pd.DataFrame(raw_att.data)
                
                # Convert log dates into manageable calendar week definitions
                all_att_df['parsed_date'] = pd.to_datetime(all_att_df['date'])
                all_att_df['Year-Week'] = all_att_df['parsed_date'].dt.strftime('%Y-W%V')
                
                # Double-check calculation values
                if 'hours' not in all_att_df.columns:
                    all_att_df['hours'] = all_att_df.apply(lambda r: ncs_round(r['check_in'], r['check_out']), axis=1)
                all_att_df['hours'] = all_att_df['hours'].fillna(0)
                
                # Pivot records into clean side-by-side calendar matrices
                weekly_pivot = all_att_df.pivot_table(
                    index='name', 
                    columns='Year-Week', 
                    values='hours', 
                    aggfunc='sum'
                ).fillna(0)
                
                st.dataframe(weekly_pivot, use_container_width=True)
                
                # Excel Exporter block
                buf_piv = io.BytesIO()
                with pd.ExcelWriter(buf_piv, engine='xlsxwriter') as wr:
                    weekly_pivot.to_excel(wr, sheet_name='Weekly Log Overview')
                st.download_button(
                    label="📥 Download Weekly Attendance Grid",
                    data=buf_piv.getvalue(),
                    file_name=f"weekly_attendance_totals_{sel_site}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.info("No completed logs available to construct tracking summaries.")
        except Exception as e:
            st.error(f"Could not calculate summary metrics: {e}")

    # --- NEW REPORT 4: UNUSED NCS HOURS AUDIT ---
    with rep_tab4:
        st.subheader(f"⚠️ Unused Allowed Hours Audit: {sel_site}")
        st.caption("Identifies children whose attended hours fall below their allocated claim limits for the current week.")
        
        try:
            kids_res = supabase.table("children").select("id", "name", "ncs_hours_allowed").eq("location", sel_site).execute()
            attendance_res = supabase.table("attendance").select("*").eq("location", sel_site).is_not("check_out", "null").execute()
            
            if kids_res.data:
                kids_df = pd.DataFrame(kids_res.data)
                att_df = pd.DataFrame(attendance_res.data) if attendance_res.data else pd.DataFrame()
                
                # Filter historical logs to isolate matching values for the current processing week
                if not att_df.empty:
                    att_df['parsed_date'] = pd.to_datetime(att_df['date'])
                    current_year_week = datetime.now().strftime('%Y-W%V')
                    att_df['Year-Week'] = att_df['parsed_date'].dt.strftime('%Y-W%V')
                    current_week_df = att_df[att_df['Year-Week'] == current_year_week].copy()
                else:
                    current_week_df = pd.DataFrame()

                audit_rows = []
                for _, kid in kids_df.iterrows():
                    c_name = kid['name']
                    allowed = kid.get('ncs_hours_allowed', 0) or 0
                    
                    # Compute hours consumed this week
                    if not current_week_df.empty:
                        kid_logs = current_week_df[current_week_df['name'] == c_name]
                        if 'hours' in kid_logs.columns:
                            used = kid_logs['hours'].sum()
                        else:
                            used = kid_logs.apply(lambda r: ncs_round(r['check_in'], r['check_out']), axis=1).sum()
                    else:
                        used = 0
                        
                    unused = max(0, allowed - used)
                    
                    # Log child profiles missing their targets
                    if unused > 0 and allowed > 0:
                        audit_rows.append({
                            "Child Name": c_name,
                            "NCS Profile Allocation (Hrs)": allowed,
                            "Actual Hours Logged This Week": used,
                            "Unused Allocation (Hrs)": unused,
                            "Operational Insight": f"Under-utilised by {unused} hours"
                        })
                
                if audit_rows:
                    audit_df = pd.DataFrame(audit_rows)
                    st.dataframe(audit_df, use_container_width=True, hide_index=True)
                    
                    # Excel Export
                    buf_aud = io.BytesIO()
                    with pd.ExcelWriter(buf_aud, engine='xlsxwriter') as wr:
                        audit_df.to_excel(wr, sheet_name='Under-Utilisation Audit', index=False)
                    st.download_button(
                        label="📥 Download Unused Hours Audit List",
                        data=buf_aud.getvalue(),
                        file_name=f"ncs_underutilisation_report_{sel_site}.xlsx",
                        mime="application/vnd.ms-excel"
                    )
                else:
                    st.success("✅ All children are fully utilising their allocated NCS hours frameworks this week!")
            else:
                st.info("No children configurations found to audit.")
        except Exception as e:
            st.error(f"Audit analysis pipeline error: {e}")

    # --- REPORT 5: HISTORICAL EXPORTS ---
    with rep_tab5:
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
# --- 8. ADMIN SETTINGS ---
elif page == "Admin Settings":
    st.title("⚙️ Site Administration")
    st.subheader("Edit Child NCS Care Framework Allocations")
    st.success("🔓 Open: Daily editing windows are active across all configurations.")
    
    try:
        children_res = supabase.table("children").select("*").eq("location", sel_site).execute()
        children_data = children_res.data
    except Exception as e:
        st.error(f"Error fetching roster records: {e}")
        children_data = []
        
    if not children_data:
        st.info("No records match your selected database location.")
    else:
        for child in children_data:
            child_id = child.get("id")
            child_name = child.get("name")
            current_allowed = child.get("ncs_hours_allowed", 0)
            if current_allowed is None:
                current_allowed = 0
                
            with st.container(border=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"👦 **{child_name}**")
                    st.caption(f"Configured Limit: **{current_allowed}** hours per week")
                with col2:
                    new_hours = st.number_input(
                        "Weekly NCS Limit",
                        min_value=0,
                        max_value=168,
                        value=int(current_allowed),
                        key=f"input_admin_ncs_{child_id}",
                        label_visibility="collapsed",
                        disabled=False
                    )
                    if new_hours != current_allowed:
                        if st.button("💾 Save", key=f"btn_save_ncs_{child_id}", type="primary", use_container_width=True):
                            try:
                                supabase.table("children").update({
                                    "ncs_hours_allowed": new_hours
                                }).eq("id", child_id).execute()
                                st.success(f"Saved update for {child_name}!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed database transaction: {e}")
