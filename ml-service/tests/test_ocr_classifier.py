"""
Unit and Integration Tests for ML Service OCR and Classification Endpoints.
Migrated to FastAPI application and services.extractor pipeline.
"""

import pytest
import numpy as np
from main import health
from src.ocr_engine import preprocess_image
from services.extractor import parse_fields_from_text

def test_health_endpoint():
    data = health()
    assert data["status"] == "healthy"
    assert data["service"] == "ml-service"
    assert "supported_features" in data

def test_preprocessing_steps():
    # Create synthetic test image
    dummy_img = np.ones((200, 400, 3), dtype=np.uint8) * 240
    processed, steps = preprocess_image(dummy_img)
    assert "grayscale" in steps
    assert "bilateral_denoise" in steps
    assert "otsu_threshold" in steps
    assert processed.shape == (200, 400)

def test_classifier_and_extractor_aadhaar():
    aadhaar_sample = """
    GOVERNMENT OF INDIA
    UNIQUE IDENTIFICATION AUTHORITY OF INDIA
    Enrollment No: 1234/56789/12345
    Name: Ramesh Kumar
    DOB: 12/05/1990
    Gender: Male
    Aadhaar Number: 5489 1234 5678
    My Aadhaar, My Identity
    """
    fields = parse_fields_from_text(aadhaar_sample, doc_type="aadhaar")
    assert fields.doc_type == "aadhaar"
    assert "Ramesh Kumar" in (fields.name or "")
    assert "1990" in (fields.dob or "")

def test_classifier_and_extractor_pan():
    pan_sample = """
    INCOME TAX DEPARTMENT
    GOVT. OF INDIA
    PERMANENT ACCOUNT NUMBER CARD
    PAN: ABCDE1234F
    Name: Ramesh Kumar
    Father's Name: Suresh Kumar
    DOB: 12/05/1990
    """
    fields = parse_fields_from_text(pan_sample, doc_type="pan")
    assert fields.doc_type == "pan"
    assert fields.pan_number == "ABCDE1234F"

def test_classifier_and_extractor_salary_slip():
    salary_sample = """
    TATA CONSULTANCY SERVICES PRIVATE LIMITED
    SALARY SLIP FOR THE MONTH OF OCTOBER 2026
    Employee Name: Ramesh Kumar
    Gross Earnings: Rs. 75,000
    Basic Pay: Rs. 35,000
    HRA: Rs. 14,000
    Total Deductions: Rs. 8,000
    Net Salary Payable: Rs. 67,000
    """
    fields = parse_fields_from_text(salary_sample, doc_type="salary_slip")
    assert fields.doc_type == "salary_slip"
    assert fields.gross_salary == 75000.0
    assert fields.total_deductions == 8000.0
    assert fields.net_salary == 67000.0

def test_classifier_and_extractor_bank_statement():
    bank_sample = """
    STATE BANK OF INDIA
    STATEMENT OF ACCOUNT FOR THE PERIOD 01/04/2026 TO 30/09/2026
    Account Name: Ramesh Kumar
    Account Number: 30192837465
    IFSC Code: SBIN0001234
    DATE        NARRATION         DEBIT    CREDIT   BALANCE
    05/04/2026  SALARY CREDIT     -        67000    120000
    """
    fields = parse_fields_from_text(bank_sample, doc_type="bank_statement")
    assert fields.doc_type == "bank_statement"
    assert fields.account_number == "30192837465"
    assert fields.ifsc == "SBIN0001234"
