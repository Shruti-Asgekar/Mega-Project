"""
Server-Rendered Jinja2 UI Routes.
Provides full web application interface at /ui, auth pages, and admin audit views.
"""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.core import config
from backend.app.core.auth import get_current_user_optional, get_current_user, require_role
from backend.app.db.database import get_db
from backend.app.db.models import Case, Applicant, ChainRecord, Document, AuditLog, User
from backend.app.modules.m3_masking_consent import format_consent_display

UI_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(UI_TEMPLATES_DIR))

ui_router = APIRouter()

@ui_router.get("/", response_class=RedirectResponse)
def index_redirect():
    return RedirectResponse(url="/ui")

@ui_router.get("/ui", response_class=HTMLResponse)
def ui_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    q = db.query(Case).filter(Case.is_deleted == False)

    # If logged in as applicant, only see own cases
    if current_user and current_user.role == "applicant":
        q = q.filter(Case.user_id == current_user.id)

    cases = q.order_by(Case.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="ui/dashboard.html",
        context={
            "cases": cases,
            "active_tab": "dashboard",
            "current_user": current_user,
            "is_production": config.IS_PRODUCTION
        }
    )

@ui_router.get("/ui/upload", response_class=HTMLResponse)
def ui_upload(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    return templates.TemplateResponse(
        request=request,
        name="ui/upload.html",
        context={
            "active_tab": "upload",
            "current_user": current_user,
            "is_production": config.IS_PRODUCTION
        }
    )

@ui_router.get("/ui/cases/{case_id}", response_class=HTMLResponse)
def ui_case_detail(
    case_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    case = db.query(Case).filter(Case.id == case_id, Case.is_deleted == False).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if current_user and current_user.role == "applicant" and case.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied to this case.")

    consent = case.consents[0] if case.consents else None
    consent_str = format_consent_display(consent) if consent else "Consent not recorded"

    flags_by_sev = {"red": [], "amber": [], "green": []}
    for f in case.flags:
        if f.severity in flags_by_sev:
            flags_by_sev[f.severity].append(f)

    return templates.TemplateResponse(
        request=request,
        name="ui/case_detail.html",
        context={
            "case": case,
            "flags_by_sev": flags_by_sev,
            "consent_str": consent_str,
            "active_tab": "dashboard",
            "current_user": current_user,
            "is_production": config.IS_PRODUCTION
        }
    )

@ui_router.get("/ui/graph", response_class=HTMLResponse)
def ui_graph(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    return templates.TemplateResponse(
        request=request,
        name="ui/graph.html",
        context={
            "active_tab": "graph",
            "current_user": current_user,
            "is_production": config.IS_PRODUCTION
        }
    )

@ui_router.get("/ui/integrity", response_class=HTMLResponse)
def ui_integrity(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    records = db.query(ChainRecord).order_by(ChainRecord.seq.desc()).all()
    enriched_records = []
    for r in records:
        doc = db.query(Document).filter(Document.id == r.document_id).first()
        enriched_records.append({
            "seq": r.seq,
            "doc_type": doc.doc_type if doc else "generic",
            "file_sha256": r.file_sha256,
            "prev_hash": r.prev_hash,
            "record_hash": r.record_hash,
            "is_tombstone": getattr(r, "is_tombstone", False),
            "tombstone_reason": getattr(r, "tombstone_reason", None),
            "created_at": r.created_at
        })

    return templates.TemplateResponse(
        request=request,
        name="ui/integrity.html",
        context={
            "records": enriched_records,
            "active_tab": "integrity",
            "current_user": current_user,
            "is_production": config.IS_PRODUCTION
        }
    )

# --------------------------------------------------------------------------
# Auth & Account Pages
# --------------------------------------------------------------------------

@ui_router.get("/login", response_class=HTMLResponse)
def ui_login(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    if current_user:
        return RedirectResponse(url="/ui")
    return templates.TemplateResponse(
        request=request,
        name="ui/login.html",
        context={"current_user": None, "is_production": config.IS_PRODUCTION}
    )

@ui_router.get("/register", response_class=HTMLResponse)
def ui_register(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    if current_user:
        return RedirectResponse(url="/ui")
    return templates.TemplateResponse(
        request=request,
        name="ui/register.html",
        context={"current_user": None, "is_production": config.IS_PRODUCTION}
    )

@ui_router.get("/account", response_class=HTMLResponse)
def ui_account(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(
        request=request,
        name="ui/account.html",
        context={
            "current_user": current_user,
            "active_tab": "account",
            "is_production": config.IS_PRODUCTION
        }
    )

@ui_router.get("/privacy", response_class=HTMLResponse)
def ui_privacy(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    return templates.TemplateResponse(
        request=request,
        name="ui/privacy.html",
        context={
            "current_user": current_user,
            "active_tab": "privacy",
            "is_production": config.IS_PRODUCTION
        }
    )

@ui_router.get("/ui/audit", response_class=HTMLResponse)
def ui_audit_trail(
    request: Request,
    action: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))

    logs = q.order_by(desc(AuditLog.timestamp)).limit(100).all()

    return templates.TemplateResponse(
        request=request,
        name="ui/audit.html",
        context={
            "logs": logs,
            "filter_action": action,
            "active_tab": "audit",
            "current_user": admin,
            "is_production": config.IS_PRODUCTION
        }
    )
