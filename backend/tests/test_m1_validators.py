"""
Table-Driven Unit Tests for Module 1 (Field Validators).
"""

import pytest
from datetime import date
from backend.app.core.contracts import FlagCode, Severity
from backend.app.modules.m1_validators import (
    validate_pan,
    validate_aadhaar,
    validate_ifsc,
    validate_dob,
    generate_valid_aadhaar,
    compute_verhoeff_checksum,
    validate_verhoeff
)

@pytest.mark.parametrize("pan,expected_code,expected_sev", [
    ("ABCPE1234F", FlagCode.PAN_FORMAT_VALID, Severity.GREEN),
    ("XYZCP5678Q", FlagCode.PAN_FORMAT_VALID, Severity.GREEN),
    ("MNOFA9999Z", FlagCode.PAN_FORMAT_VALID, Severity.GREEN),
    ("ABC123456F", FlagCode.PAN_FORMAT_INVALID, Severity.RED), # Wrong format
    ("ABCDZ1234F", FlagCode.PAN_FORMAT_INVALID, Severity.RED), # 4th char 'Z' invalid
    ("ABCDE12345", FlagCode.PAN_FORMAT_INVALID, Severity.RED), # 10th char digit
    ("SHORT", FlagCode.PAN_FORMAT_INVALID, Severity.RED),
    ("ABCDE1234FF", FlagCode.PAN_FORMAT_INVALID, Severity.RED), # Too long
])
def test_pan_validator_table(pan, expected_code, expected_sev):
    flags = validate_pan(pan)
    assert len(flags) == 1
    assert flags[0].code == expected_code
    assert flags[0].severity == expected_sev

def test_aadhaar_verhoeff_generation_and_tampering():
    prefix = "54891234567"
    valid_aadhaar = generate_valid_aadhaar(prefix)
    assert len(valid_aadhaar) == 12
    assert valid_aadhaar.startswith(prefix)

    # Valid check
    flags = validate_aadhaar(valid_aadhaar)
    assert len(flags) == 1
    assert flags[0].code == FlagCode.AADHAAR_VALID
    assert flags[0].severity == Severity.GREEN

    # One digit changed in body -> must fail Verhoeff
    corrupted_body = "54891234568" + valid_aadhaar[-1]
    flags_bad_body = validate_aadhaar(corrupted_body)
    assert len(flags_bad_body) == 1
    assert flags_bad_body[0].code == FlagCode.AADHAAR_CHECKSUM_FAIL
    assert flags_bad_body[0].severity == Severity.RED

    # Checksum digit tampered -> must fail Verhoeff
    tampered_chk = str((int(valid_aadhaar[-1]) + 1) % 10)
    flags_bad_chk = validate_aadhaar(prefix + tampered_chk)
    assert len(flags_bad_chk) == 1
    assert flags_bad_chk[0].code == FlagCode.AADHAAR_CHECKSUM_FAIL
    assert flags_bad_chk[0].severity == Severity.RED

@pytest.mark.parametrize("aadhaar,expected_code", [
    ("012345678901", FlagCode.AADHAAR_INVALID_FORMAT), # Starts with 0
    ("112345678901", FlagCode.AADHAAR_INVALID_FORMAT), # Starts with 1
    ("12345", FlagCode.AADHAAR_INVALID_FORMAT),        # Too short
    ("2345-6789-012A", FlagCode.AADHAAR_INVALID_FORMAT), # Non digit
])
def test_aadhaar_invalid_format(aadhaar, expected_code):
    flags = validate_aadhaar(aadhaar)
    assert len(flags) == 1
    assert flags[0].code == expected_code
    assert flags[0].severity == Severity.RED

@pytest.mark.parametrize("ifsc,expected_code,expected_sev", [
    ("SBIN0001234", FlagCode.IFSC_VALID, Severity.GREEN),
    ("HDFC0000001", FlagCode.IFSC_VALID, Severity.GREEN),
    ("ICIC0000999", FlagCode.IFSC_VALID, Severity.GREEN),
    ("SBIN1001234", FlagCode.IFSC_INVALID, Severity.RED), # 5th char not '0'
    ("SBI0001234", FlagCode.IFSC_INVALID, Severity.RED),  # 3 chars prefix
    ("SBIN000123", FlagCode.IFSC_INVALID, Severity.RED),   # Too short
    ("sbin0001234", FlagCode.IFSC_VALID, Severity.GREEN), # Lowercase accepted via upper()
])
def test_ifsc_validator(ifsc, expected_code, expected_sev):
    flags = validate_ifsc(ifsc)
    assert len(flags) == 1
    assert flags[0].code == expected_code
    assert flags[0].severity == expected_sev

def test_dob_validator():
    ref_date = date(2026, 10, 30)

    # Valid 30 years old (1996)
    f1 = validate_dob("15/08/1996", ref_date=ref_date)
    assert f1[0].code == FlagCode.DOB_VALID
    assert f1[0].severity == Severity.GREEN

    # Valid hyphenated
    f2 = validate_dob("1996-08-15", ref_date=ref_date)
    assert f2[0].code == FlagCode.DOB_VALID

    # Future date
    f_future = validate_dob("01/01/2030", ref_date=ref_date)
    assert f_future[0].code == FlagCode.DOB_INVALID
    assert f_future[0].severity == Severity.RED

    # Underage (16 years old)
    f_under = validate_dob("15/08/2010", ref_date=ref_date)
    assert f_under[0].code == FlagCode.DOB_AGE_OUT_OF_RANGE
    assert f_under[0].severity == Severity.AMBER

    # Over 100
    f_over = validate_dob("01/01/1920", ref_date=ref_date)
    assert f_over[0].code == FlagCode.DOB_AGE_OUT_OF_RANGE
    assert f_over[0].severity == Severity.AMBER

    # Invalid calendar date
    f_bad = validate_dob("32/13/1990", ref_date=ref_date)
    assert f_bad[0].code == FlagCode.DOB_INVALID
    assert f_bad[0].severity == Severity.RED
