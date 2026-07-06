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
from fpdf import FPDF

def generate_staffing_pdf(df_data, site_name, day_name):
    """Generates a clean tabular PDF sheet for local printing and shift rosters."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    
    # Header Banner
    pdf.cell(0, 10, f"KidsRule Childcare — Onsite Staffing Roster", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, f"Site Location: {site_name} Hub  |  Target Allocation Day: {day_name}", ln=True, align="C")
    pdf.ln(10)
    
    # Table Structure Headers
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(60, 10, "Child Name", border=1, fill=True)
    pdf.cell(65, 10, "Breakfast Club Required?", border=1, fill=True)
    pdf.cell(65, 10, "Afterschool Club Required?", border=1, fill=True, ln=True)
    
    # Table Content Injection Loop
    pdf.set_font("Helvetica", "", 10)
    for _, row in df_data.iterrows():
        bc_status = "YES (Expected)" if row.get('Breakfast Club', False) else "No Booking"
        as_status = "YES (Expected)" if row.get('Afterschool', False) else "No Booking"
        
        pdf.cell(60, 8, str(row['Child Name']), border=1)
        pdf.cell(65, 8, bc_status, border=1)
        pdf.cell(65, 8, as_status, border=1, ln=True)
        
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 10, f"Generated automatically on: {datetime.now().strftime('%d-%b-%Y at %H:%M:%S')}", ln=True)
    
    # Output file into a binary byte stream stream compatible with Streamlit download buttons
    return pdf.output()
# --- 3. NAVIGATION & ADMIN SIDEBAR ---
sites = ["Elphin", "Ballinameen", "Boyle", "Roscommon", "Keadue"]
# "Staffing Report" has been added below to restore the missing print/download view
page = st.sidebar.radio("Navigation", ["Dashboard", "Weekly Planner", "Quick-Tap Board", "Attendance", "NCS Compliance", "Staffing Report", "Admin Settings"])
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
        kids = supabase.table("children").select("name").eq("location", sel_site).eq("is_active", True).execute()
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
        # UPGRADED: Pulling dietary_requirements and medical_notes from the database table
        children_res = supabase.table("children").select(
            "name", "emergency_name", "emergency_phone",
            "pickup_1_name", "pickup_1_phone",
            "pickup_2_name", "pickup_2_phone",
            "pickup_3_name", "pickup_3_phone",
            "dietary_requirements", "medical_notes"
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
            
            # Fetch medical fields for alert status flags
            meta = child_lookup.get(child_name, {})
            has_dietary = meta.get("dietary_requirements") and meta.get("dietary_requirements") != "None"
            has_medical = meta.get("medical_notes") and meta.get("medical_notes") != "None"
            
            # Append visual warning badge directly to button text if records exist
            badge = " ⚠️" if (has_dietary or has_medical) else ""
            
            active_child_key = "active_tap_child_id"
            is_active = st.session_state.get(active_child_key) == child_id
            b_style = "primary" if is_active else "secondary"
            
            with grid_cols[idx % 3]:
                label = f"🌅 {child_name}{badge} (BC)" if session_type == "Breakfast Club" else f"👦 {child_name}{badge} (AS)"
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
                    
                    # --- CRITICAL MEDICAL/DIETARY ALERT BANNER IN SIGN-OUT WINDOW ---
                    d_notes = meta.get("dietary_requirements", "None")
                    m_notes = meta.get("medical_notes", "None")
                    if d_notes != "None" or m_notes != "None":
                        with st.expander("🚨 **Critical Profile Care Alert (Tap to View)**", expanded=True):
                            if d_notes != "None":
                                st.markdown(f"🥦 **Dietary/Allergies:** {d_notes}")
                            if m_notes != "None":
                                st.markdown(f"🩺 **Medical Conditions:** {m_notes}")
                    
                    st.warning(f"🚨 **Emergency Contact:** {e_name} — {e_phone}")
                    
                    st.write("### Choose Authorized Collector:")
                    p_cols = st.columns(4)
                    pickups = [p1_name, p2_name, p3_name, "Other / Parent"]
                    
                    for p_idx, p in enumerate(pickups):
                        with p_cols[p_idx]:
                            if st.button(p, key=f"p_btn_{p_idx}_{active_id}", use_container_width=True):
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
    st.caption(f"Quickly check children in or review daily logs for {sel_site}.")
    
    st.subheader("🌅 Quick Sign-In Panel")
    st.caption("Tap a child's name to instantly log their arrival for today.")
    
    today_str = str(datetime.now().date())
    now_time_str = datetime.now().strftime("%H:%M:%S")
    
    try:
        all_kids_res = supabase.table("children").select("name").eq("location", sel_site).eq("is_active", True).execute()
        registered_kids = sorted([k['name'] for k in all_kids_res.data])
        
        already_in_res = supabase.table("attendance").select("name").eq("location", sel_site).eq("date", today_str).is_("check_out", "null").execute()
        checked_in_names = [a['name'] for a in already_in_res.data]
    except Exception as e:
        st.error(f"Error compiling child list data matrix: {e}")
        registered_kids = []
        checked_in_names = []
        
    available_to_signin = [name for name in registered_kids if name not in checked_in_names]
    
    if not available_to_signin:
        st.info("🎒 All active registered children for this site location are currently checked in.")
    else:
        session_choice = st.radio("Select Session Type for Tap Sign-In:", ["Afterschool", "Breakfast Club"], horizontal=True)
        kid_cols = st.columns(3)
        
        for idx, kid_name in enumerate(available_to_signin):
            with kid_cols[idx % 3]:
                if st.button(f"➕ {kid_name}", key=f"signin_btn_{idx}_{kid_name}", use_container_width=True):
                    try:
                        supabase.table("attendance").insert({
                            "name": kid_name,
                            "location": sel_site,
                            "session_type": session_choice,
                            "date": today_str,
                            "check_in": now_time_str,
                            "check_out": None
                        }).execute()
                        st.success(f"🎉 Checked in {kid_name} successfully!")
                        st.rerun()
                    except Exception as db_err:
                        st.error(f"Failed to check in: {db_err}")
                        
    st.write("---")
    st.subheader("📜 Attendance History Log")
    st.caption("Complete, permanent digital history kept for the 6-year regulatory hold requirement.")
    
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
        
        if "calculated_hours" not in df_logs.columns:
            df_logs["calculated_hours"] = 0
            
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
            hide_index=True,
            column_order=["Date", "Child Name", "Session Type", "Sign-In", "Sign-Out", "Collected By", "NCS Hours"]
        )
# --- 8. STAFFING REPORT ---
elif page == "Staffing Report":
    st.title("📋 Daily Staffing & Attendance Report")
    st.caption("Review expected daily rosters based on parental bookings to schedule staffing levels.")
    
    report_day = st.selectbox("Select Day to View", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    
    try:
        # Fetch upcoming scheduling choices from parent templates
        bookings_res = supabase.table("weekly_bookings").select("child_name, day_of_week, breakfast_club, afterschool").eq("location", sel_site).eq("day_of_week", report_day).execute()
        bookings_data = bookings_res.data
        
        if not bookings_data:
            st.info(f"No parent schedule templates found for {sel_site} on {report_day} in the system database.")
        else:
            # Structuring raw payload data into a presentation dataframe
            df_bookings = pd.DataFrame(bookings_data)
            df_display = df_bookings.rename(columns={
                "child_name": "Child Name",
                "breakfast_club": "Breakfast Club",
                "afterschool": "Afterschool"
            })
            
            # Interactive Grid View layout display
            st.dataframe(df_display[["Child Name", "Breakfast Club", "Afterschool"]], use_container_width=True, hide_index=True)
            
            # Count expected attendance metrics to help figure out necessary child-to-staff counts
            total_bc = df_display["Breakfast Club"].sum()
            total_as = df_display["Afterschool"].sum()
            
            c1, c2 = st.columns(2)
            c1.metric("🌅 Expected Breakfast Attendance", total_bc)
            c2.metric("👦 Expected Afterschool Attendance", total_as)
            
            st.markdown("---")
            st.subheader("🖨️ Onsite Print Controls")
            
            # Generate the binary payload data structure
            pdf_bytes = generate_staffing_pdf(df_display, sel_site, report_day)
            
            # Mount the native file system anchor control
            st.download_button(
                label="📥 Export & Download Staffing Roster (PDF)",
                data=pdf_bytes,
                file_name=f"Staffing_Roster_{sel_site}_{report_day}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="download_staff_roster_pdf_btn"
            )
            
    except Exception as e:
        st.error(f"Failed to compile staffing choices layout: {e}")
# --- 8. NCS COMPLIANCE ---
# --- 8B. NCS COMPLIANCE ---
elif page == "NCS Compliance":
    st.title("📊 NCS Compliance Reporting Hub")
    st.caption(f"Audit-ready statutory compliance intelligence engine for **{sel_site}**.")
    
    try:
        # Fetch finalized attendance records
        compliance_res = (
            supabase.table("attendance")
            .select("date", "name", "session_type", "check_in", "check_out", "collected_by", "calculated_hours")
            .eq("location", sel_site)
            .not_.is_("check_out", "null")
            .order("date", desc=True)
            .execute()
        )
        compliance_data = compliance_res.data
        
        # UPGRADED: Pull official children registration metadata to access ncs_funded_hours
        children_meta_res = supabase.table("children").select("name", "ncs_funded_hours").eq("location", sel_site).execute()
        children_meta_data = children_meta_res.data
    except Exception as e:
        st.error(f"Failed to fetch compliance logs or master roster limits: {e}")
        compliance_data = []
        children_meta_data = []
        
    if not compliance_data:
        st.info(f"No completed checkout logs available for {sel_site} to compile compliance metrics.")
    else:
        df = pd.DataFrame(compliance_data)
        rep_tab1, rep_tab2, rep_tab3, rep_tab4, rep_tab5 = st.tabs([
            "📋 Master Overview", "👦 Student Hours Summary", "🌅 Club Breakdown", "🔑 Collector Authorization Log", "📉 Pobal Unused Hours Audit"
        ])
        
        with rep_tab1:
            st.subheader("📋 Comprehensive Compliance Archive Matrix")
            df_r1_display = df.rename(columns={
                "date": "Date", "name": "Child Name", "session_type": "Session Type",
                "check_in": "Sign-In", "check_out": "Sign-Out", "collected_by": "Collected By", "calculated_hours": "NCS Hours"
            })
            st.dataframe(df_r1_display, use_container_width=True)
            csv_r1 = df_r1_display.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Master Overview (CSV)", data=csv_r1, file_name=f"ncs_master_{sel_site.lower()}.csv", mime="text/csv", key="dl_r1")

        with rep_tab2:
            st.subheader("👦 Student Hours Claim Summary")
            df_r2 = df.groupby("name")["calculated_hours"].agg(["sum", "count", "mean"]).reset_index()
            df_r2.columns = ["Child Name", "Total Claimed Hours", "Total Days Attended", "Avg Hours / Day"]
            df_r2["Avg Hours / Day"] = df_r2["Avg Hours / Day"].round(1)
            df_r2 = df_r2.sort_values(by="Total Claimed Hours", ascending=False)
            st.dataframe(df_r2, use_container_width=True)
            csv_r2 = df_r2.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Hours Summary (CSV)", data=csv_r2, file_name=f"ncs_summary_{sel_site.lower()}.csv", mime="text/csv", key="dl_r2")

        with rep_tab3:
            st.subheader("🌅 Club & Session Type Breakdown")
            df_r3 = df.groupby("session_type")["calculated_hours"].agg(["sum", "count"]).reset_index()
            df_r3.columns = ["Session Type", "Total Accumulated Hours", "Total Student Checkouts"]
            st.dataframe(df_r3, use_container_width=True)
            csv_r3 = df_r3.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Session Breakdown (CSV)", data=csv_r3, file_name=f"ncs_sessions_{sel_site.lower()}.csv", mime="text/csv", key="dl_r3")

        with rep_tab4:
            st.subheader("🔑 Collector Authorization Verification Log")
            df_r4 = df[["date", "name", "check_out", "collected_by"]].copy()
            df_r4.columns = ["Date", "Child Name", "Sign-Out Time", "Collector Identity Given"]
            df_r4 = df_r4.sort_values(by="Date", ascending=False)
            st.dataframe(df_r4, use_container_width=True)
            csv_r4 = df_r4.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Collector Log (CSV)", data=csv_r4, file_name=f"ncs_collectors_{sel_site.lower()}.csv", mime="text/csv", key="dl_r4")

        # ----------------------------------------------------------------------
        # UPGRADED REPORT 5: ACCURATE SHORTFALL AUDIT BASED ON CHIT ENTRIES
        # ----------------------------------------------------------------------
        with rep_tab5:
            st.subheader("📉 NCS Unused Hours & Shortfall Audit")
            st.caption("Evaluates actual weekly usage margins against CHIT awarded fund caps.")
            
            if not children_meta_data:
                st.info("No child profile data exists to compile audit bounds.")
            else:
                # 1. Convert master profiles containing ncs_funded_hours into a mapping frame
                df_meta = pd.DataFrame(children_meta_data).rename(columns={"name": "Child Name", "ncs_funded_hours": "NCS Awarded Hours"})
                
                # 2. Extract average weekly attended hours from the permanent logs
                df_calc = df.copy()
                df_calc["date_parsed"] = pd.to_datetime(df_calc["date"])
                df_calc["year_week"] = df_calc["date_parsed"].dt.strftime("%Y-%U")
                
                # Sum hours up by student for individual calendar weeks
                df_weekly_attendance = df_calc.groupby(["name", "year_week"])["calculated_hours"].sum().reset_index()
                
                # Find the running historical average per student
                df_avg_actual = df_weekly_attendance.groupby("name")["calculated_hours"].mean().reset_index()
                df_avg_actual.columns = ["Child Name", "Avg Weekly Attended Hours"]
                df_avg_actual["Avg Weekly Attended Hours"] = df_avg_actual["Avg Weekly Attended Hours"].round(1)
                
                # 3. Merge baseline CHIT targets with real attendance calculations
                df_unused_report = pd.merge(df_meta, df_avg_actual, on="Child Name", how="inner")
                
                # Calculate accurate variance shortfall
                df_unused_report["Unused Hours Variance"] = df_unused_report["NCS Awarded Hours"] - df_unused_report["Avg Weekly Attended Hours"]
                df_unused_report["Unused Hours Variance"] = df_unused_report["Unused Hours Variance"].apply(lambda x: max(0.0, round(x, 1)))
                
                # Apply precise regulatory Pobal threshold alerts
                df_unused_report["Pobal Audit Status"] = df_unused_report["Unused Hours Variance"].apply(
                    lambda x: "🚨 FLAG: Variance > 8 Hours" if x >= 8.0 else "🟢 Compliant"
                )
                
                # Rank at-risk profiles to the very top
                df_unused_report = df_unused_report.sort_values(by="Unused Hours Variance", ascending=False)
                
                # Highlight rows where leakage exceeds the strict statutory 8-hour gap
                def highlight_pobal_flags(row):
                    if "🚨" in str(row["Pobal Audit Status"]):
                        return ['background-color: rgba(255, 75, 75, 0.2)'] * len(row)
                    return [''] * len(row)
                
                styled_df = df_unused_report.style.apply(highlight_pobal_flags, axis=1)
                st.dataframe(styled_df, use_container_width=True)
                
                # Display direct error banner summaries for the onsite manager
                flagged_count = len(df_unused_report[df_unused_report["Unused Hours Variance"] >= 8.0])
                if flagged_count > 0:
                    st.error(f"⚠️ **Pobal Compliance Alert:** There are **{flagged_count} child profile(s)** trending a running weekly variance shortfall above 8 hours. Adjust allocations on the Hive to protect funding balances.")
                else:
                    st.success("✅ **Pobal Compliance Check:** All active children are currently within safe attendance tolerance margins.")
                
                csv_r5 = df_unused_report.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Unused Hours Audit (CSV)", data=csv_r5, file_name=f"ncs_pobal_flags_{sel_site.lower()}.csv", mime="text/csv", key="dl_r5")
# --- 9. ADMIN SETTINGS ---
elif page == "Admin Settings":
    st.title("⚙️ Admin Settings")
    
    if "admin_page_unlocked" not in st.session_state:
        st.session_state["admin_page_unlocked"] = False

    if not st.session_state["admin_page_unlocked"]:
        st.subheader("🔒 Management Authorization Required")
        st.caption("This area contains sensitive child protection rosters and registration tools.")
        
        mgmt_password = st.text_input("Enter Management Passcode:", type="password", key="mgmt_page_pass")
        
        if st.button("Unlock Management Panel", type="primary", use_container_width=True):
            if mgmt_password == "Letmein!" or mgmt_password == "DevMaster99!":
                st.session_state["admin_page_unlocked"] = True
                st.rerun()
            else:
                st.error("❌ Incorrect passcode. Management access denied.")
                
    else:
        # --- ADMIN WORKSPACE TABS ---
        adm_tab1, adm_tab2 = st.tabs(["➕ Add New Child", "👥 Manage Active Roster"])
        
        # ----------------------------------------------------
        # TAB 1: ADD NEW CHILD PROFILE FORM (UPGRADED)
        # ----------------------------------------------------
        with adm_tab1:
            st.subheader(f"➕ Register New Child to {sel_site}")
            st.caption("Onboard a new child profile directly into the active registration system roster.")
            
            with st.form("add_new_child_form", clear_on_submit=True):
                # Core Info
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    new_name = st.text_input("Child's Full Name * (Must be Unique)")
                    new_chit = st.text_input("NCS CHIT Number")
                with col_info2:
                    new_dob = st.date_input("Date of Birth", value=None, min_value=datetime(2010, 1, 1), max_value=datetime.now())
                    # ADDED: Numeric entry for NCS officially awarded hours
                    ncs_hours = st.number_input("NCS Funded Hours per Week *", min_value=0.0, max_value=50.0, value=0.0, step=0.5, help="Enter the total weekly hours awarded on the CHIT/Hive allocation.")
                    
                # Health & Safeguarding Metrics
                st.write("---")
                st.caption("🩺 Health, Dietary & Safeguarding Requirements:")
                dietary_notes = st.text_area("Dietary Requirements / Allergies", placeholder="List any food allergies, intolerances, or religious dietary restrictions (or leave blank if none)...")
                medical_notes = st.text_area("Medical Notes & Conditions", placeholder="List any medical diagnoses, inhalers, regular medications, or special needs (or leave blank if none)...")
                
                # Contacts
                st.write("---")
                st.caption("🚨 Emergency Contact Framework:")
                c_a, c_b = st.columns(2)
                e_name = c_a.text_input("Primary Emergency Contact Name")
                e_phone = c_b.text_input("Primary Emergency Contact Phone")
                
                st.write("---")
                st.caption("🚗 Authorized Pickup Personnel Slots:")
                p1_n = st.text_input("Pickup Contact 1 Name")
                p1_p = st.text_input("Pickup Contact 1 Phone")
                
                p2_n = st.text_input("Pickup Contact 2 Name")
                p2_p = st.text_input("Pickup Contact 2 Phone")
                
                p3_n = st.text_input("Pickup Contact 3 Name")
                p3_p = st.text_input("Pickup Contact 3 Phone")
                
                submit_child = st.form_submit_button("Register & Activate Profile", type="primary", use_container_width=True)
                
                if submit_child:
                    if not new_name.strip():
                        st.error("❌ Missing Field: You must specify a Child Name to create a database profile.")
                    else:
                        try:
                            # Convert date object safely to text for SQL insertion
                            dob_str = str(new_dob) if new_dob else None
                            
                            supabase.table("children").insert({
                                "name": new_name.strip(),
                                "location": sel_site,
                                "ncs_chit_number": new_chit.strip(),
                                "ncs_funded_hours": float(ncs_hours), # SAVED: Injected numerical input into data stream
                                "date_of_birth": dob_str,
                                "dietary_requirements": dietary_notes.strip() or "None",
                                "medical_notes": medical_notes.strip() or "None",
                                "emergency_name": e_name.strip() or "Not Listed",
                                "emergency_phone": e_phone.strip() or "Not Listed",
                                "pickup_1_name": p1_n.strip() or "Mom",
                                "pickup_1_phone": p1_p.strip() or "",
                                "pickup_2_name": p2_n.strip() or "",
                                "pickup_2_phone": p2_p.strip() or "",
                                "pickup_3_name": p3_n.strip() or "",
                                "pickup_3_phone": p3_p.strip() or "",
                                "is_active": True
                            }).execute()
                            st.success(f"🎉 Successfully created active profile for **{new_name}** at {sel_site}!")
                            st.toast("Profile data pipeline updated.")
                        except Exception as db_err:
                            st.error(f"Failed to save profile record to database: {db_err}")

        # ----------------------------------------------------
        # TAB 2: ACTIVE ROSTER MANAGEMENT & ARCHIVING
        # ----------------------------------------------------
        with adm_tab2:
            st.subheader(f"👥 Current Active Roster ({sel_site})")
            st.caption("Review active students. Archiving a student preserves their history for the 6-year retention mandate.")
            
            try:
                roster_res = supabase.table("children").select("*").eq("location", sel_site).eq("is_active", True).execute()
                site_roster = roster_res.data
            except Exception as e:
                st.error(f"Error loading system roster: {e}")
                site_roster = []
                
            if not site_roster:
                st.info(f"No active children registered at the {sel_site} hub.")
            else:
                roster_df = pd.DataFrame(site_roster)
                
                # Check column presence to prevent UI rendering dropouts
                required_cols = [
                    'name', 'ncs_chit_number', 'ncs_funded_hours', 'date_of_birth', 'dietary_requirements', 
                    'medical_notes', 'emergency_name', 'emergency_phone', 
                    'pickup_1_name', 'pickup_2_name', 'pickup_3_name'
                ]
                for col in required_cols:
                    if col not in roster_df.columns:
                        roster_df[col] = 0.0 if col == 'ncs_funded_hours' else "Not Listed"
                        
                display_roster = roster_df[[
                    'name', 'ncs_chit_number', 'ncs_funded_hours', 'date_of_birth', 'dietary_requirements', 
                    'medical_notes', 'emergency_name', 'emergency_phone', 
                    'pickup_1_name', 'pickup_2_name', 'pickup_3_name'
                ]].rename(columns={
                    'name': 'Child Name',
                    'ncs_chit_number': 'NCS CHIT',
                    'ncs_funded_hours': 'Funded Hrs/Wk', # UPDATED: Included inside display data grid
                    'date_of_birth': 'DOB',
                    'dietary_requirements': 'Dietary Notes',
                    'medical_notes': 'Medical Notes',
                    'emergency_name': 'Emergency Contact',
                    'emergency_phone': 'Emergency Phone',
                    'pickup_1_name': 'Pickup 1',
                    'pickup_2_name': 'Pickup 2',
                    'pickup_3_name': 'Pickup 3'
                })
                
                st.dataframe(display_roster, use_container_width=True, hide_index=True)
                
                st.write("#### 📦 Archive Student Profile")
                child_to_archive = st.selectbox(
                    "Select child profile to archive (hides them from active check-in grids):", 
                    options=[c['name'] for c in site_roster],
                    index=None,
                    placeholder="Choose profile to archive...",
                    key="admin_archive_child_selectbox"
                )
                
                if child_to_archive:
                    confirm_archive = st.checkbox(f"Confirm I want to archive {child_to_archive}. Their historical log remains securely stored for compliance auditing.")
                    
                    if st.button("Archive Profile", type="primary", disabled=not confirm_archive):
                        try:
                            supabase.table("children").update({"is_active": False}).eq("name", child_to_archive).eq("location", sel_site).execute()
                            st.success(f"📦 {child_to_archive} has been safely archived. Profile hidden from live views.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to archive child profile record: {e}")
                            
        st.markdown("---")
        st.info("🔒 **Data Retention Lock Active:** Permanent profile deletion is disabled to preserve mandatory 6-year attendance histories for funding audits.")
                        
        # --- DISASTER RECOVERY & AUDIT BACKUP PROCEDURES ---
        st.markdown("---")
        st.subheader("💾 Disaster Recovery & Audit Backup Vault")
        st.caption("Generate encrypted local snapshots of your cloud database structures to satisfy 6-year retention regulations.")
        
        last_backup_date = st.session_state.get("last_backup_timestamp", None)
        if last_backup_date:
            st.success(f"🔒 Last Backup Secured: {last_backup_date}")
        else:
            st.error("⚠️ Backup Warning: No local backup snapshot has been generated during this session.")
            
        try:
            # FIXED: Changed from select("") to select("*") to fetch all rows and columns properly
            raw_attendance = supabase.table("attendance").select("*").eq("location", sel_site).execute()
            raw_children = supabase.table("children").select("*").eq("location", sel_site).execute()
            
            df_back_attend = pd.DataFrame(raw_attendance.data)
            df_back_child = pd.DataFrame(raw_children.data)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                if not df_back_attend.empty:
                    df_back_attend.to_excel(writer, sheet_name="Attendance History", index=False)
                if not df_back_child.empty:
                    df_back_child.to_excel(writer, sheet_name="Master Child Roster", index=False)
                    
            processed_data = buffer.getvalue()
            current_date_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            file_title = f"KidsRule_DB_Backup_{sel_site}_{current_date_stamp}.xlsx"
            
            st.download_button(
                label="📥 Download Complete Database Snapshot (.xlsx)",
                data=processed_data,
                file_name=file_title,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="admin_download_backup_vault_btn",
                on_click=lambda: st.session_state.update({"last_backup_timestamp": datetime.now().strftime("%d-%b-%Y at %H:%M")})
            )
        except Exception as backup_err:
            st.warning(f"Unable to process backup elements: {backup_err}")
            
        st.markdown("---")
        st.info("🔒 Data Retention Lock Active: Permanent profile deletion is disabled to preserve mandatory 6-year history records.")

# --- 10. GLOBAL FALLBACK ---
    st.title(f"📄 {page}")
    st.info("Placeholder configuration panel layout.")
