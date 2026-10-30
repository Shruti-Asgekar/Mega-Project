"""
Shared Output Contract Schemas for ML Service and Analysis Modules.
Matching Pydantic models for the platform-wide contract.
"""

from typing import Literal, Dict, Any, Optional, List
from pydantic import BaseModel, Field

SeverityLevel = Literal["green", "amber", "red"]

class FindingContract(BaseModel):
    module: int = Field(..., description="Module identifier (6, 7, 8, 9, 13)")
    check: str = Field(..., description="Check identifier")
    severity: SeverityLevel
    reason_code: str = Field(..., description="Unique machine-readable reason code")
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: Dict[str, Any] = Field(default_factory=dict)

class ClassificationResponse(BaseModel):
    document_type: str
    confidence: float
    probabilities: Dict[str, float]
    needs_human_check: bool
    model_version: str

class OCRResponse(BaseModel):
    text: str
    num_pages: int
    preprocessing_applied: List[str]
    confidence: float
