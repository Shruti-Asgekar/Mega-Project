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

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
IS_PRODUCTION = (ENVIRONMENT == "production") or bool(os.environ.get("RENDER"))

# Port binding
BACKEND_PORT = int(os.environ.get("PORT", os.environ.get("BACKEND_PORT", 8000)))

# ML Execution Mode: inprocess | http
# Default to inprocess in production or when ML_SERVICE_URL is unset
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
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "db" if (IS_PRODUCTION or os.environ.get("DEMO_MODE") == "true") else "disk").lower()
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(BASE_DIR / "backend" / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Demo Mode & Auto-Seeding
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() in ("true", "1", "yes")
SEED_ON_START = os.environ.get("SEED_ON_START", "false").lower() in ("true", "1", "yes")
DEMO_ADMIN_KEY = os.environ.get("DEMO_ADMIN_KEY", "demo_admin_secret_key_123")

# Upload Limits: 3 MB on public demo, 10 MB otherwise
MAX_UPLOAD_SIZE_BYTES = 3 * 1024 * 1024 if DEMO_MODE else 10 * 1024 * 1024

# Security & Fernet Key Derivation
SECRET_KEY = os.environ.get("SECRET_KEY", "default_secret_key_for_development")
_configured_fernet_key = os.environ.get("FERNET_KEY")
if _configured_fernet_key and len(_configured_fernet_key.strip()) == 44:
    FERNET_KEY = _configured_fernet_key.strip()
else:
    # Deterministically derive 32-byte urlsafe base64 key from SECRET_KEY
    _digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    FERNET_KEY = base64.urlsafe_b64encode(_digest).decode("utf-8")

# Database URL normalisation for PostgreSQL / Neon
_raw_db_url = os.environ.get("DATABASE_URL", "").strip()
if _raw_db_url:
    if _raw_db_url.startswith("postgres://"):
        DATABASE_URL = "postgresql+psycopg2://" + _raw_db_url[len("postgres://"):]
    elif _raw_db_url.startswith("postgresql://") and not _raw_db_url.startswith("postgresql+psycopg2://"):
        DATABASE_URL = "postgresql+psycopg2://" + _raw_db_url[len("postgresql://"):]
    else:
        DATABASE_URL = _raw_db_url

    # Ensure sslmode=require for Neon / remote Postgres if not present and not SQLite
    if DATABASE_URL.startswith("postgresql") and "sslmode=" not in DATABASE_URL:
        sep = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL = f"{DATABASE_URL}{sep}sslmode=require"
else:
    DATABASE_URL = "sqlite:///./kyc.db"

BLUR_THRESHOLD = float(os.environ.get("BLUR_THRESHOLD", 100.0))
RAPIDFUZZ_THRESHOLD = float(os.environ.get("RAPIDFUZZ_THRESHOLD", 85.0))
ADDRESS_CLUSTER_THRESHOLD = float(os.environ.get("ADDRESS_CLUSTER_THRESHOLD", 92.0))
