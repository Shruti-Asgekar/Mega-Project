"""
Unit Tests for Module 6 (Forgery Detection Lite).
"""

import io
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pikepdf
from backend.app.core.contracts import FlagCode, Severity
from services.forgery import (
    analyze_pdf_metadata,
    verify_salary_slip_arithmetic,
    perform_error_level_analysis
)

def create_synthetic_pdf(producer: str = "ReportLab PDF Library") -> bytes:
    """Generates an in-memory PDF with custom Producer."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(100, 700, "CONFIDENTIAL SALARY STATEMENT")
    c.drawString(100, 680, "Gross Salary: Rs 75,000")
    c.save()
    pdf_bytes = buf.getvalue()

    # Rewrite Producer using pikepdf
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        pdf.docinfo[pikepdf.Name("/Producer")] = producer
        out_buf = io.BytesIO()
        pdf.save(out_buf)
        return out_buf.getvalue()

def test_clean_reportlab_pdf_passes():
    clean_pdf = create_synthetic_pdf(producer="ReportLab PDF Library - Version 4.0")
    flags = analyze_pdf_metadata(clean_pdf)
    assert len(flags) == 1
    assert flags[0].code == FlagCode.META_CLEAN
    assert flags[0].severity == Severity.GREEN

def test_photoshop_tampered_pdf_flagged():
    forged_pdf = create_synthetic_pdf(producer="Adobe Photoshop 2024 (Windows)")
    flags = analyze_pdf_metadata(forged_pdf)
    meta_flags = [f for f in flags if f.code == FlagCode.META_EDITING_SOFTWARE]
    assert len(meta_flags) == 1
    assert meta_flags[0].severity == Severity.RED
    assert "photoshop" in meta_flags[0].details["detected_keywords"]

def test_salary_slip_arithmetic():
    # Valid arithmetic: 75000 - 8000 == 67000
    valid_flags = verify_salary_slip_arithmetic(
        gross=75000.0,
        deductions=8000.0,
        net=67000.0,
        basic=40000.0,
        hra=20000.0,
        allowances=15000.0,
        pf=5000.0,
        tax=3000.0,
        other_deductions=0.0
    )
    assert len(valid_flags) == 1
    assert valid_flags[0].code == FlagCode.SLIP_ARITHMETIC_OK
    assert valid_flags[0].severity == Severity.GREEN

    # Tampered / Inconsistent totals: gross 75000 - deductions 8000 != net 72000
    invalid_flags = verify_salary_slip_arithmetic(
        gross=75000.0,
        deductions=8000.0,
        net=72000.0
    )
    assert len(invalid_flags) == 1
    assert invalid_flags[0].code == FlagCode.SLIP_ARITHMETIC_MISMATCH
    assert invalid_flags[0].severity == Severity.RED
    assert invalid_flags[0].details["expected_net"] == 67000.0
    assert invalid_flags[0].details["found_net"] == 72000.0

def test_error_level_analysis():
    # Test on a synthetic clean image
    from PIL import Image
    import numpy as np

    img = Image.new("RGB", (100, 100), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    img_bytes = buf.getvalue()

    flags, _ = perform_error_level_analysis(img_bytes)
    assert len(flags) == 1
    assert flags[0].code == FlagCode.ELA_NORMAL
    assert flags[0].severity == Severity.GREEN
