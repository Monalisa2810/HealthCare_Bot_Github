import re

prescription_text = """
Inj. Insulin Glargine (Lantus) 100 IU/ml 20 unit Subcutaneous After meals Every night at bedtime 50 days --- 1000
Inj. Insulin Lispro (Humalog) 100 IU/ml 60 unit Subcutaneous Before meals Thrice daily 18 days --- 1000
Tab. Metformin 500 mg 1 unit Oral After meals Twice daily 30 days --- 60
Tab. Telmisartan 40 mg 1 unit Oral Before meals Once a day 30 days --- 30
"""

pattern = r"(Inj\.|Tab\.)\s+([A-Za-z\s]+)(?:\([^)]+\))?\s*([\d]+ ?(?:mg|IU/ml)?)?.*?(Once a day|Twice daily|Thrice daily|Every night at bedtime)"

matches = re.findall(pattern, prescription_text)

for form, name, strength, freq in matches:
    print(f"Form: {form}, Name: {name.strip()}, Strength: {strength}, Frequency: {freq}")
