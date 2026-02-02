import streamlit as st
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import urllib.parse
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

# --- DATA ENGINE (DIRECT DB) ---

def load_data():
    """Fetches all transactions directly from Supabase"""
    if not supabase: return pd.DataFrame()
    try:
        # Fetch all rows
        response = supabase.table("transactions").select("*").execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # Standardize columns to match app logic (Capitalized)
            df = df.rename(columns={
                "date": "Date", 
                "name": "Name", 
                "type": "Type", 
                "amount": "Amount", 
                "notes": "Notes"
            })
            df["Date"] = pd.to_datetime(df["Date"])
            df["Amount"] = pd.to_numeric(df["Amount"], errors='coerce').fillna(0)
            
            # Add derived Month columns for charts
            df["Month"] = df["Date"].dt.strftime('%Y-%m')
            df["Month_Str"] = df["Date"].dt.strftime('%B %Y')
            return df
    except Exception as e:
        st.error(f"Database Error: {e}")
    
    return pd.DataFrame(columns=["Date", "Name", "Type", "Amount", "Notes"])

def append_transaction(date_obj, name, txn_type, amount, note):
    """Inserts directly into Supabase"""
    if not supabase: return False
    try:
        data = {
            "date": date_obj.strftime("%Y-%m-%d"),
            "name": name,
            "type": txn_type,
            "amount": amount,
            "notes": note
        }
        supabase.table("transactions").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"Save Failed: {e}")
        return False

# --- MEMBER MANAGEMENT (DB) ---

def load_members_data():
    """Fetches members with Name, Phone, Status"""
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("members").select("*").execute()
        df = pd.DataFrame(response.data)
        
        # Normalize columns
        if not df.empty:
            df = df.rename(columns={"name": "Name", "phone": "Phone", "status": "Status"})
            # Handle potential nulls
            df["Status"] = df["Status"].fillna("Active")
            df["Phone"] = df["Phone"].astype(str).replace("None", "")
        else:
            return pd.DataFrame(columns=["Name", "Phone", "Status"])
            
        return df
    except: return pd.DataFrame()

def add_member(name, phone):
    if not supabase: return False
    try:
        # Check if exists first (Supabase has unique constraint, but this is cleaner)
        supabase.table("members").insert({
            "name": name, 
            "phone": str(phone), 
            "status": "Active"
        }).execute()
        return True
    except Exception as e: 
        st.error(f"Error: {e}")
        return False

def update_member_phone(name, new_phone):
    if not supabase: return False
    try:
        supabase.table("members").update({"phone": str(new_phone)}).eq("name", name).execute()
        return True
    except: return False

def archive_member(name):
    """Soft delete: Update status to Archived"""
    if not supabase: return False
    try:
        supabase.table("members").update({"status": "Archived"}).eq("name", name).execute()
        return True
    except: return False

# --- USER MANAGEMENT ---
def load_users():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("app_users").select("*").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
             df = df.rename(columns={"username": "Username", "password": "Password", "role": "Role"})
        return df
    except: return pd.DataFrame()

def add_user(u, p, r):
    if not supabase: return False
    try:
        supabase.table("app_users").insert({"username": u, "password": p, "role": r}).execute()
        return True
    except: return False

def delete_user(u):
    if not supabase: return False
    try:
        supabase.table("app_users").delete().eq("username", u).execute()
        return True
    except: return False

# --- HELPER: WHATSAPP ---
def get_whatsapp_link(phone, msg):
    encoded_msg = urllib.parse.quote(msg)
    if phone and str(phone).strip() and str(phone).lower() != "nan" and str(phone).lower() != "none":
        clean_phone = str(phone).replace(" ", "").replace("+", "").replace("-", "").replace(".", "")
        return f"https://wa.me/{clean_phone}?text={encoded_msg}"
    else:
        return f"https://wa.me/?text={encoded_msg}"

# --- PDF GENERATION ---
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
                    # Supabase returns lowercase usually, simple filter
                    match = users[(users["Username"] == u) & (users["Password"] == p)]
                    if not match.empty:
                        st.session_state["logged_in"] = True
                        st.session_state["user_role"] = match.iloc[0]["Role"]
                        st.session_state["username"] = match.iloc[0]["Username"]
                        st.rerun()
                    else: st.error("Invalid Credentials")
                else: st.error("No users found in DB")
            except Exception as e: st.error(f"Login Error: {e}")

