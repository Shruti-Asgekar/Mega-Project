"""
Application Configuration.
"""

import os
import base64
import hashlib
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(BASE_DIR / ".env")

APP_ENV = os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "development")).lower()
IS_PRODUCTION = (APP_ENV == "production") or bool(os.environ.get("RENDER"))

# Port binding
BACKEND_PORT = int(os.environ.get("PORT", os.environ.get("BACKEND_PORT", 8000)))

# ML Execution Mode: inprocess | http
_configured_ml_url = os.environ.get("ML_SERVICE_URL")
if os.environ.get("ML_MODE"):
    ML_MODE = os.environ.get("ML_MODE", "inprocess").lower()
elif _configured_ml_url and not IS_PRODUCTION:
    ML_MODE = "http"
else:
    ML_MODE = "inprocess"

ML_SERVICE_URL = _configured_ml_url or "http://localhost:8001"
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "shared_internal_secret_key_placeholder")

# Storage Backend: db | disk
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "db" if IS_PRODUCTION else "disk").lower()
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(BASE_DIR / "backend" / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Demo Mode & Auto-Seeding (Strictly false in production)
DEMO_MODE = False if IS_PRODUCTION else os.environ.get("DEMO_MODE", "false").lower() in ("true", "1", "yes")
SEED_ON_START = False if IS_PRODUCTION else os.environ.get("SEED_ON_START", "false").lower() in ("true", "1", "yes")
DEMO_ADMIN_KEY = os.environ.get("DEMO_ADMIN_KEY", "demo_admin_secret_key_123")

# Upload Limits: 3 MB on public demo, 10 MB otherwise
MAX_UPLOAD_SIZE_BYTES = 3 * 1024 * 1024 if DEMO_MODE else 10 * 1024 * 1024

# Secrets & Encryption Keys
SECRET_KEY = os.environ.get("SECRET_KEY", "kyc_platform_default_production_secret_key_secure_change_me")
IDENTIFIER_HMAC_KEY = os.environ.get("IDENTIFIER_HMAC_KEY", "kyc_identifier_hmac_secret_salt_key_123").encode("utf-8")

# Derive consistent 32-byte Fernet key from SECRET_KEY or FIELD_ENCRYPTION_KEY
_raw_enc_key = os.environ.get("FIELD_ENCRYPTION_KEY", os.environ.get("FERNET_KEY", SECRET_KEY))
if len(_raw_enc_key) == 44 and _raw_enc_key.endswith("="):
    FERNET_KEY = _raw_enc_key.encode("utf-8")
else:
    # Deterministic SHA-256 base64 urlsafe key
    key_hash = hashlib.sha256(_raw_enc_key.encode("utf-8")).digest()
    FERNET_KEY = base64.urlsafe_b64encode(key_hash)

# Authentication & Admin Bootstrap
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@kyc.local").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "System Administrator")

SESSION_EXPIRY_MINUTES = int(os.environ.get("SESSION_EXPIRY_MINUTES", "60"))
SESSION_COOKIE_NAME = "kyc_session"
CSRF_COOKIE_NAME = "csrf_token"

# DPDP & Retention Policy
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))

# Database URL Normalisation
_raw_db_url = os.environ.get("DATABASE_URL")
if _raw_db_url:
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif _raw_db_url.startswith("postgresql://") and not _raw_db_url.startswith("postgresql+"):
        _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    if "neon.tech" in _raw_db_url and "sslmode=" not in _raw_db_url:
        delimiter = "&" if "?" in _raw_db_url else "?"
        _raw_db_url = f"{_raw_db_url}{delimiter}sslmode=require"

    DATABASE_URL = _raw_db_url
else:
    DATABASE_URL = f"sqlite:///{BASE_DIR / 'dev.db'}"
