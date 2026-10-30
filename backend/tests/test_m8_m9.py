"""
Unit Tests for Module 8 (Explanation Engine) and Module 9 (Trust Score & Smart Routing).
"""

import pytest
from backend.app.core.contracts import Flag, FlagCode, Severity, RoutingDecision
from backend.app.modules.m8_explainer import render_flag_explanation, explain_flags, format_inr
from backend.app.modules.m9_trust_routing import calculate_trust_score_and_route

def test_every_flag_code_renders_without_leftover_tags():
    """Definition of Done: Every FlagCode has an explanation template that renders cleanly."""
    mock_details = {
        "pan": "ABCDE1234F",
        "ifsc": "SBIN0001234",
        "dob": "15/08/1990",
        "age": 36,
        "doc_type": "salary_slip",
        "blur_score": 45.2,
        "threshold": 100.0,
        "missing_doc_type": "bank_statement",
        "name_a": "Ramesh Kumar",
        "name_b": "Rajesh Kumar",
        "similarity": 86.0,
        "doc_a": "pan",
        "doc_b": "aadhaar",
        "dob_a": "15/08/1990",
        "dob_b": "16/08/1990",
        "slip_net": 70000.0,
        "avg_salary_credits": 50000.0,
        "deviation_pct": 40.0,
        "burden_pct": 55.0,
        "count": 2,
        "detected_keywords": ["photoshop"],
        "diff_seconds": 120,
        "gross": 75000.0,
        "deductions": 8000.0,
        "expected_net": 67000.0,
        "found_net": 72000.0,
        "cluster_size": 4
    }

    for code in FlagCode:
        # Determine appropriate severity for code
        sev = Severity.RED if any(w in code.value for w in ["INVALID", "FAIL", "BROKEN", "SUSPECTED", "MISMATCH", "ANOMALY", "BLURRY", "MISSING", "HIGH"]) else Severity.GREEN
        flag = Flag(code=code, module=1, severity=sev, score_impact=10, details=mock_details)
        rendered = render_flag_explanation(flag)

        # Assert no leftover Jinja braces and non-empty result
        assert "{{" not in rendered, f"Leftover {{ in template {code.value}: {rendered}"
        assert "}}" not in rendered, f"Leftover }} in template {code.value}: {rendered}"
        assert len(rendered.strip()) > 5, f"Rendered explanation too short for {code.value}"

def test_indian_rupee_formatting():
    assert format_inr(70000) == "₹70,000"
    assert format_inr(50000) == "₹50,000"
    assert format_inr(1500000) == "₹15,00,000"
    assert format_inr(500) == "₹500"

def test_clean_case_auto_clear():
    # Only green flags
    flags = [
        Flag(code=FlagCode.PAN_FORMAT_VALID, module=1, severity=Severity.GREEN, score_impact=0),
        Flag(code=FlagCode.AADHAAR_VALID, module=1, severity=Severity.GREEN, score_impact=0),
        Flag(code=FlagCode.DOC_QUALITY_OK, module=2, severity=Severity.GREEN, score_impact=0),
        Flag(code=FlagCode.INCOME_VERIFIED, module=5, severity=Severity.GREEN, score_impact=0),
        Flag(code=FlagCode.SLIP_ARITHMETIC_OK, module=6, severity=Severity.GREEN, score_impact=0),
        Flag(code=FlagCode.INTEGRITY_VERIFIED, module=10, severity=Severity.GREEN, score_impact=0),
    ]
    score, route, breakdown, summary = calculate_trust_score_and_route(flags)
    assert score == 100
    assert route == RoutingDecision.AUTO_CLEAR
    assert len(breakdown) == 0

def test_hard_flag_triggers_escalate():
    # Photoshop metadata detected
    flags = [
        Flag(code=FlagCode.META_EDITING_SOFTWARE, module=6, severity=Severity.RED, score_impact=35, details={"detected_keywords": ["photoshop"]}),
    ]
    score, route, breakdown, summary = calculate_trust_score_and_route(flags)
    assert route == RoutingDecision.ESCALATE

def test_routing_boundaries():
    # Border case 1: 1 amber flag with -8 points -> score = 92 (AUTO_CLEAR)
    amber_flag = Flag(code=FlagCode.NAME_MISMATCH, module=4, severity=Severity.AMBER, score_impact=8)
    score1, route1, _, _ = calculate_trust_score_and_route([amber_flag])
    assert score1 == 92
    assert route1 == RoutingDecision.AUTO_CLEAR

    # Border case 2: score 80 with 1 red flag (-20) -> OFFICER_REVIEW (cannot auto-clear with red flag)
    red_flag = Flag(code=FlagCode.NAME_MISMATCH, module=4, severity=Severity.RED, score_impact=20)
    score2, route2, _, _ = calculate_trust_score_and_route([red_flag])
    assert score2 == 80
    assert route2 == RoutingDecision.OFFICER_REVIEW

    # Border case 3: score below 50 -> ESCALATE
    multiple_flags = [
        Flag(code=FlagCode.PAN_FORMAT_INVALID, module=1, severity=Severity.RED, score_impact=25),
        Flag(code=FlagCode.AADHAAR_CHECKSUM_FAIL, module=1, severity=Severity.RED, score_impact=25),
        Flag(code=FlagCode.DOC_MISSING, module=2, severity=Severity.RED, score_impact=10),
    ]
    score3, route3, _, _ = calculate_trust_score_and_route(multiple_flags)
    assert score3 == 40
    assert route3 == RoutingDecision.ESCALATE
