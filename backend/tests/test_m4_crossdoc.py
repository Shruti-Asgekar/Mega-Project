"""
Unit Tests for Module 4 (Cross-Document Verification).
"""

import pytest
from backend.app.core.contracts import FlagCode, Severity
from backend.app.modules.m4_crossdoc import verify_cross_documents, normalize_name

def test_ramesh_vs_rajesh_name_mismatch():
    documents = [
        {
            "id": "doc-pan",
            "doc_type": "pan",
            "extracted_fields": {"name": "Ramesh Kumar", "dob": "15/08/1990"}
        },
        {
            "id": "doc-slip",
            "doc_type": "salary_slip",
            "extracted_fields": {"name": "Rajesh Kumar", "dob": "15/08/1990"}
        }
    ]

    flags = verify_cross_documents(documents)

    name_flags = [f for f in flags if f.code == FlagCode.NAME_MISMATCH]
    assert len(name_flags) == 1
    flag = name_flags[0]

    # Verify real computed score is recorded and asserted
    similarity = flag.details["similarity"]
    assert 75.0 <= similarity <= 95.0
    assert "Rajesh Kumar" in flag.details["name_b"]
    assert "Ramesh Kumar" in flag.details["name_a"]
    # Severity should be amber given high similarity but distinct identity
    assert flag.severity in (Severity.AMBER, Severity.RED)
    assert f"{int(similarity)}% match" in flag.details["message"]

def test_dob_swapped_day_month():
    documents = [
        {
            "id": "doc-aadhaar",
            "doc_type": "aadhaar",
            "extracted_fields": {"dob": "05/12/1990"}
        },
        {
            "id": "doc-pan",
            "doc_type": "pan",
            "extracted_fields": {"dob": "12/05/1990"}
        }
    ]

    flags = verify_cross_documents(documents)
    dob_flags = [f for f in flags if f.code == FlagCode.DOB_MISMATCH]
    assert len(dob_flags) == 1
    # Swapped day/month is amber
    assert dob_flags[0].severity == Severity.AMBER
    assert "swapped" in dob_flags[0].details["reason"].lower()

def test_address_fuzzy_matching():
    documents = [
        {
            "id": "doc-aadhaar",
            "doc_type": "aadhaar",
            "extracted_fields": {
                "address": "Flat 402, Sunshine Heights, MG Road, Pune 411001"
            }
        },
        {
            "id": "doc-bank",
            "doc_type": "bank_statement",
            "extracted_fields": {
                "address": "402 Sunshine Heights M.G. Road Pune - 411001"
            }
        }
    ]

    flags = verify_cross_documents(documents)
    addr_flags = [f for f in flags if f.code == FlagCode.ADDRESS_MATCH]
    assert len(addr_flags) == 1
    assert addr_flags[0].severity == Severity.GREEN
