"""
Security, Encryption, Masking, and Sanitization.
DPDP-compliant privacy safeguards:
- HMAC-SHA256 keyed hashing for fraud ring matching (without storing plaintext identifiers)
- Fernet encryption for data at rest (fields and document blobs)
- Argon2id password hashing with bcrypt fallback
- Log-scrubbing filter masking Aadhaar and PAN in logs
"""

import re
import hmac
import hashlib
import logging
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from backend.app.core.config import FERNET_KEY, IDENTIFIER_HMAC_KEY

try:
    _cipher = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)
except Exception:
    _fallback_key = Fernet.generate_key()
    _cipher = Fernet(_fallback_key)

# --------------------------------------------------------------------------
# Password Hashing (Argon2id with bcrypt fallback)
# --------------------------------------------------------------------------

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=1)
    _USE_ARGON2 = True
except Exception:
    import bcrypt
    _USE_ARGON2 = False

COMMON_PASSWORDS = {
    "password", "password123", "password1234", "1234567890", "123456789",
    "admin12345", "welcome123", "qwerty1234", "letmein123", "iloveyou12"
}

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Validates that a password is >= 10 characters and not a common dictionary variant."""
    if not password or len(password) < 10:
        return False, "Password must be at least 10 characters long."
    
    clean_lower = password.lower().strip()
    base_pwd = re.sub(r"[!@#$%^&*()_+\-=\[\]{};':\",.<>?0-9]", "", clean_lower)
    if clean_lower in COMMON_PASSWORDS or base_pwd in COMMON_PASSWORDS or any(c in clean_lower for c in ["password123", "admin1234", "qwerty1234"]):
        return False, "Password is too common and easily guessed. Please choose a stronger passphrase."
    return True, ""

def hash_password(password: str) -> str:
    """Hashes password using argon2id (or bcrypt)."""
    if _USE_ARGON2:
        return _ph.hash(password)
    else:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    """Verifies a plaintext password against the stored hash."""
    if not password or not hashed:
        return False
    try:
        if hashed.startswith("$argon2"):
            if _USE_ARGON2:
                return _ph.verify(hashed, password)
            return False
        # bcrypt fallback
        import bcrypt
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# --------------------------------------------------------------------------
# HMAC Keyed Hashing for Identity Linkage (Zero Plaintext Persistence)
# --------------------------------------------------------------------------

def compute_identifier_hmac(val: Optional[str]) -> Optional[str]:
    """
    Computes an HMAC-SHA256 keyed hash for an identifier.
    Allows exact duplicate and syndicate cluster matching across applications
    without ever storing the raw unmasked Aadhaar, phone, or bank account number.
    """
    if not val:
        return None
    cleaned = re.sub(r"[\s\-\.]", "", str(val)).strip().lower()
    if not cleaned:
        return None
    return hmac.new(IDENTIFIER_HMAC_KEY, cleaned.encode("utf-8"), hashlib.sha256).hexdigest()

# --------------------------------------------------------------------------
# Encryption at Rest (Fields & Blobs)
# --------------------------------------------------------------------------

def encrypt_value(value: Optional[str]) -> Optional[str]:
    """Encrypts plaintext string into base64 token using Fernet."""
    if value is None:
        return None
    return _cipher.encrypt(value.encode("utf-8")).decode("utf-8")

def decrypt_value(token: Optional[str]) -> Optional[str]:
    """Decrypts base64 token back to plaintext string."""
    if token is None:
        return None
    try:
        return _cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return token

def encrypt_bytes(data: bytes) -> bytes:
    """Encrypts raw byte payload (documents at rest in database)."""
    if not data:
        return data
    return _cipher.encrypt(data)

def decrypt_bytes(encrypted_data: bytes) -> bytes:
    """Decrypts encrypted byte payload."""
    if not encrypted_data:
        return encrypted_data
    try:
        return _cipher.decrypt(encrypted_data)
    except Exception:
        return encrypted_data

# --------------------------------------------------------------------------
# Masking & Scrubbing
# --------------------------------------------------------------------------

def mask_aadhaar(aadhaar: Optional[str]) -> str:
    """Masks 12-digit Aadhaar to format XXXX-XXXX-1234."""
    if not aadhaar:
        return "XXXX-XXXX-XXXX"
    cleaned = re.sub(r"\D", "", str(aadhaar))
    if len(cleaned) < 4:
        return "XXXX-XXXX-XXXX"
    last4 = cleaned[-4:]
    return f"XXXX-XXXX-{last4}"

def mask_pan(pan: Optional[str]) -> str:
    """Masks PAN, displaying only the last 5 characters."""
    if not pan:
        return "XXXXX0000X"
    cleaned = str(pan).strip().upper()
    if len(cleaned) <= 5:
        return "X" * len(cleaned)
    last5 = cleaned[-5:]
    masked_prefix = "X" * (len(cleaned) - 5)
    return f"{masked_prefix}{last5}"

def mask_account(account: Optional[str]) -> str:
    """Masks bank account number, displaying only the last 4 digits."""
    if not account:
        return "XXXX0000"
    cleaned = str(account).strip()
    if len(cleaned) <= 4:
        return "X" * len(cleaned)
    last4 = cleaned[-4:]
    return f"{'X' * (len(cleaned) - 4)}{last4}"

def mask_phone(phone: Optional[str]) -> str:
    """Masks phone number, displaying only the last 3 digits."""
    if not phone:
        return "XXXXXXX000"
    cleaned = re.sub(r"\D", "", str(phone))
    if len(cleaned) <= 3:
        return "X" * len(cleaned)
    last3 = cleaned[-3:]
    return f"{'X' * (len(cleaned) - 3)}{last3}"

def mask_extracted_fields(fields: dict) -> dict:
    """Returns a copy of fields dict with sensitive values masked."""
    masked = dict(fields)
    if "aadhaar_number" in masked and masked["aadhaar_number"]:
        masked["aadhaar_number"] = mask_aadhaar(masked["aadhaar_number"])
    if "pan_number" in masked and masked["pan_number"]:
        masked["pan_number"] = mask_pan(masked["pan_number"])
    if "account_number" in masked and masked["account_number"]:
        masked["account_number"] = mask_account(masked["account_number"])
    if "phone" in masked and masked["phone"]:
        masked["phone"] = mask_phone(masked["phone"])
    return masked

def contains_unmasked_aadhaar(text: str) -> bool:
    """Scans text for unmasked 12-digit Aadhaar patterns."""
    if not text:
        return False
    matches = re.finditer(r'(?<![a-fA-F0-9\-])\b([2-9]\d{3}[-\s]?\d{4}[-\s]?\d{4})\b(?![a-fA-F0-9\-])', text)
    for m in matches:
        candidate = re.sub(r'[-\s]', '', m.group(1))
        if len(candidate) == 12:
            return True
    return False

# --------------------------------------------------------------------------
# Log Scrubbing Filter
# --------------------------------------------------------------------------

PAN_PATTERN = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', re.IGNORECASE)
AADHAAR_PATTERN = re.compile(r'(?<!\d)\b(\d{4}[-\s]?\d{4}[-\s]?\d{4})\b(?!\d)')

def scrub_pii(text: str) -> str:
    """Replaces unmasked Aadhaar and PAN strings with masked representations."""
    if not text or not isinstance(text, str):
        return text
    # Mask Aadhaar
    def _mask_a(match):
        digits = re.sub(r'\D', '', match.group(0))
        if len(digits) == 12:
            return f"XXXX-XXXX-{digits[-4:]}"
        return match.group(0)

    text = AADHAAR_PATTERN.sub(_mask_a, text)
    # Mask PAN
    def _mask_p(match):
        return mask_pan(match.group(0))

    text = PAN_PATTERN.sub(_mask_p, text)
    return text

class LogScrubbingFilter(logging.Filter):
    """Logging filter that redacts 12-digit Aadhaar and PAN patterns from log messages."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_pii(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: scrub_pii(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(scrub_pii(v) if isinstance(v, str) else v for v in record.args)
        return True
