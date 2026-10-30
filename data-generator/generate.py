"""
Synthetic Document and Demo Scenario Generator (data-generator).
Generates deterministic, seeded synthetic KYC documents and seeds database cases:
1. clean_applicant -> AUTO_CLEAR (Verhoeff-valid Aadhaar, consistent docs, correct slip arithmetic)
2. typo_pan -> flagged instantly (PAN_FORMAT_INVALID)
3. blurry_missing -> blurred salary slip + no bank statement ("Your salary slip is blurry. Bank statement missing.")
4. name_mismatch -> Ramesh Kumar vs Rajesh Kumar
5. income_mismatch -> slip 70,000 vs bank avg ~50,000, 2 EMIs, 1 bounce
6. forged_slip -> Producer "Adobe Photoshop" + wrong totals -> ESCALATE
7. ring_1..ring_4 plus ~20 benign applicants -> FRAUD_RING_SUSPECTED cluster
"""

import os
import sys
import argparse
import random
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pikepdf

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import UPLOAD_DIR
from backend.app.core.storage import save_document
from backend.app.core.contracts import Transaction
from backend.app.core.security import encrypt_value, mask_phone
from backend.app.modules.m10_hashchain import compute_file_sha256
from backend.app.db.database import SessionLocal, engine, Base
from backend.app.db import init_db
from backend.app.db.models import Applicant, Case, Document, Consent, FlagModel, ChainRecord
from backend.app.modules.m1_validators import generate_valid_aadhaar
from backend.app.modules.m3_masking_consent import record_consent
from backend.app.pipeline.orchestrator import run_case_pipeline

SAMPLES_DIR = PROJECT_ROOT / "data-generator" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def generate_pdf(
    filename: str,
    title: str,
    fields: dict,
    producer: str = "ReportLab PDF Library"
) -> str:
    """Generates a synthetic PDF document with given fields and custom metadata."""
    out_path = str(SAMPLES_DIR / filename)
    c = canvas.Canvas(out_path, pagesize=letter)

    # Watermark
    c.setFont("Helvetica", 36)
    c.setFillColorRGB(0.9, 0.9, 0.9)
    c.saveState()
    c.translate(300, 400)
    c.rotate(45)
    c.drawCentredString(0, 0, "SYNTHETIC SAMPLE - FOR DEMO ONLY")
    c.restoreState()

    # Content
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0.1, 0.2, 0.4)
    c.drawString(60, 720, title)

    c.setFont("Helvetica", 11)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    y = 680
    for k, v in fields.items():
        label = k.replace("_", " ").title()
        c.drawString(60, y, f"{label}: {v}")
        y -= 25

    c.save()

    # Update metadata with pikepdf
    with pikepdf.open(out_path, allow_overwriting_input=True) as pdf:
        pdf.docinfo[pikepdf.Name("/Producer")] = producer
        pdf.docinfo[pikepdf.Name("/Creator")] = "KYC Synthetic Generator"
        pdf.save(out_path)

    return out_path

