"""
Unit Tests for Module 3 (Masking and Consent).
"""

import pytest
from datetime import datetime, timezone
from backend.app.db.database import SessionLocal
from backend.app.db import init_db
from backend.app.db.models import Applicant, Case, Consent
from backend.app.core.security import (
    mask_aadhaar,
    mask_pan,
    mask_account,
    mask_phone,
    contains_unmasked_aadhaar
)
from backend.app.modules.m3_masking_consent import (
    record_consent,
    format_consent_display,
    deep_scan_unmasked_aadhaar
)

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_masking_helpers():
    assert mask_aadhaar("548912345678") == "XXXX-XXXX-5678"
    assert mask_aadhaar("5489-1234-5678") == "XXXX-XXXX-5678"
    assert mask_pan("ABCDE1234F") == "XXXXX1234F"
    assert mask_account("987654321098") == "XXXXXXXX1098"
    assert mask_phone("9876543210") == "XXXXXXX210"

def test_consent_mandatory_and_recorded():
    db = SessionLocal()
    try:
        # Create dummy applicant and case
        applicant = Applicant(
            name_encrypted="enc_name",
            name_masked="Ramesh Kumar"
        )
        db.add(applicant)
        db.commit()

        case = Case(applicant_id=applicant.id, status="DRAFT")
        db.add(case)
        db.commit()

        # 1. Negative test: consent false raises error
        with pytest.raises(ValueError, match="Consent is mandatory"):
            record_consent(db, case.id, accepted=False)

        # 2. Positive test: consent accepted
        consent = record_consent(db, case.id, accepted=True, ip="192.168.1.50", text_version="v1.0")
        assert consent.accepted is True
        assert consent.ip == "192.168.1.50"
        assert consent.text_version == "v1.0"

        # Format display
        display = format_consent_display(consent)
        assert display.startswith("Consent given on ")
        assert "UTC" in display
    finally:
        db.close()

def test_unmasked_aadhaar_scanner():
    # Unmasked aadhaar must be detected
    assert contains_unmasked_aadhaar("Applicant Aadhaar is 548912345678.") is True
    assert contains_unmasked_aadhaar("Card: 5489-1234-5678 verified.") is True

    # Masked aadhaar must be safe
    assert contains_unmasked_aadhaar("Applicant Aadhaar is XXXX-XXXX-5678.") is False

    # Deep object scan
    payload = {
        "case_id": "test-123",
        "documents": [
            {"name": "aadhaar.pdf", "number": "XXXX-XXXX-9999"},
            {"notes": "Everything verified"}
        ]
    }
    assert deep_scan_unmasked_aadhaar(payload) is False

    # Leaked payload
    leaked_payload = {
        "case_id": "test-123",
        "documents": [
            {"name": "aadhaar.pdf", "raw_ocr": "UID: 5489 1234 5678"}
        ]
    }
    assert deep_scan_unmasked_aadhaar(leaked_payload) is True
