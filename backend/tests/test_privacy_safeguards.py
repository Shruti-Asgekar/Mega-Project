"""
Comprehensive tests for Privacy-by-Design Safeguards:
- Zero raw 12-digit Aadhaar persistence
- Keyed HMAC-SHA256 duplicate detection
- At-rest encryption for DocumentBlob and applicant attributes
- DPDP retention sweep and tombstone verification.
"""

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.orm import Session

from backend.app.db import init_db
from backend.app.db.database import SessionLocal
from backend.app.db.models import Applicant, Case, Document, DocumentBlob, ChainRecord
from backend.app.core.security import (
    compute_identifier_hmac, encrypt_value, decrypt_value, scrub_pii,
    encrypt_bytes, decrypt_bytes
)
from backend.app.core.storage import save_document, get_document_bytes
from backend.app.modules.ocr_extractor import extract_document_fields
from backend.app.modules.dpdp_retention import sweep_expired_retention
from backend.app.core import config
from backend.app.modules.m10_hashchain import append_document_to_chain, verify_chain, verify_case_integrity

@pytest.fixture(scope="module")
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.close()

def test_zero_raw_aadhaar_persistence_in_ocr(db):
    """Verify OCR extractor immediately converts 12-digit Aadhaar to masked format and computes HMAC."""
    raw_aadhaar = "998877665544"
    synthetic_doc_text = f"GOVERNMENT OF INDIA\nName: Anjali Verma\nDOB: 12/04/1992\nAadhaar: {raw_aadhaar}\n"
    file_bytes = synthetic_doc_text.encode("utf-8")

    fields, conf = extract_document_fields(file_bytes, "aadhaar.txt", "aadhaar")

    # Raw 12-digit number MUST NOT be in fields
    assert fields.get("aadhaar_number") != raw_aadhaar
    assert fields.get("aadhaar_number") == "XXXX-XXXX-5544"
    assert fields.get("aadhaar_last_four") == "5544"
    assert "aadhaar_hmac" in fields
    assert fields["aadhaar_hmac"] == compute_identifier_hmac(raw_aadhaar)

def test_keyed_hmac_sha256_properties():
    """Verify HMAC-SHA256 produces deterministic keyed output without exposing raw value."""
    id1 = "9876543210"
    hmac1 = compute_identifier_hmac(id1)
    hmac2 = compute_identifier_hmac(id1)
    hmac_diff = compute_identifier_hmac("9876543211")

    assert hmac1 == hmac2
    assert hmac1 != hmac_diff
    assert len(hmac1) == 64 # SHA256 hex length
    assert id1 not in hmac1

def test_at_rest_encryption_document_blob(db, monkeypatch):
    """Verify document blob payload is encrypted at rest in DB and transparently decrypted in memory."""
    monkeypatch.setattr(config, "STORAGE_BACKEND", "db")

    appl = Applicant(name_encrypted=encrypt_value("Encryption Test User"), name_masked="Encryption Test User")
    db.add(appl)
    db.commit()

    case = Case(applicant_id=appl.id, status="PROCESSING", trust_score=100, route="AUTO_CLEAR")
    db.add(case)
    db.commit()

    doc = Document(case_id=case.id, file_path="", sha256="", doc_type="pan")
    db.add(doc)
    db.flush()

    raw_payload = b"ORIGINAL_CONFIDENTIAL_PAN_CARD_BYTES_12345"
    save_document(db, doc, raw_payload, "pan.pdf")
    db.commit()

    # Inspect raw DocumentBlob row directly in database
    blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == doc.id).first()
    assert blob is not None
    # Payload stored in database MUST NOT equal plaintext
    assert blob.data != raw_payload
    assert raw_payload not in blob.data

    # Reading via get_document_bytes decrypts payload back to original
    retrieved = get_document_bytes(db, doc.id)
    assert retrieved == raw_payload

def test_dpdp_retention_sweep_tombstones(db, monkeypatch):
    """Verify expired document payloads are purged while chain linkage is preserved via tombstones."""
    monkeypatch.setattr(config, "STORAGE_BACKEND", "db")

    appl = Applicant(name_encrypted=encrypt_value("Retention Test User"), name_masked="Retention Test User")
    db.add(appl)
    db.commit()

    case = Case(
        applicant_id=appl.id,
        status="COMPLETED",
        trust_score=90,
        route="AUTO_CLEAR",
        created_at=datetime.now(timezone.utc) - timedelta(days=45),
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    db.add(case)
    db.commit()

    doc = Document(case_id=case.id, file_path="", sha256="", doc_type="salary_slip")
    db.add(doc)
    db.flush()

    payload = b"SALARY_SLIP_EMPLOYER_CONFIDENTIAL_DATA"
    save_document(db, doc, payload, "slip.pdf")
    append_document_to_chain(db, doc)

    # Prior to sweep: payload exists and case integrity has no tampering
    flags_pre = verify_case_integrity(db, case.id)
    assert len([f for f in flags_pre if f.code.value == "LEDGER_TAMPERED"]) == 0

    # Run retention sweep with force_days=30
    sweep_summary = sweep_expired_retention(db, force_days=30)
    assert sweep_summary["cases_purged"] >= 1
    assert sweep_summary["documents_cleared"] >= 1

    # Verify payload is cleared from DocumentBlob
    blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == doc.id).first()
    assert blob.data == b""

    # Verify ChainRecord is marked as tombstone
    rec = db.query(ChainRecord).filter(ChainRecord.document_id == doc.id).first()
    assert rec.is_tombstone is True
    assert "DPDP_RETENTION_EXPIRY" in rec.tombstone_reason

    # Case integrity remains intact (tombstone acknowledged, not flagged as tampered)
    flags_post = verify_case_integrity(db, case.id)
    assert len([f for f in flags_post if f.code.value == "LEDGER_TAMPERED"]) == 0

def test_log_scrubbing_filter():
    """Verify PII scrubber strips 12-digit Aadhaar and PAN patterns."""
    raw_message = "Processed customer Aadhaar 123456789012 and PAN ABCDE1234F with mobile 9876543210"
    scrubbed = scrub_pii(raw_message)

    assert "123456789012" not in scrubbed
    assert "XXXX-XXXX-9012" in scrubbed
    assert "ABCDE1234F" not in scrubbed
    assert "XXXXX1234F" in scrubbed
