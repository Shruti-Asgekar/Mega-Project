"""
Module 6 Bridge (Backend).
Exposes forgery detection and salary slip arithmetic functions.
"""

try:
    from services.forgery import (
        verify_salary_slip_arithmetic,
        analyze_pdf_metadata,
        perform_error_level_analysis
    )
except ImportError:
    import sys
    from pathlib import Path
    ml_svc_path = Path(__file__).resolve().parent.parent.parent.parent / "ml-service"
    if str(ml_svc_path) not in sys.path:
        sys.path.insert(0, str(ml_svc_path))
    from services.forgery import (
        verify_salary_slip_arithmetic,
        analyze_pdf_metadata,
        perform_error_level_analysis
    )
