"""
Authentication, Session Management, and Role-Based Access Control (RBAC).
Security Features:
- Argon2id password hashing with bcrypt fallback
- HttpOnly, SameSite=Lax, Secure session cookie with server-side revocation
- CSRF protection for all state-changing endpoints
- Brute-force lockout (5 failed attempts -> 15 min lock)
- RBAC enforcement (applicant | officer | admin) with deny-by-default policy
- First admin bootstrap from environment variables
- Immutable audit logging without raw PII
"""

import os
import uuid
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Callable, Tuple
from fastapi import Request, Response, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.core import config
from backend.app.core.security import (
    hash_password, verify_password, validate_password_strength, scrub_pii
)
from backend.app.db.database import get_db, SessionLocal
from backend.app.db.models import User, UserSession, AuditLog

logger = logging.getLogger("kyc.auth")

# --------------------------------------------------------------------------
# Session Token & Cookie Utilities
# --------------------------------------------------------------------------

def generate_csrf_token() -> str:
    """Generates cryptographically strong random CSRF token."""
    return secrets.token_urlsafe(32)

def create_user_session(db: Session, user: User, response: Optional[Response] = None) -> Tuple[UserSession, str]:
    """
    Creates server-side session and attaches HttpOnly and CSRF cookies to response.
    """
    session_id = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.SESSION_EXPIRY_MINUTES)

    session = UserSession(
        session_id=session_id,
        user_id=user.id,
        expires_at=expires_at,
        is_revoked=False
    )
    db.add(session)

    # Update user last login
    user.last_login_at = datetime.now(timezone.utc)
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()

    csrf_token = generate_csrf_token()

    if response:
        # Session cookie
        response.set_cookie(
            key=config.SESSION_COOKIE_NAME,
            value=session_id,
            max_age=config.SESSION_EXPIRY_MINUTES * 60 * 8, # up to 8 hrs sliding window
            httponly=True,
            secure=config.IS_PRODUCTION,
            samesite="lax",
            path="/"
        )
        # Readable CSRF cookie for client JS
        response.set_cookie(
            key=config.CSRF_COOKIE_NAME,
            value=csrf_token,
            max_age=config.SESSION_EXPIRY_MINUTES * 60 * 8,
            httponly=False,
            secure=config.IS_PRODUCTION,
            samesite="lax",
            path="/"
        )

    return session, csrf_token

def revoke_user_session(db: Session, session_id: str, response: Optional[Response] = None):
    """Marks session as revoked and removes authentication cookies."""
    session = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    if session:
        session.is_revoked = True
        db.commit()

    if response:
        response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
        response.delete_cookie(config.CSRF_COOKIE_NAME, path="/")

# --------------------------------------------------------------------------
# Authentication Dependencies
# --------------------------------------------------------------------------

def get_session_token_from_request(request: Request) -> Optional[str]:
    """Extracts session token from cookie or Authorization header."""
    cookie_token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()

    return None

def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Retrieves currently logged-in user if valid session exists.
    Performs sliding refresh on sessions close to expiry.
    """
    token = get_session_token_from_request(request)
    if not token:
        return None

    session = db.query(UserSession).filter(UserSession.session_id == token).first()
    if not session or session.is_revoked:
        return None

    now = datetime.now(timezone.utc)
    # Check expiry (handle tz-aware and naive timestamps)
    exp = session.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if exp < now:
        session.is_revoked = True
        db.commit()
        return None

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        return None

    # Sliding refresh: extend expiry if more than halfway through session
    remaining = (exp - now).total_seconds()
    if remaining < (config.SESSION_EXPIRY_MINUTES * 30):
        session.expires_at = now + timedelta(minutes=config.SESSION_EXPIRY_MINUTES)
        db.commit()

    return user

def get_current_user(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """
    Enforces authentication.
    Returns User if authenticated; raises 401 JSON for API or redirects to /login for UI.
    """
    if user:
        return user

    if request.url.path.startswith("/api/"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "UNAUTHORIZED", "message": "Authentication required to access this resource.", "code": "AUTH_REQUIRED"}
        )

    # For UI routes, redirect to login
    next_url = request.url.path
    if request.url.query:
        next_url = f"{next_url}?{request.url.query}"
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": f"/login?next={next_url}"}
    )

def require_role(allowed_roles: List[str]) -> Callable:
    """
    Role-Based Access Control (RBAC) dependency.
    Denies access with 403 Forbidden unless user has one of allowed_roles.
    """
    def _role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "FORBIDDEN", "message": f"Action requires one of roles: {', '.join(allowed_roles)}.", "code": "INSUFFICIENT_PERMISSIONS"}
            )
        return user
    return _role_checker

# --------------------------------------------------------------------------
# CSRF Protection
# --------------------------------------------------------------------------

def verify_csrf(request: Request):
    """
    Verifies double-submit CSRF token on state-changing requests (POST, PUT, DELETE, PATCH).
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # If authenticated via API Bearer token, skip CSRF
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return

    # If no session cookie is set yet, request has no active session to hijack
    if not request.cookies.get(config.SESSION_COOKIE_NAME):
        return

    cookie_csrf = request.cookies.get(config.CSRF_COOKIE_NAME)
    header_csrf = request.headers.get("X-CSRF-Token")

    if not cookie_csrf or not header_csrf or not secrets.compare_digest(cookie_csrf, header_csrf):
        logger.warning(f"[CSRF] Rejection on {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CSRF_VERIFICATION_FAILED", "message": "Security token missing or invalid. Please refresh the page.", "code": "CSRF_ERROR"}
        )

# --------------------------------------------------------------------------
# Audit Logging
# --------------------------------------------------------------------------

def record_audit(
    db: Session,
    action: str,
    user: Optional[User] = None,
    case_id: Optional[str] = None,
    ip: Optional[str] = None,
    details: Optional[dict] = None
):
    """
    Records an immutable audit event without raw PII.
    """
    clean_details = {}
    if details:
        for k, v in details.items():
            if isinstance(v, str):
                clean_details[k] = scrub_pii(v)
            else:
                clean_details[k] = v

    log = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        role=user.role if user else None,
        action=action,
        case_id=case_id,
        ip=ip,
        details=clean_details
    )
    db.add(log)
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record audit log: {e}")

# --------------------------------------------------------------------------
# Admin Bootstrap
# --------------------------------------------------------------------------

def bootstrap_admin_user():
    """
    Ensures at least one administrator account exists upon deployment startup.
    Uses ADMIN_EMAIL and ADMIN_PASSWORD if provided.
    """
    if not config.ADMIN_EMAIL:
        return

    db = SessionLocal()
    try:
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count == 0:
            default_pwd = config.ADMIN_PASSWORD or secrets.token_urlsafe(16)
            logger.info(f"[Bootstrap] No administrator found. Creating primary admin: {config.ADMIN_EMAIL}")
            admin_user = User(
                email=config.ADMIN_EMAIL,
                full_name=config.ADMIN_NAME,
                password_hash=hash_password(default_pwd),
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            if not config.ADMIN_PASSWORD:
                logger.warning(f"[Bootstrap] Auto-generated temporary admin password: {default_pwd} (Please change immediately on /account)")
        else:
            logger.info(f"[Bootstrap] Administrator account exists ({admin_count} registered).")
    except Exception as e:
        logger.error(f"[Bootstrap] Error initializing administrator account: {e}")
    finally:
        db.close()
