"""
Module 2 Blur and Quality Detection Service.
Uses OpenCV Laplacian variance to score image sharpness.
Text-layer PDFs automatically count as OK.
"""

import io
import os
import cv2
import numpy as np
from PIL import Image
import pdfplumber

def calculate_blur_score(
    file_bytes: bytes,
    filename: str = "",
    blur_threshold: float = 100.0
) -> dict:
    """
    Computes blur score.
    Returns:
        blur_score: float
        is_blurry: bool
        text_layer: bool
        threshold: float
    """
    ext = os.path.splitext(filename)[1].lower() if filename else ""

    # 1. Handle PDF
    if ext == ".pdf" or file_bytes[:4] == b"%PDF":
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                total_text = ""
                for page in pdf.pages[:3]:
                    txt = page.extract_text() or ""
                    total_text += txt
                if len(total_text.strip()) >= 30:
                    # Native text-layer PDF counts as perfectly sharp
                    return {
                        "blur_score": 999.0,
                        "is_blurry": False,
                        "text_layer": True,
                        "threshold": blur_threshold,
                        "details": "Native text-layer detected"
                    }
                # Scanned PDF: render first page if possible
                if len(pdf.pages) > 0:
                    first_page_img = pdf.pages[0].to_image(resolution=150).original
                    cv_img = cv2.cvtColor(np.array(first_page_img), cv2.COLOR_RGB2BGR)
                    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                    score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    return {
                        "blur_score": round(score, 2),
                        "is_blurry": score < blur_threshold,
                        "text_layer": False,
                        "threshold": blur_threshold,
                        "details": "Rendered scanned PDF page"
                    }
        except Exception:
            pass

    # 2. Handle Image
    try:
        pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        return {
            "blur_score": round(score, 2),
            "is_blurry": score < blur_threshold,
            "text_layer": False,
            "threshold": blur_threshold,
            "details": "Image Laplacian variance"
        }
    except Exception as e:
        return {
            "blur_score": 0.0,
            "is_blurry": True,
            "text_layer": False,
            "threshold": blur_threshold,
            "details": f"Failed to parse image: {str(e)}"
        }