def generate_blurry_image(filename: str, title: str, fields: dict) -> str:
    """Generates a blurry image of a document to trigger DOC_BLURRY (Laplacian < 60)."""
    # Create clean image canvas
    img = np.ones((500, 700, 3), dtype=np.uint8) * 250
    cv2.putText(img, title, (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (20, 40, 80), 2)

    y = 120
    for k, v in fields.items():
        text_line = f"{k.replace('_', ' ').title()}: {v}"
        cv2.putText(img, text_line, (50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (50, 50, 50), 2)
        y += 40

    # Apply heavy blur to guarantee variance < 60
    blurred = cv2.GaussianBlur(img, (25, 25), 0)
    out_path = str(SAMPLES_DIR / filename)
    cv2.imwrite(out_path, blurred)
    return out_path

def generate_bank_csv(filename: str, transactions: list[dict]) -> str:
    """Generates bank statement CSV file."""
    out_path = str(SAMPLES_DIR / filename)
    lines = ["Date,Description,Debit,Credit,Balance\n"]
    for t in transactions:
        lines.append(f"{t['date']},{t['description']},{t['debit']},{t['credit']},{t['balance']}\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return out_path

def create_case_in_db(
    db,
    applicant_name: str,
    phone: str,
    address: str,
    doc_paths: list[tuple[str, str]] # list of (doc_type, path)
) -> Case:
    """Creates applicant, case, documents in DB and runs pipeline."""
    app = Applicant(
        name_encrypted=encrypt_value(applicant_name),
        name_masked=applicant_name,
        phone_encrypted=encrypt_value(phone) if phone else None,
        phone_masked=mask_phone(phone) if phone else None,
        address_encrypted=encrypt_value(address) if address else None,
        address_normalised=address.strip().lower() if address else None
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    case = Case(applicant_id=app.id, status="PROCESSING")
    db.add(case)
    db.commit()
    db.refresh(case)

    # Consent
    record_consent(db, case.id, accepted=True, ip="127.0.0.1", text_version="v1.0")

    # Documents
    for doc_type, path in doc_paths:
        file_bytes = Path(path).read_bytes()
        doc = Document(
            case_id=case.id,
            file_path=path,
            sha256="",
            doc_type=doc_type
        )
        db.add(doc)
        db.flush()
        save_document(db, doc, file_bytes, Path(path).name)
    db.commit()

    # Run pipeline
    run_case_pipeline(case.id, db)
    return case

def seed_database(reset: bool = False, benign_count: int = 12):
    """Generates all 7 demo scenarios and seeds DB."""
    if reset:
        print("[Generator] Resetting database tables...")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    else:
        init_db()

    db = SessionLocal()
    random.seed(42)

    print("[Generator] Generating Scenario 1: clean_applicant -> AUTO_CLEAR...")
    v_aadhaar = generate_valid_aadhaar("54891234567")
    clean_aadhaar = generate_pdf("clean_aadhaar.pdf", "UNIQUE IDENTIFICATION AUTHORITY OF INDIA", {
        "Name": "Suresh Sharma", "DOB": "12/05/1990", "Aadhaar_Number": v_aadhaar, "Address": "Flat 201, Lotus Apts, MG Road, Mumbai 400001"
    })
    clean_pan = generate_pdf("clean_pan.pdf", "INCOME TAX DEPARTMENT - GOVT OF INDIA", {
        "Name": "Suresh Sharma", "DOB": "12/05/1990", "PAN_Number": "ABCPE1234F"
    })
    clean_slip = generate_pdf("clean_slip.pdf", "INFOSYS LIMITED - SALARY STATEMENT", {
        "Name": "Suresh Sharma", "Gross_Salary": "80,000", "Total_Deductions": "10,000", "Net_Salary": "70,000",
        "Basic_Pay": "45,000", "HRA": "25,000", "Allowances": "10,000", "PF": "6,000", "Tax": "4,000"
    })
    clean_bank_csv = generate_bank_csv("clean_bank.csv", [
        {"date": "05/05/2026", "description": "SALARY CREDIT - INFOSYS", "debit": 0, "credit": 70000, "balance": 95000},
        {"date": "05/06/2026", "description": "SALARY CREDIT - INFOSYS", "debit": 0, "credit": 70000, "balance": 120000},
    ])
    case_clean = create_case_in_db(db, "Suresh Sharma", "9820011223", "Flat 201, Lotus Apts, MG Road, Mumbai 400001", [
        ("aadhaar", clean_aadhaar), ("pan", clean_pan), ("salary_slip", clean_slip), ("bank_statement", clean_bank_csv)
    ])
    print(f"  -> clean_applicant Case ID: {case_clean.id} (Score: {case_clean.trust_score}, Route: {case_clean.route})")

    print("[Generator] Generating Scenario 2: typo_pan -> PAN_FORMAT_INVALID -> OFFICER_REVIEW...")
    typo_pan_doc = generate_pdf("typo_pan.pdf", "INCOME TAX DEPARTMENT", {
        "Name": "Amit Roy", "DOB": "10/10/1992", "PAN_Number": "ABCDZ1234F" # 'Z' 4th char is invalid
    })
    amit_aadhaar = generate_pdf("amit_aadhaar.pdf", "AADHAAR CARD", {
        "Name": "Amit Roy", "DOB": "10/10/1992", "Aadhaar_Number": generate_valid_aadhaar("78901234567")
    })
    amit_slip = generate_pdf("amit_slip.pdf", "SALARY STATEMENT", {
        "Name": "Amit Roy", "Gross Salary": "60,000", "Total Deductions": "5,000", "Net Salary": "55,000"
    })
    amit_bank = generate_bank_csv("amit_bank.csv", [
        {"date": "05/05/2026", "description": "SALARY CREDIT", "debit": 0, "credit": 55000, "balance": 75000}
    ])
    case_typo = create_case_in_db(db, "Amit Roy", "9820033445", "Sector 14, Gurgaon", [
        ("aadhaar", amit_aadhaar), ("pan", typo_pan_doc), ("salary_slip", amit_slip), ("bank_statement", amit_bank)
    ])
    print(f"  -> typo_pan Case ID: {case_typo.id} (Score: {case_typo.trust_score}, Route: {case_typo.route})")

    print("[Generator] Generating Scenario 3: blurry_missing -> Blurry slip + No bank statement...")
    blurry_slip = generate_blurry_image("blurry_slip.jpg", "SALARY STATEMENT", {
        "Name": "Rohit Verma", "Net_Salary": "45,000"
    })
    ok_aadhaar = generate_pdf("rohit_aadhaar.pdf", "AADHAAR CARD", {
        "Name": "Rohit Verma", "DOB": "01/01/1995", "Aadhaar_Number": generate_valid_aadhaar("98765432101")
    })
    ok_pan = generate_pdf("rohit_pan.pdf", "PAN CARD", {
        "Name": "Rohit Verma", "DOB": "01/01/1995", "PAN_Number": "XYZPA9988K"
    })
    case_blurry = create_case_in_db(db, "Rohit Verma", "9811122233", "Model Town, Delhi", [
        ("aadhaar", ok_aadhaar), ("pan", ok_pan), ("salary_slip", blurry_slip) # bank_statement deliberately missing
    ])
    print(f"  -> blurry_missing Case ID: {case_blurry.id} (Score: {case_blurry.trust_score})")

    print("[Generator] Generating Scenario 4: name_mismatch -> Ramesh Kumar vs Rajesh Kumar...")
    pan_ramesh = generate_pdf("ramesh_pan.pdf", "PAN CARD", {
        "Name": "Ramesh Kumar", "DOB": "15/08/1990", "PAN_Number": "ABCPA4455M"
    })
    slip_rajesh = generate_pdf("rajesh_slip.pdf", "SALARY SLIP", {
        "Name": "Rajesh Kumar", "Gross_Salary": "50,000", "Total_Deductions": "5,000", "Net_Salary": "45,000"
    })
    case_name = create_case_in_db(db, "Ramesh Kumar", "9766655544", "Kothrud, Pune", [
        ("pan", pan_ramesh), ("salary_slip", slip_rajesh)
    ])
    print(f"  -> name_mismatch Case ID: {case_name.id}")

    print("[Generator] Generating Scenario 5: income_mismatch -> Slip 70k vs Bank 50k, 2 EMIs, 1 bounce...")
    slip_70k = generate_pdf("slip_70k.pdf", "ACME CORP - SALARY STATEMENT", {
        "Name": "Manoj Patil", "Employer": "ACME CORP", "Gross_Salary": "75,000", "Total_Deductions": "5,000", "Net_Salary": "70,000"
    })
    bank_mismatch_csv = generate_bank_csv("bank_mismatch.csv", [
        {"date": "05/05/2026", "description": "SALARY CREDIT FROM ACME CORP", "debit": 0, "credit": 50000, "balance": 60000},
        {"date": "10/05/2026", "description": "ACH D - HDFC HOME LOAN EMI", "debit": 12000, "credit": 0, "balance": 48000},
        {"date": "15/05/2026", "description": "NACH - BAJAJ FINSERV LOAN EMI", "debit": 5000, "credit": 0, "balance": 43000},
        {"date": "05/06/2026", "description": "SALARY CREDIT FROM ACME CORP", "debit": 0, "credit": 50000, "balance": 75000},
        {"date": "10/06/2026", "description": "ACH D - HDFC HOME LOAN EMI", "debit": 12000, "credit": 0, "balance": 63000},
        {"date": "15/06/2026", "description": "NACH - BAJAJ FINSERV LOAN EMI", "debit": 5000, "credit": 0, "balance": 58000},
        {"date": "20/06/2026", "description": "CHQ RET - INSUFFICIENT FUNDS ECS BOUNCE", "debit": 500, "credit": 0, "balance": 57500},
    ])
    case_income = create_case_in_db(db, "Manoj Patil", "9899988877", "Shivaji Nagar, Pune", [
        ("salary_slip", slip_70k), ("bank_statement", bank_mismatch_csv)
    ])
    print(f"  -> income_mismatch Case ID: {case_income.id} (Score: {case_income.trust_score}, Route: {case_income.route})")

    print("[Generator] Generating Scenario 6: forged_slip -> Photoshop metadata + wrong totals -> ESCALATE...")
    forged_slip = generate_pdf("forged_slip.pdf", "SALARY SLIP", {
        "Name": "Vikram Singh", "Gross Salary": "75,000", "Total Deductions": "8,000", "Net Salary": "72,000" # 75k - 8k = 67k != 72k!
    }, producer="Adobe Photoshop 2024")
    case_forged = create_case_in_db(db, "Vikram Singh", "9877766655", "Indira Nagar, Bengaluru", [
        ("salary_slip", forged_slip)
    ])
    print(f"  -> forged_slip Case ID: {case_forged.id} (Score: {case_forged.trust_score}, Route: {case_forged.route})")

    print("[Generator] Generating Scenario 7: Planted Fraud Ring (4 members) + 20 Benign Applicants...")
    ring_specs = [
        ("Vijay Syndicate 1", "9876500001", "1122334455", "Flat 101, Galaxy Apts, Sector 4, Noida"),
        ("Ajay Syndicate 2", "9876500001", "9988776655", "Flat 102, Galaxy Apts, Sector 4, Noida"),
        ("Sanjay Syndicate 3", "9123400002", "9988776655", "101 Galaxy Apartments Sector 4 Noida"),
        ("Karan Syndicate 4", "9123400002", "5544332211", "Flat 101, Galaxy Apts, Sector 4, Noida"),
    ]
    for name, ph, acc, addr in ring_specs:
        slip = generate_pdf(f"{name.replace(' ', '_')}_slip.pdf", "SALARY SLIP", {
            "Name": name, "Phone": ph, "Account": acc, "Address": addr, "Net_Salary": "50,000"
        })
        c = create_case_in_db(db, name, ph, addr, [("salary_slip", slip)])

    # 20 Benign applicants with distinct addresses across cities
    benign_first_names = ["Anand", "Priya", "Kavita", "Deepak", "Nisha", "Gaurav", "Sneha", "Rahul", "Pooja", "Alok",
                          "Sunita", "Tarun", "Divya", "Arun", "Meera", "Sachin", "Swati", "Naveen", "Geeta", "Prateek"]
    cities_and_streets = [
        "12 Park Street, Kolkata 700016",
        "45 Anna Salai, Chennai 600002",
        "78 Brigade Road, Bengaluru 560001",
        "90 Banjara Hills, Hyderabad 500034",
        "11 Marine Drive, Mumbai 400020",
        "23 Civil Lines, Jaipur 302006",
        "34 Mall Road, Shimla 171001",
        "56 Connaught Place, New Delhi 110001",
        "67 Hazratganj, Lucknow 226001",
        "89 Sector 17, Chandigarh 160017",
        "15 FC Road, Pune 411004",
        "27 Race Course Road, Coimbatore 641018",
        "38 Kankarbagh, Patna 800020",
        "49 GS Road, Guwahati 781005",
        "51 Ashram Road, Ahmedabad 380009",
        "62 Bada Bazaar, Indore 452001",
        "73 South Extension, New Delhi 110049",
        "84 Alkapuri, Vadodara 390007",
        "95 Saheed Nagar, Bhubaneswar 751007",
        "16 MI Road, Jaipur 302001"
    ]
    for i, (bname, b_addr) in enumerate(zip(benign_first_names[:benign_count], cities_and_streets[:benign_count]), start=1):
        full_name = f"{bname} Deshmukh"
        b_ph = f"9988{i:06d}"
        b_acc = f"50100{i:06d}"
        b_slip = generate_pdf(f"benign_{i}_slip.pdf", "SALARY STATEMENT", {
            "Name": full_name, "Phone": b_ph, "Account": b_acc, "Address": b_addr, "Net_Salary": "60,000"
        })
        create_case_in_db(db, full_name, b_ph, b_addr, [("salary_slip", b_slip)])

    db.close()
    print("[Generator] Successfully seeded all demo scenarios and generated synthetic documents!")

def main():
    parser = argparse.ArgumentParser(description="Synthetic KYC Document and Scenario Generator")
    parser.add_argument("--reset", action="store_true", help="Reset database tables before seeding")
    parser.add_argument("--benign-count", type=int, default=12, help="Number of benign applicants to seed (default 12)")
    args = parser.parse_args()
    seed_database(reset=args.reset, benign_count=args.benign_count)

if __name__ == "__main__":
    main()
