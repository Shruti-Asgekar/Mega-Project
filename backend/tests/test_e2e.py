"""
End-to-End API Integration Tests.
Verifies API route behaviors:
- Upload with consent -> 201 Created with masked PII, Auto-Clear route
- Upload without consent -> HTTP 400 Bad Request
- Verification that no unmasked 12-digit Aadhaar exists anywhere in API responses
- Health check endpoint
- Graph data and Ledger integrity endpoints
"""

import io
import json
from unittest.mock import MagicMock
import pytest
from starlette.datastructures import UploadFile
from fastapi import HTTPException

from backend.app.db.database import SessionLocal
from backend.app.db import init_db
from backend.app.core.security import contains_unmasked_aadhaar
from backend.app.modules.m1_validators import generate_valid_aadhaar
from backend.app.api.routes import (
    api_health,
    create_case,
    get_case,
    get_graph_html,
    get_graph_data,
    verify_ledger_integrity
)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_api_health():
    db = SessionLocal()
    try:
        res = api_health(db)
        assert res["status"] == "healthy"
        assert res["service"] == "backend"
        assert "database" in res
    finally:
        db.close()

def test_upload_without_consent_returns_400():
    db = SessionLocal()
    req = MagicMock()
    req.client.host = "127.0.0.1"
    try:
        with pytest.raises(HTTPException) as exc_info:
            create_case(
                request=req,
                applicant_name="Ramesh Kumar",
                phone="9876543210",
                address="MG Road, Pune",
                consent_accepted=False,
                db=db
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail.get("code") == "CONSENT_REQUIRED"
    finally:
        db.close()

def test_upload_with_consent_auto_clear_and_pii_masked(monkeypatch):
    import time
    import random
    from backend.app.core import config
    monkeypatch.setattr(config, "ML_MODE", "inprocess")
    db = SessionLocal()

    app_uid = f"{random.randint(1000, 9999)}"
    test_applicant_name = f"Suresh Sharma {app_uid}"
    valid_aadhaar = generate_valid_aadhaar(f"5489123{app_uid}")
    unique_phone = f"9820{random.randint(100000, 999999)}"
    unique_addr = f"Flat {random.randint(100, 999)}, Tower {app_uid}, Road {app_uid}, City {app_uid}"

    # Synthetic genuine Aadhaar PDF
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 700, "UNIQUE IDENTIFICATION AUTHORITY OF INDIA")
    c.drawString(100, 680, f"Name: {test_applicant_name}")
    c.drawString(100, 660, "DOB: 12/05/1990")
    c.drawString(100, 640, f"Aadhaar: {valid_aadhaar}")
    c.drawString(100, 620, f"Address: {unique_addr}")
    c.save()
    aadhaar_file = UploadFile(filename="aadhaar.pdf", file=io.BytesIO(buf.getvalue()))

    # Synthetic PAN PDF
    buf_pan = io.BytesIO()
    c2 = canvas.Canvas(buf_pan, pagesize=letter)
    c2.drawString(100, 700, "INCOME TAX DEPARTMENT")
    c2.drawString(100, 680, f"Name: {test_applicant_name}")
    c2.drawString(100, 660, "DOB: 12/05/1990")
    c2.drawString(100, 640, "PAN: ABCPE1234F")
    c2.save()
    pan_file = UploadFile(filename="pan.pdf", file=io.BytesIO(buf_pan.getvalue()))

    # Synthetic Salary Slip PDF
    buf_slip = io.BytesIO()
    c3 = canvas.Canvas(buf_slip, pagesize=letter)
    c3.drawString(100, 700, "SALARY STATEMENT")
    c3.drawString(100, 680, f"Name: {test_applicant_name}")
    c3.drawString(100, 660, "Gross Salary: Rs 80,000")
    c3.drawString(100, 640, "Total Deductions: Rs 10,000")
    c3.drawString(100, 620, "Net Salary: Rs 70,000")
    c3.save()
    slip_file = UploadFile(filename="salary_slip.pdf", file=io.BytesIO(buf_slip.getvalue()))

    bank_csv_bytes = b"Date,Description,Debit,Credit,Balance\n05/05/2026,SALARY CREDIT,0,70000,95000\n"
    bank_file = UploadFile(filename="bank.csv", file=io.BytesIO(bank_csv_bytes))

    req = MagicMock()
    req.client.host = "127.0.0.1"

    try:
        response = create_case(
            request=req,
            applicant_name=test_applicant_name,
            phone=unique_phone,
            address=unique_addr,
            consent_accepted=True,
            consent_version="v1.0",
            aadhaar_file=aadhaar_file,
            pan_file=pan_file,
            salary_slip_file=slip_file,
            bank_statement_file=bank_file,
            db=db
        )

        case_data = response
        assert case_data["id"] is not None
        assert case_data["route"] == "AUTO_CLEAR"
        assert case_data["trust_score"] >= 80

        # Strict PII check: Unmasked Aadhaar must NOT be present in JSON response
        response_text = json.dumps(case_data)
        assert valid_aadhaar not in response_text
        assert "XXXX-XXXX-" in response_text
        assert contains_unmasked_aadhaar(response_text) is False

        # Check case detail endpoint
        case_id = case_data["id"]
        detail_data = get_case(case_id, db)
        assert detail_data["consent_display"].startswith("Consent given on ")
    finally:
        db.close()

def test_graph_endpoints():
    db = SessionLocal()
    try:
        # 1. HTML graph
        res_html = get_graph_html(db)
        assert "<title>Fraud Ring Bipartite Graph</title>" in res_html.body.decode("utf-8")

        # 2. JSON data
        data = get_graph_data(db)
        assert "nodes" in data
        assert "edges" in data
        assert "summary" in data
    finally:
        db.close()

def test_integrity_verify_endpoint():
    db = SessionLocal()
    try:
        data = verify_ledger_integrity(db)
        assert "valid" in data
        assert data["valid"] is True
    finally:
        db.close()
