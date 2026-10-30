"""
Unit Tests for Module 2 (Quality and Completeness).
"""

import pytest
from backend.app.core.contracts import FlagCode, Severity
from backend.app.modules.m2_quality import evaluate_quality_and_completeness, format_m2_demo_summary

def test_blurry_and_missing_demo_scenario():
    # Documents: salary slip is blurry (score 42.0), aadhaar and pan are sharp, bank_statement is missing!
    documents = [
        {"id": "doc-1", "doc_type": "aadhaar"},
        {"id": "doc-2", "doc_type": "pan"},
        {"id": "doc-3", "doc_type": "salary_slip"},
    ]
    blur_results = {
        "doc-1": {"blur_score": 150.0, "is_blurry": False},
        "doc-2": {"blur_score": 210.0, "is_blurry": False},
        "doc-3": {"blur_score": 45.0, "is_blurry": True},
    }

    flags = evaluate_quality_and_completeness(documents, blur_results)

    # Check blurry flag
    blurry_flags = [f for f in flags if f.code == FlagCode.DOC_BLURRY]
    assert len(blurry_flags) == 1
    assert blurry_flags[0].severity == Severity.RED
    assert blurry_flags[0].details["doc_type"] == "salary_slip"

    # Check missing flag
    missing_flags = [f for f in flags if f.code == FlagCode.DOC_MISSING]
    assert len(missing_flags) == 1
    assert missing_flags[0].details["missing_doc_type"] == "bank_statement"

    # Exact demo output requirement
    summary = format_m2_demo_summary(flags)
    assert summary == "Your salary slip is blurry. Bank statement missing."

def test_all_documents_clean():
    documents = [
        {"id": "doc-1", "doc_type": "aadhaar"},
        {"id": "doc-2", "doc_type": "pan"},
        {"id": "doc-3", "doc_type": "salary_slip"},
        {"id": "doc-4", "doc_type": "bank_statement"},
    ]
    blur_results = {
        "doc-1": {"blur_score": 120.0, "is_blurry": False},
        "doc-2": {"blur_score": 140.0, "is_blurry": False},
        "doc-3": {"blur_score": 110.0, "is_blurry": False},
        "doc-4": {"blur_score": 999.0, "is_blurry": False},
    }
    flags = evaluate_quality_and_completeness(documents, blur_results)
    assert not any(f.code in (FlagCode.DOC_BLURRY, FlagCode.DOC_MISSING) for f in flags)
    assert len([f for f in flags if f.code == FlagCode.DOC_QUALITY_OK]) == 4
