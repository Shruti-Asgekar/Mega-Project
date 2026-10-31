"""
Backend REST API and UI Routes.
Includes health check, case creation, non-blocking pipeline execution,
fraud graph API, ledger verification, and RBAC-aware queries.
"""

import os
import re
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Any
from collections import defaultdict
import psutil
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, Response, Header, BackgroundTasks, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import Applicant, Case, Document, Consent, FlagModel, ChainRecord, User
from backend.app.core import config
from backend.app.core.config import (
    UPLOAD_DIR, DEMO_MODE, DEMO_ADMIN_KEY, MAX_UPLOAD_SIZE_BYTES,
    STORAGE_BACKEND, ML_MODE, IS_PRODUCTION
)
from backend.app.core.storage import (
    save_document, get_document_bytes, tamper_document_byte, restore_tampered_documents
)
from backend.app.core.security import (
    encrypt_value, decrypt_value, mask_aadhaar, mask_pan, mask_phone, mask_account,
    mask_extracted_fields, compute_identifier_hmac
)
from backend.app.core.contracts import RoutingDecision
from backend.app.core.auth import get_current_user_optional, get_current_user, require_role
from backend.app.modules.m3_masking_consent import (
    record_consent, format_consent_display, deep_scan_unmasked_aadhaar
)
from backend.app.modules.m7_fraudring import (
    build_fraud_graph, generate_offline_graph_html, get_serializable_graph_data
)
from backend.app.modules.m10_hashchain import verify_chain, compute_file_sha256
from backend.app.pipeline.orchestrator import run_case_pipeline, run_case_pipeline_background

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".csv"}

# In-memory IP rate limiter: 30 req/minute per IP
_ip_timestamps = defaultdict(list)

def check_ip_rate_limit(request: Request, max_requests: int = 30, window_secs: int = 60):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    recent = [t for t in _ip_timestamps[client_ip] if now - t < window_secs]
    if len(recent) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail={"error": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded. Please wait a moment before trying again."}
        )
    recent.append(now)
    _ip_timestamps[client_ip] = recent

