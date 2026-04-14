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
    fmt = "%H:%M:%S"
    start = datetime.strptime(check_in, fmt)
    end = datetime.strptime(check_out, fmt)
    actual_hours = (end - start).total_seconds() / 3600
    return math.ceil(actual_hours)

# --- 3. NAVIGATION ---
sites = ["Elphin", "Ballinameen", "Boyle", "Roscommon", "Keadue"]
page = st.sidebar.radio("Navigation", ["Dashboard", "Quick-Tap Board", "Attendance", "NCS Compliance", "Admin & Reports"])
sel_site = st.sidebar.selectbox("Current Site Location", sites)

# --- 4. DASHBOARD ---
if page == "Dashboard":
    st.title(f"🏫 {sel_site} Management Hub")
    today = str(datetime.now().date())
    kids_in = supabase.table("attendance").select("id", count="exact").eq("date", today).is_("check_out", "null").execute().count
    st.metric("Children Present", kids_in)

# --- 5. QUICK-TAP BOARD ---
elif page == "Quick-Tap Board":
    st.title("🔘 Quick-Tap Attendance")
    collector_types = ["Mom", "Dad", "Brother", "Sister", "Nan", "Grandad", "Aunty", "Uncle", "Family Friend"]
    
    kids_res = supabase.table("children").select("name").eq("location", sel_site).execute()
    all_kids = sorted([k['name'] for k in kids_res.data])
    active_res = supabase.table("attendance").select("name").is_("check_out", "null").execute()
    checked_in_names = [a['name'] for a in active_res.data]

    cols = st.columns(4)
    for i, name in enumerate(all_kids):
        is_in = name in checked_in_names
        btn_label = f"🟢 {name.split()[0]}" if is_in else f"⚪ {name.split()[0]}"
        if cols[i % 4].button(btn_label, key=f"tap_{name}", use_container_width=True):
            if not is_in:
                supabase.table("attendance").insert({"name": name, "date": str(datetime.now().date()), "check_in": datetime.now().strftime("%H:%M:%S")}).execute()
                st.rerun()
            else:
                st.session_state["signing_out_child"] = name

    if "signing_out_child" in st.session_state:
        child_name = st.session_state["signing_out_child"]
        with st.container(border=True):
            st.subheader(f"Collecting: {child_name}")
            col_choice = st.pills("Who is collecting?", collector_types)
            if st.button("Finalize Sign-Out", type="primary"):
                if col_choice:
                    record = supabase.table("attendance").select("id, check_in").eq("name", child_name).is_("check_out", "null").execute()
                    if record.data:
                        rec = record.data[0]
                        now_time = datetime.now().strftime("%H:%M:%S")
                        supabase.table("attendance").update({"check_out": now_time, "hours": ncs_round(rec['check_in'], now_time), "collected_by": col_choice}).eq("id", rec['id']).execute()
                        del st.session_state["signing_out_child"]
                        st.rerun()
                else: st.error("Select collector")

# --- 6. ATTENDANCE (TRADITIONAL) ---
elif page == "Attendance":
    st.title("📍 Daily Log")
    collector_types = ["Mom", "Dad", "Brother", "Sister", "Nan", "Grandad", "Aunty", "Uncle", "Family Friend"]
    tab1, tab2 = st.tabs(["🚌 Bulk In", "👤 Sign Out"])
    with tab1:
        kids = supabase.table("children").select("name").eq("location", sel_site).execute()
        names = [k['name'] for k in kids.data]
        sel_kids = st.multiselect("Select for Bulk In", names)
        if st.button("Process Bulk In"):
            for n in sel_kids:
                supabase.table("attendance").insert({"name": n, "date": str(datetime.now().date()), "check_in": datetime.now().strftime("%H:%M:%S")}).execute()
            st.rerun()
    with tab2:
        active_res = supabase.table("attendance").select("*").is_("check_out", "null").execute()
        children_res = supabase.table("children").select("name", "location", "allergies").eq("location", sel_site).execute()
        site_children = {c['name']: c for c in children_res.data}
        site_logs = [a for a in active_res.data if a['name'] in site_children]
        for log in site_logs:
            with st.expander(f"Sign-Out: {log['name']}"):
                collector = st.selectbox("Collector", collector_types, key=f"c_{log['id']}", index=None)
                if st.button("Finalize", key=f"f_{log['id']}"):
                    if collector:
                        now = datetime.now().strftime("%H:%M:%S")
                        supabase.table("attendance").update({"check_out": now, "hours": ncs_round(log['check_in'], now), "collected_by": collector}).eq("id", log['id']).execute()
                        st.rerun()

# --- 7. NCS COMPLIANCE ---
elif page == "NCS Compliance":
    st.title("⚖️ 8-Week Tracker")

# --- 8. ADMIN & REPORTS ---
elif page == "Admin & Reports":
    st.header("⚙️ Admin & 📊 Reports")
    
    # Enrollment Form
    with st.expander("Enroll New Child"):
        with st.form("enroll"):
            n = st.text_input("Name")
            h = st.number_input("Hours", value=20)
            if st.form_submit_button("Save"):
                supabase.table("children").insert({"name": n, "location": sel_site, "registered_hours": h}).execute()
                st.success("Saved")

    st.divider()
    
    # Report Section
    st.subheader("Daily Attendance Report")
    report_date = st.date_input("Report Date", datetime.now())
    if st.button("Generate Report"):
        att_res = supabase.table("attendance").select("*").eq("date", str(report_date)).execute()
        kids_res = supabase.table("children").select("name").eq("location", sel_site).execute()
        site_kid_names = [k['name'] for k in kids_res.data]
        st.session_state.current_report = [row for row in att_res.data if row['name'] in site_kid_names]

    if "current_report" in st.session_state and st.session_state.current_report:
        report_df = pd.DataFrame(st.session_state.current_report)
        display_cols = [c for c in ["name", "check_in", "check_out", "hours", "collected_by"] if c in report_df.columns]
        final_df = report_df[display_cols]
        st.dataframe(final_df, use_container_width=True)
        st.download_button("📥 Download CSV", final_df.to_csv(index=False).encode('utf-8'), f"Report_{report_date}.csv", "text/csv")
