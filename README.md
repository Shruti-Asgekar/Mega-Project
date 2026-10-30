# Intelligent KYC & Loan Document Verification Platform with Fraud Ring Detection

An automated, privacy-preserving, enterprise-grade KYC and Loan Document Verification platform featuring 10 verification modules, cryptographic tamper-evident hash chaining, bipartite fraud ring detection, and automated policy routing.

---

## 1. System Architecture

```mermaid
flowchart TD
    subgraph Client ["Client Interfaces"]
        UI["Web UI / Rest API Client<br/>(Port 8000 & 5173)"]
    end

    subgraph Backend ["Backend Service (FastAPI :8000)"]
        Router["API & UI Router"]
        DB[("PostgreSQL 16 / SQLite Fallback<br/>(SQLAlchemy 2)")]
        Orch["Pipeline Orchestrator"]
        
        M1["M1: Field Validators<br/>(PAN, Aadhaar Verhoeff, IFSC, DOB)"]
        M3["M3: Masking & Consent<br/>(Fernet Encryption, PII Masking)"]
        M4["M4: Cross-Doc Verification<br/>(RapidFuzz Token Sort & Set Ratio)"]
        M5["M5: Income & Bank Analyzer<br/>(Recurring EMIs, Bounces, Credits)"]
        M7["M7: Fraud Ring Graph<br/>(NetworkX Bipartite Clustering)"]
        M8["M8: Explanation Engine<br/>(Jinja2 Plain-English Templates)"]
        M9["M9: Trust Score & Routing<br/>(0-100 Score, AUTO_CLEAR / ESCALATE)"]
        M10["M10: Hash Chain Ledger<br/>(SHA-256 Block Linking)"]
    end

    subgraph ML ["ML Microservice (FastAPI :8001)"]
        CV["M2: Blur Quality Detection<br/>(OpenCV Laplacian Variance)"]
        Forg["M6: Forgery Detection Lite<br/>(pikepdf Metadata, ELA Analysis)"]
        Ext["Extractor Engine<br/>(pdfplumber Text Layer / OCR)"]
    end

    UI -->|HTTP / Forms| Router
    Router --> DB
    Router --> Orch
    Orch -->|HTTP / In-Process Fallback| ML
    Orch --> M3 --> M1 --> CV --> M4 --> M5 --> Forg --> M7 --> M10 --> M8 --> M9
```

---

## 2. The 10 Verification Modules

| # | Module | Core Capability | Tech Stack | Key Flag Codes |
|---|---|---|---|---|
| **M1** | Field Validators | PAN regex & 4th char status, full 10x10 Verhoeff Aadhaar checksum, IFSC regex, DOB 18-100 calendar range | Python / Regex | `PAN_FORMAT_INVALID`, `AADHAAR_CHECKSUM_FAIL`, `IFSC_INVALID`, `DOB_INVALID` |
| **M2** | Quality & Completeness | OpenCV Laplacian variance blur scoring (threshold=100); text-layer detection; mandatory document set check | OpenCV / Python | `DOC_BLURRY`, `DOC_MISSING`, `DOC_QUALITY_OK` |
| **M3** | Masking & Consent | Fernet symmetric field encryption; automatic masking (`XXXX-XXXX-1234`); versioned consent records (timestamp, IP, text) | Fernet Cryptography | `CONSENT_REQUIRED`, `PII_MASKED` |
| **M4** | Cross-Document Verification | RapidFuzz token_sort_ratio for names, normalized exact/swapped-day DOB matching, token_set_ratio for addresses | RapidFuzz | `NAME_MISMATCH`, `DOB_MISMATCH`, `ADDRESS_MISMATCH` |
| **M5** | Income & Bank Statement Analyzer | Monthly credit grouping, salary credits keyword detection, recurring EMI pattern matching (>=2 months), EMI burden ratio, bounced payments | Pandas / Regex | `INCOME_MISMATCH`, `EMI_BURDEN_HIGH`, `BOUNCED_PAYMENTS` |
| **M6** | Forgery Detection (Lite) | PDF producer metadata inspection (Photoshop, Canva, Sejda, etc.), creation/mod date delta, slip component arithmetic, Error Level Analysis (ELA) | pikepdf / PIL | `META_EDITING_SOFTWARE`, `META_MODIFIED_AFTER_CREATED`, `SLIP_ARITHMETIC_MISMATCH`, `ELA_ANOMALY` |
| **M7** | Fraud Ring Graph | NetworkX bipartite graph linking applicants to hashed identifiers (phone, account, address clusters via RapidFuzz >=92); rendered with PyVis (Vis.js under the hood) in standalone offline HTML | NetworkX / PyVis (Vis.js) | `FRAUD_RING_SUSPECTED`, `SHARED_IDENTIFIER`, `NO_FRAUD_RING` |
| **M8** | Explanation Engine | Plain-English explanations generated from 40 Jinja2 templates for all flag codes with Indian Rupee (₹) digit grouping | Jinja2 | Generated plain-English sentences |
| **M9** | Trust Score & Smart Routing | Transparent 0-100 trust score with documented deduction matrix; tiered policy routing: `AUTO_CLEAR` (>=80, no red/amber), `OFFICER_REVIEW` (modules 1-5 red flags or score 50-79), `ESCALATE` (hard fraud flags or score <50) | Python Rule Matrix | `AUTO_CLEAR`, `OFFICER_REVIEW`, `ESCALATE` |
| **M10** | Cryptographic Hash Chain | SHA-256 sequential block ledger linking each document: SHA-256 of prev_hash + file_sha256 + doc_id + doc_type + timestamp. Tamper-evident disk re-hashing | Cryptography / SHA-256 | `INTEGRITY_VERIFIED`, `INTEGRITY_BROKEN` |

