"""
Module 9: Trust Score and Smart Routing (Backend).
- Calculates 0-100 Trust Score with documented transparent deductions
- Evaluates policy routing: AUTO_CLEAR, OFFICER_REVIEW, ESCALATE
- Generates score breakdown for UI gauge and breakdown table
"""

from typing import List, Dict, Any, Tuple
from backend.app.core.contracts import Flag, FlagCode, Severity, RoutingDecision

# Centralized, fully documented deduction weights
SCORE_DEDUCTIONS = {
    # Hard fraud and tampering flags
    FlagCode.META_EDITING_SOFTWARE: 35,
    FlagCode.SLIP_ARITHMETIC_MISMATCH: 30,
    FlagCode.FRAUD_RING_SUSPECTED: 35,
    FlagCode.INTEGRITY_BROKEN: 50,

    # Identity verification failures (Module 1)
    FlagCode.PAN_FORMAT_INVALID: 25,
    FlagCode.AADHAAR_INVALID_FORMAT: 25,
    FlagCode.AADHAAR_CHECKSUM_FAIL: 25,
    FlagCode.IFSC_INVALID: 15,
    FlagCode.DOB_INVALID: 20,
    FlagCode.DOB_AGE_OUT_OF_RANGE: 10,

    # Document quality & completeness (Module 2)
    FlagCode.DOC_MISSING: 10,

    # Cross-document mismatches (Module 4)
    # Applied dynamically based on severity: Red=20, Amber=8

    # Income & bank analysis (Module 5)
    # Income mismatch: Red=20, Amber=8
    # EMI burden: Red=20, Amber=8
    # Bounced payments: 6 per bounce, capped at 18

    # Forgery & Syndicate (Module 6 & 7)
    FlagCode.META_MODIFIED_AFTER_CREATED: 8,
    FlagCode.META_MISSING: 5,
    FlagCode.ELA_ANOMALY: 8,
    FlagCode.SHARED_IDENTIFIER: 8,

    # General
    FlagCode.DOC_UNREADABLE: 25,
}

HARD_ESCALATE_FLAGS = {
    FlagCode.META_EDITING_SOFTWARE,
    FlagCode.FRAUD_RING_SUSPECTED,
    FlagCode.INTEGRITY_BROKEN,
    FlagCode.SLIP_ARITHMETIC_MISMATCH
}

def calculate_trust_score_and_route(flags: List[Flag]) -> Tuple[int, RoutingDecision, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Computes trust score clamped between 0 and 100, and assigns routing verdict.
    Returns:
      trust_score: int (0-100)
      route: RoutingDecision (AUTO_CLEAR, OFFICER_REVIEW, ESCALATE)
      breakdown: list of deduction entries
      summary: summary statistics dictionary
    """
    score = 100
    breakdown = []
    has_red_flags = False
    has_hard_escalate = False

    for f in flags:
        if f.severity == Severity.GREEN:
            continue

        if f.severity == Severity.RED:
            has_red_flags = True
        if f.code in HARD_ESCALATE_FLAGS:
            has_hard_escalate = True

        deduction = 0
        # Determine deduction
        if f.code in SCORE_DEDUCTIONS:
            deduction = SCORE_DEDUCTIONS[f.code]
        else:
            # Dynamic severity fallback
            if f.severity == Severity.RED:
                deduction = f.score_impact or 20
            elif f.severity == Severity.AMBER:
                deduction = f.score_impact or 8

        # Special handling for blur and bounced payments based on severity
        if f.code == FlagCode.DOC_BLURRY:
            deduction = 12 if f.severity == Severity.RED else 5
        elif f.code == FlagCode.BOUNCED_PAYMENTS:
            count = f.details.get("count", 1)
            deduction = min(count * 6, 18)

        score -= deduction
        breakdown.append({
            "code": f.code.value,
            "module": f.module,
            "severity": f.severity.value,
            "deduction": deduction,
            "reason": f.explanation or f.details.get("message", f.code.value)
        })

    # Clamp score to 0..100
    clamped_score = max(0, min(100, score))

    # Smart Routing Rules
    # <50 or hard flag -> ESCALATE
    # >=80 and no red flags -> AUTO_CLEAR
    # 50-79 or any red from modules 1-5 -> OFFICER_REVIEW
    if clamped_score < 50 or has_hard_escalate:
        route = RoutingDecision.ESCALATE
    elif clamped_score >= 80 and not has_red_flags:
        route = RoutingDecision.AUTO_CLEAR
    else:
        route = RoutingDecision.OFFICER_REVIEW

    summary = {
        "initial_score": 100,
        "total_deductions": 100 - clamped_score,
        "final_score": clamped_score,
        "route": route.value,
        "has_red_flags": has_red_flags,
        "has_hard_escalate": has_hard_escalate,
        "total_penalties_applied": len(breakdown)
    }

    return clamped_score, route, breakdown, summary
