"""
Unit and Integration Tests for Verification Pipeline Orchestrator.
"""

import tempfile
from pathlib import Path
import pytest
from backend.app.db.database import SessionLocal
from backend.app.db import init_db
from backend.app.db.models import Applicant, Case, Document, ChainRecord, FlagModel, Consent
from backend.app.core.contracts import FlagCode, Severity, RoutingDecision
from backend.app.pipeline.orchestrator import run_case_pipeline
from backend.app.modules.m3_masking_consent import record_consent
from backend.app.modules.m10_hashchain import compute_file_sha256

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_pipeline_idempotency():
    db = SessionLocal()
    try:
        # Create temp files
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f1:
            f1.write(b"%PDF-1.4 sample document 1")
            p1 = f1.name
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f2:
            f2.write(b"%PDF-1.4 sample document 2")
            p2 = f2.name

        app = Applicant(name_encrypted="enc", name_masked="Pooja Sharma")
        db.add(app)
        db.commit()

        case = Case(applicant_id=app.id)
        db.add(case)
        db.commit()

        record_consent(db, case.id, accepted=True)

        d1 = Document(case_id=case.id, file_path=p1, sha256=compute_file_sha256(p1), doc_type="aadhaar")
        d2 = Document(case_id=case.id, file_path=p2, sha256=compute_file_sha256(p2), doc_type="pan")
        db.add_all([d1, d2])
        db.commit()

        # Run pipeline 1st time
        case_after_1 = run_case_pipeline(case.id, db)
        flag_count_1 = len(case_after_1.flags)
        assert flag_count_1 > 0

        # Rerun pipeline 2nd time -> must replace flags (count must not double)
        case_after_2 = run_case_pipeline(case.id, db)
        flag_count_2 = len(case_after_2.flags)
        assert flag_count_2 == flag_count_1
    finally:
        db.query(ChainRecord).filter(ChainRecord.document_id.in_([d1.id, d2.id])).delete()
        db.query(FlagModel).filter(FlagModel.case_id == case.id).delete()
        db.query(Consent).filter(Consent.case_id == case.id).delete()
        db.query(Document).filter(Document.case_id == case.id).delete()
        db.query(Case).filter(Case.id == case.id).delete()
        db.query(Applicant).filter(Applicant.id == app.id).delete()
        db.commit()
        db.close()

def test_pipeline_handles_corrupt_file_gracefully():
    db = SessionLocal()
    try:
        app = Applicant(name_encrypted="enc", name_masked="Corrupt Test")
        db.add(app)
        db.commit()

        case = Case(applicant_id=app.id)
        db.add(case)
        db.commit()

        record_consent(db, case.id, accepted=True)

        # Non-existent or corrupt path
        d_bad = Document(
            case_id=case.id,
            file_path="C:/non_existent_folder/missing.pdf",
            sha256="0" * 64,
            doc_type="aadhaar"
        )
        db.add(d_bad)
        db.commit()

        # Pipeline must NEVER crash on missing or corrupt files
        case_res = run_case_pipeline(case.id, db)
        assert case_res.status == "COMPLETED"
        unreadable_flags = [f for f in case_res.flags if f.code == FlagCode.DOC_UNREADABLE.value]
        assert len(unreadable_flags) >= 1
    finally:
        db.query(ChainRecord).filter(ChainRecord.document_id == d_bad.id).delete()
        db.query(FlagModel).filter(FlagModel.case_id == case.id).delete()
        db.query(Consent).filter(Consent.case_id == case.id).delete()
        db.query(Document).filter(Document.case_id == case.id).delete()
        db.query(Case).filter(Case.id == case.id).delete()
        db.query(Applicant).filter(Applicant.id == app.id).delete()
        db.commit()
        db.close()