---

## 3. Environment Variables

All secrets and configuration are managed via `.env` (derived from `.env.example`):

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Runtime environment mode | `development` |
| `BACKEND_PORT` | Backend application port | `8000` |
| `ML_PORT` | ML microservice port | `8001` |
| `DATABASE_URL` | PostgreSQL connection URL (auto-falls back to SQLite `kyc.db`) | `postgresql://kyc_user:kyc_secret_pass@localhost:5432/kyc_db` |
| `FERNET_KEY` | Symmetric Fernet key for encrypting full PII in database | `kE9mYq8q5fQ2v8p_placeholder_key_must_be_32_bytes=` |
| `INTERNAL_API_KEY` | Shared secret header between backend and ml-service | `shared_internal_secret_key_placeholder` |
| `BLUR_THRESHOLD` | Laplacian variance threshold for blur detection | `100.0` |
| `RAPIDFUZZ_THRESHOLD` | Cross-document similarity threshold | `85.0` |
| `ADDRESS_CLUSTER_THRESHOLD`| Graph address clustering fuzzy match threshold | `92.0` |

---

## 4. Quick Start

### Option A: Local Scripts (No Docker Required)

On Windows (PowerShell):
```powershell
.\scripts\dev.ps1
```

On Linux / macOS (Bash):
```bash
chmod +x scripts/dev.sh
./scripts/dev.sh
```

The services will start at:
- Web Dashboard & UI: **http://localhost:8000/ui**
- Backend API Docs (Swagger): **http://localhost:8000/docs**
- ML Microservice Health: **http://localhost:8001/api/health**

### Option B: Docker Compose

```bash
docker-compose up --build
```

---

## 5. Seed Synthetic Demo Scenarios

Generate synthetic documents and populate the database with all 7 predefined test scenarios:

```bash
python data-generator/generate.py --reset
```

The script populates:
1. `clean_applicant` -> Suresh Sharma: Score 95, Route: **AUTO_CLEAR**
2. `typo_pan` -> Amit Roy: Invalid PAN format, Route: **ESCALATE**
3. `blurry_missing` -> Rohit Verma: Blurry salary slip + Missing bank statement, Route: **OFFICER_REVIEW**
4. `name_mismatch` -> Ramesh Kumar (Aadhaar) vs Rajesh Kumar (PAN): Match 86%, Flagged **NAME_MISMATCH**
5. `income_mismatch` -> Manoj Patil: Slip ₹70,000 vs Bank ₹50,000, 2 EMIs, 1 bounce, Route: **ESCALATE**
6. `forged_slip` -> Vikram Singh: Adobe Photoshop metadata + Arithmetic mismatch (₹75k - ₹8k != ₹72k), Score 0, Route: **ESCALATE**
7. `planted_fraud_ring` -> 4 syndicate members linked via shared phone, account, and address in Noida, flagged **FRAUD_RING_SUSPECTED**, plus 20 benign applicants across India.

---

## 6. Running Tests

Run the complete test suite across all 10 modules:

```bash
pytest backend/tests/ ml-service/tests/
```

Expected output: **56 passed** in < 25s.

---

## 7. Tamper-Evident Ledger Demo

Demonstrate physical file tamper detection using Module 10:

1. Verify initial clean ledger integrity:
   ```bash
   python -c "from backend.app.db.database import SessionLocal; from backend.app.modules.m10_hashchain import verify_chain; print(verify_chain(SessionLocal()))"
   ```
   *(Returns `valid: True`)*

2. Flip a single bit in a document file on disk:
   ```bash
   python data-generator/tamper_demo.py
   ```

3. Re-verify ledger integrity:
   *(Returns `valid: False`, identifying the tampered file and broken block)*

4. Restore file to pristine condition:
   ```bash
   python data-generator/tamper_demo.py --restore
   ```
   *(Returns `valid: True` across all blocks)*
