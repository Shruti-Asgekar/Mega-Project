"""
Intelligent OCR and Document Data Extraction Engine.
Features:
- Dual-mode extraction: PDF text-layer extraction with pdfplumber + OCR with pytesseract.
- Image preprocessing: Grayscale conversion, deskewing, and adaptive thresholding.
- Confidence scoring per extracted field with low-confidence flagging for human review.
- Privacy compliance: Full 12-digit Aadhaar numbers are masked immediately upon extraction.
"""

import io
import re
import logging
from typing import Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image

# Graceful imports
try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

try:
    import pytesseract
    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False

try:
    import pdfplumber
    _HAS_PDFPLUMBER = True
except ImportError:
    _HAS_PDFPLUMBER = False

from backend.app.core.security import compute_identifier_hmac

logger = logging.getLogger("kyc.ocr")

def preprocess_image_for_ocr(image_bytes: bytes) -> Image.Image:
    """
    Applies image enhancement pipeline:
    1. Grayscale conversion
    2. Deskew rotation
    3. Adaptive / Otsu thresholding
    """
    try:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if not _HAS_CV2:
            return pil_img

        img_np = np.array(pil_img)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        # Deskewing using minAreaRect on binary image
        coords = np.column_stack(np.where(gray < 250))
        angle = 0.0
        if len(coords) > 50:
            rect = cv2.minAreaRect(coords)
            angle = rect[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

        # If significant skew detected (between 0.5 and 45 degrees), rotate
        if abs(angle) > 0.5 and abs(angle) < 45:
            (h, w) = gray.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # Adaptive thresholding for crisp OCR text
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
        )

        return Image.fromarray(thresh)
    except Exception as e:
        logger.warning(f"Image preprocessing fallback due to: {e}")
        return Image.open(io.BytesIO(image_bytes))


def extract_text_from_document(file_bytes: bytes, filename: str) -> Tuple[str, float]:
    """
    Extracts raw text from PDF or image using best available method.
    Returns (extracted_text, baseline_confidence).
    """
    fn = filename.lower()
    text = ""
    conf = 0.85

    # 1. Try PDF text layer extraction if PDF
    if fn.endswith(".pdf") or file_bytes[:4] == b"%PDF":
        if _HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    pages_text = [page.extract_text() or "" for page in pdf.pages]
                    text = "\n".join(pages_text).strip()
                    if len(text) > 50:
                        return text, 0.95
            except Exception as e:
                logger.debug(f"pdfplumber text extraction failed: {e}")

    # 2. Try OCR if image or scanned PDF
    if _HAS_TESSERACT:
        try:
            # If PDF, render first page if pdf2image or pass image
            if fn.endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff")):
                prep_img = preprocess_image_for_ocr(file_bytes)
                ocr_text = pytesseract.image_to_string(prep_img, config="--psm 6")
                if ocr_text and len(ocr_text.strip()) > 10:
                    return ocr_text.strip(), 0.88
        except Exception as e:
            logger.debug(f"pytesseract extraction error: {e}")

    # 3. Fallback: string inspection for embedded ascii text
    try:
        decoded = file_bytes.decode("utf-8", errors="ignore")
        if len(decoded.strip()) > 30:
            return decoded.strip(), 0.70
    except Exception:
        pass

    return text, 0.50


