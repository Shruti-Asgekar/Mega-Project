"""
Application Configuration.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./kyc.db")
BACKEND_PORT = int(os.environ.get("PORT", os.environ.get("BACKEND_PORT", 8000)))
ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://localhost:8001")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "shared_internal_secret_key_placeholder")
FERNET_KEY = os.environ.get("FERNET_KEY", "2zRv1_7Sh-fh-CbZcwppFjDks-71PHk_-HZeclMCcyo=")
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(BASE_DIR / "uploads")))
BLUR_THRESHOLD = float(os.environ.get("BLUR_THRESHOLD", 100.0))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
