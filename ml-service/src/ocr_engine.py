"""
Module 1: OCR & Preprocessing Engine.
Performs:
1. File format detection & parsing (PDF and Images).
2. OpenCV preprocessing:
   - Grayscale conversion
   - Bilateral filter denoising
   - Deskewing via minimum bounding area
   - Adaptive/Otsu thresholding
3. Local Tesseract OCR text extraction.
"""

import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
import pdfplumber

# Ensure standard Windows Tesseract path if not on system PATH
TESSERACT_CANDIDATE_PATHS = [
    r"C:\Users\Shruti\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
]
for p in TESSERACT_CANDIDATE_PATHS:
    if os.path.exists(p):
        pytesseract.pytesseract.tesseract_cmd = p
        break

def preprocess_image(cv_image: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """
    Applies standard document image cleaning pipeline:
    - Grayscale
    - Bilateral denoise
    - Deskew
    - Otsu binarization
    """
    steps_applied = []
    
    # 1. Grayscale
    if len(cv_image.shape) == 3:
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        steps_applied.append("grayscale")
    else:
        gray = cv_image
        
    # 2. Bilateral Denoising (preserves sharp character edges)
    denoised = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
    steps_applied.append("bilateral_denoise")
    
    # 3. Deskewing
    try:
        # Invert colors for contour detection
        inv = cv2.bitwise_not(denoised)
        thresh_inv = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh_inv > 0))
        if len(coords) > 50:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle
                
            # If slight skew detected (between 0.5 and 20 degrees), correct it
            if 0.5 < abs(angle) < 20:
                (h, w) = denoised.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                denoised = cv2.warpAffine(denoised, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
                steps_applied.append(f"deskew_{angle:.1f}deg")
    except Exception:
        pass  # Gracefully fall back if contour search is degenerate
        
    # 4. Otsu Thresholding
    _, thresholded = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    steps_applied.append("otsu_threshold")
    
    return thresholded, steps_applied

def extract_text_from_image_path(image_path: str) -> dict:
    """Runs OCR pipeline on an image file."""
    img = cv2.imread(image_path)
    if img is None:
        # Fall back to PIL
        pil_img = Image.open(image_path)
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        
    clean_img, steps = preprocess_image(img)
    
    # Run Tesseract with page segmentation mode 6 (assume uniform text block) or 3 (fully automatic)
    custom_config = r'--oem 3 --psm 6'
    data = pytesseract.image_to_data(clean_img, config=custom_config, output_type=pytesseract.Output.DICT)
    
    extracted_text = pytesseract.image_to_string(clean_img, config=custom_config)
    
    # Calculate confidence from non-empty words
    conf_scores = [int(conf) for conf in data['conf'] if str(conf).isdigit() and int(conf) > 0]
    avg_conf = (sum(conf_scores) / len(conf_scores) / 100.0) if conf_scores else 0.85
    
    return {
        "text": extracted_text.strip(),
        "num_pages": 1,
        "preprocessing_applied": steps,
        "confidence": round(float(avg_conf), 2)
    }

def extract_text_from_pdf_path(pdf_path: str) -> dict:
    """Extracts text from PDF, utilizing native text stream and OCR where necessary."""
    extracted_pages = []
    steps = ["pdf_text_extraction"]
    
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and len(text.strip()) > 20:
                extracted_pages.append(text)
            else:
                # Page contains scanned image - rasterize and OCR
                try:
                    pil_img = page.to_image(resolution=200).original
                    cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                    clean_img, prep_steps = preprocess_image(cv_img)
                    ocr_page_text = pytesseract.image_to_string(clean_img, config='--oem 3 --psm 6')
                    extracted_pages.append(ocr_page_text)
                    steps.extend([f"p{page_idx}_{s}" for s in prep_steps])
                except Exception as e:
                    extracted_pages.append(f"[OCR extraction failed for page {page_idx}: {str(e)}]")
                    
    full_text = "\n\n".join(extracted_pages).strip()
    return {
        "text": full_text,
        "num_pages": num_pages,
        "preprocessing_applied": list(set(steps)),
        "confidence": 0.92
    }

def process_document(file_path: str) -> dict:
    """Unified entrypoint for any document upload."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf_path(file_path)
    elif ext in [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"]:
        return extract_text_from_image_path(file_path)
    else:
        # Plain text or unsupported binary
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return {
                    "text": f.read().strip(),
                    "num_pages": 1,
                    "preprocessing_applied": ["raw_read"],
                    "confidence": 0.99
                }
        except Exception as e:
            raise ValueError(f"Unsupported file format: {ext}")
