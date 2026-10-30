"""
Module 3: Masking and Consent Management.
- Enforces mandatory, versioned applicant consent (HTTP 400 if missing or false)
- Records UTC timestamp, IP address, and consent text version
- Masking utilities (Aadhaar, PAN, Account, Phone)
- Strict pre-commit and API response unmasked PII scanner
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional, Any, Dict
from sqlalchemy.orm import Session
from backend.app.db.models import Consent, Case
from backend.app.core.security import (
    mask_aadhaar,
    mask_pan,
    mask_account,
    mask_phone,
    mask_extracted_fields,
    contains_unmasked_aadhaar
)

CONSENT_TEXT_VERSIONS = {
    "v1.0": (
        "I hereby declare that the documents and information provided are genuine. "
        "I authorize the verification system to parse, validate, and perform anti-fraud "
        "checks on my submitted KYC documents and bank statements."
    )
}

def record_consent(
    db: Session,
    case_id: str,
    accepted: bool,
    ip: str = "127.0.0.1",
    text_version: str = "v1.0"
) -> Consent:
    """
    Validates and stores applicant consent record.
    Raises ValueError if consent is not explicitly granted.
    """
    if not accepted:
        raise ValueError("Consent is mandatory before submitting KYC applications.")

    consent = Consent(
        case_id=case_id,
        accepted=True,
        timestamp=datetime.now(timezone.utc),
        ip=ip,
        text_version=text_version
    )
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent

def format_consent_display(consent: Consent) -> str:
    """Formats consent timestamp for display on case page."""
    ts_str = consent.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"Consent given on {ts_str}"

def deep_scan_unmasked_aadhaar(obj: Any) -> bool:
    """
    Recursively scans JSON objects, dicts, lists, and strings for unmasked Aadhaar.
    Returns True if an unmasked 12-digit Aadhaar pattern is found.
    """
    if isinstance(obj, str):
        return contains_unmasked_aadhaar(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if deep_scan_unmasked_aadhaar(v):
                return True
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            if deep_scan_unmasked_aadhaar(item):
                return True
    return False