@router.get("/health")
def api_health(db: Session = Depends(get_db)):
    """Fast, lightweight health check endpoint reporting DB, storage, and memory usage."""
    db_type = "postgresql" if (db.bind and "postgres" in db.bind.dialect.name) else "sqlite"
    try:
        mem_rss_mb = round(psutil.Process().memory_info().rss / (1024 * 1024), 2)
    except Exception:
        mem_rss_mb = 0.0

    return {
        "status": "healthy",
        "service": "backend",
        "database": db_type,
        "storage_mode": STORAGE_BACKEND,
        "ml_mode": ML_MODE,
        "demo_mode": DEMO_MODE,
        "environment": config.APP_ENV,
        "memory_rss_mb": mem_rss_mb,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.post("/cases", status_code=status.HTTP_202_ACCEPTED)
def create_case(
    request: Request,
    background_tasks: BackgroundTasks = None,
    applicant_name: str = Form(...),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    consent_accepted: bool = Form(...),
    consent_version: str = Form("v1.0"),
    run_async: bool = Form(True),
    aadhaar_file: Optional[UploadFile] = File(None),
    pan_file: Optional[UploadFile] = File(None),
    salary_slip_file: Optional[UploadFile] = File(None),
    bank_statement_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Submits a new KYC application case with mandatory consent and uploaded documents.
    Queues pipeline asynchronously by default and returns 202 Accepted.
    """
    check_ip_rate_limit(request, max_requests=20, window_secs=60)

    # Enforce mandatory consent
    if not consent_accepted:
        raise HTTPException(
            status_code=400,
            detail={"error": "CONSENT_REQUIRED", "message": "Explicit consent is required to process KYC application.", "code": "CONSENT_REQUIRED"}
        )

    # 1. Create Applicant
    applicant = Applicant(
        name_encrypted=encrypt_value(applicant_name),
        name_masked=applicant_name,
        phone_encrypted=encrypt_value(phone) if phone else None,
        phone_masked=mask_phone(phone) if phone else None,
        phone_hmac=compute_identifier_hmac(phone) if phone else None,
        address_encrypted=encrypt_value(address) if address else None,
        address_normalised=address.strip().lower() if address else None,
        address_hmac=compute_identifier_hmac(address) if address else None
    )
    db.add(applicant)
    db.commit()
    db.refresh(applicant)

    # 2. Create Initial Case
    user_id = current_user.id if (current_user and hasattr(current_user, "id")) else None
    case = Case(
        applicant_id=applicant.id,
        user_id=user_id,
        status="PROCESSING",
        pipeline_status="queued",
        pipeline_step="QUEUED",
        trust_score=100,
        route=RoutingDecision.OFFICER_REVIEW.value
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    # 3. Store Consent Record
    client_ip = request.client.host if request.client else "127.0.0.1"
    record_consent(
        db=db,
        case_id=case.id,
        accepted=True,
        ip=client_ip,
        text_version=consent_version
    )

    # 4. Save and register documents
    doc_inputs = [
        ("aadhaar", aadhaar_file),
        ("pan", pan_file),
        ("salary_slip", salary_slip_file),
        ("bank_statement", bank_statement_file),
    ]

    for doc_type, file_obj in doc_inputs:
        if file_obj and file_obj.filename:
            ext = os.path.splitext(file_obj.filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "INVALID_FILE_TYPE", "message": f"Invalid extension {ext}. Allowed: PDF, PNG, JPG, JPEG, CSV"}
                )

            contents = file_obj.file.read()
            if len(contents) > MAX_UPLOAD_SIZE_BYTES:
                limit_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
                raise HTTPException(
                    status_code=400,
                    detail={"error": "FILE_TOO_LARGE", "message": f"File exceeds maximum size limit of {limit_mb} MB."}
                )

            doc_rec = Document(
                case_id=case.id,
                file_path="",
                sha256="",
                doc_type=doc_type
            )
            db.add(doc_rec)
            db.flush()
            save_document(db, doc_rec, contents, file_obj.filename)

    db.commit()

    # 5. Dispatch Pipeline
    if run_async and background_tasks is not None:
        background_tasks.add_task(run_case_pipeline_background, case.id)
        return {
            "status": "queued",
            "case_id": case.id,
            "pipeline_status": "queued",
            "pipeline_step": "QUEUED",
            "poll_url": f"/api/cases/{case.id}/status",
            "message": "Application created and verification pipeline queued."
        }
    else:
        updated_case = run_case_pipeline(case.id, db)
        return serialize_case_response(updated_case, db)

@router.post("/cases/{case_id}/run", status_code=status.HTTP_202_ACCEPTED)
@router.post("/cases/{case_id}/rerun", status_code=status.HTTP_202_ACCEPTED)
def trigger_case_pipeline(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Triggers or reruns the verification pipeline asynchronously in background."""
    case = db.query(Case).filter(Case.id == case_id, Case.is_deleted == False).first()
    if not case:
        raise HTTPException(status_code=404, detail={"error": "CASE_NOT_FOUND", "message": f"Case {case_id} not found."})

    # If applicant, only own case
    if current_user and hasattr(current_user, "role") and current_user.role == "applicant" and case.user_id != current_user.id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Cannot access another applicant's case."})

    case.pipeline_status = "queued"
    case.pipeline_step = "QUEUED"
    case.pipeline_error = None
    db.commit()

    background_tasks.add_task(run_case_pipeline_background, case.id)

    return {
        "status": "queued",
        "case_id": case.id,
        "pipeline_status": "queued",
        "pipeline_step": "QUEUED",
        "poll_url": f"/api/cases/{case.id}/status",
        "message": "Pipeline queued for execution."
    }

@router.get("/cases/{case_id}/status")
def get_case_status(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Lightweight polling endpoint to inspect pipeline progress step-by-step."""
    case = db.query(Case).filter(Case.id == case_id, Case.is_deleted == False).first()
    if not case:
        raise HTTPException(status_code=404, detail={"error": "CASE_NOT_FOUND", "message": f"Case {case_id} not found."})

    if current_user and hasattr(current_user, "role") and current_user.role == "applicant" and hasattr(current_user, "id") and case.user_id != current_user.id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})

    return {
        "case_id": case.id,
        "pipeline_status": case.pipeline_status or "done",
        "pipeline_step": case.pipeline_step or "COMPLETED",
        "pipeline_error": case.pipeline_error,
        "status": case.status,
        "trust_score": case.trust_score,
        "route": case.route,
        "decision": case.decision,
        "decision_comment": case.decision_comment,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

@router.get("/cases")
def list_cases(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Lists cases in descending chronological order with RBAC filtering."""
    q = db.query(Case).filter(Case.is_deleted == False)

    # RBAC: Applicants see only their own cases
    if current_user and hasattr(current_user, "role") and current_user.role == "applicant":
        if hasattr(current_user, "id"):
            q = q.filter(Case.user_id == current_user.id)

    cases = q.order_by(Case.created_at.desc()).all()
    out = []
    for c in cases:
        out.append({
            "id": c.id,
            "applicant_name": c.applicant.name_masked if c.applicant else "Unknown",
            "status": c.status,
            "pipeline_status": c.pipeline_status or "done",
            "pipeline_step": c.pipeline_step or "COMPLETED",
            "trust_score": c.trust_score,
            "route": c.route,
            "decision": c.decision,
            "created_at": c.created_at.isoformat()
        })
    return out

@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Retrieves single case with masked fields, score breakdown, and flags."""
    case = db.query(Case).filter(Case.id == case_id, Case.is_deleted == False).first()
    if not case:
        raise HTTPException(status_code=404, detail={"error": "CASE_NOT_FOUND", "message": "Case not found."})

    if current_user and hasattr(current_user, "role") and current_user.role == "applicant" and hasattr(current_user, "id") and case.user_id != current_user.id:
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN", "message": "Access denied."})

    return serialize_case_response(case, db)

def _build_apps_data(db: Session) -> list:
    all_applicants = db.query(Applicant).all()
    apps_data = []
    for appl in all_applicants:
        phone = decrypt_value(appl.phone_encrypted) if appl.phone_encrypted else ""
        addr = decrypt_value(appl.address_encrypted) if appl.address_encrypted else ""
        c_inst = appl.cases[0] if appl.cases else None
        acc = None
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
    return apps_data

@router.get("/graph/html", response_class=HTMLResponse)
def get_graph_html(db: Session = Depends(get_db)):
    """Returns standalone offline Vis.js HTML document for fraud ring inspection."""
    apps_data = _build_apps_data(db)
    G, flags, cluster_count = build_fraud_graph(apps_data)
    html_content = generate_offline_graph_html(G, cluster_count)
    return HTMLResponse(content=html_content, status_code=200)

@router.get("/graph/data")
def get_graph_data(db: Session = Depends(get_db)):
    """Returns cached, capped JSON node and edge collections formatted for Vis.js."""
    apps_data = _build_apps_data(db)
    return get_serializable_graph_data(apps_data)

@router.get("/integrity/verify")
def verify_ledger_integrity(db: Session = Depends(get_db)):
    """Executes full cryptographic walk of hash chain blocks and stored files."""
    return verify_chain(db)

# --------------------------------------------------------------------------
# DEMO MODE ENDPOINTS (Only active when DEMO_MODE=true and not in production)
# --------------------------------------------------------------------------

@router.post("/demo/tamper/{document_id}")
@router.post("/demo/tamper")
def demo_tamper(
    request: Request,
    document_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Flips 1 byte of document payload in storage to simulate tamper detection."""
    if IS_PRODUCTION or not config.DEMO_MODE:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Demo tamper endpoints are disabled in production."})

    check_ip_rate_limit(request, max_requests=20, window_secs=60)

    try:
        doc_id, offset, orig_byte = tamper_document_byte(db, document_id)
        return {
            "status": "tampered",
            "document_id": doc_id,
            "byte_offset": offset,
            "message": f"Successfully flipped 1 byte at offset {offset} in document {doc_id}."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "TAMPER_FAILED", "message": str(e)})

@router.post("/demo/restore")
def demo_restore(
    request: Request,
    db: Session = Depends(get_db)
):
    """Restores all tampered document payloads back to their verified pristine state."""
    if IS_PRODUCTION or not config.DEMO_MODE:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Demo restore endpoints are disabled in production."})

    check_ip_rate_limit(request, max_requests=20, window_secs=60)

    try:
        count = restore_tampered_documents(db)
        return {
            "status": "restored",
            "restored_count": count,
            "message": f"Successfully restored {count} tampered document(s) to pristine state."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "RESTORE_FAILED", "message": str(e)})

@router.post("/demo/reseed")
def demo_reseed(
    request: Request,
    x_demo_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Reseeds demo data from scratch (protected by X-Demo-Key header)."""
    if IS_PRODUCTION or not config.DEMO_MODE:
        raise HTTPException(status_code=404, detail={"error": "NOT_FOUND", "message": "Demo reseed endpoints are disabled in production."})

    if not x_demo_key or x_demo_key != config.DEMO_ADMIN_KEY:
        raise HTTPException(status_code=401, detail={"error": "UNAUTHORIZED", "message": "Unauthorized: invalid X-Demo-Key."})

    check_ip_rate_limit(request, max_requests=5, window_secs=60)

    import sys
    data_gen_path = Path(__file__).resolve().parent.parent.parent.parent / "data-generator"
    if str(data_gen_path) not in sys.path:
        sys.path.insert(0, str(data_gen_path))
    from generate import seed_database
    seed_database(reset=True, benign_count=12)

    return {"status": "reseeded", "message": "Demo database successfully reseeded with synthetic cases."}

# --------------------------------------------------------------------------
# Serializer Helpers
# --------------------------------------------------------------------------

def sanitize_details_for_api(details: Any) -> Any:
    """Recursively replaces unmasked 12-digit Aadhaar in dicts/lists for API output."""
    if isinstance(details, dict):
        out = {}
        for k, v in details.items():
            if k == "aadhaar" and isinstance(v, str):
                out[k] = mask_aadhaar(v)
            else:
                out[k] = sanitize_details_for_api(v)
        return out
    elif isinstance(details, list):
        return [sanitize_details_for_api(x) for x in details]
    elif isinstance(details, str) and re.search(r"\b\d{12}\b", details):
        return re.sub(r"\b\d{8}(\d{4})\b", r"XXXX-XXXX-\1", details)
    return details

def serialize_case_response(case: Case, db: Session) -> dict:
    """Serializes Case model into clean masked API response with governance fields."""
    consent = case.consents[0] if case.consents else None
    consent_str = format_consent_display(consent) if consent else "Consent not recorded"

    # Group flags
    flags_by_sev = {"red": [], "amber": [], "green": []}
    for f in case.flags:
        item = {
            "id": f.id,
            "module": f.module,
            "code": f.code,
            "severity": f.severity,
            "score_impact": f.score_impact,
            "explanation": f.explanation,
            "details": sanitize_details_for_api(f.details or {}),
            "document_id": f.document_id
        }
        if f.severity in flags_by_sev:
            flags_by_sev[f.severity].append(item)

    docs = []
    for d in case.documents:
        docs.append({
            "id": d.id,
            "doc_type": d.doc_type,
            "quality_score": d.quality_score,
            "sha256": d.sha256,
            "masked_fields": d.masked_fields or {},
            "user_confirmed": getattr(d, "user_confirmed", False)
        })

    res = {
        "id": case.id,
        "applicant": {
            "id": case.applicant.id,
            "name": case.applicant.name_masked,
            "phone": case.applicant.phone_masked,
            "address": case.applicant.address_normalised
        },
        "status": case.status,
        "pipeline_status": getattr(case, "pipeline_status", "done") or "done",
        "pipeline_step": getattr(case, "pipeline_step", "COMPLETED") or "COMPLETED",
        "pipeline_error": getattr(case, "pipeline_error", None),
        "trust_score": case.trust_score,
        "route": case.route,
        "decision": getattr(case, "decision", None),
        "decision_comment": getattr(case, "decision_comment", None),
        "decision_by": getattr(case, "decision_by", None),
        "decided_at": case.decided_at.isoformat() if getattr(case, "decided_at", None) else None,
        "consent_display": consent_str,
        "score_breakdown": case.score_breakdown or {},
        "documents": docs,
        "flags": flags_by_sev,
        "total_flags": len(case.flags),
        "created_at": case.created_at.isoformat()
    }
    return res
