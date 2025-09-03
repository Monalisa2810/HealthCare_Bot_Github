import os, re, sqlite3, time
from datetime import datetime
from contextlib import closing
import streamlit as st
from PIL import Image
import pytesseract
import pandas as pd
from typing import List, Dict, Optional
import time
import requests

# Get all users
resp = requests.get("http://127.0.0.1:8000/users")
users = resp.json()

# Add a new user
new_user = {"name": "Lisa", "age": 25}
resp = requests.post("http://127.0.0.1:8000/users", json=new_user)
user_id = resp.json()["id"]

try:
    resp = requests.get("http://127.0.0.1:8000/users")
    if resp.status_code == 200:
        st.success("✅ Backend connected! Users fetched successfully.")
        #st.write(resp.json())
    else:
        st.error(f"❌ Backend responded with status {resp.status_code}")
except Exception as e:
    st.error(f"❌ Cannot connect to backend: {e}")


# Optional PDF support
try:
    from pdf2image import convert_from_path
    PDF_OK = True
except Exception:
    PDF_OK = False

# Optional Twilio for real family alerts
TWILIO_READY = False
try:
    from dotenv import load_dotenv
    load_dotenv()
    from twilio.rest import Client
    TW_SID = os.getenv("TWILIO_SID")
    TW_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TW_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
    if TW_SID and TW_TOKEN and TW_FROM:
        TWILIO_READY = True
        tw_client = Client(TW_SID, TW_TOKEN)
except Exception:
    TWILIO_READY = False



# ---- Windows: set tesseract path if needed ----
DEFAULT_TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.name == "nt" and os.path.exists(DEFAULT_TESS):
    pytesseract.pytesseract.tesseract_cmd = DEFAULT_TESS

DB_PATH = "hc_demo.db"

