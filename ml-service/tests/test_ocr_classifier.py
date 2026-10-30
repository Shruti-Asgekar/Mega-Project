"""
Unit and Integration Tests for Module 1 (OCR) and Module 2 (Document Classifier).
"""

import os
import json
import pytest
from app import app
from src.classifier import DocumentClassifier
from src.ocr_engine import preprocess_image
import numpy as np

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["classifier_loaded"] is True
    assert "AADHAAR" in data["classes"]
    assert "PAN" in data["classes"]

def test_unauthorized_without_internal_key(client):
    res = client.post("/classify", json={"text": "Test sample"})
    assert res.status_code == 401
    assert res.get_json()["code"] == "INVALID_INTERNAL_KEY"

def test_classifier_predictions():
    clf = DocumentClassifier.get_instance()
    
    # 1. Test Aadhaar classification
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
    res = clf.predict(aadhaar_sample)
    assert res["document_type"] == "AADHAAR"
    assert res["confidence"] > 0.60
    assert res["needs_human_check"] is False
    
    # 2. Test PAN classification
    pan_sample = """
    INCOME TAX DEPARTMENT
    GOVT. OF INDIA
    PERMANENT ACCOUNT NUMBER CARD
    PAN: ABCDE1234F
    Name: Ramesh Kumar
    Father's Name: Suresh Kumar
    DOB: 12/05/1990
    """
    res = clf.predict(pan_sample)
    assert res["document_type"] == "PAN"
    assert res["confidence"] > 0.60
    
    # 3. Test Salary Slip classification
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
    res = clf.predict(salary_sample)
    assert res["document_type"] == "SALARY_SLIP"
    assert res["confidence"] > 0.60
    
    # 4. Test Bank Statement classification
    bank_sample = """
    STATE BANK OF INDIA
    STATEMENT OF ACCOUNT FOR THE PERIOD 01/04/2026 TO 30/09/2026
    Account Name: Ramesh Kumar
    Account Number: 30192837465
    IFSC Code: SBIN0001234
    DATE        NARRATION         DEBIT    CREDIT   BALANCE
    05/04/2026  SALARY CREDIT     -        67000    120000
    """
    res = clf.predict(bank_sample)
    assert res["document_type"] == "BANK_STATEMENT"
    assert res["confidence"] > 0.60

def test_preprocessing_steps():
    # Create synthetic test image
    dummy_img = np.ones((200, 400, 3), dtype=np.uint8) * 240
    processed, steps = preprocess_image(dummy_img)
    assert "grayscale" in steps
    assert "bilateral_denoise" in steps
    assert "otsu_threshold" in steps
    assert processed.shape == (200, 400)

def test_classify_api_with_valid_key(client):
    headers = {"X-Internal-Key": "shared_internal_secret_key_placeholder"}
    payload = {
        "text": "INCOME TAX DEPARTMENT GOVT OF INDIA PERMANENT ACCOUNT NUMBER CARD PAN ABCDE1234F"
    }
    res = client.post("/classify", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["document_type"] == "PAN"
    assert data["confidence"] > 0.50
