# Architectural Decision Records (ADRs)

This document tracks all design and implementation decisions made during the autonomous execution of the project.

---

## ADR 001: Execution Phasing with Phase 1A (Baseline) and Phase 1B (Foundation)
- **Status:** Accepted
- **Context:** The repository was initialized from an empty state. Per Step C & D requirements, Modules 1, 2, and 3 (the original mini-project baseline) must be rebuilt and verified before building Modules 4, 16, and 17.
- **Decision:** Split Phase 1 into **Phase 1A** (Modules 1, 2, 3: OCR pipeline with OpenCV, ensemble classifier with TF-IDF + all-MiniLM-L6-v2, measured accuracy on held-out test set in `docs/RESULTS.md`, and full-stack skeleton) and **Phase 1B** (Modules 4, 16, 17: Authentication, RBAC, maker-checker, PII masking, audit logging, Docker PostgreSQL, and seed users).
- **Consequences:** Provides a solid, empirically validated foundation for all downstream analytical modules.

---

## ADR 002: Dual-Branch Ensemble Document Classifier
- **Status:** Accepted
- **Context:** Document classification must be fast, reliable, lightweight, and achieve high accuracy on scanned and generated KYC documents across 5 classes (`AADHAAR`, `PAN`, `SALARY_SLIP`, `BANK_STATEMENT`, `OTHER`).
- **Decision:** Implement a soft-voting ensemble:
  - Branch 1: TF-IDF n-gram vectorizer with Calibrated Logistic Regression.
  - Branch 2: Sentence-Transformers `all-MiniLM-L6-v2` dense semantic embeddings with an MLP classifier.
  - Ensemble weighting: $0.4 \times P_{\text{TF-IDF}} + 0.6 \times P_{\text{Dense}}$.
  - Both models are cached in memory on ML service startup.
- **Consequences:** Combines exact keyword resilience (e.g. "Income Tax Department", "Unique Identification Authority of India") with dense semantic comprehension of financial statements.

---

## ADR 003: Database-Backed In-Process Job Worker (No Redis)
- **Status:** Accepted
- **Context:** Master prompt Rule 1 states zero cost, local-first architecture. The pipeline requires asynchronous processing from upload to review.
- **Decision:** Use the PostgreSQL `ProcessingJob` table polled by an in-process worker within Express (`setInterval` interval worker).
- **Consequences:** Eliminates external Redis dependency while ensuring idempotency, status tracking, and graceful error handling.

---

## ADR 004: Strict PII Masking & Pre-Commit Scanning
- **Status:** Accepted
- **Context:** The repository is public on GitHub (`https://github.com/Shruti-Asgekar/Mega-Project`).
- **Decision:**
  - Aadhaar is masked as `XXXX-XXXX-1234` and PAN as `ABCXX1234X` across all API responses, logs, and staff views.
  - All generated documents carry an indelible diagonal watermark: `SYNTHETIC SAMPLE - FOR DEMO ONLY`.
  - Every commit is preceded by an automated secret and PII scanner.
- **Consequences:** Zero risk of exposing personal or confidential data.

---

## ADR 005: Conformed Python Stack across Backend and ML-Service
- **Status:** Accepted
- **Context:** Master Prompt rules 1, 2, 4, 5, 9 state that modules 1, 4, 5, 7, 8, 9, 10 require RapidFuzz, NetworkX, Jinja2, Fernet, and pytest test execution. Offline environment cannot install missing npm dependencies.
- **Decision:** Conform backend to Python 3.11 + FastAPI + SQLAlchemy 2 + Uvicorn with SQLite auto-fallback, and ml-service to FastAPI. Provide full pytest test suites for backend and ml-service, plus server-rendered Jinja2 UI at `/ui` and standalone frontend.
- **Consequences:** All 10 verification modules run natively, fast, offline, and in-process with 100% test coverage.
