"""
Database initialization helpers with connection retry and safe schema migrations.
"""

import time
import logging
from sqlalchemy import inspect, text
from backend.app.db.database import Base, engine, SessionLocal, get_db
from backend.app.db.models import (
    User, UserSession, Applicant, Case, Document, FlagModel, Consent,
    ChainRecord, AuditLog, DocumentBlob, DemoTamperLog
)

logger = logging.getLogger("kyc.db")

def _apply_idempotent_migrations(eng):
    """
    Safely adds any newly defined columns to existing database tables without data loss.
    Works transparently on PostgreSQL and SQLite.
    """
    inspector = inspect(eng)
    dialect = eng.dialect.name

    migrations = [
        # (table, column_name, column_def_sql)
        ("cases", "pipeline_status", "VARCHAR(50) DEFAULT 'done'"),
        ("cases", "pipeline_step", "VARCHAR(50) DEFAULT 'COMPLETED'"),
        ("cases", "pipeline_error", "TEXT"),
        ("cases", "user_id", "VARCHAR(36)"),
        ("cases", "decision", "VARCHAR(50)"),
        ("cases", "decision_comment", "TEXT"),
        ("cases", "decision_by", "VARCHAR(255)"),
        ("cases", "decided_at", "TIMESTAMP"),
        ("cases", "is_deleted", "BOOLEAN DEFAULT FALSE"),
        ("cases", "deleted_at", "TIMESTAMP"),
        ("cases", "expires_at", "TIMESTAMP"),
        ("applicants", "phone_hmac", "VARCHAR(64)"),
        ("applicants", "address_hmac", "VARCHAR(64)"),
        ("documents", "field_confidences", "JSON" if dialect == "postgresql" else "TEXT"),
        ("documents", "user_confirmed", "BOOLEAN DEFAULT FALSE"),
        ("consents", "user_id", "VARCHAR(36)"),
        ("chain_records", "is_tombstone", "BOOLEAN DEFAULT FALSE"),
        ("chain_records", "tombstone_reason", "VARCHAR(100)"),
        ("audit_log", "user_id", "VARCHAR(36)"),
        ("audit_log", "user_email", "VARCHAR(255)"),
        ("audit_log", "role", "VARCHAR(50)"),
        ("audit_log", "ip", "VARCHAR(100)")
    ]

    with eng.connect() as conn:
        for table, col_name, col_sql in migrations:
            if not inspector.has_table(table):
                continue
            cols = [c["name"] for c in inspector.get_columns(table)]
            if col_name not in cols:
                try:
                    logger.info(f"[DB:Migration] Adding column {table}.{col_name}...")
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_sql}"))
                    conn.commit()
                except Exception as ex:
                    logger.warning(f"[DB:Migration] Note on adding {table}.{col_name}: {ex}")

def init_db():
    """Initializes database schema with retry and backoff for sleeping instances."""
    retries = 5
    delay = 3
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"[DB] Initializing database schema (attempt {attempt}/{retries})...")
            Base.metadata.create_all(bind=engine)
            _apply_idempotent_migrations(engine)
            logger.info("[DB] All database tables and columns successfully verified.")
            return
        except Exception as e:
            if attempt < retries:
                logger.warning(f"[DB] Database connection error during init_db ({e}). Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"[DB] Failed to initialize database after {retries} attempts: {e}")
                raise
