import os
from pathlib import Path

templates_dir = Path("backend/app/templates/explanations")
templates_dir.mkdir(parents=True, exist_ok=True)

templates = {
    # Module 1
    "PAN_FORMAT_INVALID": "PAN format is invalid: {{ details.pan|default('Value') }} does not follow the required structure or has an unrecognized entity type.",
    "PAN_FORMAT_VALID": "PAN format is valid.",
    "AADHAAR_INVALID_FORMAT": "Aadhaar format is invalid: must contain 12 numeric digits and not begin with 0 or 1.",
    "AADHAAR_CHECKSUM_FAIL": "Aadhaar Verhoeff cryptographic checksum validation failed.",
    "AADHAAR_VALID": "Aadhaar format and Verhoeff checksum are valid.",
    "IFSC_INVALID": "IFSC code {{ details.ifsc|default('') }} is invalid: must match standard bank branch format.",
    "IFSC_VALID": "IFSC code is valid and recognized.",
    "DOB_INVALID": "Date of birth is invalid or set in the future: {{ details.dob|default('') }}.",
    "DOB_AGE_OUT_OF_RANGE": "Applicant age {{ details.age|default('') }} is outside standard eligibility criteria (18-100 years).",
    "DOB_VALID": "Date of birth is valid (age: {{ details.age|default('eligible') }}).",

    # Module 2
    "DOC_BLURRY": "Your {{ details.doc_type|default('document')|replace('_', ' ') }} is blurry (Laplacian variance {{ details.blur_score|default(0)|round(1) }} < {{ details.threshold|default(100) }}).",
    "DOC_MISSING": "{{ details.missing_doc_type|default('Required document')|replace('_', ' ')|capitalize }} missing.",
    "DOC_QUALITY_OK": "Document image quality and sharpness are acceptable.",
    "DOC_ANALYSIS_DEGRADED": "Document analysis running in degraded in-process fallback mode.",

    # Module 4
    "NAME_MISMATCH": "Name differs across documents: '{{ details.name_a|default('') }}' vs '{{ details.name_b|default('') }}' ({{ details.similarity|default(0)|round|int }}% match).",
    "NAME_MATCH": "Name matches across documents ('{{ details.name_a|default('') }}').",
    "DOB_MISMATCH": "Date of birth discrepancy detected between {{ details.doc_a|default('doc') }} ({{ details.dob_a|default('') }}) and {{ details.doc_b|default('doc') }} ({{ details.dob_b|default('') }}).",
    "DOB_MATCH": "Date of birth matches across submitted documents.",
    "ADDRESS_MISMATCH": "Address varies across documents ({{ details.similarity|default(0)|round|int }}% similarity match).",
    "ADDRESS_MATCH": "Address details match across documents ({{ details.similarity|default(100)|round|int }}% match).",

    # Module 5
    "INCOME_MISMATCH": "Salary slip net income {{ details.slip_net|inr }} is {{ details.deviation_pct|round|int }}% higher than average bank salary credits of {{ details.avg_salary_credits|inr }}.",
    "INCOME_VERIFIED": "Salary slip net income is consistent with average monthly bank credits.",
    "EMI_BURDEN_HIGH": "Critical EMI burden of {{ details.burden_pct|round(1) }}% exceeds safe threshold.",
    "EMI_BURDEN_NORMAL": "Monthly EMI commitments are within acceptable financial debt limits.",
    "BOUNCED_PAYMENTS": "Detected {{ details.count|default(1) }} bounced/returned transaction(s) in bank statement.",
    "NO_BOUNCED_PAYMENTS": "No bounced cheques or failed NACH/ECS debit transactions detected.",

    # Module 6
    "META_EDITING_SOFTWARE": "Document metadata indicates unauthorized modification software was used: {{ details.detected_keywords|default([])|join(', ') }}.",
    "META_MODIFIED_AFTER_CREATED": "Document was modified {{ details.diff_seconds|default(0)|round|int }} seconds after initial compilation.",
    "META_MISSING": "Document structural metadata is stripped or missing.",
    "META_CLEAN": "Document metadata is intact and shows authentic PDF creation.",
    "SLIP_ARITHMETIC_MISMATCH": "Salary slip arithmetic mismatch: Gross ({{ details.gross|inr }}) - Deductions ({{ details.deductions|inr }}) = Expected Net {{ details.expected_net|inr }}, but found {{ details.found_net|inr }}.",
    "SLIP_ARITHMETIC_OK": "Salary slip arithmetic is mathematically consistent.",
    "ELA_ANOMALY": "Error Level Analysis (ELA) detected localized image tampering anomaly.",
    "ELA_NORMAL": "Error Level Analysis shows uniform compression artifact levels.",

    # Module 7
    "FRAUD_RING_SUSPECTED": "Suspicious syndicate cluster: linked to {{ details.cluster_size|default(3) - 1 }} other applications via shared phone, bank account, or address.",
    "SHARED_IDENTIFIER": "Applicant shares credential details with 1 other application.",
    "NO_FRAUD_RING": "No shared identity or credential clustering detected.",

    # Module 10
    "INTEGRITY_BROKEN": "Cryptographic ledger integrity check failed: file hash or block linkage corrupted.",
    "INTEGRITY_VERIFIED": "All document cryptographic fingerprints match immutable hash chain records.",

    # Pipeline
    "DOC_UNREADABLE": "Document file is corrupt, password-protected, or unreadable."
}

for code, content in templates.items():
    file_path = templates_dir / f"{code}.j2"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")

print(f"Generated {len(templates)} Jinja2 templates in {templates_dir}")
