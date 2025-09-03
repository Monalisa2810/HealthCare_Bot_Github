# backend_api.py
import os, re, sqlite3
from contextlib import closing
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

DB_PATH = "med_dict.db"

# ---------------- DB ----------------
def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        # Users
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT, age INTEGER, diabetes_type TEXT,
            height_cm REAL, weight_kg REAL, contact TEXT
        )""")
        # Family
        c.execute("""CREATE TABLE IF NOT EXISTS family (
            id INTEGER PRIMARY KEY,
            user_id INTEGER, name TEXT, relation TEXT, phone TEXT
        )""")
        # Medications
        c.execute("""CREATE TABLE IF NOT EXISTS meds (
            id INTEGER PRIMARY KEY,
            user_id INTEGER, form TEXT, name TEXT,
            strength TEXT, frequency TEXT, reminder_times TEXT
        )""")
        # Logs
        c.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER, med_id INTEGER,
            status TEXT, note TEXT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        # Vitals
        c.execute("""CREATE TABLE IF NOT EXISTS vitals (
            id INTEGER PRIMARY KEY,
            user_id INTEGER, kind TEXT, value REAL,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()

init_db()

# ---------------- FastAPI ----------------
app = FastAPI(title="Diabetes Care Backend API")

# Allow CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Models ----------------
class UserCreate(BaseModel):
    name: str
    age: Optional[int] = 0
    diabetes_type: Optional[str] = ""
    height_cm: Optional[float] = 0.0
    weight_kg: Optional[float] = 0.0
    contact: Optional[str] = ""

class FamilyMemberCreate(BaseModel):
    user_id: int
    name: str
    relation: str
    phone: str

class MedCreate(BaseModel):
    user_id: int
    form: str
    name: str
    strength: Optional[str] = ""
    frequency: Optional[str] = "Once a day"
    times_csv: Optional[str] = "08:00"

class LogCreate(BaseModel):
    user_id: int
    med_id: int
    status: str
    note: Optional[str] = ""

class VitalCreate(BaseModel):
    user_id: int
    kind: str
    value: float

# ---------------- Routes ----------------
@app.get("/users")
def get_users():
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        users = c.execute("SELECT id, name FROM users").fetchall()
    return [{"id": u[0], "name": u[1]} for u in users]

@app.post("/users")
def add_user(u: UserCreate):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("""INSERT INTO users (name, age, diabetes_type, height_cm, weight_kg, contact)
                     VALUES (?,?,?,?,?,?)""",
                  (u.name, u.age, u.diabetes_type, u.height_cm, u.weight_kg, u.contact))
        conn.commit()
        uid = c.lastrowid
    return {"id": uid}

@app.get("/family/{user_id}")
def get_family(user_id: int):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        fam = c.execute("SELECT id, name, relation, phone FROM family WHERE user_id=?", (user_id,)).fetchall()
    return [{"id": f[0], "name": f[1], "relation": f[2], "phone": f[3]} for f in fam]

@app.post("/family")
def add_family(f: FamilyMemberCreate):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("INSERT INTO family (user_id, name, relation, phone) VALUES (?,?,?,?)",
                  (f.user_id, f.name, f.relation, f.phone))
        conn.commit()
        fid = c.lastrowid
    return {"id": fid}

@app.delete("/family/{fid}")
def delete_family(fid: int):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("DELETE FROM family WHERE id=?", (fid,))
        conn.commit()
    return {"status": "deleted"}

@app.get("/meds/{user_id}")
def get_meds(user_id: int):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        meds = c.execute("SELECT id, form, name, strength, frequency, reminder_times FROM meds WHERE user_id=?",(user_id,)).fetchall()
    return [{"id": m[0], "form": m[1], "name": m[2], "strength": m[3], "frequency": m[4], "times_csv": m[5]} for m in meds]

@app.post("/meds")
def add_meds(m: MedCreate):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("""INSERT INTO meds (user_id, form, name, strength, frequency, reminder_times)
                     VALUES (?,?,?,?,?,?)""",
                  (m.user_id, m.form, m.name, m.strength, m.frequency, m.times_csv))
        conn.commit()
        mid = c.lastrowid
    return {"id": mid}

@app.put("/meds/{mid}")
def edit_med(mid: int, m: MedCreate):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("""UPDATE meds SET form=?, name=?, strength=?, frequency=?, reminder_times=? WHERE id=?""",
                  (m.form, m.name, m.strength, m.frequency, m.times_csv, mid))
        conn.commit()
    return {"status": "updated"}

@app.delete("/meds/{mid}")
def delete_med(mid: int):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("DELETE FROM meds WHERE id=?", (mid,))
        conn.commit()
    return {"status": "deleted"}

@app.post("/logs")
def add_log(l: LogCreate):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("INSERT INTO logs (user_id, med_id, status, note) VALUES (?,?,?,?)",
                  (l.user_id, l.med_id, l.status, l.note))
        conn.commit()
        lid = c.lastrowid
    return {"id": lid}

@app.get("/logs/{user_id}")
def get_logs(user_id: int, limit: int = 50):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        logs = c.execute("""SELECT l.ts, m.name, l.status, l.note
                            FROM logs l LEFT JOIN meds m ON l.med_id=m.id
                            WHERE l.user_id=? ORDER BY l.ts DESC LIMIT ?""",
                         (user_id, limit)).fetchall()
    return [{"ts": l[0], "medicine": l[1], "status": l[2], "note": l[3]} for l in logs]

@app.post("/vitals")
def add_vitals(v: VitalCreate):
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("INSERT INTO vitals (user_id, kind, value) VALUES (?,?,?)",
                  (v.user_id, v.kind, v.value))
        conn.commit()
    return {"status": "ok"}

# ---------------- Real-Time Alerts ----------------
def check_abnormal_vitals(user_id: int):
    alerts = []
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("SELECT kind, value FROM vitals WHERE user_id=? ORDER BY ts DESC", (user_id,))
        vitals = {row[0]: row[1] for row in c.fetchall()}

        rbs = vitals.get("blood_sugar_random")
        if rbs is not None:
            if rbs > 130: alerts.append(f"Blood sugar HIGH: {rbs} mg/dl")
            elif rbs < 80: alerts.append(f"Blood sugar LOW: {rbs} mg/dl")

        hba = vitals.get("hba1c")
        if hba is not None and hba > 7:
            alerts.append(f"HbA1c HIGH: {hba}%")

        sys = vitals.get("bp_sys")
        dia = vitals.get("bp_dia")
        if sys and dia:
            if sys > 140 or dia > 90: alerts.append(f"Hypertension: {sys}/{dia} mmHg")
            elif sys < 90 or dia < 60: alerts.append(f"Low BP: {sys}/{dia} mmHg")

        hr = vitals.get("heart_rate")
        spo2 = vitals.get("spo2")
        if hr and hr > 120: alerts.append(f"High heart rate: {hr} bpm")
        if spo2 and spo2 < 90: alerts.append(f"Low SpO₂: {spo2}%")
    return alerts

def check_missed_meds(user_id: int, threshold=3):
    alerts = []
    with closing(db_conn()) as conn, closing(conn.cursor()) as c:
        c.execute("""SELECT m.name, COUNT(*) as missed
                     FROM logs l JOIN meds m ON l.med_id=m.id
                     WHERE l.user_id=? AND l.status='Missed'
                     GROUP BY m.name
                     HAVING missed>=?""", (user_id, threshold))
        for med_name, missed in c.fetchall():
            alerts.append(f"{med_name} missed {missed} times")
    return alerts

@app.get("/new_alerts")
def new_alerts(user_id: int = Query(...)):
    alerts = []
    alerts += check_abnormal_vitals(user_id)
    alerts += check_missed_meds(user_id)
    return {"alerts": alerts}
