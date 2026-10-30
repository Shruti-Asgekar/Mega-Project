"""
Synthetic Document Generator for Baseline Document Classifier Training & Testing.
Generates realistic, clearly synthetic texts and document representations for:
- AADHAAR
- PAN
- SALARY_SLIP
- BANK_STATEMENT
- OTHER (Bills, Receipts, Agreements)

All generated content is 100% synthetic and bears clear markers.
"""

import os
import random
import json
from datetime import datetime, timedelta
from faker import Faker

fake = Faker('en_IN')
Faker.seed(42)
random.seed(42)

WATERMARK = "SYNTHETIC SAMPLE - FOR DEMO ONLY"

def generate_verhoeff_aadhaar():
    """Generates a valid 12-digit Aadhaar number with Verhoeff checksum."""
    d = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    ]
    p = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]
    ]
    inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]

    # First digit 2-9 per UIDAI rules
    first_digit = str(random.randint(2, 9))
    other_10 = "".join([str(random.randint(0, 9)) for _ in range(10)])
    num11 = first_digit + other_10

    c = 0
    reversed_digits = [int(x) for x in reversed(num11)]
    for i, digit in enumerate(reversed_digits):
        c = d[c][p[(i + 1) % 8][digit]]
    checksum = inv[c]
    full_aadhaar = num11 + str(checksum)
    return full_aadhaar

def generate_pan_number():
    """Generates standard Indian PAN format: 5 letters, 4 digits, 1 letter."""
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    fourth = random.choice(["P", "C", "H", "F", "A", "T", "B", "L", "J", "G"])
    prefix = "".join(random.choices(letters, k=3)) + fourth + random.choice(letters)
    digits = f"{random.randint(1000, 9999):04d}"
    last = random.choice(letters)
    return f"{prefix}{digits}{last}"

def generate_aadhaar_text():
    name = fake.name()
    dob = fake.date_of_birth(minimum_age=19, maximum_age=65).strftime("%d/%m/%Y")
    gender = random.choice(["Male", "Female", "Transgender"])
    aadhaar_num = generate_verhoeff_aadhaar()
    formatted_aadhaar = f"{aadhaar_num[:4]} {aadhaar_num[4:8]} {aadhaar_num[8:]}"
    address = fake.address().replace("\n", ", ")
    
    templates = [
        f"""GOVERNMENT OF INDIA
UNIQUE IDENTIFICATION AUTHORITY OF INDIA
Enrollment No: {random.randint(1000,9999)}/{random.randint(10000,99999)}/{random.randint(10000,99999)}
To:
{name}
S/O {fake.name_male()}
Address: {address}
DOB: {dob}
Gender: {gender}
VID: {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)}
My Aadhaar, My Identity
{formatted_aadhaar}
Aadhaar is a proof of identity, not of citizenship.
Help: 1947 | www.uidai.gov.in
{WATERMARK}""",
        f"""भारत सरकार
Government of India
Unique Identification Authority of India (UIDAI)
Name: {name}
DOB: {dob}
लिंग / Gender: {gender}
आधार संख्या / Aadhaar Number:
{formatted_aadhaar}
मेरा आधार, मेरी पहचान
Address: {address}
Unique Identification Authority of India, Post Box No 1947, GPO Bangalore
{WATERMARK}""",
        f"""UIDAI E-Aadhaar Document
GOVERNMENT OF INDIA
Name: {name}
Father: {fake.name_male()}
DOB: {dob}
Gender: {gender}
Aadhaar No: {formatted_aadhaar}
Downloaded Date: {datetime.now().strftime("%d/%m/%Y")}
Generation Date: {(datetime.now() - timedelta(days=200)).strftime("%d/%m/%Y")}
Address: {address}
Official Identity Proof
{WATERMARK}"""
    ]
    return random.choice(templates)

def generate_pan_text():
    name = fake.name()
    father_name = fake.name_male()
    dob = fake.date_of_birth(minimum_age=19, maximum_age=65).strftime("%d/%m/%Y")
    pan_num = generate_pan_number()
    
    templates = [
        f"""INCOME TAX DEPARTMENT
GOVT. OF INDIA
PERMANENT ACCOUNT NUMBER CARD
PAN: {pan_num}
Name: {name}
Father's Name: {father_name}
Date of Birth: {dob}
Signature
Authorized Signatory
Income Tax Department, National Securities Depository Limited
{WATERMARK}""",
        f"""आयकर विभाग
INCOME TAX DEPARTMENT
GOVERNMENT OF INDIA
Permanent Account Number: {pan_num}
{name}
{father_name}
{dob}
Card Issue Date: {(datetime.now() - timedelta(days=600)).strftime("%d/%m/%Y")}
QR Code Encrypted Information
{WATERMARK}""",
        f"""Govt of India - Income Tax Department
PAN Card Verification Slip
Permanent Account Number: {pan_num}
Holder Name: {name}
Parent Name: {father_name}
DOB: {dob}
Status: INDIVIDUAL
Category: RESIDENT
{WATERMARK}"""
    ]
    return random.choice(templates)

