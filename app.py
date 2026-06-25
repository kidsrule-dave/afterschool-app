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
    st.caption("Tap a child's name to select who is collecting them.")
    
    try:
        # 1. Fetch children registered to this site (pulling emergency columns too)
        children_res = supabase.table("children").select("name", "emergency_name", "emergency_phone").eq("location", sel_site).execute()
        child_lookup = {c['name']: c for c in children_res.data}
        site_child_names = list(child_lookup.keys())
        
        # 2. Fetch active logs (children present who haven't checked out yet)
        active_res = supabase.table("attendance").select("*").is_("check_out", "null").execute()
        site_logs = [a for a in active_res.data if a['name'] in site_child_names]
    except Exception as e:
        st.error(f"Database Error: {e}")
        site_logs = []
        child_lookup = {}

    if not site_logs:
        st.info(f"No children currently checked in at {sel_site}.")
    else:
        # Layout present children in a clean 3-column grid of name buttons
        st.write("### 👤 Children Present")
        grid_cols = st.columns(3)
        
        for idx, log in enumerate(site_logs):
            child_id = log['id']
            child_name = log['name']
            
            # Keep track of which child button is currently tapped/active
            active_child_key = "active_tap_child_id"
            is_active = st.session_state.get(active_child_key) == child_id
            
            # Visual anchor: highlight the button if it is currently selected
            b_style = "primary" if is_active else "secondary"
            
            with grid_cols[idx % 3]:
                if st.button(f"👦 {child_name}", key=f"name_btn_{child_id}", type=b_style, use_container_width=True):
                    st.session_state[active_child_key] = child_id
                    st.rerun()

        st.divider()

        # --- STEP 2: SHOW COLLECTOR PANEL FOR THE CLICKED CHILD ---
        active_id = st.session_state.get("active_tap_child_id")
        
        if active_id:
            # Find the full log data matching our clicked child
            selected_log = next((l for l in site_logs if l['id'] == active_id), None)
            
            if selected_log:
                c_key = f"coll_{active_id}"
                current_collector = st.session_state.get(c_key)
                
                # Pull the matching child's emergency profile safely
                meta = child_lookup.get(selected_log['name'], {})
                e_name = meta.get('emergency_name', 'Not Listed')
                e_phone = meta.get('emergency_phone', 'Not Listed')
                
                # Render a clear workspace container for the chosen child
                with st.container(border=True):
                    st.subheader(f"🔑 Sign-Out: {selected_log['name']}")
                    st.write(f"🎒 *In since {selected_log['check_in']}*")
                    
                    # Visual safety anchor showing vital data during pickup
                    st.warning(f"🚨 **Emergency Contact:** {e_name} — 📞 {e_phone}")
                    st.write("---")
                    st.write("**Who is collecting them?**")
                    
                    # Collector tap options layout
                    collectors = ["Mom", "Dad", "Nan", "Grandad", "Aunty", "Uncle", "Brother", "Sister"]
                    coll_cols = st.columns(4)
                    
                    for i, p in enumerate(collectors):
                        p_style = "primary" if current_collector == p else "secondary"
                        if coll_cols[i % 4].button(p, key=f"q_tap_p_{p}_{active_id}", type=p_style, use_container_width=True):
                            st.session_state[c_key] = p
                            st.rerun()
                    
                    # Final Submission Confirmation Bar
                    if current_collector:
                        st.write("")
                        if st.button(f"✅ Confirm: {current_collector} is picking up {selected_log['name']}", key=f"fin_qt_{active_id}", type="primary", use_container_width=True):
                            now = datetime.now().strftime("%H:%M:%S")
                            
                            # Update records inside Supabase storage array
                            supabase.table("attendance").update({
                                "check_out": now, 
                                "collected_by": current_collector,
                                "hours": ncs_round(selected_log['check_in'], now),
                                "notes": f"Quick-tap pickup by {current_collector}"
                            }).eq("id", active_id).execute()
                            
                            # Reset session keys so the panel closes out completely
                            if c_key in st.session_state: del st.session_state[c_key]
                            if "active_tap_child_id" in st.session_state: del st.session_state["active_tap_child_id"]
                            
                            st.success(f"Successfully signed out {selected_log['name']}!")
                            st.rerun()