# --- MAIN APP ---
def main_app():
    c1, c2 = st.columns([3, 1])
    c1.title("💰 Welfare Fund (DB)")
    if c2.button("Logout"):
        st.session_state["logged_in"] = False; st.rerun()

    # Load Data directly from DB
    members_df = load_members_data()
    df = load_data()
    
    # Filter Active Members for Dropdowns
    active_members = []
    if not members_df.empty:
        if "Status" in members_df.columns:
            active_members = members_df[members_df["Status"] == "Active"]["Name"].tolist()
        else:
            active_members = members_df["Name"].tolist()

    # --- ADMIN SIDEBAR ---
    if st.session_state["user_role"] == "admin":
        st.sidebar.title("🛠️ Admin")
        
        # 1. NEW TRANSACTION
        st.sidebar.header("📝 Add Transaction")
        with st.sidebar.form("add_txn_web", clear_on_submit=True):
            date_val = st.date_input("Date", datetime.now(), format="DD/MM/YYYY")
            name = st.selectbox("Member", active_members if active_members else ["No Active Members"])
            
            # Show Phone Logic
            phone_num = ""
            if not members_df.empty and name in members_df["Name"].values:
                # Safe access
                try: phone_num = str(members_df.loc[members_df["Name"] == name, "Phone"].values[0])
                except: phone_num = ""
            
            if phone_num and len(phone_num) > 3: st.caption(f"📞 Linked: {phone_num}")
            else: st.caption("⚠️ No Phone")

            txn = st.selectbox("Type", TRANSACTION_TYPES)
            amt = st.number_input("Amount", min_value=0, value=0, step=1)
            note = st.text_input("Note")
            
            if st.form_submit_button("Save"):
                if append_transaction(date_val, name, txn, amt, note):
                    st.sidebar.success("Saved to DB!")
                    # Refresh page to see data
                    st.rerun()
                    
                    # WhatsApp Link
                    msg = f"Receipt: {amt} | {name} | {txn} | {date_val.strftime('%d/%m/%Y')}"
                    wa_link = get_whatsapp_link(phone_num, msg)
                    st.sidebar.link_button("💬 Send Receipt", wa_link)

        st.sidebar.divider()

        # 2. USER MANAGEMENT
        with st.sidebar.expander("👤 Users (Password Protected)"):
            current_users = load_users()
            if not current_users.empty: st.dataframe(current_users[["Username", "Role"]], hide_index=True)
            
            st.write("**Add User**")
            nu = st.text_input("User", key="nu"); np = st.text_input("Pass", type="password", key="np"); nr = st.selectbox("Role", ["admin", "viewer"], key="nr")
            mp_a = st.text_input("Master Password", type="password", key="mp_a")
            if st.button("Create"):
                if mp_a == MASTER_PASSWORD:
                    if add_user(nu, np, nr): st.success("Added!"); st.rerun()
                else: st.error("Wrong Password")
                
            if not current_users.empty:
                st.divider()
                du = st.selectbox("Delete User", current_users["Username"].tolist())
                mp_d = st.text_input("Master Password", type="password", key="mp_d")
                if st.button("Delete"):
                    if mp_d == MASTER_PASSWORD:
                        if delete_user(du): st.success("Deleted"); st.rerun()
                    else: st.error("Wrong Password")

        # 3. MEMBER MANAGEMENT
        with st.sidebar.expander("👥 Members (Password Protected)"):
            # ADD
            st.write("**Add Member**")
            nm = st.text_input("Name"); nph = st.text_input("Phone")
            mp_m = st.text_input("Master Password", type="password", key="mp_m")
            if st.button("Add"):
                if mp_m == MASTER_PASSWORD:
                    if add_member(nm, nph): st.success("Added!"); st.rerun()
                else: st.error("Wrong Password")
            
            st.divider()
            
            # UPDATE
            st.write("**Update Phone**")
            up_m = st.selectbox("Member", active_members, key="up_m")
            up_p = st.text_input("New Phone")
            mp_up = st.text_input("Master Password", type="password", key="mp_up")
            if st.button("Update"):
                if mp_up == MASTER_PASSWORD:
                    if update_member_phone(up_m, up_p): st.success("Updated!"); st.rerun()
                else: st.error("Wrong Password")
            
            st.divider()
            
            # ARCHIVE
            st.write("**Archive Member**")
            dm = st.selectbox("Archive", active_members, key="dm")
            mp_del = st.text_input("Master Password", type="password", key="mp_del")
            if st.button("Archive"):
                if mp_del == MASTER_PASSWORD:
                    if archive_member(dm): st.success("Archived!"); st.rerun()
                else: st.error("Wrong Password")

    # --- TABS ---
    web_tabs = st.tabs(["🏠 Dashboard", "📈 Trends", "👤 Individual", "🗓️ Monthly"])
    
    # DASHBOARD
    with web_tabs[0]: 
        search_query = st.text_input("🔍 Search Transactions")
        display_df = df.copy()
        
        # Simple string search filter
        if search_query:
            display_df = display_df[display_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)]
        
        if not display_df.empty:
            wel = display_df[display_df["Type"] == "Welfare Amount"]["Amount"].sum()
            fees = display_df[display_df["Type"].isin(["Loan Processing Fee", "Loan Extension Fee"])]["Amount"].sum()
            out = display_df[display_df["Type"] == "Loan Taken"]["Amount"].sum() - display_df[display_df["Type"] == "Loan Repayment"]["Amount"].sum()
            bal = wel + fees - out
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Welfare", f"{wel:,.0f}"); c2.metric("Loans Out", f"{out:,.0f}"); c3.metric("Fees", f"{fees:,.0f}"); c4.metric("Balance", f"{bal:,.0f}")
            st.divider()
            
            # Balance Table Calculation
            # We iterate ALL members (active + archived) to show historical balances
            all_members_list = members_df["Name"].tolist() if not members_df.empty else []
            
            stats = []
            for m in all_members_list:
                m_df = df[df["Name"] == m]
                w = m_df[m_df["Type"] == "Welfare Amount"]["Amount"].sum()
                b = m_df[m_df["Type"] == "Loan Taken"]["Amount"].sum() - m_df[m_df["Type"] == "Loan Repayment"]["Amount"].sum()
                stats.append([m, w, b])
            
            bal_df = pd.DataFrame(stats, columns=["Name", "Total Paid", "Loan Balance"])
            
            if search_query: st.dataframe(display_df, hide_index=True, use_container_width=True)
            else: st.dataframe(bal_df, hide_index=True, use_container_width=True)
            
            st.download_button("📄 Download PDF", create_balance_pdf(bal_df), "balances.pdf", "application/pdf")
        else:
            st.info("No transactions found in database.")

    # TRENDS
    with web_tabs[1]:
        if not df.empty:
            st.bar_chart(df.groupby(["Month", "Type"])["Amount"].sum().unstack(fill_value=0))

    # INDIVIDUAL
    with web_tabs[2]: 
        if not df.empty:
            all_members_list = members_df["Name"].tolist() if not members_df.empty else []
            person = st.selectbox("Member", all_members_list, key="ind_per")
            p_df = df[df["Name"] == person].sort_values("Date", ascending=False)
            
            if not p_df.empty:
                bal = p_df[p_df["Type"]=="Loan Taken"]["Amount"].sum() - p_df[p_df["Type"]=="Loan Repayment"]["Amount"].sum()
                c1, c2 = st.columns(2)
                c1.download_button("📄 PDF", create_individual_pdf(person, p_df, bal), f"{person}.pdf", "application/pdf")
                
                # Phone Logic
                ph = ""
                if not members_df.empty and person in members_df["Name"].values:
                    try: ph = str(members_df.loc[members_df["Name"] == person, "Phone"].values[0])
                    except: ph = ""
                c2.link_button("💬 WhatsApp", get_whatsapp_link(ph, f"Hi {person}, Balance: {bal:,.0f}"))

                p_df["Date"] = p_df["Date"].dt.strftime('%d/%m/%Y')
                st.dataframe(p_df, use_container_width=True, hide_index=True)

    # MONTHLY
    with web_tabs[3]: 
        if not df.empty:
            month = st.selectbox("Month", df["Month_Str"].unique())
            m_df = df[df["Month_Str"] == month]
            st.download_button("📄 Download", create_monthly_pdf(month, m_df), f"{month}.pdf", "application/pdf")
            m_df["Date"] = m_df["Date"].dt.strftime('%d/%m/%Y')
            st.dataframe(m_df, use_container_width=True, hide_index=True)

if "logged_in" not in st.session_state: st.session_state["logged_in"] = False
if not st.session_state["logged_in"]: login_screen()
else: main_app()
                
