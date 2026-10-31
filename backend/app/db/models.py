"""
Database Models (SQLAlchemy 2).
Supports PostgreSQL and SQLite. Sensitive full values are Fernet-encrypted.
Includes document blob storage for ephemeral environments, cryptographic hash chain,
user authentication, session management, and DPDP-compliant retention tombstones.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON, LargeBinary
)
from sqlalchemy.orm import relationship
from backend.app.db.database import Base

def gen_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(50), nullable=False, default="applicant")  # applicant | officer | admin
    is_active = Column(Boolean, default=True, nullable=False)
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    last_login_at = Column(DateTime, nullable=True)

    cases = relationship("Case", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="sessions")

class Applicant(Base):
    __tablename__ = "applicants"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name_encrypted = Column(Text, nullable=False)
    name_masked = Column(String(255), nullable=False)
    phone_encrypted = Column(Text, nullable=True)
    phone_masked = Column(String(50), nullable=True)
    phone_hmac = Column(String(64), nullable=True, index=True)
    address_encrypted = Column(Text, nullable=True)
    address_normalised = Column(Text, nullable=True)
    address_hmac = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=utc_now)

    cases = relationship("Case", back_populates="applicant", cascade="all, delete-orphan")

class Case(Base):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    applicant_id = Column(String(36), ForeignKey("applicants.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Pipeline & Lifecycle Status
    status = Column(String(50), default="SUBMITTED")  # SUBMITTED | PROCESSING | COMPLETED | ARCHIVED
    pipeline_status = Column(String(50), default="queued")  # queued | running | done | failed
    pipeline_step = Column(String(50), default="QUEUED")  # QUEUED | EXTRACTING | QUALITY | CROSS_DOC | INCOME | FRAUD_GRAPH | HASH_CHAIN | ROUTING | COMPLETED
    pipeline_error = Column(Text, nullable=True)
    
    trust_score = Column(Integer, default=100)
    route = Column(String(50), default="OFFICER_REVIEW")
    score_breakdown = Column(JSON, default=dict)
    
    # Officer Review & Decision Recording
    decision = Column(String(50), nullable=True)  # APPROVED | REJECTED | INFO_REQUESTED
    decision_comment = Column(Text, nullable=True)
    decision_by = Column(String(255), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    
    # Retention & DPDP Controls
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="cases")
    applicant = relationship("Applicant", back_populates="cases")
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    flags = relationship("FlagModel", back_populates="case", cascade="all, delete-orphan")
    consents = relationship("Consent", back_populates="case", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="case", cascade="all, delete-orphan")

class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    file_path = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)
    doc_type = Column(String(50), nullable=False)
    quality_score = Column(Float, nullable=True)
    masked_fields = Column(JSON, default=dict)
    extracted_json = Column(JSON, default=dict)
    field_confidences = Column(JSON, default=dict)
    user_confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    case = relationship("Case", back_populates="documents")
    flags = relationship("FlagModel", back_populates="document", cascade="all, delete-orphan")
    chain_record = relationship("ChainRecord", back_populates="document", uselist=False, cascade="all, delete-orphan")
    blob = relationship("DocumentBlob", back_populates="document", uselist=False, cascade="all, delete-orphan")

class DocumentBlob(Base):
    __tablename__ = "document_blobs"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    filename = Column(String(255), nullable=False)
    data = Column(LargeBinary, nullable=False)  # Encrypted at rest via Fernet
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    document = relationship("Document", back_populates="blob")

class FlagModel(Base):
    __tablename__ = "flags"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    code = Column(String(100), nullable=False)
    module = Column(Integer, nullable=False)
    severity = Column(String(20), nullable=False)  # red, amber, green
    score_impact = Column(Integer, default=0)
    details = Column(JSON, default=dict)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    case = relationship("Case", back_populates="flags")
    document = relationship("Document", back_populates="flags")

class Consent(Base):
    __tablename__ = "consents"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    user_id = Column(String(36), nullable=True)
    accepted = Column(Boolean, nullable=False, default=True)
    timestamp = Column(DateTime, nullable=False, default=utc_now)
    ip = Column(String(100), nullable=False, default="127.0.0.1")
    text_version = Column(String(50), nullable=False, default="v1.0")

    case = relationship("Case", back_populates="consents")

class ChainRecord(Base):
    __tablename__ = "chain_records"

    seq = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, unique=True)
    file_sha256 = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=False)
    record_hash = Column(String(64), nullable=False)
    is_tombstone = Column(Boolean, default=False, nullable=False)
    tombstone_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    document = relationship("Document", back_populates="chain_record")

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), nullable=True, index=True)
    user_email = Column(String(255), nullable=True)
    role = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    ip = Column(String(100), nullable=True)
    details = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=utc_now, index=True)

    case = relationship("Case", back_populates="audit_logs")

class DemoTamperLog(Base):
    __tablename__ = "demo_tamper_log"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    byte_offset = Column(Integer, nullable=False)
    original_byte = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now)
