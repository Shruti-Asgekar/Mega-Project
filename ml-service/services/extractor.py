"""
Text and Field Extraction Service (ml-service).
Uses pdfplumber for digital text layer, with graceful fallback if pytesseract is absent.
Extracts structured ExtractedFields from KYC documents.
"""

import io
import os
import re
from typing import Optional, Dict, Any, List
import pdfplumber
from PIL import Image
from backend.app.core.contracts import ExtractedFields, Transaction

# Check Tesseract availability
TESSERACT_AVAILABLE = False
try:
    import pytesseract
    # Candidate windows paths
    for p in [r"C:\Users\Shruti\AppData\Local\Programs\Tesseract-OCR\tesseract.exe", r"C:\Program Files\Tesseract-OCR\tesseract.exe"]:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            break
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except Exception:
    TESSERACT_AVAILABLE = False

def extract_raw_text(file_bytes: bytes, filename: str) -> str:
    """Extracts raw text from PDF or image using available engines."""
    ext = os.path.splitext(filename)[1].lower() if filename else ""
    text_content = ""

    if ext == ".pdf" or file_bytes[:4] == b"%PDF":
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text() or ""
                    text_content += txt + "\n"
        except Exception:
            pass

    if len(text_content.strip()) < 20 and TESSERACT_AVAILABLE:
        try:
            # Fall back to image OCR if digital text is empty
            if ext != ".pdf" and file_bytes[:4] != b"%PDF":
                pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
                text_content = pytesseract.image_to_string(pil_img)
        except Exception:
            pass

    return text_content

def parse_fields_from_text(raw_text: str, doc_type: str = "generic") -> ExtractedFields:
    """Extracts structured ExtractedFields from raw text using pattern recognition."""
    fields = ExtractedFields(doc_type=doc_type)
    text_lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    # 1. PAN Pattern
    pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", raw_text)
    if pan_match:
        fields.pan_number = pan_match.group(1)

    # 2. Aadhaar Pattern
    aadhaar_match = re.search(r"\b([2-9][0-9]{3}[\s-]?[0-9]{4}[\s-]?[0-9]{4})\b", raw_text)
    if aadhaar_match:
        fields.aadhaar_number = re.sub(r"\D", "", aadhaar_match.group(1))

    # 3. IFSC Pattern
    ifsc_match = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", raw_text)
    if ifsc_match:
        fields.ifsc = ifsc_match.group(1)

    # 4. DOB Pattern
    dob_match = re.search(r"(?:DOB|Date of Birth|Birth Date)[:\s]+([0-9]{2}[/-][0-9]{2}[/-][0-9]{4}|[0-9]{4}[/-][0-9]{2}[/-][0-9]{2})", raw_text, re.IGNORECASE)
    if dob_match:
        fields.dob = dob_match.group(1)

    # 5. Name Pattern
    name_match = re.search(r"(?:Name|Employee Name|Account Name|Cardholder)[:\s]+([A-Za-z\s\.]+)", raw_text, re.IGNORECASE)
    if name_match:
        cleaned_name = name_match.group(1).split("\n")[0].strip()
        if len(cleaned_name) > 2 and len(cleaned_name) < 40:
            fields.name = cleaned_name

    # 6. Phone Pattern
    phone_match = re.search(r"(?:Phone|Mobile|Contact)[:\s]*(\+?91[\s-]?)?([6-9]\d{9})\b", raw_text, re.IGNORECASE)
    if phone_match:
        fields.phone = phone_match.group(2)

    # 7. Account Number Pattern
    acc_match = re.search(r"(?:Account\s*(?:Number|No\.?)?|A/C|Acc)[:\s#]+(\d{9,18})\b", raw_text, re.IGNORECASE)
    if acc_match:
        fields.account_number = acc_match.group(1)

    # 8. Salary Slip Amounts
    gross_match = re.search(r"(?:Gross Salary|Gross Earnings|Total Earnings|Gross)[:\s_]*(?:Rs\.?|₹)?\s*([0-9,]+(?:\.[0-9]{2})?)", raw_text, re.IGNORECASE)
    if gross_match:
        fields.gross_salary = float(gross_match.group(1).replace(",", ""))

    ded_match = re.search(r"(?:Total Deductions|Deductions)[:\s_]*(?:Rs\.?|₹)?\s*([0-9,]+(?:\.[0-9]{2})?)", raw_text, re.IGNORECASE)
    if ded_match:
        fields.total_deductions = float(ded_match.group(1).replace(",", ""))

    net_match = re.search(r"(?:Net\s*Salary(?:\s*Payable)?|Net\s*Pay|Take\s*Home)[:\s_]*(?:Rs\.?|₹)?\s*([0-9,]+(?:\.[0-9]{2})?)", raw_text, re.IGNORECASE)
    if net_match:
        fields.net_salary = float(net_match.group(1).replace(",", ""))

    # 9. Employer
    emp_match = re.search(r"(?:Employer|Company)[:\s]+([A-Za-z0-9\s\.,&]+)", raw_text, re.IGNORECASE)
    if emp_match:
        fields.employer = emp_match.group(1).split("\n")[0].strip()

    # 10. Address
    addr_match = re.search(r"(?:Address|Permanent Address)[:\s]+([^\n]+(?:\n[^\n]+)?)", raw_text, re.IGNORECASE)
    if addr_match:
        fields.address = " ".join(addr_match.group(1).split()).strip()

    return fields
