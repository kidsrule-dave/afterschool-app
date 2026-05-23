import streamlit as st
import pandas as pd
import math
import io
from datetime import datetime
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas

# --- 1. SECURE CONNECTION ---
# Replace these with your real project API credentials from your Supabase settings!
SUPABASE_URL = "https://supabase.co"
SUPABASE_KEY = "sb_publishable_HFSxcJjKT8c0M1_UoFLznA_J6HzGbdm"

# Programmatically strip trailing slashes to prevent connection errors
clean_url = SUPABASE_URL.strip().rstrip("/")
supabase: Client = create_client(clean_url, SUPABASE_KEY)

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
        kids_res = supabase.table("attendance").select("id", count="exact").eq("date", today).eq("location", sel_site).is_("check_out", "null").execute()
        kids_in = kids_res.count if kids_res.count else 0
    except:
        kids_in = 0
        
    st.metric("Children Present Today", kids_in)

# --- 5. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Sign-Out")
    st.caption("Tap a child's name to select who is collecting them.")
    
    try:
        # 1. Fetch children registered to this site
        children_res = supabase.table("children").select("name").eq("location", sel_site).execute()
        site_child_names = [c['name'] for c in children_res.data]
        
        # 2. Fetch active logs (children present who haven't checked out yet)
        active_res = supabase.table("attendance").select("*").is_("check_out", "null").execute()
        site_logs = [a for a in active_res.data if a['name'] in site_child_names]
    except Exception as e:
        st.error(f"Database Error: {e}")
        site_logs = []

    if not site_logs:
        st.info(f"No children currently checked in at {sel_site}.")
    else:
        st.write("### 👤 Children Present")
        grid_cols = st.columns(3)
        
        for idx, log in enumerate(site_logs):
            child_id = log['id']
            child_name = log['name']
            
            active_child_key = "active_tap_child_id"
            is_active = st.session_state.get(active_child_key) == child_id
            b_style = "primary" if is_active else "secondary"
            
            with grid_cols[idx % 3]:
                if st.button(f"👦 {child_name}", key=f"name_btn_{child_id}", type=b_style, use_container_width=True):
                    st.session_state[active_child_key] = child_id
                    st.rerun()

        st.divider()

        # Show collector selection panel for the selected child
        active_id = st.session_state.get("active_tap_child_id")
        
        if active_id:
            selected_log = next((l for l in site_logs if l['id'] == active_id), None)
            
            if selected_log:
                c_key = f"coll_{active_id}"
                current_collector = st.session_state.get(c_key)
                
                with st.container(border=True):
                    st.subheader(f"🔑 Sign-Out: {selected_log['name']}")
                    st.write(f"🎒 *In since {selected_log['check_in']}*")
                    st.write("---")
                    st.write("**Who is collecting them?**")
                    
                    collectors = ["Mom", "Dad", "Nan", "Grandad", "Aunty", "Uncle", "Brother", "Sister"]
                    coll_cols = st.columns(4)
                    
                    for i, p in enumerate(collectors):
                        p_style = "primary" if current_collector == p else "secondary"
                        if coll_cols[i % 4].button(p, key=f"q_tap_p_{p}_{active_id}", type=p_style, use_container_width=True):
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

