import streamlit as st
import pandas as pd
import math
import io
from datetime import datetime
from supabase import create_client, Client

# --- 1. SECURE CONNECTION ---
SUPABASE_URL = "https://supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind3b2ZkdGRqcHBydnR6am1xZ2JrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5MTQzMTcsImV4cCI6MjA5MTQ5MDMxN30.jirzLPRXKfr1Z3slm-0CchvTU7lXgLtTWuCk1RDhmfQ"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. UTILS ---
def ncs_round(check_in, check_out):
    """Calculates attendance duration and rounds up to the next full hour."""
    try:
        fmt = "%H:%M:%S"
        start = datetime.strptime(check_in, fmt)
        end = datetime.strptime(check_out, fmt)
        actual_hours = (end - start).total_seconds() / 3600
        return math.ceil(actual_hours)
    except Exception:
        return 0

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
        
    st.metric("Children Present Today", kids_in)

# --- 5. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Sign-Out")
    st.caption("Tap a child's name to select who is collecting them.")
    
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

# --- 6. ATTENDANCE & SIGN-IN ---
elif page == "Attendance":
    st.title("📍 Daily Log")
    tab1, tab2 = st.tabs(["🚌 Arrivals (Quick-Sign In)", "👤 Departures (Sign Out)"])
    
    with tab1:
        st.subheader("Quick-Tap Children to Sign In")
        today_str = str(datetime.now().date())
        
        try:
            kids = supabase.table("children").select("name").eq("location", sel_site).execute()
            all_names = sorted([k['name'] for k in kids.data])
            
            active_res = supabase.table("attendance").select("name").eq("date", today_str).eq("location", sel_site).is_("check_out", "null").execute()
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
                        st.button(f"✅ {child_name} (IN)", key=f"signin_done_{idx}", disabled=True, use_container_width=True)
                    else:
                        if st.button(f"➕ {child_name}", key=f"signin_btn_{idx}", use_container_width=True):
                            now_time = datetime.now().strftime("%H:%M:%S")
                            try:
                                supabase.table("attendance").insert({
                                    "name": child_name,
                                    "date": today_str,
                                    "check_in": now_time,
                                    "location": sel_site
                                }).execute()
                                st.success(f"Signed in {child_name} at {now_time}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Sign-in error: {e}")
        else:
            st.info(f"No children registered under the {sel_site} site roster.")

    with tab2:
        st.subheader("Manual Deviations & Notes")
        st.caption("Review or append operational details to today's active sign-out transactions.")

# --- 7. NCS COMPLIANCE & REPORTING ---
elif page == "NCS Compliance":
    st.title("📊 Weekly NCS Compliance Tracker")
    st.caption(f"Review calculated attendance caps and flags for **{sel_site}**.")

    try:
        kids_res = supabase.table("children").select("id", "name", "ncs_hours_allowed").eq("location", sel_site).execute()
        kids_data = kids_res.data

        attendance_res = supabase.table("attendance").select("*").eq("location", sel_site).is_not("check_out", "null").execute()
        att_data = attendance_res.data
    except Exception as e:
        st.error(f"Error loading system metrics: {e}")
        kids_data, att_data = [], []

    if not kids_data:
        st.info("No children configurations found to build metrics.")
    else:
        report_rows = []
        overage_count = 0

        for child in kids_data:
            c_name = child.get("name")
            allowed_hours = child.get("ncs_hours_allowed", 0)
            if allowed_hours is None:
                allowed_hours = 0
            
            child_logs = [log for log in att_data if log.get("name") == c_name]
            total_used_hours = 0
            
            for log in child_logs:
                if "hours" in log and log["hours"] is not None:
                    total_used_hours += log["hours"]
                else:
                    total_used_hours += ncs_round(log.get("check_in"), log.get("check_out"))

            overage = max(0, total_used_hours - allowed_hours)
            status = "🚨 Exceeded Cap" if overage > 0 else "✅ Compliant"
            
            if overage > 0:
                overage_count += 1

            report_rows.append({
                "Child Name": c_name,
                "Weekly Framework (Hrs)": allowed_hours,
                "Hours Logged": total_used_hours,
                "Overage": overage,
                "Status": status
            })

        report_df = pd.DataFrame(report_rows)
        
        # Summary Overview Metric Card
        st.metric(
            label="Children Over Allocated Threshold", 
            value=overage_count, 
            delta=f"{overage_count} flags active" if overage_count > 0 else "All Clear",
            delta_color="inverse" if overage_count > 0 else "normal"
        )
        
Use code with caution.
# Structured Tabular Log Overview
st.dataframe(report_df, use_container_width=True, hide_index=True)
--- 8. ADMIN SETTINGS ---
elif page == "Admin Settings":
st.title("⚙️ Site Administration")
st.subheader("Edit Child NCS Care Framework Allocations")
st.caption(f"Assign max claimable weekly child-care constraints for {sel_site}.")
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
col1, col2 = st.columns()
with col1:
st.write(f"👦 {child_name}")
st.caption(f"Configured Limit: {current_allowed} hours per week")
with col2:
new_hours = st.number_input(
"Weekly NCS Limit",
min_value=0,
max_value=168,
value=int(current_allowed),
key=f"input_admin_ncs_{child_id}",
label_visibility="collapsed"
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
