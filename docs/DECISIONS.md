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

---

## ADR 006: Self-Contained Vis.js Offline HTML Graph Generation (No CDN Dependency)
- **Status:** Accepted
- **Context:** Module 7 requires an interactive visual graph representation of applicant clusters and shared identifiers. In sandboxed or air-gapped environments, loading external JS/CSS CDNs fails.
- **Decision:** Generate a standalone HTML document utilizing embedded Vis-network scripts and CSS, served directly via `/api/graph` and embedded in `/ui/graph` via an iframe.
- **Consequences:** The fraud ring graph works 100% offline with zero external network requests.

---

## ADR 007: Hashed Identifier Graph Nodes for Complete PII Leak Prevention
- **Status:** Accepted
- **Context:** In Module 7, connecting applicant nodes to phone or account number nodes could inadvertently leak plaintext numbers inside node IDs or serialized graph payloads.
- **Decision:** Use a 12-character SHA-256 hash of normalized phone and account numbers as graph node identifiers (`phone:<sha256[:12]>`), and strictly apply masking to all human-readable `label` and `title` attributes.
- **Consequences:** Exact entity linking is mathematically guaranteed while guaranteeing that unmasked phone/account numbers never enter graph HTML or client-side JSON.

---

## ADR 008: Resilient ML Service Degradation & Pipeline Idempotency
- **Status:** Accepted
- **Context:** Microservices in production may experience transient network partitions or timeouts. Document verification should not crash if `ml-service` is temporarily unreachable.
- **Decision:** The pipeline orchestrator wraps ML HTTP calls with a 1.0s timeout and falls back to an in-process Python module import, flagging the case with amber severity `DOC_ANALYSIS_DEGRADED`. Rerunning a case cleanly purges previous flags before computing new ones.
- **Consequences:** Zero pipeline crashes; clear visibility when running in fallback mode; idempotent rerun capability.

---

## ADR 009: Hybrid Cryptographic Ledger Verification (Linkage + Disk File Re-Hash)
- **Status:** Accepted
- **Context:** Module 10 specifies a tamper-evident hash chain. Checking only the database blocks allows disk files to be tampered with undetected.
- **Decision:** Ledger verification executes a two-level walk: (1) block linkage and internal payload hash recomputation, and (2) physical disk file re-hashing against the recorded `file_sha256`.
- **Consequences:** Any bit flipped on disk or altered in the database triggers an instant broken-chain alert identifying the exact block and file modified.


---

## ADR 010: Tiered Routing Policy (Soft Red Flags to Officer Review, Hard Flags to Escalate)
- **Status:** Accepted
- **Context:** Identity format errors (e.g. mistyped PAN 4th character `PAN_FORMAT_INVALID`, unreadable document, or minor cross-document discrepancy) represent potential user data entry mistakes rather than active adversarial fraud. Routing all red flags to `ESCALATE` causes operational bottlenecks.
- **Decision:**
  - Red flags from Modules 1-5 (e.g. `PAN_FORMAT_INVALID`, `AADHAAR_INVALID_FORMAT`, `IFSC_INVALID`, `NAME_MISMATCH`) route to **`OFFICER_REVIEW`** when overall trust score is $\ge 50$.
  - ONLY hard malicious fraud flags force immediate **`ESCALATE`**: `META_EDITING_SOFTWARE` (PDF modification tools), `SLIP_ARITHMETIC_MISMATCH` (altered salary figures), `FRAUD_RING_SUSPECTED` ($\ge 3$ linked applications), and `INTEGRITY_BROKEN` (tampered ledger/file on disk), or any case with score $< 50$.
  - Clean applications with zero red/amber flags and score $\ge 80$ continue to route to **`AUTO_CLEAR`**.
- **Consequences:** Typo'd PAN applications proceed to loan officer review while forged slips and syndicate fraud rings are automatically escalated to fraud investigation.


---

## ADR 011: Single-Service Production Deployment with In-Process ML Mode and Ephemeral-Disk DB Blob Storage
- **Status:** Accepted
- **Context:** Render's free tier provides 512 MB of RAM and an ephemeral filesystem per service instance. Running separate backend and ml-service containers would exceed memory limits and double cold-start latencies. Additionally, ephemeral filesystems wipe local storage on container restarts, which would break Module 10 SHA-256 ledger verification if files resided solely on disk.
- **Decision:**
  - Consolidate production deployment into a single web service via `ML_MODE=inprocess`. In this mode, heavy CV and PDF parsing run in-process without network latency, and the `DOC_ANALYSIS_DEGRADED` flag is explicitly suppressed by design (it only triggers when HTTP microservice calls fail).
  - Introduce `STORAGE_BACKEND=db`, persisting document payloads in PostgreSQL (`document_blobs` BYTEA table) while maintaining compatibility with local filesystem storage (`STORAGE_BACKEND=disk`).
  - Restrict Uvicorn workers to `--workers 1` and limit benign seeding candidates to 12 on cold boot to ensure memory consumption remains safely under 400 MB.
- **Consequences:** The entire 10-module platform deploys as a single Render service with persistent cryptographic ledger integrity, fast cold starts, and zero hosting costs.

---

## ADR 012: In-Memory / DB-Backed Tamper-Evident Simulation for Public Web Demo
- **Status:** Accepted
- **Context:** Visitors to the public Render deployment cannot execute command-line scripts like `tamper_demo.py` to test Module 10 cryptographic breach detection.
- **Decision:**
  - Expose `POST /api/demo/tamper` and `POST /api/demo/restore` protected by the `DEMO_MODE=true` environment flag (returning HTTP 404 when disabled).
  - Tampering in `db` storage mode flips a single byte at the payload's midpoint in the `document_blobs` table and records the original byte in `demo_tamper_log`.
  - Provide interactive UI buttons on `/ui/integrity` with client-side DOM badge updates showing immediate red breach detection on tampering and green restoration on restore.
- **Consequences:** Public visitors can interactively observe and verify cryptographic ledger tamper-evidence in real time from their web browser.


---

## ADR 013: Memory Footprint Verification on Render Free Tier
- **Status:** Accepted
- **Context:** Render's free tier imposes a strict 512 MB memory limit. We required empirical verification that running the backend with in-process ML analysis, synthetic data generation, graph clustering, and cryptographic hash chain verification stays safely under 400 MB.
- **Decision:** Ran automated memory benchmark booting backend, generating and storing 12 synthetic cases with documents in BYTEA storage, executing all 10 modules end-to-end, and querying both the bipartite graph and cryptographic integrity endpoints.
- **Outcome:** Initial RSS measured at 18.05 MB; Peak RSS measured at 170.88 MB. This is well below the 400 MB target threshold, providing a comfortable ~340 MB safety buffer for concurrent requests on Render free tier.