# --- 6. ATTENDANCE & SIGN-OUT ---
elif page == "Attendance":
    st.title("📍 Daily Log")
    tab1, tab2 = st.tabs(["🚌 Arrivals (Quick-Sign In)", "👤 Departures (Sign Out)"])
    
    with tab1:
        st.subheader("🚌 Select Sign-In Track")
        mode_toggle = st.radio("Arrival Mode", ["On-Site Walk-In", "School Bus Collection Roster"], horizontal=True)
        today_str = str(datetime.now().date())
        current_day_name = datetime.now().strftime("%A")

        # --- OPTION A: STANDARD ON-SITE TOUCHSCREEN CHECK-IN ---
        if mode_toggle == "On-Site Walk-In":
            try:
                kids = supabase.table("children").select("name").eq("location", sel_site).execute()
                all_names = sorted([k['name'] for k in kids.data])
                active_res = supabase.table("attendance").select("name").eq("date", today_str).eq("location", sel_site).is_("check_out", "null").execute()
                already_in = [a['name'] for a in active_res.data]
            except Exception as e:
                st.error(f"Error loading roster: {e}")
                all_names, already_in = [], []

            if all_names:
                arr_cols = st.columns(3)
                for idx, child_name in enumerate(all_names):
                    with arr_cols[idx % 3]:
                        if child_name in already_in:
                            st.button(f"✅ {child_name} (IN)", key=f"std_in_{idx}", disabled=True, use_container_width=True)
                        else:
                            if st.button(f"➕ {child_name}", key=f"std_btn_{idx}", type="secondary", use_container_width=True):
                                supabase.table("attendance").insert({
                                    "name": child_name, "location": sel_site, "date": today_str,
                                    "check_in": datetime.now().strftime("%H:%M:%S"), "check_in_method": "Walk-In"
                                }).execute()
                                st.rerun()
            else:
                st.info("No children registered at this site yet. Go to Admin Settings to register them.")

        # --- OPTION B: BUS ATTENDANCE DRIVER MODE ---
        elif mode_toggle == "School Bus Collection Roster":
            st.info(f"📅 Active Route Schedule: **{current_day_name}** | Base Hub Target: **{sel_site}**")
            
            try:
                kids_res = supabase.table("children").select("name", "school", "collection_days").eq("location", sel_site).execute()
                todays_bus_kids = [k for k in kids_res.data if current_day_name in k.get('collection_days', [])]
                schools_on_route = sorted(list(set([k['school'] for k in todays_bus_kids])))
                
                active_res = supabase.table("attendance").select("name").eq("date", today_str).eq("location", sel_site).is_("check_out", "null").execute()
                already_in = [a['name'] for a in active_res.data]
            except Exception as e:
                st.error(f"Transport database lookup failed: {e}")
                todays_bus_kids, schools_on_route, already_in = [], [], []

            if not schools_on_route:
                st.warning(f"No children are booked onto a bus collection route for {sel_site} on {current_day_name}s.")
            else:
                selected_pickup_school = st.selectbox("Select School Collection Point", schools_on_route)
                school_roster = [k for k in todays_bus_kids if k['school'] == selected_pickup_school]
                
                st.write(f"### 📋 Roster Checklist for {selected_pickup_school}")
                
                school_names = [k['name'] for k in school_roster]
                collected_count = sum(1 for name in school_names if name in already_in)
                total_count = len(school_names)
                
                st.progress(collected_count / total_count if total_count > 0 else 0.0)
                st.caption(f"🚌 Collected status: **{collected_count} of {total_count} children** safely boarded.")

                bus_cols = st.columns(2)
                for i, child_data in enumerate(school_roster):
                    c_name = child_data['name']
                    with bus_cols[i % 2]:
                        if c_name in already_in:
