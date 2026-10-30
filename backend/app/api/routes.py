"""
Backend REST API and UI Routes.
Includes health check, case creation, graph visualization, ledger verification,
and public demo endpoints (tamper, restore, reseed) when DEMO_MODE=true.
"""

import os
import re
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Any
from collections import defaultdict
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, Response, Header
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import Applicant, Case, Document, Consent, FlagModel, ChainRecord
from backend.app.core import config
from backend.app.core.config import (
    UPLOAD_DIR, DEMO_MODE, DEMO_ADMIN_KEY, MAX_UPLOAD_SIZE_BYTES,
    STORAGE_BACKEND, ML_MODE
)
from backend.app.core.storage import (
    save_document, get_document_bytes, tamper_document_byte, restore_tampered_documents
)
from backend.app.core.security import (
    encrypt_value, decrypt_value, mask_aadhaar, mask_pan, mask_phone, mask_account,
    mask_extracted_fields
)
from backend.app.core.contracts import RoutingDecision
from backend.app.modules.m3_masking_consent import (
    record_consent, format_consent_display, deep_scan_unmasked_aadhaar
)
from backend.app.modules.m7_fraudring import build_fraud_graph, generate_offline_graph_html
from backend.app.modules.m10_hashchain import verify_chain, compute_file_sha256
from backend.app.pipeline.orchestrator import run_case_pipeline

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".csv"}

# In-memory IP rate limiter: 20 req/minute per IP
_ip_timestamps = defaultdict(list)

def check_ip_rate_limit(request: Request, max_requests: int = 20, window_secs: int = 60):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    recent = [t for t in _ip_timestamps[client_ip] if now - t < window_secs]
    if len(recent) >= max_requests:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a moment before trying again.")
    recent.append(now)
    _ip_timestamps[client_ip] = recent

