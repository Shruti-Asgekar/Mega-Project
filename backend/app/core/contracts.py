"""
Shared Data Contracts and Enums for Verification Modules.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class FlagCode(str, Enum):
    # Module 1
    PAN_FORMAT_INVALID = "PAN_FORMAT_INVALID"
    PAN_FORMAT_VALID = "PAN_FORMAT_VALID"
    AADHAAR_INVALID_FORMAT = "AADHAAR_INVALID_FORMAT"
    AADHAAR_CHECKSUM_FAIL = "AADHAAR_CHECKSUM_FAIL"
    AADHAAR_VALID = "AADHAAR_VALID"
    IFSC_INVALID = "IFSC_INVALID"
    IFSC_VALID = "IFSC_VALID"
    DOB_INVALID = "DOB_INVALID"
    DOB_AGE_OUT_OF_RANGE = "DOB_AGE_OUT_OF_RANGE"
    DOB_VALID = "DOB_VALID"

    # Module 2
    DOC_BLURRY = "DOC_BLURRY"
    DOC_MISSING = "DOC_MISSING"
    DOC_QUALITY_OK = "DOC_QUALITY_OK"
    DOC_ANALYSIS_DEGRADED = "DOC_ANALYSIS_DEGRADED"

    # Module 4
    NAME_MISMATCH = "NAME_MISMATCH"
    NAME_MATCH = "NAME_MATCH"
    DOB_MISMATCH = "DOB_MISMATCH"
    DOB_MATCH = "DOB_MATCH"
    ADDRESS_MISMATCH = "ADDRESS_MISMATCH"
    ADDRESS_MATCH = "ADDRESS_MATCH"

    # Module 5
    INCOME_MISMATCH = "INCOME_MISMATCH"
    INCOME_VERIFIED = "INCOME_VERIFIED"
    EMI_BURDEN_HIGH = "EMI_BURDEN_HIGH"
    EMI_BURDEN_NORMAL = "EMI_BURDEN_NORMAL"
    BOUNCED_PAYMENTS = "BOUNCED_PAYMENTS"
    NO_BOUNCED_PAYMENTS = "NO_BOUNCED_PAYMENTS"

    # Module 6
    META_EDITING_SOFTWARE = "META_EDITING_SOFTWARE"
    META_MODIFIED_AFTER_CREATED = "META_MODIFIED_AFTER_CREATED"
    META_MISSING = "META_MISSING"
    META_CLEAN = "META_CLEAN"
    SLIP_ARITHMETIC_MISMATCH = "SLIP_ARITHMETIC_MISMATCH"
    SLIP_ARITHMETIC_OK = "SLIP_ARITHMETIC_OK"
    ELA_ANOMALY = "ELA_ANOMALY"
    ELA_NORMAL = "ELA_NORMAL"

    # Module 7
    FRAUD_RING_SUSPECTED = "FRAUD_RING_SUSPECTED"
    SHARED_IDENTIFIER = "SHARED_IDENTIFIER"
    NO_FRAUD_RING = "NO_FRAUD_RING"

    # Module 10
    INTEGRITY_BROKEN = "INTEGRITY_BROKEN"
    INTEGRITY_VERIFIED = "INTEGRITY_VERIFIED"

    # General Pipeline
    DOC_UNREADABLE = "DOC_UNREADABLE"

class Severity(str, Enum):
    RED = "red"
    AMBER = "amber"
    GREEN = "green"

class RoutingDecision(str, Enum):
    AUTO_CLEAR = "AUTO_CLEAR"
    OFFICER_REVIEW = "OFFICER_REVIEW"
    ESCALATE = "ESCALATE"

class Transaction(BaseModel):
    date: str
    description: str
    debit: float = 0.0
    credit: float = 0.0
    balance: float = 0.0

class ExtractedFields(BaseModel):
    doc_type: str = Field(description="aadhaar|pan|salary_slip|bank_statement")
    name: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    aadhaar_number: Optional[str] = None
    pan_number: Optional[str] = None
    ifsc: Optional[str] = None
    phone: Optional[str] = None
    account_number: Optional[str] = None
    employer: Optional[str] = None
    gross_salary: Optional[float] = None
    total_deductions: Optional[float] = None
    net_salary: Optional[float] = None
    basic_pay: Optional[float] = None
    hra: Optional[float] = None
    allowances: Optional[float] = None
    pf: Optional[float] = None
    tax: Optional[float] = None
    other_deductions: Optional[float] = None
    month: Optional[str] = None
    transactions: List[Transaction] = Field(default_factory=list)

class Flag(BaseModel):
    code: FlagCode
    module: int
    severity: Severity
    score_impact: int
    details: Dict[str, Any] = Field(default_factory=dict)
    document_id: Optional[str] = None
    explanation: Optional[str] = None