# ---------------- DB helpers ----------------
def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT, age INTEGER, diabetes_type TEXT,
            height_cm REAL, weight_kg REAL, contact TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS family (
            id INTEGER PRIMARY KEY,
            user_id INTEGER, name TEXT, relation TEXT, phone TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS meds (
            id INTEGER PRIMARY KEY,
            user_id INTEGER, form TEXT, name TEXT,
            strength TEXT, frequency TEXT, reminder_times TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER, med_id INTEGER,
            status TEXT, note TEXT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        # ---------- NEW TABLE ----------
        c.execute("""CREATE TABLE IF NOT EXISTS vitals (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            kind TEXT,
            value REAL,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        # -------------------------------
        conn.commit()


init_db()

# ------------- Utils -------------


def bmi_status(height_cm: float, weight_kg: float) -> Optional[str]:
    try:
        h = height_cm / 100.0
        bmi = weight_kg / (h*h)
        if bmi < 18.5: return f"Underweight (BMI {bmi:.1f})"
        if bmi < 25:   return f"Normal (BMI {bmi:.1f})"
        if bmi < 30:   return f"Overweight (BMI {bmi:.1f})"
        return f"Obese (BMI {bmi:.1f})"
    except Exception:
        return None

def classify_control(random_blood_sugar: Optional[float]=None,
                     hba1c: Optional[float]=None,
                     bp_sys: Optional[float]=None,
                     bp_dia: Optional[float]=None,
                     heart_rate: Optional[float]=None,
                     spo2: Optional[float]=None) -> List[str]:
    alerts = []
    if heart_rate is not None and spo2 is not None:
        if heart_rate > 120 or spo2 < 90: alerts.append("⚠️ Acute risk: HR>120 or SpO2<90")
        else: alerts.append("✅ HR/SpO2 ok")
    if random_blood_sugar is not None:
        if random_blood_sugar > 130: alerts.append("⚠️ Blood sugar HIGH")
        elif random_blood_sugar < 80: alerts.append("⚠️ Blood sugar LOW")
        else: alerts.append("✅ Blood sugar normal")
    if hba1c is not None:
        if hba1c < 5.7: alerts.append("✅ HbA1c controlled (HbA1c < 5.7%)")
        elif hba1c < 6.4: alerts.append("⚠️ Prediabetes (HbA1c > 5.7% && HbA1c < 6.4%)")
        else: alerts.append("⚠️ Poor long-term control (HbA1c > 6.4%)")
    if bp_sys is not None and bp_dia is not None:
        if bp_sys > 140 or bp_dia > 90: alerts.append("⚠️ Hypertension")
        elif bp_sys < 90 or bp_dia < 60: alerts.append("⚠️ Low BP")
        else: alerts.append("✅ BP normal")
    return alerts

def send_family_whatsapp(numbers: List[str], message: str):
    if not numbers: return
    if TWILIO_READY:
        for n in numbers:
            try:
                tw_client.messages.create(
                    body=message, 
                    from_=TW_FROM, 
                    to=f"whatsapp:{n}" if not n.startswith("whatsapp:") else n
                )
            except Exception as e:
                print("Twilio send error:", e)
    else:
        # Demo: just print
        print("Family alert (mock):", message, "->", numbers)


# ---------------- OCR Parsing ----------------
frequency_to_times = {
    "Once a day": ["08:00"],
    "Twice daily": ["08:00","20:00"],
    "Thrice daily": ["08:00","14:00","20:00"],
    "Every night at bedtime": ["22:00"]
}

# Updated pattern to include Tab., Cap., Inj., Syrup, Drops, etc.
RX_PATTERN = re.compile(
    r"(Tab\.|Caps\.|Inj\.|Syrup|Drops|mj\.)\s*"          # Form
    r"([A-Za-z0-9\s]+?)"                                  # Name (non-greedy)
    r"(?:\s*([\d\.]+\s*(?:mg|ng|IU/ml|units?|ml))?)?"     # Strength (optional)
    r".*?"                                                # Anything in between
    r"(once daily|twice daily|thrice daily|every night at bedtime|at bedtime|before breakfast|after meals|after breakfast|after lunch|after dinner)",
    flags=re.IGNORECASE
)

def parse_prescription_text(text: str):
    items = []
    for line in text.splitlines():
        # ---------- FIXED: removed 'flags' from search because RX_PATTERN is already compiled ----------
        m = RX_PATTERN.search(line)  # <-- fixed line
        if m:
            form, name, strength, freq = m.groups()
            norm = next((f for f in frequency_to_times if f.lower() in freq.lower()), "Once a day")
            times = ",".join(frequency_to_times[norm])
            items.append({
                "form": form,
                "name": name.strip(),
                "strength": strength.strip() if strength else "",
                "frequency": norm,
                "times_csv": times
            })
    return items

def ocr_any(file_bytes):
    img = Image.open(file_bytes)
    return pytesseract.image_to_string(img)

# ---------------- UI ----------------
st.set_page_config(page_title="SmartCare Diabetes Assistant", page_icon="💉", layout="wide")
st.title("🏥 SmartCare Diabetes Assistant")

# ---------------- User Selection ----------------
with closing(db_conn()) as conn, closing(conn.cursor()) as c:
    users = c.execute("SELECT id, name FROM users").fetchall()
user_names = [u[1] for u in users]
user_ids = [u[0] for u in users]

st.sidebar.subheader("Select or Add User")
selected_user = st.sidebar.selectbox("Choose User", ["--New User--"] + user_names)

if selected_user == "--New User--":
    new_name = st.sidebar.text_input("Enter name for new user")
    if st.sidebar.button("Add User") and new_name.strip():
        with closing(db_conn()) as conn, closing(conn.cursor()) as c:
            c.execute("INSERT INTO users (name) VALUES (?)", (new_name.strip(),))
            conn.commit()
            USER_ID = c.lastrowid  # <-- make sure USER_ID is set
            st.rerun()
else:
    USER_ID = user_ids[user_names.index(selected_user)]

tabs = st.tabs(["⚕ Profile", "📄 Prescription Upload", "💊 Meds & Tracker", "🤖 Chatbot", "⏰ Demo Reminders"])
# --------- Profile Tab ---------
with tabs[0]:
    st.subheader("👤 Patient Profile")
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("SELECT name, age, diabetes_type, height_cm, weight_kg, contact FROM users WHERE id=?", (USER_ID,))
        row = c.fetchone() or ("", None, "", None, None, "")
    name = st.text_input("Name", row[0] or "")
    age = st.number_input("Age", min_value=0, max_value=120, value=int(row[1] or 0))
    dtype = st.selectbox("Diabetes Type", ["", "Type 1", "Type 2", "Gestational"], index=(["","Type 1","Type 2","Gestational"].index(row[2]) if row[2] in ["","Type 1","Type 2","Gestational"] else 0))
    height = st.number_input("Height (cm)", min_value=0.0, value=float(row[3] or 0.0), step=0.1)
    weight = st.number_input("Weight (kg)", min_value=0.0, value=float(row[4] or 0.0), step=0.1)
    contact = st.text_input("Primary Contact (phone/WhatsApp)", row[5] or "")
    if st.button("Save Profile", type="primary"):
        with closing(db_conn()) as conn, closing(conn.cursor()) as c:
            c.execute("""UPDATE users SET name=?, age=?, diabetes_type=?, height_cm=?, weight_kg=?, contact=? WHERE id=?""",
                      (name, age, dtype, height, weight, contact, USER_ID))
            conn.commit()
        st.success("Profile saved.")
    if height and weight:
        st.info(bmi_status(height, weight))

    st.divider()
    st.subheader("👨‍👩‍👧‍👦 Family Members")
    fam_name = st.text_input("Family member name")
    fam_rel = st.text_input("Relation")
    fam_phone = st.text_input("Phone (WhatsApp)")
    if st.button("Add Family Member"):
        with closing(db_conn()) as conn, closing(conn.cursor()) as c:
            c.execute("INSERT INTO family (user_id, name, relation, phone) VALUES (?,?,?,?)",
                      (USER_ID, fam_name, fam_rel, fam_phone))
            conn.commit()
        st.success("Family member added.")
    


    # Show family with delete option
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        fams = c.execute("SELECT id, name, relation, phone FROM family WHERE user_id=?", (USER_ID,)).fetchall()
    for fid, fname, frel, fphone in fams:
        col1, col2, col3, col4 = st.columns([3,3,3,1])
        col1.write(fname)
        col2.write(frel)
        col3.write(fphone)
        if col4.button("❌", key=f"famdel_{fid}"):
            with closing(db_conn()) as conn, closing(conn.cursor()) as c:
                c.execute("DELETE FROM family WHERE id=?", (fid,))
                conn.commit()
            st.success(f"Deleted {fname}")
            st.rerun()

# --------- Prescription Upload Tab ---------
with tabs[1]:
    st.subheader("Upload Prescription (Image)")
    up = st.file_uploader("Choose file", type=["png","jpg","jpeg"])
    if up is not None:
        text = ocr_any(up)
        st.text_area("OCR Text", text, height=200)
        parsed = parse_prescription_text(text)
        if parsed:
            st.success("Parsed medicines:")
            for m in parsed:
                st.write(f"- {m['form']} {m['name']} {m['strength']} — {m['frequency']} → {m['times_csv']}")
            if st.button("Save to My Medicines"):
                if USER_ID is None:
                    st.error("Please select a user first!")
                else:
                    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
                        for m in parsed:
                            c.execute("""INSERT INTO meds (user_id, form, name, strength, frequency, reminder_times)
                                         VALUES (?,?,?,?,?,?)""",
                                      (USER_ID, m["form"], m["name"], m["strength"], m["frequency"], m["times_csv"]))
                        conn.commit()
                    st.success("Saved to meds.")
                    st.rerun()  # <-- force refresh so Tabs[2] sees new meds

        else:
            st.warning("No medicines matched our pattern. Adjust regex if needed.")

# --------- Meds & Tracker Tab ---------
with tabs[2]:
    st.subheader("My Medicines (Editable)")
    with closing(db_conn()) as conn:
        meds_df = pd.read_sql_query(
            "SELECT id, form, name, strength, frequency, reminder_times FROM meds WHERE user_id=?",
            conn,
            params=(USER_ID,)
        )
    st.dataframe(meds_df, use_container_width=True)

    # Edit/Delete meds
    for idx, row in meds_df.iterrows():
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2,2,2,2,2,2,1])
        col1.write(row['form'])
        col2.write(row['name'])
        col3.write(row['strength'])
        col4.write(row['frequency'])
        col5.write(row['reminder_times'])
        if col6.button("Edit", key=f"edit_{row['id']}"):
            st.session_state.edit_med_id = row['id']
            st.session_state.edit_form = row['form']
            st.session_state.edit_name = row['name']
            st.session_state.edit_strength = row['strength']
            st.session_state.edit_freq = row['frequency']
            st.session_state.edit_times = row['reminder_times']
            st.rerun()
        if col7.button("❌", key=f"meddel_{row['id']}"):
            with closing(db_conn()) as conn, closing(conn.cursor()) as c:
                c.execute("DELETE FROM meds WHERE id=?", (row['id'],))
                conn.commit()
            st.success(f"Deleted {row['name']}")
            st.rerun()

    # Edit med form
    if 'edit_med_id' in st.session_state:
        st.divider()
        st.subheader("Edit Medicine")
        edit_form = st.text_input("Form", st.session_state.edit_form)
        edit_name = st.text_input("Name", st.session_state.edit_name)
        edit_strength = st.text_input("Strength", st.session_state.edit_strength)
        edit_freq = st.selectbox("Frequency", list(frequency_to_times.keys()), index=list(frequency_to_times.keys()).index(st.session_state.edit_freq))
        edit_times = ",".join(frequency_to_times[edit_freq])
        if st.button("Save Changes"):
            with closing(db_conn()) as conn, closing(conn.cursor()) as c:
                c.execute("""UPDATE meds SET form=?, name=?, strength=?, frequency=?, reminder_times=? WHERE id=?""",
                          (edit_form, edit_name, edit_strength, edit_freq, edit_times, st.session_state.edit_med_id))
                conn.commit()
            st.success("Medicine updated.")
            del st.session_state['edit_med_id']
            st.rerun()

        st.divider()
    st.subheader("Add Latest Vitals (to evaluate control)")
    col1, col2, col3 = st.columns(3)
    with col1:
        rbs = st.number_input("Random Blood Sugar (mg/dl)", min_value=0.0, step=1.0)
        hba = st.number_input("HbA1c (%)", min_value=0.0, step=0.1, format="%.1f")
    with col2:
        sys = st.number_input("BP Systolic (mmHg)", min_value=0.0, step=1.0)
        dia = st.number_input("BP Diastolic (mmHg)", min_value=0.0, step=1.0)
    with col3:
        hr  = st.number_input("Heart Rate (bpm)", min_value=0.0, step=1.0)
        spo = st.number_input("SpO₂ (%)", min_value=0.0, step=1.0)

    def alert_family_if_vitals_abnormal(user_id, alerts):
        if not alerts: return
        with closing(db_conn()) as conn, closing(conn.cursor()) as c:
            c.execute("SELECT phone FROM family WHERE user_id=?", (user_id,))
            phones = [r[0] for r in c.fetchall() if r[0]]
        if phones:
            msg = f"⚠️ ALERT: Abnormal vitals detected: {', '.join(alerts)}"
            send_family_whatsapp(phones, msg)

    if st.button("Save Vitals & Classify"):
        with closing(db_conn()) as conn, closing(conn.cursor()) as c:
            if rbs: c.execute("INSERT INTO vitals (user_id, kind, value) VALUES (?,?,?)", (USER_ID, "blood_sugar_random", rbs))
            if hba: c.execute("INSERT INTO vitals (user_id, kind, value) VALUES (?,?,?)", (USER_ID, "hba1c", hba))
            if sys: c.execute("INSERT INTO vitals (user_id, kind, value) VALUES (?,?,?)", (USER_ID, "bp_sys", sys))
            if dia: c.execute("INSERT INTO vitals (user_id, kind, value) VALUES (?,?,?)", (USER_ID, "bp_dia", dia))
            if hr:  c.execute("INSERT INTO vitals (user_id, kind, value) VALUES (?,?,?)", (USER_ID, "heart_rate", hr))
            if spo: c.execute("INSERT INTO vitals (user_id, kind, value) VALUES (?,?,?)", (USER_ID, "spo2", spo))
            conn.commit()
        msgs = classify_control(
            random_blood_sugar = rbs if rbs>0 else None,
            hba1c = hba if hba>0 else None,
            bp_sys = sys if sys>0 else None,
            bp_dia = dia if dia>0 else None,
            heart_rate = hr if hr>0 else None,
            spo2 = spo if spo>0 else None
        )

        abnormal_alerts = [m for m in msgs if "⚠️" in m]
        for m in msgs:
            st.write(m)

         # Alert family immediately under the tab
        if abnormal_alerts:
            alert_family_if_vitals_abnormal(USER_ID, abnormal_alerts)
            st.error("⚠️ Family notified due to abnormal vitals!")

    st.divider()
    st.subheader("Dose Logs")
    with closing(db_conn()) as conn:
        logs_df = __import__("pandas").read_sql_query("""
            SELECT l.ts, m.name AS medicine, l.status, l.note
            FROM logs l LEFT JOIN meds m ON l.med_id=m.id
            WHERE l.user_id=?
            ORDER BY l.ts DESC LIMIT 200
        """, conn, params=(USER_ID,))
    st.dataframe(logs_df, use_container_width=True)
    st.subheader("Real-Time Alerts")
    if "last_alert_check" not in st.session_state:
        st.session_state.last_alert_check = 0

    now = time.time()
    if now - st.session_state.last_alert_check > 20:
        st.session_state.last_alert_check = now
        try:
            resp = requests.get(f"http://127.0.0.1:8000/new_alerts?user_id={USER_ID}")
            alerts = resp.json().get("alerts", [])
            for a in alerts:
                st.toast(f"⚠️ {a}")
        except Exception as e:
            st.warning(f"Alert check failed: {e}")



# --------- Chatbot Tab ---------
with tabs[3]:
    st.subheader("Chat with your Assistant")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    q = st.text_input("💬 Your message", key="chat_input")

    # Load OpenAI
    OPENAI_KEY = os.getenv("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", None)
    ai_ready = False
    if OPENAI_KEY:
        try:
            import openai
            openai.api_key = OPENAI_KEY
            ai_ready = True
        except Exception as e:
            st.warning(f"AI not available: {e}")
            ai_ready = False

    def rule_based_answer(query: str) -> str:
        ql = query.lower()
        with closing(db_conn()) as conn, closing(conn.cursor()) as c:
            if "next" in ql and ("dose" in ql or "dosage" in ql or "insulin" in ql):
                c.execute("SELECT name, reminder_times FROM meds WHERE user_id=?", (USER_ID,))
                meds = c.fetchall()
                if not meds: return "No medicines saved yet."
                now = datetime.now().strftime("%H:%M")
                upcoming = []
                for name, times_csv in meds:
                    for t in times_csv.split(","):
                        if t.strip() >= now:
                            upcoming.append(f"{name} at {t.strip()}")
                return "Next doses:\n- " + "\n- ".join(upcoming) if upcoming else "All doses for today are done."
            if "metformin" in ql:
                return "Metformin helps lower blood sugar. Read more: https://medlineplus.gov/druginfo/meds/a682611.html"
            if "diabetes" in ql:
                return "Learn about diabetes: https://www.nhs.uk/conditions/diabetes/"
            return "I can help with next doses, drug info, or diabetes basics."

    def ai_answer(history):
        messages = [{"role":"system","content":"You are a friendly diabetes care assistant. Answer clearly and provide reliable medical links where possible."}]
        for role, msg in history:
            messages.append({"role":"user" if role=="user" else "assistant", "content": msg})
        resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
        return resp.choices[0].message.content

    if st.button("Send"):
        if q.strip():
            st.session_state.chat_history.append(("user", q))
            if ai_ready:
                ans = ai_answer(st.session_state.chat_history)
            else:
                ans = rule_based_answer(q)
            st.session_state.chat_history.append(("bot", ans))

    for role, msg in st.session_state.chat_history:
        if role == "user":
            st.markdown(f" **You:** {msg}")
        else:
            st.markdown(f" **Bot:** {msg}")

# --------- Demo Reminders Tab ---------
with tabs[4]:
    st.subheader("Demo Reminders (20s loop for presentation)")
    st.caption("Click start to trigger reminder events every ~20 seconds. Respond Taken/Missed to simulate adherence and family alerts after 3 misses.")
    if "demo_running" not in st.session_state:
        st.session_state.demo_running = False
    if "last_reminder" not in st.session_state:
        st.session_state.last_reminder = None

    def fire_demo_reminder():
        # pick first med
        with closing(db_conn()) as conn, closing(conn.cursor()) as c:
            c.execute("SELECT id, name, strength FROM meds WHERE user_id=? ORDER BY id ASC LIMIT 1", (USER_ID,))
            med = c.fetchone()
            if not med: return "No medicines saved."
            med_id, mname, mstr = med
            c.execute("INSERT INTO logs (user_id, med_id, status, note) VALUES (?,?,?,?)",
                      (USER_ID, med_id, "REMINDER", f"Please take {mname} {mstr} now"))
            conn.commit()
        st.session_state.last_reminder = (med_id, mname, mstr, datetime.now().strftime("%H:%M:%S"))
        return f"⏰ Reminder: Take {mname} {mstr} now."

    colA, colB = st.columns(2)
    with colA:
        if not st.session_state.demo_running:
            if st.button("▶️ Start demo reminders"):
                st.session_state.demo_running = True
                st.success("Demo reminders running. A reminder will fire every ~20s (simulate).")
        else:
            if st.button("⏹ Stop demo reminders"):
                st.session_state.demo_running = False
                st.warning("Demo reminders stopped.")

    with colB:
        if st.button("⏰ Fire a reminder now"):
            msg = fire_demo_reminder()
            st.write(msg)

    if st.session_state.demo_running:
        # time-based auto trigger every ~20s using a timestamp key
        now_sec = int(time.time())
        if now_sec % 20 == 0:
            st.toast(fire_demo_reminder())

    st.divider()
    st.subheader("Respond to the last reminder")
    if st.session_state.last_reminder:
        med_id, mname, mstr, ts = st.session_state.last_reminder
        st.write(f"Last reminder: **{mname} {mstr}** at {ts}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Taken"):
                with closing(db_conn()) as conn, closing(conn.cursor()) as c:
                    c.execute("INSERT INTO logs (user_id, med_id, status, note) VALUES (?,?,?,?)",
                              (USER_ID, med_id, "Taken", "User confirmed"))
                    conn.commit()
                st.success("Logged as Taken.")
        with c2:
            if st.button("❌ Missed"):
                with closing(db_conn()) as conn, closing(conn.cursor()) as c:
                    c.execute("INSERT INTO logs (user_id, med_id, status, note) VALUES (?,?,?,?)",
                              (USER_ID, med_id, "Missed", "User missed"))
                    conn.commit()
                # count misses for this med
                with closing(db_conn()) as conn, closing(conn.cursor()) as c:
                    c.execute("SELECT COUNT(*) FROM logs WHERE user_id=? AND med_id=? AND status='Missed'", (USER_ID, med_id))
                    misses = c.fetchone()[0]
                if misses >= 3:
                    # collect family phones
                    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
                        c.execute("SELECT phone FROM family WHERE user_id=?", (USER_ID,))
                        fam_nums = [r[0] for r in c.fetchall() if r[0]]
                    alert_msg = f"⚠️ ALERT: {name or 'Patient'} has missed {mname} dose 3+ times. Please check in."
                    send_family_whatsapp(fam_nums, alert_msg)
                    st.error("Family notified.")
                else:
                    st.warning(f"Missed logged. Current misses for this med: {misses}")

    st.divider()
    st.subheader("Event Log (latest)")
    with closing(db_conn()) as conn:
        demo_df = __import__("pandas").read_sql_query("""
            SELECT ts, status, COALESCE(m.name,'') AS medicine, note
            FROM logs l LEFT JOIN meds m ON l.med_id=m.id
            WHERE l.user_id=?
            ORDER BY ts DESC LIMIT 30
        """, conn, params=(USER_ID,))
    st.dataframe(demo_df, use_container_width=True)
