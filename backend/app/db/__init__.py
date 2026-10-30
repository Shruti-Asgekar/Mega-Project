"""
Database initialization helpers.
"""

from backend.app.db.database import Base, engine, SessionLocal, get_db
from backend.app.db.models import Applicant, Case, Document, FlagModel, Consent, ChainRecord, AuditLog

def init_db():
    Base.metadata.create_all(bind=engine)
