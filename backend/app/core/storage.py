"""
Storage Abstraction Layer.
Supports database blob storage (BYTEA / LargeBinary) for ephemeral/cloud environments (Render/Neon)
and filesystem storage for local development. Provides unified byte access and safe temp-file context.
Encrypts document payloads at rest using Fernet while computing hash chain signatures over original bytes.
"""

import os
import hashlib
import tempfile
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Generator, Tuple
from sqlalchemy.orm import Session

from backend.app.core import config
from backend.app.core.security import encrypt_bytes, decrypt_bytes
from backend.app.db.models import Document, DocumentBlob, DemoTamperLog

logger = logging.getLogger("kyc.storage")

def save_document(
    db: Session,
    document: Document,
    file_bytes: bytes,
    filename: str
) -> str:
    """
    Persists document bytes either in PostgreSQL BYTEA table or on local filesystem.
    Computes sha256 over original plaintext bytes, then encrypts payload at rest.
    """
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    document.sha256 = file_sha256

    # Encrypt at rest
    encrypted_payload = encrypt_bytes(file_bytes)

    if config.STORAGE_BACKEND == "db":
        # Database blob storage (encrypted at rest)
        blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == document.id).first()
        if blob:
            blob.filename = filename
            blob.data = encrypted_payload
        else:
            blob = DocumentBlob(
                document_id=document.id,
                filename=filename,
                data=encrypted_payload
            )
            db.add(blob)
        document.file_path = f"db://{document.id}/{filename}"
        logger.info(f"[Storage:db] Saved document {document.id} ({len(file_bytes)} plaintext bytes, encrypted at rest) to document_blobs")
    else:
        # Filesystem storage
        clean_name = f"{document.id}_{os.path.basename(filename)}"
        target_path = config.UPLOAD_DIR / clean_name
        target_path.write_bytes(encrypted_payload)
        document.file_path = str(target_path)
        logger.info(f"[Storage:disk] Saved document {document.id} (encrypted at rest) to {target_path}")

    return document.file_path

def get_document_bytes(db: Session, document_id: str) -> Optional[bytes]:
    """Retrieves document bytes transparently from DB blob or filesystem, decrypting if encrypted."""
    # 1. Try DB blob table first
    blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == document_id).first()
    if blob and blob.data:
        return decrypt_bytes(blob.data)

    # 2. Try disk file path from document record
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc and doc.file_path and not doc.file_path.startswith("db://"):
        disk_path = Path(doc.file_path)
        if disk_path.exists():
            raw = disk_path.read_bytes()
            return decrypt_bytes(raw)

    return None

@contextmanager
def get_document_file_context(db: Session, document_id: str) -> Generator[Path, None, None]:
    """
    Context manager that guarantees a readable decrypted physical file on disk.
    Creates a temporary decrypted file and securely deletes it on exit.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise FileNotFoundError(f"Document {document_id} not found in database.")

    data = get_document_bytes(db, document_id)
    if data is None:
        raise FileNotFoundError(f"No bytes found for document {document_id} in blob or disk.")

    ext = Path(doc.file_path).suffix if doc.file_path else ".bin"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        yield tmp_path
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass

def tamper_document_byte(db: Session, document_id: Optional[str] = None) -> Tuple[str, int, int]:
    """
    Flips a single byte in stored document data to simulate physical tampering.
    Only permitted when DEMO_MODE=true and not in production.
    """
    if config.IS_PRODUCTION or not config.DEMO_MODE:
        raise PermissionError("Tampering simulation is disabled in pilot and production environments.")

    # Pick target document
    doc = None
    if document_id:
        doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        doc = db.query(Document).order_by(Document.created_at.desc()).first()
    if not doc:
        raise ValueError("No documents exist in the database to simulate tampering.")

    target_id = doc.id

    # 1. If in DB mode
    blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == target_id).first()
    if blob and blob.data:
        raw_bytes = bytearray(blob.data)
        if len(raw_bytes) == 0:
            raise ValueError(f"Document {target_id} has 0 bytes.")
        offset = len(raw_bytes) // 2
        orig_byte = raw_bytes[offset]
        raw_bytes[offset] = (orig_byte ^ 0xFF) # Invert bits
        blob.data = bytes(raw_bytes)

        # Record in tamper log
        log = DemoTamperLog(
            document_id=target_id,
            byte_offset=offset,
            original_byte=orig_byte
        )
        db.add(log)
        db.commit()
        logger.warning(f"[Storage:Tamper] Flipped byte at offset {offset} for document {target_id} in DB")
        return target_id, offset, orig_byte

    # 2. Disk mode
    if doc.file_path and not doc.file_path.startswith("db://"):
        p = Path(doc.file_path)
        if p.exists():
            raw_bytes = bytearray(p.read_bytes())
            offset = len(raw_bytes) // 2
            orig_byte = raw_bytes[offset]
            raw_bytes[offset] = (orig_byte ^ 0xFF)
            p.write_bytes(bytes(raw_bytes))

            log = DemoTamperLog(
                document_id=target_id,
                byte_offset=offset,
                original_byte=orig_byte
            )
            db.add(log)
            db.commit()
            logger.warning(f"[Storage:Tamper] Flipped byte at offset {offset} for document {target_id} on disk")
            return target_id, offset, orig_byte

    raise ValueError(f"Could not locate storage payload for document {target_id}")

def restore_tampered_documents(db: Session) -> int:
    """Restores all tampered documents to their verified original states."""
    if config.IS_PRODUCTION or not config.DEMO_MODE:
        raise PermissionError("Tamper restoration is disabled in pilot and production environments.")

    tamper_logs = db.query(DemoTamperLog).all()
    if not tamper_logs:
        return 0

    count = 0
    for log in tamper_logs:
        target_id = log.document_id
        offset = log.byte_offset
        orig_byte = log.original_byte

        # Try DB
        blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == target_id).first()
        if blob and blob.data:
            raw_bytes = bytearray(blob.data)
            if offset < len(raw_bytes):
                raw_bytes[offset] = orig_byte
                blob.data = bytes(raw_bytes)
                count += 1

        # Try Disk
        doc = db.query(Document).filter(Document.id == target_id).first()
        if doc and doc.file_path and not doc.file_path.startswith("db://"):
            p = Path(doc.file_path)
            if p.exists():
                raw_bytes = bytearray(p.read_bytes())
                if offset < len(raw_bytes):
                    raw_bytes[offset] = orig_byte
                    p.write_bytes(bytes(raw_bytes))
                    count += 1

        db.delete(log)

    db.commit()
    logger.info(f"[Storage:Restore] Successfully restored {count} tampered document payload(s).")
    return count
