"""
Storage Abstraction Layer.
Supports database blob storage (BYTEA / LargeBinary) for ephemeral/cloud environments (Render/Neon)
and filesystem storage for local development. Provides unified byte access and safe temp-file context.
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
    Updates document sha256 and file_path accordingly.
    """
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    document.sha256 = file_sha256

    if config.STORAGE_BACKEND == "db":
        # Database blob storage
        blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == document.id).first()
        if blob:
            blob.filename = filename
            blob.data = file_bytes
        else:
            blob = DocumentBlob(
                document_id=document.id,
                filename=filename,
                data=file_bytes
            )
            db.add(blob)
        document.file_path = f"db://{document.id}/{filename}"
        logger.info(f"[Storage:db] Saved document {document.id} ({len(file_bytes)} bytes) to document_blobs")
    else:
        # Filesystem storage
        clean_name = f"{document.id}_{os.path.basename(filename)}"
        target_path = config.UPLOAD_DIR / clean_name
        target_path.write_bytes(file_bytes)
        document.file_path = str(target_path)
        logger.info(f"[Storage:disk] Saved document {document.id} to {target_path}")

    return document.file_path

def get_document_bytes(db: Session, document_id: str) -> Optional[bytes]:
    """Retrieves document bytes transparently from DB blob or filesystem."""
    # 1. Try DB blob table first
    blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == document_id).first()
    if blob and blob.data:
        return blob.data

    # 2. Try disk file path from document record
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc and doc.file_path and not doc.file_path.startswith("db://"):
        disk_path = Path(doc.file_path)
        if disk_path.exists():
            return disk_path.read_bytes()

    return None

@contextmanager
def get_document_file_context(db: Session, document_id: str) -> Generator[Path, None, None]:
    """
    Context manager that guarantees a readable physical file on disk.
    If the document is stored in DB blob, creates a temporary file and deletes it on exit.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise FileNotFoundError(f"Document {document_id} not found in database.")

    # If physical file already exists on disk, use it directly
    if doc.file_path and not doc.file_path.startswith("db://"):
        p = Path(doc.file_path)
        if p.exists():
            yield p
            return

    # Otherwise stream bytes from DB blob into temporary file
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
    Records the original byte and offset in demo_tamper_log.
    """
    # Pick target document
    doc = None
    if document_id:
        doc = db.query(Document).filter(Document.id == document_id).first()

    if not doc:
        # Find first document that has bytes
        candidates = db.query(Document).all()
        for cand in candidates:
            if get_document_bytes(db, cand.id) is not None:
                doc = cand
                break

    if not doc:
        raise ValueError("No verified documents found to tamper.")

    data = get_document_bytes(db, doc.id)
    if not data or len(data) == 0:
        raise ValueError(f"Document {doc.id} contains empty payload.")

    content = bytearray(data)
    idx = len(content) // 2
    orig_byte = content[idx]
    content[idx] ^= 0xFF # Flip bits

    # Record tamper action in log
    tamper_rec = DemoTamperLog(
        document_id=doc.id,
        byte_offset=idx,
        original_byte=orig_byte
    )
    db.add(tamper_rec)

    # Persist tampered bytes
    blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == doc.id).first()
    if blob:
        blob.data = bytes(content)
    elif doc.file_path and not doc.file_path.startswith("db://"):
        Path(doc.file_path).write_bytes(content)

    db.commit()
    logger.warning(f"[TAMPER] Document {doc.id} tampered at offset {idx} (original={orig_byte})")
    return doc.id, idx, orig_byte

def restore_tampered_documents(db: Session) -> int:
    """Restores all tampered documents to their original bytes and clears tamper logs."""
    logs = db.query(DemoTamperLog).all()
    restored_count = 0

    for log in logs:
        data = get_document_bytes(db, log.document_id)
        if data and len(data) > log.byte_offset:
            content = bytearray(data)
            content[log.byte_offset] = log.original_byte

            blob = db.query(DocumentBlob).filter(DocumentBlob.document_id == log.document_id).first()
            if blob:
                blob.data = bytes(content)

            doc = db.query(Document).filter(Document.id == log.document_id).first()
            if doc and doc.file_path and not doc.file_path.startswith("db://"):
                p = Path(doc.file_path)
                if p.exists():
                    p.write_bytes(content)

            restored_count += 1
        db.delete(log)

    db.commit()
    logger.info(f"[RESTORE] Restored {restored_count} tampered document(s).")
    return restored_count