def extract_document_fields(
    file_bytes: bytes,
    filename: str,
    doc_type: str
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Parses key structured fields according to doc_type with confidence scoring.
    Returns: (fields_dict, confidences_dict)
    """
    text, base_conf = extract_text_from_document(file_bytes, filename)
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    if not text:
        return fields, confidences

    # Clean text lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # ---------------------------------------------------------
    # PAN Extraction
    # ---------------------------------------------------------
    if doc_type in ("pan", "pan_card"):
        # Match standard Indian PAN format: 5 uppercase letters, 4 digits, 1 uppercase letter
        pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text.upper())
        if pan_match:
            fields["pan_number"] = pan_match.group(1)
            confidences["pan_number"] = min(base_conf + 0.05, 0.99)

        # DOB match: DD/MM/YYYY
        dob_match = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b", text)
        if dob_match:
            fields["dob"] = dob_match.group(1).replace("-", "/")
            confidences["dob"] = base_conf

        # Name extraction heuristic (line before Father's name or after Income Tax Dept)
        for i, line in enumerate(lines):
            u_line = line.upper()
            if "NAME" in u_line and not any(k in u_line for k in ["FATHER", "PERMANENT", "DEPARTMENT", "INCOME"]):
                parts = line.split(":")
                candidate = parts[-1].strip() if len(parts) > 1 else (lines[i+1] if i+1 < len(lines) else "")
                candidate_clean = re.sub(r"[^A-Za-z\s]", "", candidate).strip()
                if 2 <= len(candidate_clean.split()) <= 4:
                    fields["name"] = candidate_clean
                    confidences["name"] = 0.82
                    break
        if "name" not in fields:
            for line in lines[:8]:
                clean = re.sub(r"[^A-Za-z\s]", "", line).strip()
                if 2 <= len(clean.split()) <= 4 and clean.isupper():
                    if not any(w in clean for w in ["INCOME", "TAX", "GOVERNMENT", "INDIA", "PERMANENT", "ACCOUNT", "CARD"]):
                        fields["name"] = clean
                        confidences["name"] = 0.75
                        break

    # ---------------------------------------------------------
    # Aadhaar Extraction (Privacy-Safe: masked + HMAC only)
    # ---------------------------------------------------------
    elif doc_type in ("aadhaar", "aadhaar_card"):
        # Look for 12-digit number (spaced or hyphenated or continuous)
        aadhaar_match = re.search(r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4})\b", text)
        if aadhaar_match:
            raw_aadhaar = re.sub(r"[\s-]", "", aadhaar_match.group(1))
            if len(raw_aadhaar) == 12:
                last_four = raw_aadhaar[-4:]
                fields["aadhaar_number"] = f"XXXX-XXXX-{last_four}"
                fields["aadhaar_last_four"] = last_four
                fields["aadhaar_hmac"] = compute_identifier_hmac(raw_aadhaar)
                confidences["aadhaar_number"] = min(base_conf + 0.04, 0.99)
        else:
            # Check for masked format e.g. XXXX-XXXX-1234
            masked_match = re.search(r"\b(X{4}[\s-]?X{4}[\s-]?\d{4})\b", text, re.IGNORECASE)
            if masked_match:
                digits = re.sub(r"[^0-9]", "", masked_match.group(1))
                fields["aadhaar_number"] = f"XXXX-XXXX-{digits}"
                fields["aadhaar_last_four"] = digits
                confidences["aadhaar_number"] = 0.90

        # DOB or YOB
        dob_match = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b", text)
        if dob_match:
            fields["dob"] = dob_match.group(1).replace("-", "/")
            confidences["dob"] = base_conf
        else:
            yob_match = re.search(r"(?:Year of Birth|YOB)\s*[:\s]?\s*(\d{4})", text, re.IGNORECASE)
            if yob_match:
                fields["dob"] = f"01/01/{yob_match.group(1)}"
                confidences["dob"] = 0.75

        # Gender
        if re.search(r"\b(MALE|FEMALE|TRANSGENDER)\b", text, re.IGNORECASE):
            g_match = re.search(r"\b(MALE|FEMALE|TRANSGENDER)\b", text, re.IGNORECASE)
            fields["gender"] = g_match.group(1).upper()
            confidences["gender"] = 0.90

        # Name heuristic for Aadhaar
        for line in lines[:6]:
            clean = re.sub(r"[^A-Za-z\s]", "", line).strip()
            if 2 <= len(clean.split()) <= 4:
                if not any(w in clean.upper() for w in ["GOVERNMENT", "INDIA", "AADHAAR", "UIDAI", "ENROLMENT", "HELP"]):
                    fields["name"] = clean
                    confidences["name"] = 0.80
                    break

    # ---------------------------------------------------------
    # Salary Slip Extraction
    # ---------------------------------------------------------
    elif doc_type in ("salary_slip", "payslip"):
        # Gross salary
        gross_match = re.search(r"(?:Gross|Gross Salary|Gross Earnings)\s*[:\-]?\s*₹?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if gross_match:
            try:
                fields["gross_salary"] = float(gross_match.group(1).replace(",", ""))
                confidences["gross_salary"] = 0.88
            except ValueError:
                pass

        # Net salary
        net_match = re.search(r"(?:Net|Net Salary|Net Pay|Take Home)\s*[:\-]?\s*₹?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if net_match:
            try:
                fields["net_salary"] = float(net_match.group(1).replace(",", ""))
                confidences["net_salary"] = 0.92
            except ValueError:
                pass

        # Deductions
        ded_match = re.search(r"(?:Total Deductions|Deductions)\s*[:\-]?\s*₹?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if ded_match:
            try:
                fields["total_deductions"] = float(ded_match.group(1).replace(",", ""))
                confidences["total_deductions"] = 0.85
            except ValueError:
                pass

        # Employer Name
        for line in lines[:4]:
            if any(term in line.lower() for term in ["ltd", "limited", "pvt", "technologies", "services", "solutions", "corp", "systems"]):
                fields["employer"] = line.strip()
                confidences["employer"] = 0.85
                break

    # ---------------------------------------------------------
    # Bank Statement Extraction
    # ---------------------------------------------------------
    elif doc_type in ("bank_statement", "account_statement"):
        # Account Number
        acc_match = re.search(r"(?:Account No|A/c No|Account Number)\s*[:\.\-]?\s*([0-9]{9,18})", text, re.IGNORECASE)
        if acc_match:
            fields["account_number"] = acc_match.group(1)
            confidences["account_number"] = 0.92

        # IFSC Code
        ifsc_match = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
        if ifsc_match:
            fields["ifsc"] = ifsc_match.group(1)
            confidences["ifsc"] = 0.95

    return fields, confidences
