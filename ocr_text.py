import pytesseract
from PIL import Image

# If PATH works, this line is optional, but you can keep it for safety:
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Open an image (try with a clear text image first)
img = Image.open(r"C:\Users\MONALISA DAS\HealthCare_Bot\prescription_2025-09-02_16-20-2.png")

# Extract text
text = pytesseract.image_to_string(img)

print("📝 OCR Output:")
print(text)
