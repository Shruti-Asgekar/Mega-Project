"""
Module 1: Field Validators.
- PAN format and 4th character status validator
- Aadhaar format and Verhoeff checksum validator + generator
- IFSC code regex validator
- DOB parse, calendar validity, and 18-100 age range validator
"""

import re
from datetime import datetime, date
from typing import Optional, List, Tuple
from backend.app.core.contracts import Flag, FlagCode, Severity
from backend.app.core.security import mask_aadhaar

# Verhoeff tables
VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

VERHOEFF_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)

PAN_ALLOWED_4TH_CHARS = set("PCHFATBLJG")

def compute_verhoeff_checksum(num_str: str) -> int:
    """Computes the Verhoeff check digit for a given digit string."""
    c = 0
    for i, digit in enumerate(reversed(num_str), start=1):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][int(digit)]]
    return VERHOEFF_INV[c]

def validate_verhoeff(num_str: str) -> bool:
    """Validates a number string using the full Verhoeff algorithm."""
    c = 0
    for i, digit in enumerate(reversed(num_str), start=0):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][int(digit)]]
    return c == 0

def generate_valid_aadhaar(prefix11: str) -> str:
    """
    Generates a 12-digit valid Aadhaar number from an 11-digit prefix.
    Prefix must be 11 digits and not start with 0 or 1.
    """
    cleaned = re.sub(r"\D", "", str(prefix11))
    if len(cleaned) != 11:
        raise ValueError(f"Prefix must be exactly 11 digits, got {len(cleaned)}")
    if cleaned[0] in ("0", "1"):
        raise ValueError("Aadhaar first digit cannot be 0 or 1")
    chk = compute_verhoeff_checksum(cleaned)
    return f"{cleaned}{chk}"

def validate_pan(pan: Optional[str], document_id: Optional[str] = None) -> List[Flag]:
    """
    Validates PAN format: ^[A-Z]{5}[0-9]{4}[A-Z]$, 4th char in P,C,H,F,A,T,B,L,J,G.
    """
    if not pan:
        return []
    cleaned = pan.strip().upper()
    pan_regex = r"^[A-Z]{5}[0-9]{4}[A-Z]$"
    if not re.match(pan_regex, cleaned) or cleaned[3] not in PAN_ALLOWED_4TH_CHARS:
        return [
            Flag(
                code=FlagCode.PAN_FORMAT_INVALID,
                module=1,
                severity=Severity.RED,
                score_impact=25,
                details={"pan": cleaned, "reason": "Invalid structure or 4th character not recognized"},
                document_id=document_id
            )
        ]
    return [
        Flag(
            code=FlagCode.PAN_FORMAT_VALID,
            module=1,
            severity=Severity.GREEN,
            score_impact=0,
            details={"pan": cleaned},
            document_id=document_id
        )
    ]

def validate_aadhaar(aadhaar: Optional[str], document_id: Optional[str] = None) -> List[Flag]:
    """
    Validates Aadhaar format (12 digits, first not 0/1) and Verhoeff checksum.
    """
    if not aadhaar:
        return []
    cleaned = re.sub(r"[\s-]", "", aadhaar.strip())
    if not re.match(r"^[0-9]{12}$", cleaned) or cleaned[0] in ("0", "1"):
        return [
            Flag(
                code=FlagCode.AADHAAR_INVALID_FORMAT,
                module=1,
                severity=Severity.RED,
                score_impact=25,
                details={"aadhaar": mask_aadhaar(cleaned), "reason": "Must be 12 digits and cannot start with 0 or 1"},
                document_id=document_id
            )
        ]
    if not validate_verhoeff(cleaned):
        return [
            Flag(
                code=FlagCode.AADHAAR_CHECKSUM_FAIL,
                module=1,
                severity=Severity.RED,
                score_impact=25,
                details={"aadhaar": mask_aadhaar(cleaned), "reason": "Verhoeff checksum verification failed"},
                document_id=document_id
            )
        ]
    return [
        Flag(
            code=FlagCode.AADHAAR_VALID,
            module=1,
            severity=Severity.GREEN,
            score_impact=0,
            details={"aadhaar": mask_aadhaar(cleaned)},
            document_id=document_id
        )
    ]

def validate_ifsc(ifsc: Optional[str], document_id: Optional[str] = None) -> List[Flag]:
    """
    Validates Indian Financial System Code: ^[A-Z]{4}0[A-Z0-9]{6}$
    """
    if not ifsc:
        return []
    cleaned = ifsc.strip().upper()
    if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", cleaned):
        return [
            Flag(
                code=FlagCode.IFSC_INVALID,
                module=1,
                severity=Severity.RED,
                score_impact=15,
                details={"ifsc": cleaned, "reason": "Invalid IFSC structure"},
                document_id=document_id
            )
        ]
    return [
        Flag(
            code=FlagCode.IFSC_VALID,
            module=1,
            severity=Severity.GREEN,
            score_impact=0,
            details={"ifsc": cleaned},
            document_id=document_id
        )
    ]

def parse_dob(dob_str: str) -> Optional[date]:
    """Tries parsing DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD."""
    cleaned = dob_str.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None

def validate_dob(dob_str: Optional[str], document_id: Optional[str] = None, ref_date: Optional[date] = None) -> List[Flag]:
    """
    Validates DOB format, ensures it is not future date, and age is 18-100.
    """
    if not dob_str:
        return []
    parsed_date = parse_dob(dob_str)
    if parsed_date is None:
        return [
            Flag(
                code=FlagCode.DOB_INVALID,
                module=1,
                severity=Severity.RED,
                score_impact=20,
                details={"dob": dob_str, "reason": "Unrecognized date format or invalid calendar date"},
                document_id=document_id
            )
        ]
    today = ref_date or date.today()
    if parsed_date > today:
        return [
            Flag(
                code=FlagCode.DOB_INVALID,
                module=1,
                severity=Severity.RED,
                score_impact=20,
                details={"dob": dob_str, "reason": "Date of birth cannot be in the future"},
                document_id=document_id
            )
        ]
    # Age calculation
    age = today.year - parsed_date.year - ((today.month, today.day) < (parsed_date.month, parsed_date.day))
    if age < 18 or age > 100:
        return [
            Flag(
                code=FlagCode.DOB_AGE_OUT_OF_RANGE,
                module=1,
                severity=Severity.AMBER,
                score_impact=10,
                details={"dob": dob_str, "age": age, "reason": f"Age {age} is outside eligible range (18-100)"},
                document_id=document_id
            )
        ]
    return [
        Flag(
            code=FlagCode.DOB_VALID,
            module=1,
            severity=Severity.GREEN,
            score_impact=0,
            details={"dob": dob_str, "age": age},
            document_id=document_id
        )
    ]
