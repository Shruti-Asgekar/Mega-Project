"""
Tests for Deployment Features:
1. Storage backend dual-mode support (DB BYTEA vs Disk Filesystem)
2. In-process ML mode verification (DOC_ANALYSIS_DEGRADED flag must NOT fire)
3. Public demo tamper and restore endpoints (active in DEMO_MODE, 404 otherwise)
"""

import os
import hashlib
import pytest
from unittest.mock import MagicMock
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from backend.app.db.database import Base
from backend.app.db.models import Applicant, Case, Document, ChainRecord, DocumentBlob, DemoTamperLog
from backend.app.core import config
from backend.app.core.storage import (
    save_document, get_document_bytes, get_document_file_context,
    tamper_document_byte, restore_tampered_documents
)
from backend.app.modules.m10_hashchain import append_document_to_chain, verify_chain
from backend.app.pipeline.orchestrator import run_case_pipeline
from backend.app.api.routes import demo_tamper, demo_restore

@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()

def test_storage_backend_db_mode(memory_db, monkeypatch):
    """Verifies that DB storage stores bytes in document_blobs and verifies ledger."""
    monkeypatch.setattr(config, "STORAGE_BACKEND", "db")

    case = Case(applicant_id="app-1", status="SUBMITTED")
    memory_db.add(case)
    memory_db.flush()

    doc = Document(case_id=case.id, file_path="", sha256="", doc_type="pan")
    memory_db.add(doc)
    memory_db.flush()

    raw_payload = b"%PDF-1.4 synthetic pan card bytes payload 1234567890"
    path = save_document(memory_db, doc, raw_payload, "pan.pdf")
    memory_db.commit()

    assert path.startswith("db://")
    assert doc.sha256 == hashlib.sha256(raw_payload).hexdigest()

    # Verify retrieval
    retrieved = get_document_bytes(memory_db, doc.id)
    assert retrieved == raw_payload

    # Verify temp file context
    with get_document_file_context(memory_db, doc.id) as tmp_path:
        assert tmp_path.exists()
        assert tmp_path.read_bytes() == raw_payload
    assert not tmp_path.exists() # Cleaned up

    # Append to chain and verify
    append_document_to_chain(memory_db, doc)
    audit = verify_chain(memory_db)
    assert audit["valid"] is True
    assert audit["total_records"] == 1

def test_storage_backend_disk_mode(memory_db, tmp_path, monkeypatch):
    """Verifies that disk storage stores file on filesystem and verifies ledger."""
    monkeypatch.setattr(config, "STORAGE_BACKEND", "disk")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)

    case = Case(applicant_id="app-2", status="SUBMITTED")
    memory_db.add(case)
    memory_db.flush()

    doc = Document(case_id=case.id, file_path="", sha256="", doc_type="aadhaar")
    memory_db.add(doc)
    memory_db.flush()

    raw_payload = b"%PDF-1.4 synthetic aadhaar bytes payload 9876543210"
    path = save_document(memory_db, doc, raw_payload, "aadhaar.pdf")
    memory_db.commit()

    assert not path.startswith("db://")
    assert Path(path).exists()
    assert doc.sha256 == hashlib.sha256(raw_payload).hexdigest()

    # Verify retrieval
    retrieved = get_document_bytes(memory_db, doc.id)
    assert retrieved == raw_payload

    # Append to chain and verify
    append_document_to_chain(memory_db, doc)
    audit = verify_chain(memory_db)
    assert audit["valid"] is True

