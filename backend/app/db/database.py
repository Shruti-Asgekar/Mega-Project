"""
Database Engine & Session Management with Neon PostgreSQL support and SQLite fallback.
"""

import time
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.core.config import DATABASE_URL

logger = logging.getLogger("kyc.db")

def get_engine():
    db_url = DATABASE_URL
    is_postgres = db_url.startswith("postgresql")

    if is_postgres:
        logger.info(f"[DB] Initializing PostgreSQL engine (pool_size=3, recycle=300)...")
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=3,
            max_overflow=2,
            connect_args={"connect_timeout": 10}
        )
        return engine

    # SQLite for local dev
    logger.info(f"[DB] Initializing SQLite database at {db_url}")
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
        pool_pre_ping=True
    )
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
