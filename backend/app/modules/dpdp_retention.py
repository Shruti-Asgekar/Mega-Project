"""
DPDP Act & Privacy Compliance: Data Retention and Right-to-Erasure Sweep.
Ensures expired records are purged while maintaining cryptographic chain integrity through tombstones.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.app.core import config
from backend.app.db.models import Case, Document, DocumentBlob, ChainRecord, Applicant, UserSession, AuditLog

logger = logging.getLogger("kyc.retention")

def sweep_expired_retention(db: Session, force_days: int = None) -> Dict[str, Any]:
    """
    Sweeps database for expired records exceeding the DPDP data retention policy window.
    Actions:
    1. Removes DocumentBlob payload data (encrypted document content)
    2. Writes a Tombstone marker in the cryptographic chain ledger
    3. Clears applicant encrypted PII (phone, address)
    4. Marks Case as is_deleted=True
    5. Cleans expired UserSession tokens
    """
    retention_days = force_days if force_days is not None else config.RETENTION_DAYS
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(days=retention_days)

    # 1. Sweep expired cases
    cases_query = db.query(Case).filter(
        Case.is_deleted == False
    ).all()

    expired_cases: List[Case] = []
    for c in cases_query:
        # Check explicit expires_at or age vs retention_days
        c_time = c.created_at
        if c_time.tzinfo is None:
            c_time = c_time.replace(tzinfo=timezone.utc)

        if c.expires_at:
            exp = c.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                expired_cases.append(c)
                continue

        if c_time < cutoff_time:
            expired_cases.append(c)

    purged_documents_count = 0
    tombstones_recorded_count = 0

    for case in expired_cases:
        case.is_deleted = True
        case.deleted_at = now

        for doc in case.documents:
            # Check and delete payload from DocumentBlob
            blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == doc.id).first()
            if blob:
                # Replace payload with empty bytes to free storage
                blob.data = b""
                purged_documents_count += 1

            # Check chain record and mark as tombstone
            chain_rec = db.query(ChainRecord).filter(ChainRecord.document_id == doc.id).first()
            if chain_rec:
                chain_rec.is_tombstone = True
                chain_rec.tombstone_reason = f"DPDP_RETENTION_EXPIRY (Retention {retention_days} days reached)"
                tombstones_recorded_count += 1

        # Clear encrypted PII from applicant
        if case.applicant:
            case.applicant.phone_encrypted = None
            case.applicant.address_encrypted = None

        # Add audit log
        audit = AuditLog(
            case_id=case.id,
            action="RETENTION_PURGED",
            details={
                "retention_days": retention_days,
                "reason": "DPDP retention period elapsed; document payloads purged and chain tombstoned."
            }
        )
        db.add(audit)

    # 2. Sweep expired user sessions
    expired_sessions = db.query(UserSession).filter(
        UserSession.expires_at < now
    ).delete()

    db.commit()

    summary = {
        "status": "success",
        "timestamp": now.isoformat(),
        "retention_days": retention_days,
        "cases_purged": len(expired_cases),
        "documents_cleared": purged_documents_count,
        "tombstones_created": tombstones_recorded_count,
        "expired_sessions_cleared": expired_sessions
    }
    logger.info(f"[RetentionSweep] Completed: {summary}")
    return summary
