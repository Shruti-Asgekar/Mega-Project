"""
Module 2: Quality and Completeness Rules (Backend).
- Evaluates document blur scores
- Identifies missing required documents from [aadhaar, pan, salary_slip, bank_statement]
- Generates composite summary: "Your salary slip is blurry. Bank statement missing."
"""

from typing import List, Dict, Any, Optional
from backend.app.core.contracts import Flag, FlagCode, Severity

REQUIRED_DOCS = ["aadhaar", "pan", "salary_slip", "bank_statement"]

DOC_DISPLAY_NAMES = {
    "aadhaar": "Aadhaar card",
    "pan": "PAN card",
    "salary_slip": "salary slip",
    "bank_statement": "bank statement"
}

def evaluate_quality_and_completeness(
    documents: List[Dict[str, Any]],
    blur_results: Dict[str, Dict[str, Any]]
) -> List[Flag]:
    """
    Evaluates blur scores and completeness for case documents.
    documents: list of dicts with keys {"id": str, "doc_type": str, "file_path": str}
    blur_results: dict mapping document_id to blur result dict {"blur_score": float, "is_blurry": bool}
    """
    flags: List[Flag] = []
    present_types = set()

    for doc in documents:
        doc_id = doc.get("id")
        doc_type = doc.get("doc_type", "").lower()
        present_types.add(doc_type)

        res = blur_results.get(doc_id, {})
        blur_score = res.get("blur_score", 999.0)

        display_name = DOC_DISPLAY_NAMES.get(doc_type, doc_type.replace("_", " "))

        if blur_score < 60.0:
            flags.append(
                Flag(
                    code=FlagCode.DOC_BLURRY,
                    module=2,
                    severity=Severity.RED,
                    score_impact=12,
                    details={
                        "doc_type": doc_type,
                        "blur_score": blur_score,
                        "threshold": 100.0,
                        "message": f"Your {display_name} is blurry."
                    },
                    document_id=doc_id
                )
            )
        elif 60.0 <= blur_score < 100.0:
            flags.append(
                Flag(
                    code=FlagCode.DOC_BLURRY,
                    module=2,
                    severity=Severity.AMBER,
                    score_impact=5,
                    details={
                        "doc_type": doc_type,
                        "blur_score": blur_score,
                        "threshold": 100.0,
                        "message": f"Your {display_name} has borderline sharpness."
                    },
                    document_id=doc_id
                )
            )
        else:
            flags.append(
                Flag(
                    code=FlagCode.DOC_QUALITY_OK,
                    module=2,
                    severity=Severity.GREEN,
                    score_impact=0,
                    details={"doc_type": doc_type, "blur_score": blur_score},
                    document_id=doc_id
                )
            )

    # Check for missing required documents
    for req_type in REQUIRED_DOCS:
        if req_type not in present_types:
            display_name = DOC_DISPLAY_NAMES.get(req_type, req_type.replace("_", " ")).capitalize()
            flags.append(
                Flag(
                    code=FlagCode.DOC_MISSING,
                    module=2,
                    severity=Severity.RED,
                    score_impact=10,
                    details={
                        "missing_doc_type": req_type,
                        "message": f"{display_name} missing."
                    }
                )
            )

    return flags

def format_m2_demo_summary(flags: List[Flag]) -> str:
    """
    Produces the targeted demo output:
    e.g. 'Your salary slip is blurry. Bank statement missing.'
    """
    messages = []
    # Collect blurry messages
    for f in flags:
        if f.code == FlagCode.DOC_BLURRY and "message" in f.details:
            messages.append(f.details["message"])
    # Collect missing messages
    for f in flags:
        if f.code == FlagCode.DOC_MISSING and "message" in f.details:
            messages.append(f.details["message"])
    return " ".join(messages)
