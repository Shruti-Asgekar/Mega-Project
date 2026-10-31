"""
Authentication & RBAC API Routes.
Provides registration, login, logout, password change, account management,
officer case decision recording, and admin audit log inspection.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.app.core import config
from backend.app.core.security import (
    hash_password, verify_password, validate_password_strength, scrub_pii, decrypt_value
)
from backend.app.core.auth import (
    create_user_session, revoke_user_session, get_current_user,
    get_current_user_optional, require_role, record_audit, verify_csrf,
    get_session_token_from_request
)
from backend.app.db.database import get_db
from backend.app.db.models import User, UserSession, Case, AuditLog, Applicant, Document
from backend.app.modules.dpdp_retention import sweep_expired_retention

router = APIRouter()

# --------------------------------------------------------------------------
# Request / Response Models
# --------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=10)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=10)

class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED|INFO_REQUESTED)$")
    comment: str = Field(..., min_length=3, max_length=1000)

class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool

# --------------------------------------------------------------------------
# Authentication Endpoints
# --------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Registers a new Applicant account.
    Validates password strength, hashes with Argon2id, creates session, and records audit log.
    """
    # 1. Check existing user
    existing = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "EMAIL_EXISTS", "message": "An account with this email address already exists.", "field": "email"}
        )

    # 2. Validate password strength
    is_valid, reason = validate_password_strength(payload.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "WEAK_PASSWORD", "message": reason, "field": "password"}
        )

    # 3. Create user
    user = User(
        email=payload.email.lower().strip(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role="applicant",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 4. Auto-login (create session)
    session, csrf_token = create_user_session(db, user, response)

    client_ip = request.client.host if request.client else None
    record_audit(db, "USER_REGISTERED", user=user, ip=client_ip, details={"role": "applicant"})

    return {
        "status": "success",
        "message": "Account created successfully.",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        },
        "csrf_token": csrf_token
    }


@router.post("/login")
def login_user(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Logs in with email and password.
    Enforces brute-force lockout (5 failed attempts -> 15 min lock).
    """
    email_clean = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email_clean).first()
    client_ip = request.client.host if request.client else None

    if not user:
        # Prevent timing-based user enumeration with dummy verify
        verify_password(payload.password, "$argon2id$v=19$m=65536,t=3,p=4$dummyhash$dummyhash")
        record_audit(db, "LOGIN_FAILED", ip=client_ip, details={"email": email_clean, "reason": "unknown_email"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "Invalid email or password."}
        )

    # Check lockout
    now = datetime.now(timezone.utc)
    if user.locked_until:
        lock_time = user.locked_until
        if lock_time.tzinfo is None:
            lock_time = lock_time.replace(tzinfo=timezone.utc)
        if lock_time > now:
            remaining_min = int((lock_time - now).total_seconds() // 60) + 1
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail={
                    "error": "ACCOUNT_LOCKED",
                    "message": f"Account temporarily locked due to repeated failed logins. Please try again in {remaining_min} minute(s)."
                }
            )
        else:
            # Lock expired
            user.locked_until = None
            user.failed_attempts = 0
            db.commit()

    # Verify password
    if not verify_password(payload.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= 5:
            user.locked_until = now + timedelta(minutes=15)
            db.commit()
            record_audit(db, "ACCOUNT_LOCKED", user=user, ip=client_ip, details={"attempts": user.failed_attempts})
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail={"error": "ACCOUNT_LOCKED", "message": "Account locked for 15 minutes due to 5 failed attempts."}
            )

        db.commit()
        record_audit(db, "LOGIN_FAILED", user=user, ip=client_ip, details={"attempt": user.failed_attempts})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "Invalid email or password."}
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "ACCOUNT_DISABLED", "message": "Your account has been deactivated. Contact an administrator."}
        )

    session, csrf_token = create_user_session(db, user, response)
    record_audit(db, "USER_LOGGED_IN", user=user, ip=client_ip)

    return {
        "status": "success",
        "message": "Login successful.",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        },
        "csrf_token": csrf_token
    }


@router.post("/logout")
def logout_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Revokes the current session and clears authentication cookies.
    """
    token = get_session_token_from_request(request)
    if token:
        revoke_user_session(db, token, response)

    client_ip = request.client.host if request.client else None
    if user:
        record_audit(db, "USER_LOGGED_OUT", user=user, ip=client_ip)

    return {"status": "success", "message": "Logged out successfully."}


@router.get("/me")
def get_current_user_profile(user: User = Depends(get_current_user)):
    """Returns the authenticated user's profile."""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
    }


@router.post("/change-password")
def change_user_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Changes password after verifying existing password and enforcing complexity."""
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "WRONG_PASSWORD", "message": "Current password is incorrect.", "field": "old_password"}
        )

    is_valid, reason = validate_password_strength(payload.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "WEAK_PASSWORD", "message": reason, "field": "new_password"}
        )

    user.password_hash = hash_password(payload.new_password)
    db.commit()

    client_ip = request.client.host if request.client else None
    record_audit(db, "PASSWORD_CHANGED", user=user, ip=client_ip)

    return {"status": "success", "message": "Password changed successfully."}


@router.post("/delete-account")
def delete_own_account(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    DPDP Right to Erasure: Removes user account and their associated verification cases.
    """
    client_ip = request.client.host if request.client else None
    user_id = user.id
    user_email = user.email

    # Mark user cases as deleted
    user_cases = db.query(Case).filter(Case.user_id == user_id).all()
    for c in user_cases:
        c.is_deleted = True
        c.deleted_at = datetime.now(timezone.utc)

    # Revoke sessions
    db.query(UserSession).filter(UserSession.user_id == user_id).delete()

    # Soft-delete or remove user
    user.is_active = False
    user.email = f"deleted_{uuid.uuid4().hex[:8]}@anonymized.local"
    db.commit()

    token = get_session_token_from_request(request)
    if token:
        revoke_user_session(db, token, response)

    record_audit(db, "ACCOUNT_DELETED", user=None, ip=client_ip, details={"user_id": user_id, "anonymized_email": user_email})

    return {"status": "success", "message": "Your account and data have been removed per DPDP regulations."}


@router.get("/download-data")
def download_own_data(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    DPDP Right to Data Portability: Returns an export of personal records in privacy-masked JSON format.
    """
    user_cases = db.query(Case).filter(Case.user_id == user.id, Case.is_deleted == False).all()
    cases_export = []
    for c in user_cases:
        appl = c.applicant
        cases_export.append({
            "case_id": c.id,
            "status": c.status,
            "trust_score": c.trust_score,
            "route": c.route,
            "decision": c.decision,
            "applicant": {
                "name": appl.name_masked if appl else None,
                "created_at": c.created_at.isoformat() if c.created_at else None
            },
            "documents": [
                {
                    "id": d.id,
                    "doc_type": d.doc_type,
                    "quality_score": d.quality_score,
                    "masked_fields": d.masked_fields
                }
                for d in c.documents
            ]
        })

    record_audit(db, "DATA_PORTABILITY_EXPORTED", user=user)

    return {
        "user_profile": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None
        },
        "cases": cases_export,
        "exported_at": datetime.now(timezone.utc).isoformat()
    }


# --------------------------------------------------------------------------
# Officer Decision Recording
# --------------------------------------------------------------------------

@router.post("/cases/{case_id}/decision")
def record_case_decision(
    case_id: str,
    payload: DecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    officer: User = Depends(require_role(["officer", "admin"]))
):
    """
    Allows verification officers and admins to record an approval, rejection, or info request.
    Mandatory rationale comment required for accountability.
    """
    case = db.query(Case).filter(Case.id == case_id, Case.is_deleted == False).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "CASE_NOT_FOUND", "message": f"Case {case_id} not found."}
        )

    case.decision = payload.decision
    case.decision_comment = payload.comment.strip()
    case.decision_by = officer.email
    case.decided_at = datetime.now(timezone.utc)
    db.commit()

    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        "CASE_DECISION_RECORDED",
        user=officer,
        case_id=case.id,
        ip=client_ip,
        details={"decision": payload.decision, "comment": payload.comment.strip()}
    )

    return {
        "status": "success",
        "message": f"Case decision '{payload.decision}' recorded successfully.",
        "case_id": case.id,
        "decision": case.decision,
        "decision_by": case.decision_by,
        "decided_at": case.decided_at.isoformat()
    }


# --------------------------------------------------------------------------
# Administrator Audit Logs & Governance
# --------------------------------------------------------------------------

@router.get("/admin/audit")
def get_admin_audit_logs(
    action: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    """
    Admin-only: Inspects system audit trails with pagination and filtering.
    """
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)

    total = q.count()
    logs = q.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": lg.id,
                "timestamp": lg.timestamp.isoformat() if lg.timestamp else None,
                "action": lg.action,
                "user_email": lg.user_email,
                "role": lg.role,
                "case_id": lg.case_id,
                "ip": lg.ip,
                "details": lg.details
            }
            for lg in logs
        ]
    }


@router.post("/admin/retention-sweep")
def trigger_admin_retention_sweep(
    days: Optional[int] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(["admin"]))
):
    """
    Admin-only: Manually triggers DPDP data retention sweep.
    """
    result = sweep_expired_retention(db, force_days=days)
    record_audit(db, "RETENTION_SWEEP_TRIGGERED", user=admin, details=result)
    return result
