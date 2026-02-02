import streamlit as st
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import urllib.parse
from io import BytesIO
from supabase import create_client, Client

# --- CONFIGURATION ---
TRANSACTION_TYPES = [
    "Welfare Amount", "Loan Repayment", "Loan Taken", 
    "Loan Processing Fee", "Loan Extension Fee"
]

MASTER_PASSWORD = "secure999"

# --- SUPABASE CONNECTION ---
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except:
        return None

supabase = init_supabase()

# --- AUDIT ENGINE ---
def log_audit(action, details):
    if not supabase: return
    try:
        user = st.session_state.get("username", "System")
        supabase.table("audit_logs").insert({
            "username": user,
            "action": action,
            "details": details
        }).execute()
    except: pass

def load_audit_logs():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("audit_logs").select("*").order("created_at", desc=True).limit(100).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df = df.rename(columns={"created_at": "Time", "username": "User", "action": "Action", "details": "Details"})
            df["Time"] = pd.to_datetime(df["Time"]).dt.strftime('%d/%m/%Y %H:%M')
        return df
    except: return pd.DataFrame()

# --- DATA ENGINE ---
def load_data():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("transactions").select("*").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df = df.rename(columns={"date": "Date", "name": "Name", "type": "Type", "amount": "Amount", "notes": "Notes", "id": "ID"})
            df["Date"] = pd.to_datetime(df["Date"])
            df["Amount"] = pd.to_numeric(df["Amount"], errors='coerce').fillna(0)
            df["Month"] = df["Date"].dt.strftime('%Y-%m')
            df["Month_Str"] = df["Date"].dt.strftime('%B %Y')
            return df
    except: pass
    return pd.DataFrame(columns=["Date", "Name", "Type", "Amount", "Notes"])

def append_transaction(date_obj, name, txn_type, amount, note):
    if not supabase: return False
    try:
        data = {"date": date_obj.strftime("%Y-%m-%d"), "name": name, "type": txn_type, "amount": amount, "notes": note}
        supabase.table("transactions").insert(data).execute()
        log_audit("Add Transaction", f"{name} | {txn_type} | {amount}")
        return True
    except: return False

def delete_transaction_record(txn_id, details_str):
    if not supabase: return False
    try:
        supabase.table("transactions").delete().eq("id", txn_id).execute()
        log_audit("Delete Transaction", f"Deleted ID {txn_id}: {details_str}")
        return True
    except: return False

# --- ALERT SYSTEM (RE-ADDED) ---
def generate_alerts(df, members_df):
    alerts = []
    if df.empty: return alerts

    # 1. Low Fund Check
    wel = df[df["Type"] == "Welfare Amount"]["Amount"].sum()
    fees = df[df["Type"].isin(["Loan Processing Fee", "Loan Extension Fee"])]["Amount"].sum()
    loans_out = df[df["Type"] == "Loan Taken"]["Amount"].sum() - df[df["Type"] == "Loan Repayment"]["Amount"].sum()
    balance = wel + fees - loans_out
    
    if balance < 2000:
        alerts.append(f"⚠️ **Low Fund Balance:** Only {balance:,.0f} remaining!")

    # 2. Monthly Welfare Check
    if not members_df.empty and "Status" in members_df.columns:
        active_members = members_df[members_df["Status"] == "Active"]["Name"].tolist()
        
        today = date.today()
        current_month_key = today.strftime('%Y-%m') # e.g. 2023-10
        current_month_name = today.strftime('%B')
        
        for m in active_members:
            # Check if this member has a 'Welfare Amount' transaction in the current month
            has_paid = df[
                (df["Name"] == m) & 
                (df["Type"] == "Welfare Amount") & 
                (df["Month"] == current_month_key)
            ]
            
            if has_paid.empty:
                alerts.append(f"📅 **Missing Welfare:** {m} hasn't paid for {current_month_name}")

    return alerts

# --- MEMBER MANAGEMENT ---
def load_members_data():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("members").select("*").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df = df.rename(columns={"name": "Name", "phone": "Phone", "status": "Status"})
            df["Status"] = df["Status"].fillna("Active")
            df["Phone"] = df["Phone"].astype(str).replace("None", "")
        else: return pd.DataFrame(columns=["Name", "Phone", "Status"])
        return df
    except: return pd.DataFrame()

def add_member(name, phone):
    if not supabase: return False
    try:
        supabase.table("members").insert({"name": name, "phone": str(phone), "status": "Active"}).execute()
        log_audit("Add Member", f"Added {name}")
        return True
    except: return False

