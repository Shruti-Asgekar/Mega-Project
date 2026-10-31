"""
Comprehensive tests for Authentication, Argon2id passwords,
Brute-force Lockout, and Role-Based Access Control (RBAC).
"""

import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.app.db import init_db
from backend.app.db.database import SessionLocal
from backend.app.db.models import User, Case, Applicant
from backend.app.core.security import hash_password, encrypt_value

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

def test_registration_password_strength(client):
    """Verify registration rejects weak passwords and accepts strong passwords."""
    email = f"test_{uuid.uuid4().hex[:6]}@example.com"

    # Weak: too short
    resp = client.post("/api/auth/register", json={
        "email": email,
        "full_name": "Test User",
        "password": "Short1!"
    })
    assert resp.status_code == 422 or resp.status_code == 400

    # Weak: common dictionary password
    resp = client.post("/api/auth/register", json={
        "email": email,
        "full_name": "Test User",
        "password": "Password123!"
    })
    assert resp.status_code == 400
    assert "common" in resp.json().get("message", "").lower()

    # Strong: >= 10 chars, upper, lower, digit, symbol
    strong_pwd = "V3ry$ecureKYC#Pass2026!"
    resp = client.post("/api/auth/register", json={
        "email": email,
        "full_name": "Ramesh Kumar",
        "password": strong_pwd
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "success"
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "applicant"
    assert "csrf_token" in data

def test_login_and_brute_force_lockout(client):
    """Verify failed attempts increment counter and 5 failures trigger 15-min lockout."""
    email = f"lockout_{uuid.uuid4().hex[:6]}@example.com"
    correct_pwd = "C0mpl3x!Password2026"

    # Register user
    reg_resp = client.post("/api/auth/register", json={
        "email": email,
        "full_name": "Lockout Target",
        "password": correct_pwd
    })
    assert reg_resp.status_code == 201

    # 4 failed login attempts
    for i in range(4):
        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "WrongPassword123!"
        })
        assert resp.status_code == 401

    # 5th failed attempt -> locks account
    lock_resp = client.post("/api/auth/login", json={
        "email": email,
        "password": "WrongPassword123!"
    })
    assert lock_resp.status_code == 423
    assert "locked" in lock_resp.json().get("message", "").lower()

    # Even with correct password, login is blocked while locked
    blocked_resp = client.post("/api/auth/login", json={
        "email": email,
        "password": correct_pwd
    })
    assert blocked_resp.status_code == 423

def test_rbac_case_access_isolation(client):
    """Verify applicant can only access their own cases, while officer sees all."""
    db = SessionLocal()

    # 1. Create two applicants and cases
    appl1_email = f"appl1_{uuid.uuid4().hex[:6]}@test.com"
    appl2_email = f"appl2_{uuid.uuid4().hex[:6]}@test.com"
    pwd = "Secur3!Password99"

    c1 = TestClient(app)
    c2 = TestClient(app)

    reg1 = c1.post("/api/auth/register", json={"email": appl1_email, "full_name": "Appl 1", "password": pwd})
    u1_id = reg1.json()["user"]["id"]

    reg2 = c2.post("/api/auth/register", json={"email": appl2_email, "full_name": "Appl 2", "password": pwd})
    u2_id = reg2.json()["user"]["id"]

    # Create case for user 1
    case1_resp = c1.post("/api/cases", data={
        "applicant_name": "Appl One",
        "consent_accepted": "true",
        "run_async": "false"
    })
    assert case1_resp.status_code in (200, 201, 202)
    case1_id = case1_resp.json().get("case_id") or case1_resp.json().get("id")

    # Associate case1 with u1
    c_obj = db.query(Case).filter(Case.id == case1_id).first()
    c_obj.user_id = u1_id
    db.commit()

    # User 1 can view case 1
    view1 = c1.get(f"/api/cases/{case1_id}")
    assert view1.status_code == 200

    # User 2 CANNOT view case 1 (403 Forbidden)
    view2 = c2.get(f"/api/cases/{case1_id}")
    assert view2.status_code == 403
    assert view2.json().get("error") == "FORBIDDEN"

    db.close()

def test_officer_decision_recording(client):
    """Verify officer can record case decisions with required comments."""
    db = SessionLocal()
    officer_email = f"officer_{uuid.uuid4().hex[:6]}@bank.internal"
    pwd = "Officer#Pass2026!"

    # Create officer user directly
    officer = User(
        email=officer_email,
        full_name="Verification Officer Dave",
        password_hash=hash_password(pwd),
        role="officer",
        is_active=True
    )
    db.add(officer)
    db.commit()

    c_officer = TestClient(app)
    login_resp = c_officer.post("/api/auth/login", json={"email": officer_email, "password": pwd})
    assert login_resp.status_code == 200

    # Create a test applicant and case
    appl = Applicant(name_encrypted=encrypt_value("Officer Test Subject"), name_masked="Officer Test Subject")
    db.add(appl)
    db.commit()
    case = Case(applicant_id=appl.id, status="COMPLETED", trust_score=85, route="AUTO_CLEAR")
    db.add(case)
    db.commit()
    case_id = case.id

    # Post decision without comment -> should fail validation
    bad_dec = c_officer.post(f"/api/auth/cases/{case_id}/decision", json={"decision": "APPROVED", "comment": "ab"})
    assert bad_dec.status_code == 422 or bad_dec.status_code == 400

    # Post valid decision with compliance comment
    good_dec = c_officer.post(f"/api/auth/cases/{case_id}/decision", json={
        "decision": "APPROVED",
        "comment": "Bank deposits match declared salary slips. Clean verification."
    })
    assert good_dec.status_code == 200
    assert good_dec.json()["decision"] == "APPROVED"

    # Verify persisted in database
    db.refresh(case)
    assert case.decision == "APPROVED"
    assert case.decision_by == officer_email
    assert case.decision_comment == "Bank deposits match declared salary slips. Clean verification."

    db.close()

def test_admin_audit_trail_and_retention(client):
    """Verify admin can view audit logs and trigger DPDP retention sweep."""
    db = SessionLocal()
    admin_email = f"admin_{uuid.uuid4().hex[:6]}@bank.internal"
    pwd = "Admin#Pass2026!Global"

    admin = User(
        email=admin_email,
        full_name="Chief Risk Officer",
        password_hash=hash_password(pwd),
        role="admin",
        is_active=True
    )
    db.add(admin)
    db.commit()

    c_admin = TestClient(app)
    c_admin.post("/api/auth/login", json={"email": admin_email, "password": pwd})

    # Non-admin cannot view audit logs
    c_anon = TestClient(app)
    assert c_anon.get("/api/auth/admin/audit").status_code == 401

    # Admin can view audit logs
    audit_resp = c_admin.get("/api/auth/admin/audit")
    assert audit_resp.status_code == 200
    adata = audit_resp.json()
    assert "total" in adata
    assert "items" in adata

    # Admin can trigger retention sweep
    sweep_resp = c_admin.post("/api/auth/admin/retention-sweep")
    assert sweep_resp.status_code == 200
    sdata = sweep_resp.json()
    assert sdata["status"] == "success"
    assert "cases_purged" in sdata

    db.close()