@router.get("/health")
def api_health(db: Session = Depends(get_db)):
    """Fast, lightweight health check endpoint used by cloud orchestrators / Render."""
    db_type = "postgresql" if (db.bind and "postgres" in db.bind.dialect.name) else "sqlite"
    return {
        "status": "healthy",
        "service": "backend",
        "database": db_type,
        "storage_mode": STORAGE_BACKEND,
        "ml_mode": ML_MODE,
        "demo_mode": DEMO_MODE,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.post("/cases", status_code=201)
def create_case(
    request: Request,
    applicant_name: str = Form(...),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    consent_accepted: bool = Form(...),
    consent_version: str = Form("v1.0"),
    aadhaar_file: Optional[UploadFile] = File(None),
    pan_file: Optional[UploadFile] = File(None),
    salary_slip_file: Optional[UploadFile] = File(None),
    bank_statement_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """
    Submits a new KYC application case with mandatory consent and uploaded documents.
    """
    check_ip_rate_limit(request, max_requests=20, window_secs=60)

    # Enforce mandatory consent
    if not consent_accepted:
        raise HTTPException(
            status_code=400,
            detail={"error": "Explicit consent is required to process KYC application.", "code": "CONSENT_REQUIRED"}
        )

    # 1. Create Applicant
    applicant = Applicant(
        name_encrypted=encrypt_value(applicant_name),
        name_masked=applicant_name,
        phone_encrypted=encrypt_value(phone) if phone else None,
        phone_masked=mask_phone(phone) if phone else None,
        address_encrypted=encrypt_value(address) if address else None,
        address_normalised=address.strip().lower() if address else None
    )
    db.add(applicant)
    db.commit()
    db.refresh(applicant)

    # 2. Create Initial Case
    case = Case(
        applicant_id=applicant.id,
        status="PROCESSING",
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
                raise HTTPException(status_code=400, detail=f"Invalid file extension {ext}. Allowed: PDF, PNG, JPG, JPEG, CSV")

            contents = file_obj.file.read()
            if len(contents) > MAX_UPLOAD_SIZE_BYTES:
                limit_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
                raise HTTPException(status_code=400, detail=f"File exceeds maximum size limit of {limit_mb} MB.")

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

    # 5. Execute Pipeline
    updated_case = run_case_pipeline(case.id, db)

    return serialize_case_response(updated_case, db)

@router.get("/cases")
def list_cases(db: Session = Depends(get_db)):
    """Lists all cases in descending chronological order."""
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    out = []
    for c in cases:
        out.append({
            "id": c.id,
            "applicant_name": c.applicant.name_masked if c.applicant else "Unknown",
            "status": c.status,
            "trust_score": c.trust_score,
            "route": c.route,
            "created_at": c.created_at.isoformat()
        })
    return out

@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    """Retrieves single case with masked fields, score breakdown, and flags."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return serialize_case_response(case, db)

@router.get("/graph/html", response_class=HTMLResponse)
def get_graph_html(db: Session = Depends(get_db)):
    """Returns standalone offline Vis.js HTML document for fraud ring inspection."""
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

    G, flags, cluster_count = build_fraud_graph(apps_data)
    html_content = generate_offline_graph_html(G, cluster_count)
    return HTMLResponse(content=html_content, status_code=200)

@router.get("/graph/data")
def get_graph_data(db: Session = Depends(get_db)):
    """Returns raw JSON node and edge collections for custom graph renderers."""
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

    G, flags, cluster_count = build_fraud_graph(apps_data)
    nodes = []
    for n, data in G.nodes(data=True):
        nodes.append({
            "id": n,
            "label": data.get("label", n),
            "group": data.get("group", "entity"),
            "color": data.get("color", "#999999")
        })
    edges = []
    for u, v, data in G.edges(data=True):
        edges.append({
            "from": u,
            "to": v,
            "type": data.get("type", "links")
        })
    return {
        "nodes": nodes,
        "edges": edges,
        "ring_count": cluster_count.get("ring_applicants_count", 0) if isinstance(cluster_count, dict) else cluster_count,
        "summary": cluster_count,
        "flags": [f.model_dump() for f in flags]
    }

@router.get("/integrity/verify")
def verify_ledger_integrity(db: Session = Depends(get_db)):
    """Executes full cryptographic walk of hash chain blocks and stored files."""
    audit_result = verify_chain(db)
    if not audit_result.get("valid"):
        return JSONResponse(status_code=409, content=audit_result)
    return audit_result

# --------------------------------------------------------------------------
# DEMO MODE ENDPOINTS (Only active when DEMO_MODE=true, returns 404 otherwise)
# --------------------------------------------------------------------------

@router.post("/demo/tamper/{document_id}")
@router.post("/demo/tamper")
def demo_tamper(
    request: Request,
    document_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Flips 1 byte of document payload in storage to simulate tamper detection."""
    if not config.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Demo endpoints are disabled in production.")

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
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/demo/restore")
def demo_restore(
    request: Request,
    db: Session = Depends(get_db)
):
    """Restores all tampered document payloads back to their verified pristine state."""
    if not config.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Demo endpoints are disabled in production.")

    check_ip_rate_limit(request, max_requests=20, window_secs=60)

    try:
        count = restore_tampered_documents(db)
        return {
            "status": "restored",
            "restored_count": count,
            "message": f"Successfully restored {count} tampered document(s) to pristine state."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/demo/reseed")
def demo_reseed(
    request: Request,
    x_demo_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Reseeds demo data from scratch (protected by X-Demo-Key header)."""
    if not config.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Demo endpoints are disabled in production.")

    if not x_demo_key or x_demo_key != config.DEMO_ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid X-Demo-Key.")

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
    """Serializes Case model into clean masked API response."""
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
            "masked_fields": d.masked_fields or {}
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
        "trust_score": case.trust_score,
        "route": case.route,
        "consent_display": consent_str,
        "score_breakdown": case.score_breakdown or {},
        "documents": docs,
        "flags": flags_by_sev,
        "total_flags": len(case.flags),
        "created_at": case.created_at.isoformat()
    }
    return res
