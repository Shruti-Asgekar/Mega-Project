"""
Backend REST API and UI Routes.
"""

import os
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import Applicant, Case, Document, Consent, FlagModel, ChainRecord
from backend.app.core.config import UPLOAD_DIR
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
MAX_FILE_SIZE = 10 * 1024 * 1024 # 10 MB

def save_uploaded_file(upload: UploadFile) -> tuple[str, str]:
    """Validates and saves uploaded file under UUID filename. Returns (saved_path, sha256)."""
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid file type {ext}. Allowed: PDF, PNG, JPG, JPEG, CSV")

    contents = upload.file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10 MB.")

    file_uuid = str(uuid.uuid4())
    filename = f"{file_uuid}{ext}"
    saved_path = str(UPLOAD_DIR / filename)

    with open(saved_path, "wb") as f:
        f.write(contents)

    sha256 = compute_file_sha256(saved_path)
    return saved_path, sha256

@router.get("/health")
def api_health(db: Session = Depends(get_db)):
    db_type = "postgresql" if (db.bind and "postgres" in db.bind.dialect.name) else "sqlite"
    return {
        "status": "healthy",
        "service": "backend",
        "database": db_type,
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

    # 2. Create Case
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
            file_path, sha256 = save_uploaded_file(file_obj)
            doc_rec = Document(
                case_id=case.id,
                file_path=file_path,
                sha256=sha256,
                doc_type=doc_type
            )
            db.add(doc_rec)

    db.commit()

    # 5. Execute Pipeline
    updated_case = run_case_pipeline(case.id, db)

    return serialize_case_response(updated_case, db)

@router.get("/cases")
def list_cases(db: Session = Depends(get_db)):
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    out = []
    for c in cases:
        out.append({
            "id": c.id,
            "applicant_name": c.applicant.name_masked,
            "status": c.status,
            "trust_score": c.trust_score,
            "route": c.route,
            "created_at": c.created_at.isoformat(),
            "flags_count": len(c.flags),
            "documents_count": len(c.documents)
        })
    return {"cases": out}

@router.get("/cases/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return serialize_case_response(case, db)

@router.post("/cases/{case_id}/rerun")
def rerun_case(case_id: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    updated = run_case_pipeline(case_id, db)
    return serialize_case_response(updated, db)

@router.get("/graph", response_class=HTMLResponse)
def get_graph_html(db: Session = Depends(get_db)):
    """Serves standalone interactive graph HTML."""
    all_applicants = db.query(Applicant).all()
    apps_data = []
    for appl in all_applicants:
        c_inst = appl.cases[0] if appl.cases else None
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

    G, _, _ = build_fraud_graph(apps_data)
    html_content = generate_offline_graph_html(G)
    return HTMLResponse(content=html_content)

@router.get("/graph/data")
def get_graph_data(db: Session = Depends(get_db)):
    all_applicants = db.query(Applicant).all()
    apps_data = []
    for appl in all_applicants:
        c_inst = appl.cases[0] if appl.cases else None
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

    G, flags, summary = build_fraud_graph(apps_data)
    nodes = [{"id": n, **attrs} for n, attrs in G.nodes(data=True)]
    edges = [{"from": u, "to": v, **attrs} for u, v, attrs in G.edges(data=True)]
    return {"nodes": nodes, "edges": edges, "summary": summary}

@router.get("/integrity/verify")
def verify_ledger_integrity(db: Session = Depends(get_db)):
    return verify_chain(db)

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