def test_demo_tamper_and_restore_db_mode(memory_db, monkeypatch):
    """Verifies tamper simulation flips a byte and restore recovers original state."""
    monkeypatch.setattr(config, "STORAGE_BACKEND", "db")

    case = Case(applicant_id="app-demo", status="SUBMITTED")
    memory_db.add(case)
    memory_db.flush()

    doc = Document(case_id=case.id, file_path="", sha256="", doc_type="salary_slip")
    memory_db.add(doc)
    memory_db.flush()

    original_bytes = b"CONFIDENTIAL SALARY STATEMENT RS 50000 PER MONTH"
    save_document(memory_db, doc, original_bytes, "slip.pdf")
    append_document_to_chain(memory_db, doc)
    memory_db.commit()

    # Initial chain is intact
    assert verify_chain(memory_db)["valid"] is True

    # Tamper 1 byte
    doc_id, offset, orig_byte = tamper_document_byte(memory_db, doc.id)
    assert doc_id == doc.id
    tampered_bytes = get_document_bytes(memory_db, doc.id)
    assert tampered_bytes != original_bytes

    # Verification must fail
    broken_audit = verify_chain(memory_db)
    assert broken_audit["valid"] is False
    assert broken_audit["first_broken_seq"] == 1

    # Restore original
    restored_count = restore_tampered_documents(memory_db)
    assert restored_count == 1
    restored_bytes = get_document_bytes(memory_db, doc.id)
    assert restored_bytes == original_bytes

    # Verification must pass again
    healed_audit = verify_chain(memory_db)
    assert healed_audit["valid"] is True

def test_inprocess_ml_mode_suppresses_degraded_flag(memory_db, monkeypatch):
    """Verifies that inprocess ML mode does not fire DOC_ANALYSIS_DEGRADED."""
    monkeypatch.setattr(config, "ML_MODE", "inprocess")
    monkeypatch.setattr(config, "STORAGE_BACKEND", "db")

    appl = Applicant(
        name_encrypted="enc_name",
        name_masked="John Doe",
        phone_masked="9820011223"
    )
    memory_db.add(appl)
    memory_db.flush()

    case = Case(applicant_id=appl.id, status="PROCESSING")
    memory_db.add(case)
    memory_db.flush()

    doc = Document(case_id=case.id, file_path="", sha256="", doc_type="pan")
    memory_db.add(doc)
    memory_db.flush()

    pdf_bytes = b"%PDF-1.4 synthetic test pdf with PAN ABCPE1234F"
    save_document(memory_db, doc, pdf_bytes, "test_pan.pdf")
    memory_db.commit()

    updated_case = run_case_pipeline(case.id, memory_db)
    flag_codes = [f.code for f in updated_case.flags]

    # Must NOT have DOC_ANALYSIS_DEGRADED
    assert "DOC_ANALYSIS_DEGRADED" not in flag_codes

def test_demo_endpoints_disabled_when_not_demo_mode(memory_db, monkeypatch):
    """Confirms demo endpoints return 404 when DEMO_MODE is False."""
    monkeypatch.setattr(config, "DEMO_MODE", False)
    req = MagicMock()
    req.client.host = "127.0.0.1"

    with pytest.raises(HTTPException) as exc1:
        demo_tamper(request=req, db=memory_db)
    assert exc1.value.status_code == 404

    with pytest.raises(HTTPException) as exc2:
        demo_restore(request=req, db=memory_db)
    assert exc2.value.status_code == 404

def test_demo_endpoints_enabled_when_demo_mode(memory_db, monkeypatch):
    """Confirms demo endpoints return 200 and function when DEMO_MODE is True."""
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "STORAGE_BACKEND", "db")

    case = Case(applicant_id="app-demo-2", status="SUBMITTED")
    memory_db.add(case)
    memory_db.flush()

    doc = Document(case_id=case.id, file_path="", sha256="", doc_type="pan")
    memory_db.add(doc)
    memory_db.flush()

    pdf_bytes = b"SAMPLE TEST DOCUMENT FOR DEMO TAMPERING 12345"
    save_document(memory_db, doc, pdf_bytes, "pan.pdf")
    append_document_to_chain(memory_db, doc)
    memory_db.commit()

    req = MagicMock()
    req.client.host = "127.0.0.1"

    # Tamper
    tamper_res = demo_tamper(request=req, document_id=doc.id, db=memory_db)
    assert tamper_res["status"] == "tampered"
    assert verify_chain(memory_db)["valid"] is False

    # Restore
    restore_res = demo_restore(request=req, db=memory_db)
    assert restore_res["status"] == "restored"
    assert verify_chain(memory_db)["valid"] is True
