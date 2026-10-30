"""
Database Engine & Session Management with automatic SQLite fallback.
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.core.config import DATABASE_URL

logger = logging.getLogger("kyc.db")

def get_engine():
    db_url = DATABASE_URL
    if db_url.startswith("postgresql"):
        try:
            test_engine = create_engine(db_url, connect_args={"connect_timeout": 2}, pool_pre_ping=True)
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info(f"[DB] Connected successfully to PostgreSQL at {db_url.split('@')[-1]}")
            return test_engine
        except Exception as e:
            logger.warning(f"[DB] PostgreSQL unreachable ({e}). Falling back to SQLite at ./kyc.db")
            db_url = "sqlite:///./kyc.db"

    # SQLite
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
        pool_pre_ping=True
    )
    logger.info(f"[DB] Active database engine: {db_url}")
    return engine

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