def generate_salary_slip_text():
    company = fake.company()
    emp_name = fake.name()
    emp_id = f"EMP{random.randint(10000, 99999)}"
    designation = fake.job()
    month = random.choice(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])
    year = 2026
    
    basic = random.randint(25000, 80000)
    hra = int(basic * 0.4)
    conveyance = 1600
    special_allowance = random.randint(5000, 20000)
    gross = basic + hra + conveyance + special_allowance
    
    pf = int(basic * 0.12)
    prof_tax = 200
    income_tax = int(gross * 0.08)
    deductions = pf + prof_tax + income_tax
    net = gross - deductions
    
    templates = [
        f"""{company.upper()} PRIVATE LIMITED
SALARY SLIP FOR THE MONTH OF {month.upper()} {year}
Employee Name: {emp_name}
Employee ID: {emp_id}
Designation: {designation}
Department: Information Technology
Date of Joining: 15/06/2021
Bank Account: {random.randint(10000000000, 99999999999)}
PF UAN: 100{random.randint(100000000, 999999999)}
Days Worked: 30 | LOP: 0
-------------------------------------------------------
EARNINGS                  AMOUNT   DEDUCTIONS            AMOUNT
-------------------------------------------------------
Basic Salary              {basic}    Provident Fund        {pf}
House Rent Allowance      {hra}    Professional Tax      {prof_tax}
Conveyance Allowance      {conveyance}    Income Tax (TDS)      {income_tax}
Special Allowance         {special_allowance}
-------------------------------------------------------
GROSS EARNINGS: Rs. {gross}
TOTAL DEDUCTIONS: Rs. {deductions}
NET SALARY PAYABLE: Rs. {net}
(In Words: Rupees {fake.words(nb=4)})
This is a computer generated salary statement and requires no signature.
{WATERMARK}""",
        f"""PAYSLIP - {month} {year}
Organization: {company}
Staff Member: {emp_name} | Code: {emp_id} | Role: {designation}
Gross Pay: INR {gross}
Basic Component: {basic}
HRA Component: {hra}
Other Allowances: {conveyance + special_allowance}
Deductions Total: INR {deductions}
PF Contribution: {pf}
TDS: {income_tax}
Net Remitted to Bank: INR {net}
Pay Date: 30/{random.randint(1,12):02d}/{year}
{WATERMARK}"""
    ]
    return random.choice(templates)

def generate_bank_statement_text():
    bank = random.choice(["State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank", "Punjab National Bank", "Kotak Mahindra Bank"])
    holder = fake.name()
    acc_no = f"{random.randint(1000000000, 9999999999)}"
    ifsc = f"{bank[:4].upper().replace(' ', '')}0{random.randint(100000, 999999)}"
    address = fake.address().replace("\n", ", ")
    
    balance = random.randint(40000, 150000)
    tx_lines = []
    current_date = datetime(2026, 4, 1)
    
    for i in range(12):
        current_date += timedelta(days=random.randint(3, 10))
        d_str = current_date.strftime("%d/%m/%Y")
        if i % 3 == 0:
            # Salary credit
            amount = random.randint(45000, 75000)
            balance += amount
            narration = f"ACH CREDIT SALARY BY {fake.company()[:15]}"
            tx_lines.append(f"{d_str}  {narration:<35}  -         {amount:>10.2f}  {balance:>12.2f}")
        elif i % 4 == 0:
            # EMI debit
            amount = random.randint(8000, 18000)
            balance -= amount
            narration = f"NACH DEBIT EMI {random.choice(['BAJAJ FIN', 'HDFC LOAN', 'KOTAK PRIME'])}"
            tx_lines.append(f"{d_str}  {narration:<35}  {amount:>10.2f}  -         {balance:>12.2f}")
        else:
            # General debit / UPI
            amount = random.randint(500, 4500)
            balance -= amount
            narration = f"UPI/{random.randint(10000000,99999999)}/{fake.first_name()}"
            tx_lines.append(f"{d_str}  {narration:<35}  {amount:>10.2f}  -         {balance:>12.2f}")
            
    tx_block = "\n".join(tx_lines)
    
    template = f"""{bank.upper()}
STATEMENT OF ACCOUNT FOR THE PERIOD 01/04/2026 TO 30/09/2026
Account Name: {holder}
Address: {address}
Account Number: {acc_no}
Account Type: Regular Savings Account
IFSC Code: {ifsc}
Branch: {fake.city()} Main Branch
Currency: INR
-----------------------------------------------------------------------------------------
DATE        NARRATION                             DEBIT(INR)  CREDIT(INR)  BALANCE(INR)
-----------------------------------------------------------------------------------------
{tx_block}
-----------------------------------------------------------------------------------------
Closing Balance as of Statement Date: INR {balance:.2f}
Total Credits: INR {random.randint(250000, 450000):.2f} | Total Debits: INR {random.randint(200000, 400000):.2f}
Registered Office: Banking Operations Center, Mumbai
{WATERMARK}"""
    return template