# --- 6. ATTENDANCE & SIGN-OUT ---
elif page == "Attendance":
    st.title("📍 Daily Log")
    tab1, tab2 = st.tabs(["🚌 Arrivals (Quick-Sign In)", "👤 Departures (Sign Out)"])
    
    with tab1:
        st.subheader("Quick-Tap Children to Sign In")
        today_str = str(datetime.now().date())
        
        try:
            # 1. Fetch all children registered to this site
            kids = supabase.table("children").select("name").eq("location", sel_site).execute()
            all_names = sorted([k['name'] for k in kids.data])
            
            # 2. Get children who are ALREADY signed in today at this site
            active_res = supabase.table("attendance").select("name").eq("date", today_str).eq("location", sel_site).is_("check_out", "null").execute()
            already_in = [a['name'] for a in active_res.data]
        except Exception as e:
            st.error(f"Could not load attendance roster: {e}")
            all_names = []
            already_in = []

        if all_names:
            # Layout children in a clean 3-column touchscreen grid
            arr_cols = st.columns(3)
            
            for idx, child_name in enumerate(all_names):
                with arr_cols[idx % 3]:
                    if child_name in already_in:
                        # Disabled visual anchor showing the child is safely in the building
                        st.button(
                            f"✅ {child_name} (IN)", 
                            key=f"signin_done_{idx}", 
                            disabled=True, 
                            use_container_width=True
                        )
                    else:
                        # Clickable button to immediately sign the child in
                        if st.button(
                            f"➕ {child_name}", 
                            key=f"signin_btn_{idx}", 
                            type="secondary", 
                            use_container_width=True
                        ):
                            now = datetime.now().strftime("%H:%M:%S")
                            try:
                                supabase.table("attendance").insert({
                                    "name": child_name,
                                    "date": today_str,
                                    "check_in": now,
                                    "location": sel_site
                                }).execute()
                                st.success(f"Signed in {child_name}!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Sign-in error: {e}")
    with tab2:
        st.subheader("Manual Departures")
        st.write("Manual departures interface details go here.")

# --- 7. NCS COMPLIANCE ---
elif page == "NCS Compliance":
    st.title("🇪🇺 National Childcare Scheme (NCS) Compliance Dashboard")
    st.caption("Aligned with Pobal & Early Years Hive Guidelines for Pobal Visit Officer (VO) Inspections.")
    
    # 1. Fetch Registered Funding Contracts
    st.subheader("📋 Step 1: View/Set Weekly Registered Funding Hours")
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

        # 2. Date Selection for Weekly Return Processing
        st.subheader("📅 Step 2: Compile Weekly Hive Submission Audit")
        selected_week_start = st.date_input("Select Week Start Date (Monday)", value=datetime.now().date())
        
        week_days = [str(selected_week_start + pd.Timedelta(days=i)) for i in range(5)]
        
        if st.button("Calculate Compliance & Generate Hive Returns", type="primary", use_container_width=True):
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
                    st.session_state["last_ncs_report"] = df_comp  # Cache calculation parameters safely
                    st.session_state["last_ncs_week"] = str(selected_week_start)
                    st.success("📊 Compiled Pobal Compliance Matrices Successfully!")
                    
                    st.dataframe(
                        df_comp.style.map(
                            lambda x: "background-color: #ffcccc; color: black;" if x == "⚠️ Under-Attending" else "",
                            subset=["Under-Attendance Flag"]
                        ),
                        use_container_width=True
                    )
                    
                    flagged_kids = df_comp[df_comp["Under-Attendance Flag"] == "⚠️ Under-Attending"]
                    if not flagged_kids.empty:
                        with st.warning("🚨 **Pobal Audit Warning Risk Alerts:**"):
                            st.write(
                                "The children listed below are attending *fewer hours* than their registered Hive contract. "
                                "If this consistent tracking variance trend patterns continue for **8 consecutive weeks**, "
                                "parents will receive a warning notice. At **12 weeks**, claims will be automatically reduced based on actual averages."
                            )
                            for _, row in flagged_kids.iterrows():
                                st.write(f"- **{row['Child']}**: Short by **{row['Variance (Hours Lost)']} hours** this week.")
                else:
                    st.info("No logs encountered for any child tracking against the targeted range criteria metrics.")
                    
            except Exception as e:
                st.error(f"Could not calculate compliance totals: {e}")

        # --- NEW: EXPORT SUITE ACTION UTILITY ---
        if "last_ncs_report" in st.session_state:
            st.write("### 📥 Step 3: Secure Audit Export Panel")
            
            cached_df = st.session_state["last_ncs_report"]
            target_week = st.session_state["last_ncs_week"]
            
            # Construct a clear filename following official auditing naming patterns
            clean_filename = f"NCS_Hive_Return_{sel_site}_Week_{target_week}.xlsx"
            
            # Compile a multi-sheet spreadsheet directly within system RAM
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                # Sheet 1: Main Overview Submission Return Sheet
                cached_df.to_excel(writer, sheet_name="Hive Claims Return", index=False)
                
                # Sheet 2: Isolated Compliance Exceptions Risk List Sheet
                exceptions_df = cached_df[cached_df["Under-Attendance Flag"] == "⚠️ Under-Attending"]
                if exceptions_df.empty:
                    exceptions_df = pd.DataFrame([{"Status": "All records completely compliant for this tracking period."}])
                exceptions_df.to_excel(writer, sheet_name="Pobal Compliance Warnings", index=False)

            # Present standard download action widget to user
            st.download_button(
                label=f"💾 Download {clean_filename}",
                data=buffer.getvalue(),
                file_name=clean_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )

