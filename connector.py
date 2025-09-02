import re
import sqlite3
import schedule
import time

# -------------------------
# Step 1: Prescription Text (replace later with OCR output)
# -------------------------
prescription_text = """
Inj. Insulin Glargine (Lantus) 100 IU/ml 20 unit Subcutaneous After meals Every night at bedtime 50 days --- 1000
Inj. Insulin Lispro (Humalog) 100 IU/ml 60 unit Subcutaneous Before meals Thrice daily 18 days --- 1000
Tab. Metformin 500 mg 1 unit Oral After meals Twice daily 30 days --- 60
Tab. Telmisartan 40 mg 1 unit Oral Before meals Once a day 30 days --- 30
"""

# -------------------------
# Step 2: Regex to Extract Medicines
# -------------------------
pattern = r"(Inj\.|Tab\.)\s+([A-Za-z\s]+)(?:\([^)]+\))?\s*([\d]+ ?(?:mg|IU/ml)?)?.*?(Once a day|Twice daily|Thrice daily|Every night at bedtime)"
matches = re.findall(pattern, prescription_text)

# -------------------------
# Step 3: Frequency → Reminder Times Mapping
# -------------------------
frequency_to_times = {
    "Once a day": ["08:00"],
    "Twice daily": ["08:00", "20:00"],
    "Thrice daily": ["08:00", "14:00", "20:00"],
    "Every night at bedtime": ["22:00"]
}

# -------------------------
# Step 4: Setup SQLite Database (Recreate Table Fresh)
# -------------------------
conn = sqlite3.connect("meds.db")
c = conn.cursor()

c.execute("DROP TABLE IF EXISTS meds")  # reset old schema
c.execute("""
CREATE TABLE meds (
    id INTEGER PRIMARY KEY,
    form TEXT,
    name TEXT,
    strength TEXT,
    frequency TEXT,
    reminder_times TEXT
)
""")

c.execute("DROP TABLE IF EXISTS logs")  # extra table for tracking taken/missed
c.execute("""
CREATE TABLE logs (
    id INTEGER PRIMARY KEY,
    med_id INTEGER,
    status TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Insert extracted meds
for form, name, strength, freq in matches:
    times = ",".join(frequency_to_times.get(freq, ["08:00"]))
    c.execute("INSERT INTO meds (form, name, strength, frequency, reminder_times) VALUES (?, ?, ?, ?, ?)",
              (form, name.strip(), strength, freq, times))

conn.commit()
conn.close()

print("✅ Medicines saved to database")

# -------------------------
# Step 5: Scheduler to Send Reminders
# -------------------------
def send_reminder(med_name, strength, reminder_time):
    print(f"⏰ Reminder: Take {med_name} ({strength}) at {reminder_time}")
    # later replace with WhatsApp send function

def load_meds_and_schedule():
    conn = sqlite3.connect("meds.db")
    c = conn.cursor()
    c.execute("SELECT id, name, strength, reminder_times FROM meds")
    meds = c.fetchall()
    conn.close()

    for med_id, name, strength, reminder_times in meds:
        times = reminder_times.split(",")
        for reminder_time in times:
            schedule.every().day.at(reminder_time).do(send_reminder, name, strength, reminder_time)

# Load into scheduler
load_meds_and_schedule()
print("✅ Reminder system started... waiting for scheduled times.")

# Run forever
while True:
    schedule.run_pending()
    time.sleep(1)