def generate_other_text():
    types = ["utility_bill", "rent_agreement", "medical_invoice", "miscellaneous_letter"]
    chosen = random.choice(types)
    
    if chosen == "utility_bill":
        return f"""MAHARASHTRA STATE ELECTRICITY DISTRIBUTION CO. LTD.
ELECTRICITY CONSUMPTION BILL FOR {random.choice(['JULY', 'AUGUST', 'SEPTEMBER'])} 2026
Consumer Name: {fake.name()}
Consumer Number: {random.randint(100000000000, 999999999999)}
Billing Unit: 4502 | Tariff: LT-1 Residential
Meter Number: MTR{random.randint(100000,999999)}
Units Consumed: {random.randint(120, 380)} kWh
Energy Charges: Rs. {random.randint(1200, 3500)}.00
Fuel Adjustment Charges: Rs. 185.00
Electricity Duty: Rs. 210.00
Net Amount Payable: Rs. {random.randint(1800, 4200)}.00
Due Date: 15/10/2026
{WATERMARK}"""
    elif chosen == "rent_agreement":
        return f"""RESIDENTIAL LEASE AGREEMENT
This agreement made on {datetime.now().strftime("%d day of %B, %Y")} between:
LESSOR: {fake.name()} residing at {fake.address().replace(chr(10), ', ')}
AND
LESSEE: {fake.name()} residing at {fake.address().replace(chr(10), ', ')}
The lessor agrees to let out premises situated at Flat No {random.randint(101,904)}, {fake.street_name()}, {fake.city()}.
Monthly Rent: Rs. {random.randint(15000, 35000)} per month payable by 5th of each month.
Security Deposit: Rs. {random.randint(50000, 100000)} refundable upon termination.
Lock-in Period: 11 months.
Signed and Delivered by Lessor and Lessee.
{WATERMARK}"""
    elif chosen == "medical_invoice":
        return f"""APOLLO CLINICAL DIAGNOSTICS & HOSPITAL
INVOICE / RECEIPT FOR INVESTIGATIONS
Bill No: INV-{random.randint(10000, 99999)} | Date: {datetime.now().strftime("%d/%m/%Y")}
Patient Name: {fake.name()} | Age: {random.randint(22,60)} | Gender: {random.choice(['M', 'F'])}
Doctor: Dr. {fake.name()} (MD General Medicine)
-------------------------------------------------------
Description                       Qty   Rate     Amount
-------------------------------------------------------
Complete Blood Count (CBC)         1    450.00   450.00
Lipid Profile Extensive            1    1200.00  1200.00
Fasting Blood Sugar                1    150.00   150.00
Ultrasound Abdomen                 1    1800.00  1800.00
-------------------------------------------------------
Total Payable: Rs. 3600.00
Payment Mode: UPI / Online
Authorized Signature
{WATERMARK}"""
    else:
        return f"""GENERAL CORRESPONDENCE / NOTICE
Reference: GEN-{random.randint(1000, 9999)}/2026
Date: {datetime.now().strftime("%d/%m/%Y")}
To Whomsoever It May Concern,
This is to certify that {fake.name()} has participated in the community civic development program
held between 01/01/2026 and 30/06/2026 in the municipal district of {fake.city()}.
The organization wishes the individual continued success in their future endeavors.
Issued by General Administration Department.
{WATERMARK}"""

def create_dataset(train_per_class=100, test_per_class=25):
    """Creates train and held-out test datasets."""
    generators = {
        "AADHAAR": generate_aadhaar_text,
        "PAN": generate_pan_text,
        "SALARY_SLIP": generate_salary_slip_text,
        "BANK_STATEMENT": generate_bank_statement_text,
        "OTHER": generate_other_text
    }
    
    train_data = []
    test_data = []
    
    for label, gen_func in generators.items():
        for _ in range(train_per_class):
            train_data.append({"text": gen_func(), "label": label})
        for _ in range(test_per_class):
            test_data.append({"text": gen_func(), "label": label})
            
    random.shuffle(train_data)
    random.shuffle(test_data)
    return train_data, test_data

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "corpus")
    os.makedirs(out_dir, exist_ok=True)
    
    print("Generating baseline synthetic corpus for 5 classes...")
    train, test = create_dataset(train_per_class=100, test_per_class=25)
    
    train_path = os.path.join(out_dir, "train.json")
    test_path = os.path.join(out_dir, "test.json")
    
    with open(train_path, "w", encoding="utf-8") as f:
        json.dump(train, f, indent=2)
    with open(test_path, "w", encoding="utf-8") as f:
        json.dump(test, f, indent=2)
        
    print(f"Dataset successfully created: {len(train)} train samples, {len(test)} held-out test samples.")