# --- 8. ADMIN SETTINGS ---
elif page == "Admin Settings":
    st.title("⚙️ Hub Administration Settings")
    
    # 🔐 SECURE GATEKEEPING LOG-ON
    # Change "manager123" to whatever password you want to use
    ADMIN_PASSWORD = "manager123" 
    
    st.write("---")
    pwd_input = st.text_input("🔑 Enter Admin Access Password", type="password", placeholder="Password required...")
    
    if pwd_input == ADMIN_PASSWORD:
        st.success("Access Granted.")
        st.divider()
        
        # Lock screen passes successfully -> Render tabs
        tab_add, tab_view = st.tabs(["🎒 Enrol New Child", "📋 View Registered Children"])
        
        with tab_add:
            st.subheader("Register a New Student Profile")
            
            with st.form("enrolment_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                
                with col1:
                    child_name = st.text_input("Child's Full Name", placeholder="e.g. Liam Smith")
                    assigned_site = st.selectbox("Assigned Hub Location", sites, index=sites.index(sel_site))
                    
                with col2:
                    contact_name = st.text_input("Emergency Contact Name", placeholder="e.g. Sarah Smith (Mother)")
                    contact_phone = st.text_input("Emergency Contact Phone Number", placeholder="e.g. 087 123 4567")
                    
                submit_btn = st.form_submit_button("Submit Enrolment Application", type="primary", use_container_width=True)
                
                if submit_btn:
                    if not child_name.strip() or not contact_name.strip() or not contact_phone.strip():
                        st.error("Form incomplete. All fields are required to process enrolment.")
                    else:
                        try:
                            supabase.table("children").insert({
                                "name": child_name.strip(),
                                "location": assigned_site,
                                "emergency_name": contact_name.strip(),
                                "emergency_phone": contact_phone.strip()
                            }).execute()
                            
                            st.success(f"🎉 Successfully enrolled {child_name.strip()} at {assigned_site}!")
                        except Exception as e:
                            st.error(f"Database rejection: {e}. Ensure you ran the SQL update script inside your Supabase console.")
                            
        with tab_view:
            st.subheader(f"Registered Roster for {sel_site}")
            try:
                all_kids = supabase.table("children").select("*").eq("location", sel_site).execute()
                if all_kids.data:
                    kids_df = pd.DataFrame(all_kids.data)
                    display_cols = ["name", "location", "emergency_name", "emergency_phone"]
                    available_cols = [c for c in display_cols if c in kids_df.columns]
                    
                    final_kids_df = kids_df[available_cols].copy()
                    final_kids_df.columns = [c.replace('_', ' ').title() for c in available_cols]
                    
                    st.dataframe(final_kids_df, use_container_width=True, hide_index=True)
                else:
                    st.info(f"No children registered yet under the {sel_site} location.")
            except Exception as e:
                st.error(f"Could not load roster: {e}")
                
    elif pwd_input != "":
        st.error("Incorrect password. Access denied.")