def update_member_phone(name, new_phone):
    if not supabase: return False
    try:
        supabase.table("members").update({"phone": str(new_phone)}).eq("name", name).execute()
        log_audit("Update Phone", f"Updated {name} to {new_phone}")
        return True
    except: return False

def archive_member(name):
    if not supabase: return False
    try:
        supabase.table("members").update({"status": "Archived"}).eq("name", name).execute()
        log_audit("Archive Member", f"Archived {name}")
        return True
    except: return False

# --- USER MANAGEMENT ---
def load_users():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("app_users").select("*").execute()
        df = pd.DataFrame(response.data)
        if not df.empty: df = df.rename(columns={"username": "Username", "password": "Password", "role": "Role"})
        return df
    except: return pd.DataFrame()

def add_user(u, p, r):
    if not supabase: return False
    try:
        supabase.table("app_users").insert({"username": u, "password": p, "role": r}).execute()
        log_audit("Add User", f"Created user {u} as {r}")
        return True
    except: return False

def delete_user(u):
    if not supabase: return False
    try:
        supabase.table("app_users").delete().eq("username", u).execute()
        log_audit("Delete User", f"Deleted user {u}")
        return True
    except: return False

# --- BACKUP & RESTORE UTILS ---
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

def restore_from_csv(table_name, uploaded_file):
    if not supabase: return False, "No Connection"
    try:
        df = pd.read_csv(uploaded_file)
        records = df.to_dict(orient='records')
        chunk_size = 100
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i+chunk_size]
            supabase.table(table_name).upsert(chunk).execute()
        return True, f"Restored {len(records)} rows to {table_name}"
    except Exception as e:
        return False, str(e)

# --- HELPER ---
def get_whatsapp_link(phone, msg):
    encoded_msg = urllib.parse.quote(msg)
    if phone and str(phone).strip() and str(phone).lower() not in ["nan", "none", ""]:
        clean_phone = str(phone).replace(" ", "").replace("+", "").replace("-", "").replace(".", "")
        return f"https://wa.me/{clean_phone}?text={encoded_msg}"
    return f"https://wa.me/?text={encoded_msg}"

