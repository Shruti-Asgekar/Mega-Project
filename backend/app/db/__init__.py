"""
Database initialization helpers with connection retry.
"""

import time
import logging
from backend.app.db.database import Base, engine, SessionLocal, get_db
from backend.app.db.models import (
    Applicant, Case, Document, FlagModel, Consent, ChainRecord, AuditLog,
    DocumentBlob, DemoTamperLog
)

logger = logging.getLogger("kyc.db")

def init_db():
    """Initializes database schema with retry and backoff for sleeping instances."""
    retries = 5
    delay = 3
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"[DB] Initializing database schema (attempt {attempt}/{retries})...")
            Base.metadata.create_all(bind=engine)
            logger.info("[DB] All database tables successfully created and verified.")
            return
        except Exception as e:
            if attempt < retries:
                logger.warning(f"[DB] Database connection error during init_db ({e}). Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"[DB] Failed to initialize database after {retries} attempts: {e}")
                raise
