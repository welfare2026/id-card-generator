import streamlit as st
import pandas as pd
import os
import hashlib
import urllib.parse
from datetime import datetime, date
from fpdf import FPDF
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================= CONFIG =================
SHEET_NAME = "Welfare_Database"
DATA_FILE = "welfare_database.csv"
MEMBERS_FILE = "members.csv"
AUDIT_FILE = "audit_log.csv"
MASTER_PASSWORD = "secure999"

TRANSACTION_TYPES = [
    "Welfare Amount",
    "Loan Taken",
    "Loan Repayment",
    "Loan Processing Fee",
    "Loan Extension Fee"
]

# ================= SECURITY =================
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ================= GOOGLE SHEETS =================
def connect_to_gsheet():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"],
        ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds).open(SHEET_NAME)

# ================= AUDIT =================
def log_action(user, action):
    row = {
        "Time": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "User": user,
        "Action": action
    }
    pd.DataFrame([row]).to_csv(
        AUDIT_FILE,
        mode="a",
        header=not os.path.exists(AUDIT_FILE),
        index=False
    )

# ================= DATA =================
def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_csv(DATA_FILE)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
        return df
    return pd.DataFrame(columns=["Date", "Name", "Type", "Amount", "Notes"])

def save_data(df):
    df2 = df.copy()
    df2["Date"] = df2["Date"].dt.strftime("%d/%m/%Y")
    df2.to_csv(DATA_FILE, index=False)

    sh = connect_to_gsheet()
    wk = sh.worksheet("Transactions")
    wk.clear()
    wk.update([df2.columns.tolist()] + df2.values.tolist())

# ================= MEMBERS =================
def load_members():
    if os.path.exists(MEMBERS_FILE):
        return pd.read_csv(MEMBERS_FILE)["Name"].tolist()
    sh = connect_to_gsheet()
    wk = sh.worksheet("Members")
    names = [r["Name"] for r in wk.get_all_records()]
    pd.DataFrame(names, columns=["Name"]).to_csv(MEMBERS_FILE, index=False)
    return names

# ================= USERS =================
def load_users():
    sh = connect_to_gsheet()
    return pd.DataFrame(sh.worksheet("Users").get_all_records())

# ================= ALERTS =================
def generate_alerts(df, members):
    alerts = []
    today = pd.Timestamp.today()

    welfare = df[df["Type"] == "Welfare Amount"]["Amount"].sum()
    loans = df[df["Type"] == "Loan Taken"]["Amount"].sum() - \
            df[df["Type"] == "Loan Repayment"]["Amount"].sum()

    if welfare - loans < 1000:
        alerts.append(f"⚠️ Low Welfare Balance: {welfare - loans:,.0f}")

    for m in members:
        mdf = df[df["Name"] == m]
        bal = mdf[mdf["Type"] == "Loan Taken"]["Amount"].sum() - \
              mdf[mdf["Type"] == "Loan Repayment"]["Amount"].sum()

        last_pay = mdf[mdf["Type"] == "Loan Repayment"]["Date"].max()

        if bal > 0 and pd.notna(last_pay):
            if (today - last_pay).days > 30:
                alerts.append(f"🚨 {m} loan overdue")

        this_month = today.strftime("%B %Y")
        paid = mdf[
            (mdf["Type"] == "Welfare Amount") &
            (mdf["Date"].dt.strftime("%B %Y") == this_month)
        ]
        if paid.empty:
            alerts.append(f"📅 {m} missing welfare ({this_month})")

    return alerts

# ================= PDF =================
class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "Welfare Report", ln=True, align="C")

def member_pdf(name, df, balance):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 8, f"Member: {name}", ln=True)
    pdf.cell(0, 8, f"Loan Balance: {balance:,.0f}", ln=True)
    pdf.ln(5)

    for _, r in df.iterrows():
        pdf.cell(0, 6, f"{r['Date'].strftime('%d/%m/%Y')} | {r['Type']} | {r['Amount']}", ln=True)

    return pdf.output(dest="S").encode("latin-1")

# ================= LOGIN =================
def login():
    st.title("🔒 Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        users = load_users()
        match = users[
            (users["Username"] == u) &
            (users["Password"] == hash_password(p))
        ]
        if not match.empty:
            st.session_state.user = u
            st.session_state.role = match.iloc[0]["Role"]
            st.rerun()
        else:
            st.error("Invalid login")

# ================= MAIN =================
def app():
    st.sidebar.write(f"👤 {st.session_state.user}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    df = load_data()
    members = load_members()

    # SEARCH
    search = st.text_input("🔍 Search")
    if search:
        df = df[
            df["Name"].str.contains(search, case=False, na=False) |
            df["Notes"].str.contains(search, case=False, na=False) |
            df["Type"].str.contains(search, case=False, na=False)
        ]

    # ALERTS
    alerts = generate_alerts(df, members)
    if alerts:
        st.subheader("🚨 Alerts")
        for a in alerts:
            st.error(a)

    # DASHBOARD
    st.subheader("📊 Dashboard")
    welfare = df[df["Type"] == "Welfare Amount"]["Amount"].sum()
    loans = df[df["Type"] == "Loan Taken"]["Amount"].sum() - \
            df[df["Type"] == "Loan Repayment"]["Amount"].sum()
    fees = df[df["Type"].str.contains("Fee")]["Amount"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Welfare", f"{welfare:,.0f}")
    c2.metric("Loans", f"{loans:,.0f}")
    c3.metric("Fees", f"{fees:,.0f}")

    chart = pd.DataFrame({
        "Amount": [loans, welfare - loans, fees]
    }, index=["Loans", "Available", "Fees"])
    st.bar_chart(chart)

    # INDIVIDUAL
    st.subheader("👤 Member View")
    m = st.selectbox("Select Member", members)
    mdf = df[df["Name"] == m]
    bal = mdf[mdf["Type"] == "Loan Taken"]["Amount"].sum() - \
          mdf[mdf["Type"] == "Loan Repayment"]["Amount"].sum()

    if not mdf.empty:
        pdf = member_pdf(m, mdf, bal)
        st.download_button("📄 Download PDF", pdf, f"{m}.pdf")

        if bal > 0:
            msg = f"Hi {m}, your loan balance is {bal:,.0f}"
            st.link_button("💬 WhatsApp Reminder",
                           f"https://wa.me/?text={urllib.parse.quote(msg)}")

    st.dataframe(mdf, use_container_width=True)

    # EDIT (ADMIN)
    if st.session_state.role == "admin":
        st.subheader("✏️ Edit Data")
        edited = st.data_editor(df, num_rows="dynamic")
        mp = st.text_input("Master Password", type="password")
        if st.button("Save Changes"):
            if mp == MASTER_PASSWORD:
                save_data(edited)
                log_action(st.session_state.user, "Edited Database")
                st.success("Saved")
                st.rerun()
            else:
                st.error("Wrong password")

        if os.path.exists(AUDIT_FILE):
            st.subheader("🧾 Audit Log")
            st.dataframe(pd.read_csv(AUDIT_FILE))

# ================= START =================
if "user" not in st.session_state:
    login()
else:
    app()
