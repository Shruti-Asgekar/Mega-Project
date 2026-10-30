"""
Module 10: Tamper-Evident Cryptographic Hash Chain.
- Sequential immutable blockchain-like ledger for verified KYC documents
- record_hash = SHA256(prev_hash || file_sha256 || document_id || doc_type || created_at_iso)
- Genesis prev_hash = 64 zeros ("0" * 64)
- Verification walk re-computes block hashes, checks linkage, and re-hashes physical files on disk
"""

import hashlib
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db.models import ChainRecord, Document, Case
from backend.app.core.contracts import Flag, FlagCode, Severity

GENESIS_PREV_HASH = "0" * 64

def compute_file_sha256(file_path: str) -> str:
    """Calculates SHA-256 hash of a file on disk."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def format_chain_timestamp(dt: datetime) -> str:
    """Standardized UTC ISO timestamp for hash chain calculation."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def compute_record_hash(
    prev_hash: str,
    file_sha256: str,
    document_id: str,
    doc_type: str,
    created_at_iso: str
) -> str:
    """
    Computes cryptographic block digest:
    SHA256(prev_hash || file_sha256 || document_id || doc_type || created_at_iso)
    """
    raw_payload = f"{prev_hash}{file_sha256}{document_id}{doc_type}{created_at_iso}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

def append_document_to_chain(
    db: Session,
    document: Document
) -> ChainRecord:
    """
    Appends a new document to the immutable hash chain inside an atomic transaction.
    Uses row-locking to guarantee linear progression.
    """
    # Check if already in chain
    existing = db.query(ChainRecord).filter(ChainRecord.document_id == document.id).first()
    if existing:
        return existing

    # Lock table or select last record
    is_postgres = db.bind and db.bind.dialect.name == "postgresql"
    if is_postgres:
        last_record = db.query(ChainRecord).order_by(ChainRecord.seq.desc()).with_for_update().first()
    else:
        last_record = db.query(ChainRecord).order_by(ChainRecord.seq.desc()).first()

    prev_hash = last_record.record_hash if last_record else GENESIS_PREV_HASH
    created_at = datetime.now(timezone.utc)
    created_at_iso = format_chain_timestamp(created_at)

    record_hash = compute_record_hash(
        prev_hash=prev_hash,
        file_sha256=document.sha256,
        document_id=document.id,
        doc_type=document.doc_type,
        created_at_iso=created_at_iso
    )

    chain_rec = ChainRecord(
        document_id=document.id,
        file_sha256=document.sha256,
        prev_hash=prev_hash,
        record_hash=record_hash,
        created_at=created_at
    )
    db.add(chain_rec)
    db.commit()
    db.refresh(chain_rec)
    return chain_rec

