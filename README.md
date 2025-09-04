# HealthCare_Bot
Hackathon HealthCareBot
🏥 SmartCare Diabetes Assistant

A Streamlit-based healthcare assistant that helps patients with diabetes management by integrating:

🧑‍⚕️ Patient profiles with BMI and vitals tracking

📄 OCR-based prescription upload (extract meds automatically)

💊 Medicine tracker & dose reminders

📊 Real-time alerts with WhatsApp family notifications

🤖 Chatbot assistant (rule-based + OpenAI)

⏰ Demo reminder loop for presentations

🚀 Features
1. Patient Profiles

Create and manage user profiles

Save age, diabetes type, height, weight, contact info

Calculate BMI and show health status

2. Family Alerts

Add family contacts

Automatically notify them on:

Abnormal vitals

Multiple missed doses

3. Prescription Upload

Upload prescription image (JPG/PNG)

OCR (Tesseract) extracts medicine name, strength, and frequency

Auto-saves medicines into local DB

4. Medicine Tracker

View, edit, and delete medicines

Save logs of taken/missed doses

Track reminders

5. Vitals Tracking

Record blood sugar, HbA1c, BP, heart rate, SpO₂

Automatic classification:

✅ Normal ranges

⚠️ Alerts for high/low readings

Trigger WhatsApp alerts if abnormal

6. Chatbot

Rule-based Q&A for next doses and drug info

Optional AI chatbot powered by OpenAI (if API key set)

7. Demo Reminders

Fire reminders every 20s for presentation/demo purposes

Log “Taken” or “Missed”

Notify family after 3 consecutive misses

🛠️ Tech Stack

Frontend: Streamlit

Backend API: FastAPI (example at http://127.0.0.1:8000)

Database: SQLite3 (hc_demo.db)

OCR: Tesseract (pytesseract, with optional PDF2Image)

Notifications: WhatsApp via Twilio

AI Chat: OpenAI GPT models
