import streamlit as st
import pandas as pd
import math
import io
from datetime import datetime
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas

# --- 1. SECURE CONNECTION ---
SUPABASE_URL = "https://supabase.co"
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
    st.title("📊 NCS Compliance")
    st.write("Compliance tracking systems setup details go here.")

# --- 8. ADMIN SETTINGS ---
elif page == "Admin Settings":
    st.title("⚙️ Admin Settings")
    st.subheader("🎒 Enrol New Child")
    
