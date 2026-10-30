"""
Unit Tests for Module 10 (Tamper-Evident Hash Chain).
"""

import tempfile
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.database import Base
from backend.app.db.models import Applicant, Case, Document, ChainRecord
from backend.app.core.contracts import FlagCode, Severity, RoutingDecision
from backend.app.modules.m10_hashchain import (
    append_document_to_chain,
    verify_chain,
    verify_case_integrity,
    compute_file_sha256
)
from backend.app.modules.m9_trust_routing import calculate_trust_score_and_route
import importlib.util

tamper_demo_path = Path(__file__).resolve().parent.parent.parent / "data-generator" / "tamper_demo.py"
spec = importlib.util.spec_from_file_location("tamper_demo", str(tamper_demo_path))
tamper_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tamper_mod)
tamper_file = tamper_mod.tamper_file
restore_file = tamper_mod.restore_file

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()

def test_tamper_demo_and_chain_verification(test_db):
    db = test_db
    # Create temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 sample genuine document content for KYC testing 123456789")
        tmp_path = tmp.name

    try:
        sha = compute_file_sha256(tmp_path)

        # Create applicant, case, doc
        app = Applicant(name_encrypted="enc", name_masked="Ramesh Kumar")
        db.add(app)
        db.commit()

        case = Case(applicant_id=app.id, status="PROCESSING")
        db.add(case)
        db.commit()

        doc = Document(
            case_id=case.id,
            file_path=tmp_path,
            sha256=sha,
            doc_type="aadhaar"
        )
        db.add(doc)
        db.commit()

        # 1. Append to chain
        chain_rec = append_document_to_chain(db, doc)
        assert chain_rec.seq >= 1
        assert chain_rec.file_sha256 == sha

        # 2. Verify clean state -> GREEN
        res = verify_chain(db)
        assert res["valid"] is True
        assert res["total_records"] == 1
        assert res["first_broken_seq"] is None

        # Check case integrity flags
        initial_flags = verify_case_integrity(db, case.id)
        assert len(initial_flags) == 1
        assert initial_flags[0].code == FlagCode.INTEGRITY_VERIFIED

        # 3. Tamper file on disk (flip byte)
        tamper_file(tmp_path)

        # 4. Verification must turn RED
        res_tampered = verify_chain(db)
        assert res_tampered["valid"] is False
        assert "modified or corrupted" in res_tampered["reason"]

        tampered_flags = verify_case_integrity(db, case.id)
        broken_flags = [f for f in tampered_flags if f.code == FlagCode.INTEGRITY_BROKEN]
        assert len(broken_flags) == 1
        assert broken_flags[0].severity == Severity.RED

        # Routing must ESCALATE
        score, route, _, _ = calculate_trust_score_and_route(tampered_flags)
        assert route == RoutingDecision.ESCALATE

        # 5. Restore file -> GREEN
        restore_file(tmp_path)
        res_restored = verify_chain(db)
        assert res_restored["valid"] is True

        restored_flags = verify_case_integrity(db, case.id)
        assert restored_flags[0].code == FlagCode.INTEGRITY_VERIFIED
    finally:
        # Cleanup temp file
        Path(tmp_path).unlink(missing_ok=True)
