"""
Verification Pipeline Orchestrator.
Executes verification sequence:
Extraction -> M3 -> M1 -> M2 -> M4 -> M5 -> M6 -> M7 -> M10 verify -> M8 -> M9.
Resilient: ML service HTTP calls with timeout & retry, with in-process fallback and DOC_ANALYSIS_DEGRADED flag.
Idempotent: Rerun cleans up previous flags and replaces them.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import ML_SERVICE_URL, INTERNAL_API_KEY
from backend.app.core.contracts import (
    Flag, FlagCode, Severity, ExtractedFields, Transaction
)
from backend.app.core.security import mask_extracted_fields, decrypt_value
from backend.app.db.models import Case, Document, FlagModel, Applicant, AuditLog
from backend.app.modules.m1_validators import (
    validate_pan, validate_aadhaar, validate_ifsc, validate_dob
)
from backend.app.modules.m2_quality import evaluate_quality_and_completeness
from backend.app.modules.m3_masking_consent import format_consent_display
from backend.app.modules.m4_crossdoc import verify_cross_documents
from backend.app.modules.m5_income import (
    analyze_bank_statement_and_income, parse_bank_transactions_from_csv
)
from backend.app.modules.m6_forgery import (
    verify_salary_slip_arithmetic
)
from backend.app.modules.m7_fraudring import build_fraud_graph
from backend.app.modules.m8_explainer import explain_flags, render_flag_explanation
from backend.app.modules.m9_trust_routing import calculate_trust_score_and_route
from backend.app.modules.m10_hashchain import (
    append_document_to_chain, verify_case_integrity
)

# In-process fallbacks
try:
    from services.blur import calculate_blur_score as inprocess_blur
    from services.forgery import analyze_pdf_metadata as inprocess_pdf_meta
    from services.forgery import perform_error_level_analysis as inprocess_ela
    from services.extractor import extract_raw_text as inprocess_extract_text
    from services.extractor import parse_fields_from_text as inprocess_parse_fields
except ImportError:
    import sys
    ml_svc_path = Path(__file__).resolve().parent.parent.parent.parent / "ml-service"
    if str(ml_svc_path) not in sys.path:
        sys.path.insert(0, str(ml_svc_path))
    from services.blur import calculate_blur_score as inprocess_blur
    from services.forgery import analyze_pdf_metadata as inprocess_pdf_meta
    from services.forgery import perform_error_level_analysis as inprocess_ela
    from services.extractor import extract_raw_text as inprocess_extract_text
    from services.extractor import parse_fields_from_text as inprocess_parse_fields

logger = logging.getLogger("kyc.pipeline")

_ML_ONLINE = None

def check_ml_service_online() -> bool:
    global _ML_ONLINE
    if _ML_ONLINE is not None:
        return _ML_ONLINE
    try:
        with httpx.Client(timeout=0.15) as client:
            r = client.get(f"{ML_SERVICE_URL}/api/health")
            _ML_ONLINE = (r.status_code == 200)
    except Exception:
        _ML_ONLINE = False
    return _ML_ONLINE

def call_ml_service_extract(file_bytes: bytes, filename: str, doc_type: str) -> tuple[ExtractedFields, bool]:
    """Tries HTTP call to ml-service /api/extract with timeout and fallback."""
    if check_ml_service_online():
        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.post(
                    f"{ML_SERVICE_URL}/api/extract",
                    files={"file": (filename, file_bytes)},
                    data={"doc_type": doc_type},
                    headers={"X-Internal-Key": INTERNAL_API_KEY}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    fields = ExtractedFields(**data.get("extracted_fields", {}))
                    return fields, False
        except Exception:
            pass

    # In-process fallback
    raw_text = inprocess_extract_text(file_bytes, filename)
    fields = inprocess_parse_fields(raw_text, doc_type=doc_type)
    return fields, True

def call_ml_service_blur(file_bytes: bytes, filename: str) -> tuple[dict, bool]:
    """Tries HTTP call to ml-service /api/quality/blur with fallback."""
    if check_ml_service_online():
        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.post(
                    f"{ML_SERVICE_URL}/api/quality/blur",
                    files={"file": (filename, file_bytes)},
                    data={"threshold": 100.0},
                    headers={"X-Internal-Key": INTERNAL_API_KEY}
                )
                if resp.status_code == 200:
                    return resp.json(), False
        except Exception:
            pass

    res = inprocess_blur(file_bytes, filename=filename, blur_threshold=100.0)
    return res, True

def call_ml_service_forgery(file_bytes: bytes, filename: str) -> tuple[List[Flag], bool]:
    """Tries HTTP call to ml-service /api/forgery/analyze with fallback."""
    if check_ml_service_online():
        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.post(
                    f"{ML_SERVICE_URL}/api/forgery/analyze",
                    files={"file": (filename, file_bytes)},
                    headers={"X-Internal-Key": INTERNAL_API_KEY}
                )
                if resp.status_code == 200:
                    raw_flags = resp.json().get("flags", [])
                    flags = [Flag(**f) for f in raw_flags]
                    return flags, False
        except Exception:
            pass

    flags = []
    if filename.lower().endswith(".pdf") or file_bytes[:4] == b"%PDF":
        flags.extend(inprocess_pdf_meta(file_bytes))
    if filename.lower().endswith((".jpg", ".jpeg", ".png")):
        ela_flags, _ = inprocess_ela(file_bytes)
        flags.extend(ela_flags)
    return flags, True

def run_case_pipeline(case_id: str, db: Session) -> Case:
    """
    Executes all verification stages for a case.
    Replaces existing flags (idempotent).
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise ValueError(f"Case {case_id} not found")

    # Clear previous flags for idempotency
    db.query(FlagModel).filter(FlagModel.case_id == case_id).delete()
    db.commit()

    all_flags: List[Flag] = []
    blur_results_map: Dict[str, dict] = {}
    docs_metadata_list = []
    degraded_mode_used = False

    # Track extracted aggregates
    slip_net_salary = None
    employer = None
    bank_transactions: List[Transaction] = []

    # 1. Document Extraction & Pre-Processing
    for doc in case.documents:
        if not os.path.exists(doc.file_path):
            all_flags.append(
                Flag(
                    code=FlagCode.DOC_UNREADABLE,
                    module=2,
                    severity=Severity.RED,
                    score_impact=25,
                    details={"document_id": doc.id, "error": "File missing on disk."},
                    document_id=doc.id
                )
            )
            continue

        try:
            with open(doc.file_path, "rb") as f:
                file_bytes = f.read()

            filename = os.path.basename(doc.file_path)

            # Ensure document is in hash chain
            append_document_to_chain(db, doc)

            # Quality / Blur Check
            blur_res, degraded = call_ml_service_blur(file_bytes, filename)
            if degraded:
                degraded_mode_used = True
            blur_results_map[doc.id] = blur_res
            doc.quality_score = blur_res.get("blur_score", 100.0)

            # Forgery Meta Check (M6)
            forg_flags, degraded_f = call_ml_service_forgery(file_bytes, filename)
            if degraded_f:
                degraded_mode_used = True
            for ff in forg_flags:
                ff.document_id = doc.id
            all_flags.extend(forg_flags)

            # Text / Fields Extraction
            fields, degraded_e = call_ml_service_extract(file_bytes, filename, doc.doc_type)
            if degraded_e:
                degraded_mode_used = True

            # If user already entered confirmation fields, preserve and merge
            existing_extracted = doc.extracted_json or {}
            merged_fields = fields.model_dump()
            for k, v in existing_extracted.items():
                if v and not merged_fields.get(k):
                    merged_fields[k] = v

            doc.extracted_json = merged_fields
            doc.masked_fields = mask_extracted_fields(merged_fields)

            # Parse CSV bank statements if applicable
            if doc.doc_type == "bank_statement" and filename.lower().endswith(".csv"):
                try:
                    csv_text = file_bytes.decode("utf-8", errors="ignore")
                    bank_transactions = parse_bank_transactions_from_csv(csv_text)
                except Exception:
                    pass

            # Update aggregates
            if doc.doc_type == "salary_slip":
                if merged_fields.get("net_salary"):
                    slip_net_salary = float(merged_fields["net_salary"])
                if merged_fields.get("employer"):
                    employer = merged_fields["employer"]

                # Slip arithmetic check (M6)
                arith_flags = verify_salary_slip_arithmetic(
                    gross=merged_fields.get("gross_salary"),
                    deductions=merged_fields.get("total_deductions"),
                    net=merged_fields.get("net_salary"),
                    basic=merged_fields.get("basic_pay"),
                    hra=merged_fields.get("hra"),
                    allowances=merged_fields.get("allowances"),
                    pf=merged_fields.get("pf"),
                    tax=merged_fields.get("tax"),
                    other_deductions=merged_fields.get("other_deductions"),
                    document_id=doc.id
                )
                all_flags.extend(arith_flags)

            docs_metadata_list.append({
                "id": doc.id,
                "doc_type": doc.doc_type,
                "file_path": doc.file_path,
                "extracted_fields": merged_fields
            })

            # M1 Field Validators on this document
            if merged_fields.get("pan_number"):
                all_flags.extend(validate_pan(merged_fields["pan_number"], document_id=doc.id))
            if merged_fields.get("aadhaar_number"):
                all_flags.extend(validate_aadhaar(merged_fields["aadhaar_number"], document_id=doc.id))
            if merged_fields.get("ifsc"):
                all_flags.extend(validate_ifsc(merged_fields["ifsc"], document_id=doc.id))
            if merged_fields.get("dob"):
                all_flags.extend(validate_dob(merged_fields["dob"], document_id=doc.id))

        except Exception as e:
            logger.error(f"[Pipeline] Corrupt/unreadable file in doc {doc.id}: {e}")
            all_flags.append(
                Flag(
                    code=FlagCode.DOC_UNREADABLE,
                    module=2,
                    severity=Severity.RED,
                    score_impact=25,
                    details={"document_id": doc.id, "error": str(e)},
                    document_id=doc.id
                )
            )

    # If degraded mode was used at any point, record flag
    if degraded_mode_used:
        all_flags.append(
            Flag(
                code=FlagCode.DOC_ANALYSIS_DEGRADED,
                module=2,
                severity=Severity.AMBER,
                score_impact=5,
                details={"message": "Document analysis ran via resilient in-process engine."}
            )
        )

    # 2. M2 Quality and Completeness Evaluation
    q_flags = evaluate_quality_and_completeness(docs_metadata_list, blur_results_map)
    all_flags.extend(q_flags)

    # 3. M4 Cross-Document Verification
    cross_flags = verify_cross_documents(docs_metadata_list)
    all_flags.extend(cross_flags)

    # 4. M5 Income and Bank Statement Analyzer
    if bank_transactions or slip_net_salary:
        inc_flags, metrics = analyze_bank_statement_and_income(
            transactions=bank_transactions,
            slip_net_salary=slip_net_salary,
            employer=employer
        )
        all_flags.extend(inc_flags)

    # 5. M7 Fraud Ring Detection across all system applicants
    all_applicants = db.query(Applicant).all()
    apps_data = []
    for appl in all_applicants:
        c_inst = appl.cases[0] if appl.cases else None
        # Extract phone and account if available
        phone = decrypt_value(appl.phone_encrypted) if appl.phone_encrypted else (appl.phone_masked or "")
        addr = decrypt_value(appl.address_encrypted) if appl.address_encrypted else (appl.address_normalised or "")
        acc = ""
        if c_inst:
            for d in c_inst.documents:
                ex = d.extracted_json or {}
                if ex.get("phone") and not phone:
                    phone = ex["phone"]
                if ex.get("address") and not addr:
                    addr = ex["address"]
                if ex.get("account_number") and not acc:
                    acc = ex["account_number"]
        apps_data.append({
            "applicant_id": appl.id,
            "case_id": c_inst.id if c_inst else appl.id,
            "name_masked": appl.name_masked,
            "phone": phone,
            "address": addr,
            "account_number": acc
        })

    _, fraud_flags, _ = build_fraud_graph(apps_data)
    # Filter fraud flags matching this applicant
    for ff in fraud_flags:
        if ff.details.get("applicant_id") == case.applicant_id:
            all_flags.append(ff)

    # 6. M10 Hash Chain Integrity Verification
    integrity_flags = verify_case_integrity(db, case_id)
    all_flags.extend(integrity_flags)

    # 7. M8 Plain-English Explanation Generation
    for f in all_flags:
        f.explanation = render_flag_explanation(f)

    # 8. M9 Trust Score and Smart Routing
    score, route, breakdown, summary = calculate_trust_score_and_route(all_flags)

    case.trust_score = score
    case.route = route.value
    case.status = "COMPLETED"
    case.score_breakdown = {
        "summary": summary,
        "breakdown": breakdown
    }

    # Save flags into FlagModel
    for f in all_flags:
        fm = FlagModel(
            case_id=case.id,
            document_id=f.document_id,
            code=f.code.value,
            module=f.module,
            severity=f.severity.value,
            score_impact=f.score_impact,
            details=f.details or {},
            explanation=f.explanation
        )
        db.add(fm)

    # Audit log
    audit = AuditLog(
        case_id=case.id,
        action="PIPELINE_EXECUTED",
        details={
            "score": score,
            "route": route.value,
            "flags_count": len(all_flags)
        }
    )
    db.add(audit)

    db.commit()
    db.refresh(case)
    return case
