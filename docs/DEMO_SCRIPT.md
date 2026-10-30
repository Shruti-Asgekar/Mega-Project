# 7-Minute Demo Script & Evaluator Walkthrough

This document outlines a step-by-step, 7-minute demonstration of the Intelligent KYC Verification & Anti-Fraud Platform.

---

## Preparation (30 seconds before demo)

1. Ensure the services are running:
   ```bash
   .\scripts\dev.ps1  # or ./scripts/dev.sh
   ```
2. Reset and seed all 7 synthetic demo scenarios:
   ```bash
   python data-generator/generate.py --reset
   ```
3. Open browser to **`http://localhost:8000/ui`**.

---

## Minute 1: System Overview & Dashboard Navigation

- **Action**: Land on `http://localhost:8000/ui`.
- **Highlights**:
  - Show the clean responsive dashboard listing applications.
  - Notice the **Trust Scores** (0 to 95) and **Routing Badges**:
    - `AUTO_CLEAR` (Green)
    - `OFFICER_REVIEW` (Amber)
    - `ESCALATE` (Red)
  - Point out that **all PII is strictly masked by default** across table views (`XXXX-XXXX-1234`, `XXXXXXX210`).

---

## Minute 2: Scenario 1 — Clean Application & Mandatory Consent (Auto-Clear)

- **Action**: Click on the first case (**Suresh Sharma**).
- **Highlights**:
  - Point to top header: **Trust Score: 95 / 100**, Route: **`AUTO_CLEAR`**.
  - Show the **Consent Record**: `"Consent given on 2026-10-30T... from IP 127.0.0.1 (v1.0)"`.
  - Highlight the passed green verification badges:
    - PAN format valid (`ABCPE1234F` - individual status verified).
    - Aadhaar Verhoeff checksum valid.
    - 100% cross-document match across Name, DOB, and Address.
    - PDF metadata clean (created via standard document generator, no editing software).

---

## Minute 3: Scenario 3 & 4 — Quality & Cross-Document Forensic Verification

- **Action**: Return to Dashboard, click on **Rohit Verma**.
  - **Result**: Trust score drops to **73**, Route: **`OFFICER_REVIEW`**.
  - Show the plain-English explanation at top:
    - `"Your salary slip is blurry (Laplacian variance 0.4 < 100.0). Bank statement missing."`
  - Explains why the loan cannot be automatically cleared and requests document re-upload.
- **Action**: Return to Dashboard, click on **Ramesh Kumar**.
  - **Result**: Cross-document verification flags **`NAME_MISMATCH`**.
  - Show explanation:
    - `"Name differs across documents: 'Ramesh Kumar' vs 'Rajesh Kumar' (86% match)."`
  - Demonstrates fuzzy RapidFuzz similarity detecting subtle name swaps while allowing small typographical tolerances.

---

## Minute 4: Scenario 5 — Income & Bank Statement Forensic Analysis

- **Action**: Return to Dashboard, click on **Manoj Patil**.
- **Highlights**:
  - View the **Income & Bank Statement Metrics Table**:
    - Declared Slip Net Salary: **₹70,000**
    - Bank Average Salary Credits: **₹50,000**
    - Deviation: **-28.6%** (exceeds 25% threshold -> flagged `INCOME_MISMATCH` Red).
    - Recurring EMIs detected: **2 active loans** (totaling ₹32,000/mo).
    - EMI Burden: **45.7%** (flagged `EMI_BURDEN_HIGH` Amber).
    - Bounced Payments: **1 ECS bounce** detected (flagged `BOUNCED_PAYMENTS` Amber).
  - Score drops to **49**, Route automatically switches to **`ESCALATE`**.

---

## Minute 5: Scenario 6 — Document Forgery & PDF Metadata Tampering

- **Action**: Click on **Vikram Singh**.
- **Highlights**:
  - Score: **0 / 100**, Route: **`ESCALATE`** (Red alert).
  - Show the dual forensic forgery triggers:
    1. **Metadata Tampering**: `"Document metadata indicates unauthorized modification software was used: photoshop."`
    2. **Arithmetic Manipulation**: `"Salary slip arithmetic mismatch: expected net ₹67,000 but found ₹72,000."` (₹75k gross - ₹8k deductions = ₹67k, but forged slip printed ₹72k).

---

## Minute 6: Scenario 7 — Interactive Bipartite Fraud Ring Graph

- **Action**: Click on the **Fraud Ring Graph** tab in the navigation bar (`http://localhost:8000/ui/graph`).
- **Highlights**:
  - Notice the **interactive NetworkX / Vis.js graph visualization**:
    - Embedded offline without external CDN dependencies.
    - Hovering over nodes shows masked details only (`XXXXXXX001`, `XXXXXX4455`).
  - Point to the **4-Member Red Cluster** in Noida:
    - **Vijay Syndicate 1**, **Ajay Syndicate 2**, **Sanjay Syndicate 3**, **Karan Syndicate 4** connected through shared phone numbers, bank accounts, and fuzzy address clustering (`Galaxy Apts, Sector 4, Noida`).
  - Contrast with the **20 Benign Applicants** rendered as disconnected grey singletons across different Indian cities (Kolkata, Chennai, Bengaluru, Hyderabad, etc.).

---

## Minute 7: Module 10 — Tamper-Evident Hash Chain & Live Bit-Flip Demo

- **Action**: Click on the **Ledger Integrity** tab (`http://localhost:8000/ui/integrity`).
- **Highlights**:
  - Status is **GREEN**: `"Ledger integrity verified across all 37 blocks."`
  - Show the table of chained blocks with sequential block numbers, SHA-256 file hashes, and parent hashes.
- **Action**: Open terminal and flip a single byte in a stored file:
  ```bash
  python data-generator/tamper_demo.py
  ```
- **Action**: Refresh the browser page (`http://localhost:8000/ui/integrity`):
  - Ledger immediately turns **RED**:
  - Alert banner: `"Physical document on disk has been modified or corrupted! Disk SHA-256 differs from ledger at Block #1."`
- **Action**: In terminal, run restore:
  ```bash
  python data-generator/tamper_demo.py --restore
  ```
- **Action**: Refresh browser page:
  - Ledger immediately turns back to **GREEN** (`"Ledger integrity verified across all 37 blocks."`).