def verify_chain(db: Session) -> Dict[str, Any]:
    """
    Audits the entire hash chain from genesis to head:
    1. Recomputes record_hash for each block
    2. Validates prev_hash cryptographic linkage
    3. Re-hashes the physical file on disk against stored file_sha256
    """
    records = db.query(ChainRecord).order_by(ChainRecord.seq.asc()).all()
    if not records:
        return {
            "valid": True,
            "total_records": 0,
            "first_broken_seq": None,
            "message": "Hash chain is empty (genesis state intact).",
            "records": []
        }

    expected_prev = GENESIS_PREV_HASH
    record_audits = []

    for rec in records:
        doc = db.query(Document).filter(Document.id == rec.document_id).first()
        doc_type = doc.doc_type if doc else "unknown"
        file_path = doc.file_path if doc else ""

        # 1. Linkage Check
        if rec.prev_hash != expected_prev:
            return {
                "valid": False,
                "first_broken_seq": rec.seq,
                "document_id": rec.document_id,
                "reason": f"Linkage broken at block #{rec.seq}. Stored prev_hash does not match preceding block.",
                "records": record_audits
            }

        # 2. Block Hash Recomputation Check
        recomputed_rec_hash = compute_record_hash(
            prev_hash=rec.prev_hash,
            file_sha256=rec.file_sha256,
            document_id=rec.document_id,
            doc_type=doc_type,
            created_at_iso=format_chain_timestamp(rec.created_at)
        )
        if recomputed_rec_hash != rec.record_hash:
            return {
                "valid": False,
                "first_broken_seq": rec.seq,
                "document_id": rec.document_id,
                "reason": f"Block #{rec.seq} internal hash mismatch. Payload has been tampered with.",
                "records": record_audits
            }

        # 3. Disk File Re-Hash Check
        if os.path.exists(file_path):
            current_disk_hash = compute_file_sha256(file_path)
            if current_disk_hash != rec.file_sha256:
                return {
                    "valid": False,
                    "first_broken_seq": rec.seq,
                    "document_id": rec.document_id,
                    "reason": f"Physical document on disk has been modified or corrupted! Disk SHA-256 differs from ledger.",
                    "records": record_audits
                }
        else:
            return {
                "valid": False,
                "first_broken_seq": rec.seq,
                "document_id": rec.document_id,
                "reason": f"Physical document file missing on disk at {file_path}.",
                "records": record_audits
            }

        record_audits.append({
            "seq": rec.seq,
            "document_id": rec.document_id,
            "doc_type": doc_type,
            "file_sha256": rec.file_sha256[:16] + "...",
            "record_hash": rec.record_hash[:16] + "...",
            "status": "VERIFIED"
        })
        expected_prev = rec.record_hash

    return {
        "valid": True,
        "total_records": len(records),
        "first_broken_seq": None,
        "message": f"Ledger integrity verified across all {len(records)} blocks.",
        "records": record_audits
    }

def verify_case_integrity(db: Session, case_id: str) -> List[Flag]:
    """
    Verifies chain records and disk files for all documents belonging to a case.
    """
    flags: List[Flag] = []
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return flags

    for doc in case.documents:
        # Check disk file
        if not os.path.exists(doc.file_path):
            flags.append(
                Flag(
                    code=FlagCode.INTEGRITY_BROKEN,
                    module=10,
                    severity=Severity.RED,
                    score_impact=50,
                    details={"document_id": doc.id, "reason": "Physical document file missing on disk."},
                    document_id=doc.id
                )
            )
            continue

        disk_hash = compute_file_sha256(doc.file_path)
        if disk_hash != doc.sha256:
            flags.append(
                Flag(
                    code=FlagCode.INTEGRITY_BROKEN,
                    module=10,
                    severity=Severity.RED,
                    score_impact=50,
                    details={
                        "document_id": doc.id,
                        "stored_sha256": doc.sha256,
                        "disk_sha256": disk_hash,
                        "reason": "File on disk has been altered after initial verification."
                    },
                    document_id=doc.id
                )
            )
            continue

        # Check chain record
        chain_rec = db.query(ChainRecord).filter(ChainRecord.document_id == doc.id).first()
        if not chain_rec:
            flags.append(
                Flag(
                    code=FlagCode.INTEGRITY_BROKEN,
                    module=10,
                    severity=Severity.RED,
                    score_impact=50,
                    details={"document_id": doc.id, "reason": "No cryptographic chain record found for document."},
                    document_id=doc.id
                )
            )
            continue

        # Recompute
        rec_hash = compute_record_hash(
            prev_hash=chain_rec.prev_hash,
            file_sha256=doc.sha256,
            document_id=doc.id,
            doc_type=doc.doc_type,
            created_at_iso=format_chain_timestamp(chain_rec.created_at)
        )
        if rec_hash != chain_rec.record_hash:
            flags.append(
                Flag(
                    code=FlagCode.INTEGRITY_BROKEN,
                    module=10,
                    severity=Severity.RED,
                    score_impact=50,
                    details={"document_id": doc.id, "reason": "Hash chain record signature invalid."},
                    document_id=doc.id
                )
            )
            continue

    if not flags:
        flags.append(
            Flag(
                code=FlagCode.INTEGRITY_VERIFIED,
                module=10,
                severity=Severity.GREEN,
                score_impact=0,
                details={"status": "All documents verified against cryptographic ledger."}
            )
        )

    return flags
