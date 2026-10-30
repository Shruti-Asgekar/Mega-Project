"""
ML Microservice (FastAPI).
Stateless image, CV, and PDF analysis service running on port 8001.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import starlette.routing
_orig_router_init = starlette.routing.Router.__init__
def _compat_router_init(self, routes=None, redirect_slashes=True, default=None, on_startup=None, on_shutdown=None, lifespan=None, **kwargs):
    _orig_router_init(self, routes=routes, redirect_slashes=redirect_slashes, default=default, lifespan=lifespan)
    self.on_startup = on_startup or []
    self.on_shutdown = on_shutdown or []
starlette.routing.Router.__init__ = _compat_router_init

from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from services.blur import calculate_blur_score
from services.forgery import (
    analyze_pdf_metadata,
    verify_salary_slip_arithmetic,
    perform_error_level_analysis
)
from services.extractor import (
    extract_raw_text,
    parse_fields_from_text,
    TESSERACT_AVAILABLE
)
from backend.app.core.contracts import ExtractedFields

app = FastAPI(
    title="KYC ML Verification Microservice",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INTERNAL_KEY = os.environ.get("X_INTERNAL_KEY", "shared_internal_secret_key_placeholder")

def verify_internal_key(x_internal_key: Optional[str] = Header(None)):
    if x_internal_key and x_internal_key != INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized internal call")

@app.get("/api/health")
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ml-service",
        "tesseract_available": TESSERACT_AVAILABLE,
        "supported_features": ["blur", "forgery_pikepdf", "salary_arithmetic", "ela", "extractor"]
    }

@app.post("/api/quality/blur")
async def analyze_blur_endpoint(
    file: UploadFile = File(...),
    threshold: float = Form(100.0)
):
    contents = await file.read()
    res = calculate_blur_score(contents, filename=file.filename or "", blur_threshold=threshold)
    return res

@app.post("/api/forgery/analyze")
async def analyze_forgery_endpoint(
    file: UploadFile = File(...),
    doc_type: str = Form("generic")
):
    contents = await file.read()
    flags = []

    # 1. Metadata check for PDFs
    if (file.filename and file.filename.lower().endswith(".pdf")) or contents[:4] == b"%PDF":
        pdf_flags = analyze_pdf_metadata(contents)
        flags.extend([f.model_dump() for f in pdf_flags])

    # 2. ELA for images
    if file.filename and file.filename.lower().endswith((".jpg", ".jpeg", ".png")):
        ela_flags, _ = perform_error_level_analysis(contents)
        flags.extend([f.model_dump() for f in ela_flags])

    return {"flags": flags}

@app.post("/api/extract")
async def extract_fields_endpoint(
    file: UploadFile = File(...),
    doc_type: str = Form("generic")
):
    contents = await file.read()
    raw_text = extract_raw_text(contents, file.filename or "")
    fields = parse_fields_from_text(raw_text, doc_type=doc_type)
    return {
        "raw_text": raw_text,
        "extracted_fields": fields.model_dump()
    }
