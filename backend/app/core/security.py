"""
Security, Encryption, Masking, and Sanitization.
"""

import re
from typing import Optional
from cryptography.fernet import Fernet
from backend.app.core.config import FERNET_KEY

try:
    _cipher = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)
except Exception:
    # Generate fallback key if configured key is invalid length/format
    _fallback_key = Fernet.generate_key()
    _cipher = Fernet(_fallback_key)

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

def mask_aadhaar(aadhaar: Optional[str]) -> str:
    """Masks 12-digit Aadhaar to format XXXX-XXXX-1234."""
    if not aadhaar:
        return "XXXX-XXXX-XXXX"
    cleaned = re.sub(r"\D", "", aadhaar)
    if len(cleaned) < 4:
        return "XXXX-XXXX-XXXX"
    last4 = cleaned[-4:]
    return f"XXXX-XXXX-{last4}"

def mask_pan(pan: Optional[str]) -> str:
    """Masks PAN, displaying only the last 5 characters."""
    if not pan:
        return "XXXXX0000X"
    cleaned = pan.strip().upper()
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
    cleaned = re.sub(r"\D", "", phone)
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
    """
    Scans text for unmasked 12-digit Aadhaar patterns.
    Matches 12 consecutive digits or 4-4-4 separated digits where first digit is 2-9.
    Excludes hex UUID segments or strings attached to hyphens/hex characters.
    """
    if not text:
        return False
    matches = re.finditer(r'(?<![a-fA-F0-9\-])\b([2-9]\d{3}[-\s]?\d{4}[-\s]?\d{4})\b(?![a-fA-F0-9\-])', text)
    for m in matches:
        candidate = re.sub(r'[-\s]', '', m.group(1))
        if len(candidate) == 12:
            return True
    return False
