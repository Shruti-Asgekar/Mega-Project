"""
Server-Rendered Jinja2 UI Routes.
Provides full web application interface at /ui.
"""

from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.app.db.database import get_db
from backend.app.db.models import Case, Applicant, ChainRecord, Document
from backend.app.modules.m3_masking_consent import format_consent_display

UI_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(UI_TEMPLATES_DIR))

ui_router = APIRouter()

@ui_router.get("/", response_class=RedirectResponse)
def index_redirect():
    return RedirectResponse(url="/ui")

@ui_router.get("/ui", response_class=HTMLResponse)
def ui_dashboard(request: Request, db: Session = Depends(get_db)):
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    return templates.TemplateResponse(
        "ui/dashboard.html",
        {"request": request, "cases": cases, "active_tab": "dashboard"}
    )

@ui_router.get("/ui/upload", response_class=HTMLResponse)
def ui_upload(request: Request):
    return templates.TemplateResponse(
        "ui/upload.html",
        {"request": request, "active_tab": "upload"}
    )

@ui_router.get("/ui/cases/{case_id}", response_class=HTMLResponse)
def ui_case_detail(case_id: str, request: Request, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    consent = case.consents[0] if case.consents else None
    consent_str = format_consent_display(consent) if consent else "Consent not recorded"

    flags_by_sev = {"red": [], "amber": [], "green": []}
    for f in case.flags:
        if f.severity in flags_by_sev:
            flags_by_sev[f.severity].append(f)

    return templates.TemplateResponse(
        "ui/case_detail.html",
        {
            "request": request,
            "case": case,
            "flags_by_sev": flags_by_sev,
            "consent_str": consent_str,
            "active_tab": "dashboard"
        }
    )

@ui_router.get("/ui/graph", response_class=HTMLResponse)
def ui_graph(request: Request):
    return templates.TemplateResponse(
        "ui/graph.html",
        {"request": request, "active_tab": "graph"}
    )

@ui_router.get("/ui/integrity", response_class=HTMLResponse)
def ui_integrity(request: Request, db: Session = Depends(get_db)):
    records = db.query(ChainRecord).order_by(ChainRecord.seq.desc()).all()
    # Enrich with doc_type
    enriched_records = []
    for r in records:
        doc = db.query(Document).filter(Document.id == r.document_id).first()
        enriched_records.append({
            "seq": r.seq,
            "doc_type": doc.doc_type if doc else "generic",
            "file_sha256": r.file_sha256,
            "prev_hash": r.prev_hash,
            "record_hash": r.record_hash,
            "created_at": r.created_at
        })

    return templates.TemplateResponse(
        "ui/integrity.html",
        {"request": request, "records": enriched_records, "active_tab": "integrity"}
    )