# --- PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Welfare Fund Report', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def create_balance_pdf(df):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Member Balances", ln=True)
    pdf.cell(200, 10, txt=f"Date: {datetime.now().strftime('%d/%m/%Y')}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(60, 10, "Name", 1); pdf.cell(50, 10, "Total Paid", 1); pdf.cell(50, 10, "Loan Balance", 1); pdf.ln()
    pdf.set_font("Arial", size=10)
    for _, row in df.iterrows():
        pdf.cell(60, 10, str(row['Name']), 1); pdf.cell(50, 10, str(row['Total Paid']), 1); pdf.cell(50, 10, str(row['Loan Balance']), 1); pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

def create_individual_pdf(member_name, df, balance):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Member: {member_name}", ln=True)
    pdf.cell(200, 10, txt=f"Date: {datetime.now().strftime('%d/%m/%Y')}", ln=True)
    pdf.cell(200, 10, txt=f"Loan Balance: {balance:,.0f}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(30, 10, "Date", 1); pdf.cell(50, 10, "Type", 1); pdf.cell(30, 10, "Amount", 1); pdf.cell(80, 10, "Notes", 1); pdf.ln()
    pdf.set_font("Arial", size=10)
    for _, row in df.iterrows():
        d = row['Date'].strftime('%d/%m/%Y') if pd.notna(row['Date']) else ""
        pdf.cell(30, 10, d, 1); pdf.cell(50, 10, str(row['Type']), 1); pdf.cell(30, 10, str(row['Amount']), 1); pdf.cell(80, 10, str(row['Notes']), 1); pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

def create_monthly_pdf(month_name, df):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Monthly Report: {month_name}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(30, 10, "Date", 1); pdf.cell(40, 10, "Name", 1); pdf.cell(50, 10, "Type", 1); pdf.cell(30, 10, "Amount", 1); pdf.ln()
    pdf.set_font("Arial", size=10)
    for _, row in df.iterrows():
        d = row['Date'].strftime('%d/%m/%Y') if pd.notna(row['Date']) else ""
        pdf.cell(30, 10, d, 1); pdf.cell(40, 10, str(row['Name']), 1); pdf.cell(50, 10, str(row['Type']), 1); pdf.cell(30, 10, str(row['Amount']), 1); pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- LOGIN ---
def login_screen():
    st.title("🔒 Login Required")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            try:
                users = load_users()
                if not users.empty:
                    match = users[(users["Username"] == u) & (users["Password"] == p)]
                    if not match.empty:
                        st.session_state["logged_in"] = True
                        st.session_state["user_role"] = match.iloc[0]["Role"]
                        st.session_state["username"] = match.iloc[0]["Username"]
                        st.rerun()
                    else: st.error("Invalid Credentials")
                else: st.error("No users found or DB Error")
            except Exception as e: st.error(f"Login Error: {e}")

# --- MAIN APP ---
def main_app():
    c1, c2 = st.columns([3, 1])
    c1.title("💰 Welfare Fund")
    if c2.button("Logout"):
        st.session_state["logged_in"] = False; st.rerun()

    members_df = load_members_data()
    active_members = members_df[members_df["Status"] == "Active"]["Name"].tolist() if not members_df.empty else []
    df = load_data()

    # --- ALERTS / NOTIFICATIONS ---
    if not df.empty:
        alerts = generate_alerts(df, members_df)
        if alerts:
            with st.expander(f"🚨 Notifications ({len(alerts)})", expanded=True):
                for a in alerts: st.warning(a)

    # --- ADMIN SIDEBAR ---
    if st.session_state["user_role"] == "admin":
        st.sidebar.title("🛠️ Admin Controls")
        
        # 1. NEW TRANSACTION
        st.sidebar.header("📝 Add Transaction")
        with st.sidebar.form("add_txn_web", clear_on_submit=True):
            date_val = st.date_input("Date", datetime.now(), format="DD/MM/YYYY")
            name = st.selectbox("Member", active_members if active_members else ["No Active Members"])
            
            ph = ""
            if not members_df.empty and name in members_df["Name"].values:
                try: ph = str(members_df.loc[members_df["Name"] == name, "Phone"].values[0])
                except: pass
            if ph: st.caption(f"📞 {ph}")

            txn = st.selectbox("Type", TRANSACTION_TYPES)
            amt = st.number_input("Amount", min_value=0, value=0, step=1)
            note = st.text_input("Note")
            
            if st.form_submit_button("Save"):
                if append_transaction(date_val, name, txn, amt, note):
                    st.sidebar.success("Saved!")
                    st.rerun()
                    wa_link = get_whatsapp_link(ph, f"Receipt: {amt} | {name} | {txn}")
                    st.sidebar.link_button("💬 WhatsApp Receipt", wa_link)

        st.sidebar.divider()
        
        # 2. DELETE RECORD
        with st.sidebar.expander("🗑️ Delete Transaction"):
            if not df.empty:
                recent_df = df.sort_values("Date", ascending=False).head(30)
                txn_options = {f"{r['Date'].strftime('%d/%m')} | {r['Name']} | {r['Amount']} ({r['Type']})": r["ID"] for _, r in recent_df.iterrows()}
                sel_txn_str = st.selectbox("Select Record", list(txn_options.keys()))
                sel_txn_id = txn_options[sel_txn_str]
                mp_del_rec = st.text_input("Master Password", type="password", key="mp_del_rec")
                if st.button("Delete Record"):
                    if mp_del_rec == MASTER_PASSWORD:
                        if delete_transaction_record(sel_txn_id, sel_txn_str): st.success("Deleted!"); st.rerun()
                        else: st.error("Failed")
                    else: st.error("Wrong Password")
            else: st.info("No records")

        # 3. MEMBER MANAGEMENT
        with st.sidebar.expander("👥 Members"):
            st.write("**Add Member**")
            nm = st.text_input("Name"); nph = st.text_input("Phone")
            mp_m = st.text_input("Master Password", type="password", key="mp_m")
            if st.button("Add"):
                if mp_m == MASTER_PASSWORD:
                    if add_member(nm, nph): st.success("Added!"); st.rerun()
                else: st.error("Wrong Password")
            
            st.divider()
            st.write("**Archive Member**")
            dm = st.selectbox("Archive", active_members, key="dm")
            mp_del = st.text_input("Master Password", type="password", key="mp_del")
            if st.button("Archive"):
                if mp_del == MASTER_PASSWORD:
                    if archive_member(dm): st.success("Archived!"); st.rerun()
                else: st.error("Wrong Password")

        # 4. USER MANAGEMENT
        with st.sidebar.expander("👤 Users"):
            current_users = load_users()
            if not current_users.empty: st.dataframe(current_users[["Username", "Role"]], hide_index=True)
            nu = st.text_input("User", key="nu"); np = st.text_input("Pass", type="password", key="np"); nr = st.selectbox("Role", ["admin", "viewer"], key="nr")
            mp_a = st.text_input("Master Password", type="password", key="mp_a")
            if st.button("Create User"):
                if mp_a == MASTER_PASSWORD:
                    if add_user(nu, np, nr): st.success("Added!"); st.rerun()
                else: st.error("Wrong Password")

        # 5. BACKUP & RESTORE
        st.sidebar.divider()
        with st.sidebar.expander("💾 Backup & Restore"):
            st.caption("Download your data regularly!")
            
            if not df.empty:
                st.download_button("📥 Backup Transactions", convert_df_to_csv(df), "transactions_backup.csv", "text/csv")
            if not members_df.empty:
                st.download_button("📥 Backup Members", convert_df_to_csv(members_df), "members_backup.csv", "text/csv")
            if not current_users.empty:
                st.download_button("📥 Backup Users", convert_df_to_csv(current_users), "users_backup.csv", "text/csv")
            
            st.divider()
            st.write("**Restore Data**")
            st.caption("⚠️ This appends data to the database.")
            up_file = st.file_uploader("Upload CSV", type=["csv"])
            table_target = st.selectbox("Target Table", ["transactions", "members", "app_users"])
            mp_res = st.text_input("Master Password", type="password", key="mp_res")
            
            if st.button("Restore from File"):
                if mp_res == MASTER_PASSWORD:
                    if up_file:
                        success, msg = restore_from_csv(table_target, up_file)
                        if success: st.success(msg); st.rerun()
                        else: st.error(msg)
                    else: st.error("Upload a file first")
                else: st.error("Wrong Password")

    # --- TABS ---
    web_tabs = st.tabs(["🏠 Dashboard", "📈 Trends", "👤 Individual", "🗓️ Monthly", "📜 Audit Logs"])
    
    # DASHBOARD
    with web_tabs[0]: 
        search_query = st.text_input("🔍 Search")
        display_df = df.copy()
        if search_query: display_df = display_df[display_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)]
        
        if not display_df.empty:
            wel = display_df[display_df["Type"] == "Welfare Amount"]["Amount"].sum()
            fees = display_df[display_df["Type"].isin(["Loan Processing Fee", "Loan Extension Fee"])]["Amount"].sum()
            out = display_df[display_df["Type"] == "Loan Taken"]["Amount"].sum() - display_df[display_df["Type"] == "Loan Repayment"]["Amount"].sum()
            bal = wel + fees - out
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Welfare", f"{wel:,.0f}"); c2.metric("Loans Out", f"{out:,.0f}"); c3.metric("Fees", f"{fees:,.0f}"); c4.metric("Balance", f"{bal:,.0f}")
            st.divider()
            
            stats = []
            all_members_list = members_df["Name"].tolist() if not members_df.empty else []
            for m in all_members_list:
                m_df = df[df["Name"] == m]
                w = m_df[m_df["Type"] == "Welfare Amount"]["Amount"].sum()
                b = m_df[m_df["Type"] == "Loan Taken"]["Amount"].sum() - m_df[m_df["Type"] == "Loan Repayment"]["Amount"].sum()
                stats.append([m, w, b])
            bal_df = pd.DataFrame(stats, columns=["Name", "Total Paid", "Loan Balance"])
            
            if search_query: st.dataframe(display_df, hide_index=True, use_container_width=True)
            else: st.dataframe(bal_df, hide_index=True, use_container_width=True)
            st.download_button("📄 Download PDF", create_balance_pdf(bal_df), "balances.pdf", "application/pdf")
        else: st.info("No transactions found.")

    # TRENDS
    with web_tabs[1]:
        if not df.empty: st.bar_chart(df.groupby(["Month", "Type"])["Amount"].sum().unstack(fill_value=0))

    # INDIVIDUAL
    with web_tabs[2]: 
        if not df.empty:
            person = st.selectbox("Member", members_df["Name"].tolist() if not members_df.empty else [], key="ind_per")
            p_df = df[df["Name"] == person].sort_values("Date", ascending=False)
            if not p_df.empty:
                bal = p_df[p_df["Type"]=="Loan Taken"]["Amount"].sum() - p_df[p_df["Type"]=="Loan Repayment"]["Amount"].sum()
                c1, c2 = st.columns(2)
                c1.download_button("📄 PDF", create_individual_pdf(person, p_df, bal), f"{person}.pdf", "application/pdf")
                ph = ""
                if not members_df.empty and person in members_df["Name"].values:
                    try: ph = str(members_df.loc[members_df["Name"] == person, "Phone"].values[0])
                    except: pass
                c2.link_button("💬 WhatsApp", get_whatsapp_link(ph, f"Hi {pe
