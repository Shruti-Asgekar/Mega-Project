"""
Module 4: Cross-Document Verification (RapidFuzz).
- Compares Name across all document pairs using token_sort_ratio after normalization
- Compares DOB across all document pairs (exact=green, swapped day/month=amber, otherwise=red)
- Compares Address across all document pairs using token_set_ratio
"""

import re
from itertools import combinations
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz
from backend.app.core.contracts import Flag, FlagCode, Severity
from backend.app.modules.m1_validators import parse_dob

HONORIFICS_REGEX = r"\b(mr|mrs|ms|shri|smt|dr|prof|kumar|kumari)\b"

def normalize_name(name: Optional[str]) -> str:
    """Normalizes name: lowercase, strip common honorifics, strip punctuation."""
    if not name:
        return ""
    cleaned = name.lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # Strip honorifics
    cleaned = re.sub(HONORIFICS_REGEX, " ", cleaned)
    # Collapse whitespace
    return " ".join(cleaned.split())

def normalize_address(address: Optional[str]) -> str:
    """Normalizes address: lowercase, strip punctuation, collapse whitespace."""
    if not address:
        return ""
    cleaned = address.lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())

def compare_dobs(dob1_str: str, dob2_str: str) -> tuple[Severity, str]:
    """
    Compares two DOB strings.
    Returns (Severity, reason).
    """
    d1 = parse_dob(dob1_str)
    d2 = parse_dob(dob2_str)
    if not d1 or not d2:
        return Severity.RED, "Unable to parse one or both dates of birth"

    if d1 == d2:
        return Severity.GREEN, "Date of birth matches exactly"

    # Check for swapped day and month
    if d1.year == d2.year and d1.day == d2.month and d1.month == d2.day:
        return Severity.AMBER, "Date of birth appears to have swapped day and month format"

    return Severity.RED, "Date of birth does not match across documents"

def verify_cross_documents(documents: List[Dict[str, Any]]) -> List[Flag]:
    """
    Compares every pair of documents that contain name, dob, or address.
    Each item in documents is expected to have:
      'id': str, 'doc_type': str, 'extracted_fields': dict (ExtractedFields)
    """
    flags: List[Flag] = []
    pairs = list(combinations(documents, 2))

    for doc_a, doc_b in pairs:
        type_a = doc_a.get("doc_type", "doc")
        type_b = doc_b.get("doc_type", "doc")
        fields_a = doc_a.get("extracted_fields", {})
        fields_b = doc_b.get("extracted_fields", {})

        pair_label = f"{type_a} vs {type_b}"

        # 1. Compare Names
        name_a = fields_a.get("name")
        name_b = fields_b.get("name")
        if name_a and name_b:
            norm_a = normalize_name(name_a)
            norm_b = normalize_name(name_b)
            score = float(fuzz.token_sort_ratio(norm_a, norm_b))
            rounded_score = round(score, 1)

            if norm_a == norm_b:
                flags.append(
                    Flag(
                        code=FlagCode.NAME_MATCH,
                        module=4,
                        severity=Severity.GREEN,
                        score_impact=0,
                        details={
                            "doc_a": type_a, "doc_b": type_b,
                            "name_a": name_a, "name_b": name_b,
                            "similarity": 100.0
                        }
                    )
                )
            else:
                # Differing names (e.g. Ramesh Kumar vs Rajesh Kumar)
                if score >= 90.0:
                    sev = Severity.AMBER
                    impact = 8
                elif score >= 75.0:
                    sev = Severity.AMBER
                    impact = 8
                else:
                    sev = Severity.RED
                    impact = 20

                flags.append(
                    Flag(
                        code=FlagCode.NAME_MISMATCH,
                        module=4,
                        severity=sev,
                        score_impact=impact,
                        details={
                            "doc_a": type_a, "doc_b": type_b,
                            "name_a": name_a, "name_b": name_b,
                            "similarity": rounded_score,
                            "message": f"Name differs across documents: '{name_a}' vs '{name_b}' ({int(rounded_score)}% match)."
                        }
                    )
                )

        # 2. Compare DOB
        dob_a = fields_a.get("dob")
        dob_b = fields_b.get("dob")
        if dob_a and dob_b:
            sev, reason = compare_dobs(str(dob_a), str(dob_b))
            if sev == Severity.GREEN:
                flags.append(
                    Flag(
                        code=FlagCode.DOB_MATCH,
                        module=4,
                        severity=Severity.GREEN,
                        score_impact=0,
                        details={"doc_a": type_a, "doc_b": type_b, "dob": dob_a}
                    )
                )
            else:
                impact = 8 if sev == Severity.AMBER else 20
                flags.append(
                    Flag(
                        code=FlagCode.DOB_MISMATCH,
                        module=4,
                        severity=sev,
                        score_impact=impact,
                        details={
                            "doc_a": type_a, "doc_b": type_b,
                            "dob_a": dob_a, "dob_b": dob_b,
                            "reason": reason
                        }
                    )
                )

        # 3. Compare Address
        addr_a = fields_a.get("address")
        addr_b = fields_b.get("address")
        if addr_a and addr_b:
            norm_addr_a = normalize_address(addr_a)
            norm_addr_b = normalize_address(addr_b)
            addr_score = float(fuzz.token_set_ratio(norm_addr_a, norm_addr_b))
            rounded_addr = round(addr_score, 1)

            if addr_score >= 90.0:
                flags.append(
                    Flag(
                        code=FlagCode.ADDRESS_MATCH,
                        module=4,
                        severity=Severity.GREEN,
                        score_impact=0,
                        details={"doc_a": type_a, "doc_b": type_b, "similarity": rounded_addr}
                    )
                )
            elif 75.0 <= addr_score < 90.0:
                flags.append(
                    Flag(
                        code=FlagCode.ADDRESS_MISMATCH,
                        module=4,
                        severity=Severity.AMBER,
                        score_impact=8,
                        details={
                            "doc_a": type_a, "doc_b": type_b,
                            "addr_a": addr_a, "addr_b": addr_b,
                            "similarity": rounded_addr
                        }
                    )
                )
            else:
                flags.append(
                    Flag(
                        code=FlagCode.ADDRESS_MISMATCH,
                        module=4,
                        severity=Severity.RED,
                        score_impact=20,
                        details={
                            "doc_a": type_a, "doc_b": type_b,
                            "addr_a": addr_a, "addr_b": addr_b,
                            "similarity": rounded_addr
                        }
                    )
                )

    return flags
