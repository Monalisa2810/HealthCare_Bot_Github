# med_dict_setup.py
import sqlite3

conn = sqlite3.connect("med_dict.db")
c = conn.cursor()

c.execute("DROP TABLE IF EXISTS medicines")
c.execute("""
CREATE TABLE medicines (
    id INTEGER PRIMARY KEY,
    form TEXT,
    name TEXT,
    strength TEXT
)
""")

# Common diabetes medicines
meds = [
    ("Tab.", "Metformin", "500mg"),
    ("Tab.", "Glimepiride", "2mg"),
    ("Tab.", "Pioglitazone", "15mg"),
    ("Inj.", "Insulin Glargine", "20 units"),
    ("Inj.", "Insulin Lispro", "10 units"),
]

c.executemany("INSERT INTO medicines (form, name, strength) VALUES (?,?,?)", meds)

conn.commit()
conn.close()
print("✅ Medicine dictionary created in med_dict.db")
