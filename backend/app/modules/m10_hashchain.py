"""
Module 10: Cryptographic Hash Chain Ledger.
Maintains an immutable append-only hash chain linking all documents.
Detects tampering, physical modifications, or history re-writing.
Supports DPDP-compliant tombstone records when data is purged under retention.
"""

import os
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.app.core.contracts import Flag, FlagCode, Severity
from backend.app.db.models import Document, ChainRecord, Case

GENESIS_PREV_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hex digest of a physical file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()

def compute_bytes_sha256(data: bytes) -> str:
    """Computes SHA-256 hex digest of a byte sequence."""
    return hashlib.sha256(data).hexdigest()

def format_chain_timestamp(dt: datetime) -> str:
    """Standardizes datetime to ISO 8601 UTC string for consistent hashing."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def compute_record_hash(
    prev_hash: str,
    file_sha256: str,
    document_id: str,
    doc_type: str,
    created_at_iso: str
) -> str:
    """
    Computes cryptographic block hash for a chain record:
    SHA-256(prev_hash + file_sha256 + document_id + doc_type + created_at)
    """
    raw_payload = f"{prev_hash}{file_sha256}{document_id}{doc_type}{created_at_iso}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()

def append_document_to_chain(db: Session, document: Document) -> ChainRecord:
    """
    Appends a new verified document to the immutable cryptographic hash chain.
    """
    existing = db.query(ChainRecord).filter(ChainRecord.document_id == document.id).first()
    if existing:
        return existing

    latest_record = db.query(ChainRecord).order_by(ChainRecord.seq.desc()).first()
    prev_hash = latest_record.record_hash if latest_record else GENESIS_PREV_HASH

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
        is_tombstone=False,
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
    3. Re-hashes the physical file/blob against stored file_sha256
    4. Supports tombstone blocks where data was hard-deleted under DPDP policies.
    """
    from backend.app.core.storage import get_document_bytes

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

        # 2. Block Hash Recomputation Check (support standard and microsecond timestamps)
        created_at_utc = rec.created_at if rec.created_at.tzinfo else rec.created_at.replace(tzinfo=timezone.utc)
        recomputed_rec_hash = compute_record_hash(
            prev_hash=rec.prev_hash,
            file_sha256=rec.file_sha256,
            document_id=rec.document_id,
            doc_type=doc_type,
            created_at_iso=created_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        if recomputed_rec_hash != rec.record_hash:
            recomputed_rec_hash = compute_record_hash(
                prev_hash=rec.prev_hash,
                file_sha256=rec.file_sha256,
                document_id=rec.document_id,
                doc_type=doc_type,
                created_at_iso=created_at_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            )

        if recomputed_rec_hash != rec.record_hash:
            return {
                "valid": False,
                "first_broken_seq": rec.seq,
                "document_id": rec.document_id,
                "reason": f"Block #{rec.seq} internal hash mismatch. Payload has been tampered with.",
                "records": record_audits
            }

        # 3. Handle DPDP Retention Tombstone
        if getattr(rec, "is_tombstone", False):
            record_audits.append({
                "seq": rec.seq,
                "document_id": rec.document_id,
                "doc_type": doc_type,
                "file_sha256": rec.file_sha256[:16] + "...",
                "record_hash": rec.record_hash[:16] + "...",
                "status": "TOMBSTONE_VERIFIED"
            })
            expected_prev = rec.record_hash
            continue

        # 4. Document Data Re-Hash Check (DB Blob or Filesystem)
        doc_bytes = get_document_bytes(db, rec.document_id)
        if doc_bytes is None:
            return {
                "valid": False,
                "first_broken_seq": rec.seq,
                "document_id": rec.document_id,
                "reason": f"Physical document file/data missing from storage for seq {rec.seq} ({file_path}).",
                "records": record_audits
            }

        current_hash = hashlib.sha256(doc_bytes).hexdigest()
        if current_hash != rec.file_sha256:
            return {
                "valid": False,
                "first_broken_seq": rec.seq,
                "document_id": rec.document_id,
                "reason": "Physical document data has been modified or corrupted! SHA-256 differs from ledger.",
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
    Verifies chain records and payload integrity for all documents belonging to a case.
    """
    from backend.app.core.storage import get_document_bytes

    flags: List[Flag] = []
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return flags

    for doc in case.documents:
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

        if getattr(chain_rec, "is_tombstone", False):
            continue

        # Check payload bytes
        doc_bytes = get_document_bytes(db, doc.id)
        if doc_bytes is None:
            flags.append(
                Flag(
                    code=FlagCode.INTEGRITY_BROKEN,
                    module=10,
                    severity=Severity.RED,
                    score_impact=50,
                    details={"document_id": doc.id, "reason": "Physical document file/blob missing in storage."},
                    document_id=doc.id
                )
            )
            continue

        current_hash = hashlib.sha256(doc_bytes).hexdigest()
        if current_hash != doc.sha256:
            flags.append(
                Flag(
                    code=FlagCode.INTEGRITY_BROKEN,
                    module=10,
                    severity=Severity.RED,
                    score_impact=50,
                    details={
                        "document_id": doc.id,
                        "stored_sha256": doc.sha256,
                        "calculated_sha256": current_hash,
                        "reason": "Payload has been altered after initial verification."
                    },
                    document_id=doc.id
                )
            )
            continue

        # Recompute block hash (support standard and microsecond timestamps)
        rec_created_utc = chain_rec.created_at if chain_rec.created_at.tzinfo else chain_rec.created_at.replace(tzinfo=timezone.utc)
        rec_hash = compute_record_hash(
            prev_hash=chain_rec.prev_hash,
            file_sha256=doc.sha256,
            document_id=doc.id,
            doc_type=doc.doc_type,
            created_at_iso=rec_created_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        if rec_hash != chain_rec.record_hash:
            rec_hash = compute_record_hash(
                prev_hash=chain_rec.prev_hash,
                file_sha256=doc.sha256,
                document_id=doc.id,
                doc_type=doc.doc_type,
                created_at_iso=rec_created_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            )
        if rec_hash != chain_rec.record_hash:
            flags.append(
                Flag(
                    code=FlagCode.INTEGRITY_BROKEN,
                    module=10,
                    severity=Severity.RED,
                    score_impact=50,
                    details={
                        "document_id": doc.id,
                        "reason": "Chain block header hash mismatch; immutable ledger record modified."
                    },
                    document_id=doc.id
                )
            )
            continue

        # Intact
        flags.append(
            Flag(
                code=FlagCode.INTEGRITY_VERIFIED,
                module=10,
                severity=Severity.GREEN,
                score_impact=0,
                details={"document_id": doc.id, "seq": chain_rec.seq, "sha256": doc.sha256},
                document_id=doc.id
            )
        )

    return flags