# --- 6b. NCS COMPLIANCE & REPORTS MANAGEMENT ---
    elif page == "NCS Compliance":
    st.title("🇪🇺 NCS Compliance & Attendance Reports")
    st.caption("Aligned with Pobal & Early Years Hive Guidelines for Pobal Visit Officer (VO) Inspections.")
    
    try:
        kids_res = supabase.table("children").select("name", "location").eq("location", sel_site).execute()
        site_kids = sorted([k['name'] for k in kids_res.data])
    except Exception as e:
        st.error(f"Error loading children data: {e}")
        site_kids = []

    if not site_kids:
        st.info(f"No children registered at {sel_site} yet.")
    else:
        if "reg_hours" not in st.session_state:
            st.session_state.reg_hours = {name: 20 for name in site_kids}
            
        col1, col2 = st.columns(2)
        with col1:
            target_child = st.selectbox("Select Child to Adjust Hive CHICK Registration", site_kids)
        with col2:
            st.session_state.reg_hours[target_child] = st.number_input(
                "Registered Weekly Hours", 
                min_value=0, max_value=45, value=st.session_state.reg_hours.get(target_child, 20)
            )

        st.divider()

        st.subheader("📊 Step 2: Choose Report Configuration")
        report_type = st.radio("Select Report Interval", ["Weekly Hive Audit", "Monthly Attendance Summary"], horizontal=True)

        # --- CONFIGURATION A: WEEKLY HIVE AUDIT REPORT ---
        if report_type == "Weekly Hive Audit":
            selected_week_start = st.date_input("Select Week Start Date (Monday)", value=datetime.now().date())
            week_days = [str(selected_week_start + pd.Timedelta(days=i)) for i in range(5)]
            
            if st.button("Calculate Weekly Compliance & Hive Returns", type="primary", use_container_width=True):
                try:
                    att_res = supabase.table("attendance").select("*").in_("date", week_days).execute()
                    att_data = att_res.data
                    
                    compliance_report = []
                    for child_name in site_kids:
                        child_logs = [log for log in att_data if log['name'] == child_name]
                        
                        total_actual_hours = 0.0
                        total_ncs_rounded_hours = 0
                        days_attended = 0
                        
                        for log in child_logs:
                            if log['check_in'] and log['check_out']:
                                days_attended += 1
                                fmt = "%H:%M:%S"
                                start = datetime.strptime(log['check_in'], fmt)
                                end = datetime.strptime(log['check_out'], fmt)
                                
                                duration_hours = (end - start).total_seconds() / 3600
                                total_actual_hours += duration_hours
                                total_ncs_rounded_hours += math.ceil(duration_hours)
                        
                        registered_hours = st.session_state.reg_hours.get(child_name, 20)
                        hours_to_claim = min(total_ncs_rounded_hours, registered_hours)
                        under_attending = total_ncs_rounded_hours < registered_hours
                        variance = registered_hours - total_ncs_rounded_hours if under_attending else 0
                        
                        compliance_report.append({
                            "Child": child_name,
                            "Days Present": days_attended,
                            "Actual Active Hours": round(total_actual_hours, 2),
                            "Daily Rounded Total": total_ncs_rounded_hours,
                            "Hive CHICK Cap": registered_hours,
                            "Claimable Hive Hours": hours_to_claim,
                            "Under-Attendance Flag": "⚠️ Under-Attending" if under_attending else "✅ Compliant",
                            "Variance (Hours Lost)": variance
                        })
                    
                    if compliance_report:
                        df_comp = pd.DataFrame(compliance_report)
                        st.session_state["last_weekly_report"] = df_comp
                        st.session_state["last_weekly_date"] = str(selected_week_start)
                    else:
                        st.info("No logs encountered for any child tracking against this targeted week.")
                except Exception as e:
                    st.error(f"Could not calculate weekly totals: {e}")

            if "last_weekly_report" in st.session_state:
                df_w = st.session_state["last_weekly_report"]
                w_date = st.session_state["last_weekly_date"]
                
                st.write(f"### 📅 Live Weekly Audit Grid: Week of {w_date}")
                st.dataframe(
                    df_w.style.map(
                        lambda x: "background-color: #ffcccc; color: black;" if x == "⚠️ Under-Attending" else "",
                        subset=["Under-Attendance Flag"]
                    ),
                    use_container_width=True
                )
                
                clean_filename = f"Weekly_NCS_Return_{sel_site}_Week_{w_date}.xlsx"
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                    df_w.to_excel(writer, sheet_name="Hive Weekly Return", index=False)
                    ex_df = df_w[df_w["Under-Attendance Flag"] == "⚠️ Under-Attending"]
                    if ex_df.empty:
                        ex_df = pd.DataFrame([{"Status": "All records completely compliant."}])
                    ex_df.to_excel(writer, sheet_name="Under-Attendance Warnings", index=False)

                st.download_button(
                    label=f"💾 Download {clean_filename}",
                    data=buffer.getvalue(),
                    file_name=clean_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

        # --- CONFIGURATION B: MONTHLY ATTENDANCE SUMMARY REPORT ---
        elif report_type == "Monthly Attendance Summary":
            col_m, col_y = st.columns(2)
            with col_m:
                months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
                selected_month_name = st.selectbox("Select Month", months, index=datetime.now().month - 1)
                month_idx = months.index(selected_month_name) + 1
            with col_y:
                selected_year = st.selectbox("Select Year", ["2025", "2026", "2027", "2028"], index=1)

            if st.button("Generate Monthly Attendance Report", type="primary", use_container_width=True):
                try:
                    start_date = f"{selected_year}-{str(month_idx).zfill(2)}-01"
                    end_date = str((pd.to_datetime(start_date) + pd.offsets.MonthEnd(0)).date())
                    
                    att_res = supabase.table("attendance").select("*")\
                        .gte("date", start_date)\
                        .lte("date", end_date)\
                        .execute()
                    
                    att_data = att_res.data
                    
                    monthly_report = []
                    for child_name in site_kids:
                        child_logs = [log for log in att_data if log['name'] == child_name]
                        
                        total_hours_monthly = 0.0
                        days_attended_monthly = 0
                        collector_breakdown = []
                        
                        for log in child_logs:
                            if log['check_in'] and log['check_out']:
                                days_attended_monthly += 1
                                fmt = "%H:%M:%S"
                                start = datetime.strptime(log['check_in'], fmt)
                                end = datetime.strptime(log['check_out'], fmt)
                                duration_hours = (end - start).total_seconds() / 3600
                                total_hours_monthly += duration_hours
                                
                                if log.get('collected_by'):
                                    collector_breakdown.append(log['collected_by'])
                        
                        frequent_collector = max(set(collector_breakdown), key=collector_breakdown.count) if collector_breakdown else "N/A"
                        
                        monthly_report.append({
                            "Child Name": child_name,
                            "Days Attended This Month": days_attended_monthly,
                            "Total Raw Hours Logged": round(total_hours_monthly, 2),
                            "Average Hours Per Day": round(total_hours_monthly / days_attended_monthly, 2) if days_attended_monthly > 0 else 0,
                            "Primary Collector": frequent_collector
                        })
                    
                    if monthly_report:
                        df_m = pd.DataFrame(monthly_report)
                        st.session_state["last_monthly_report"] = df_m
                        st.session_state["last_monthly_meta"] = f"{selected_month_name}_{selected_year}"
                    else:
                        st.info(f"No records found in the system for {selected_month_name} {selected_year}.")
                
                except Exception as e:
                    st.error(f"Could not calculate monthly totals: {e}")

            if "last_monthly_report" in st.session_state:
                df_m = st.session_state["last_monthly_report"]                            
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
                df['collected_by'] = "N/A"
            if 'hours' not in df.columns:
                df['hours'] = 0
                
            df = df[["name", "check_in", "check_out", "collected_by", "hours"]]
            df.columns = ["Child Name", "Sign In Time", "Sign Out Time", "Collected By", "Total Hours Calculated"]
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No attendance records match this location for the selected date.")
            
    except Exception as e:
        st.error(f"Error compiling report data: {e}")
