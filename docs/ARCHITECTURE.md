# System Architecture & Technical Specifications

## 1. System Overview

The Intelligent KYC & Loan Document Verification Platform is built with a resilient, modular microservice architecture designed to automate identity verification, document forensics, financial analysis, and anti-fraud syndicate detection.

```mermaid
flowchart TB
    subgraph ClientLayer ["Client Layer"]
        Browser["Modern Web Browser<br/>(Dashboard, Upload, Graph, Ledger UI)"]
        CLI["API Clients & Dev Scripts"]
    end

    subgraph BackendApp ["FastAPI Backend (:8000)"]
        API["REST & UI Endpoints"]
        Sec["Security & Masking Layer<br/>(Fernet Encryption & Sanitization)"]
        Orchestrator["Pipeline Orchestrator<br/>(Extraction -> M1-M10 -> Explainer -> Routing)"]
        
        subgraph InternalModules ["Backend Verification Modules"]
            M1["M1: Field Validators<br/>(Verhoeff, PAN, IFSC, DOB)"]
            M3["M3: Consent & Masking Engine"]
            M4["M4: RapidFuzz Cross-Doc Engine"]
            M5["M5: Income & Bank Statement Analyzer"]
            M7["M7: NetworkX Fraud Ring Bipartite Graph"]
            M8["M8: Jinja2 Plain-English Explainer"]
            M9["M9: Trust Score & Routing Engine"]
            M10["M10: SHA-256 Hash Chain Ledger"]
        end
        
        DBEngine["SQLAlchemy 2 Engine<br/>(PostgreSQL with automatic SQLite kyc.db fallback)"]
    end

    subgraph MLApp ["Stateless ML Microservice (:8001)"]
        BlurCV["M2: OpenCV Laplacian Variance Blur Scorer"]
        PikeMeta["M6: pikepdf Metadata & ELA Forgery Analyzer"]
        OCR["Text Layer & Tesseract OCR Extractor"]
    end

    subgraph DataStore ["Persistence Layer"]
        Storage["Private Document Store (/uploads)"]
        Database[("Relational Database")]
    end

    Browser -->|HTTP POST/GET| API
    CLI -->|HTTP Requests| API
    API --> Sec
    Sec --> Orchestrator
    Orchestrator --> InternalModules
    Orchestrator -.->|HTTP or Resilient In-Process Fallback| MLApp
    InternalModules --> DBEngine
    DBEngine --> Database
    API --> Storage
```

---

## 2. Cryptographic Hash Chain Ledger (Module 10)

Every uploaded document is stamped into an immutable sequential SHA-256 block chain upon ingestion.

```mermaid
flowchart LR
    subgraph Genesis ["Block #0 (Genesis)"]
        G_Prev["prev_hash:<br/>0000...0000 (64 zeros)"]
    end

    subgraph Block1 ["Block #1 (Document 1)"]
        B1_Prev["prev_hash: G_Hash"]
        B1_Data["file_sha256<br/>document_id<br/>doc_type<br/>created_at_utc"]
        B1_Hash["record_hash:<br/>SHA256(prev || sha || id || type || time)"]
    end

    subgraph Block2 ["Block #2 (Document 2)"]
        B2_Prev["prev_hash: Block1.record_hash"]
        B2_Data["file_sha256<br/>document_id<br/>doc_type<br/>created_at_utc"]
        B2_Hash["record_hash:<br/>SHA256(prev || sha || id || type || time)"]
    end

    subgraph BlockN ["Block #N (Document N)"]
        BN_Prev["prev_hash: Block(N-1).record_hash"]
        BN_Data["file_sha256<br/>document_id<br/>doc_type<br/>created_at_utc"]
        BN_Hash["record_hash:<br/>SHA256(prev || sha || id || type || time)"]
    end

    Genesis --> Block1 --> Block2 --> BlockN
```

### Verification Walk
When verifying ledger integrity (`GET /api/integrity/verify` or UI Integrity tab):
1. **Linkage Check**: Confirms `block[i].prev_hash == block[i-1].record_hash`.
2. **Payload Recomputation**: Re-computes SHA-256 over stored block payload fields.
3. **Physical File Disk Check**: Reads physical file on disk, recomputes SHA-256, and compares with `file_sha256` recorded in the immutable block. Any byte alteration on disk immediately breaks verification and identifies the offending block.

---

## 3. Fraud Ring Bipartite Graph (Module 7)

```mermaid
graph TD
    subgraph RingCluster ["Planted Noida Fraud Ring (Cluster Size: 4)"]
        App1(("Vijay Syndicate 1"))
        App2(("Ajay Syndicate 2"))
        App3(("Sanjay Syndicate 3"))
        App4(("Karan Syndicate 4"))
        
        Phone1{"Phone: XXXXXXX001"}
        Phone2{"Phone: XXXXXXX002"}
        Acc1["Account: XXXXXX4455"]
        Acc2["Account: XXXXXX6655"]
        Acc3["Account: XXXXXX2211"]
        Addr1[["Address Cluster #1<br/>Galaxy Apts, Noida"]]

        App1 --- Phone1
        App2 --- Phone1
        App1 --- Acc1
        App2 --- Acc2
        App3 --- Acc2
        App3 --- Phone2
        App4 --- Phone2
        App4 --- Acc3
        App1 --- Addr1
        App2 --- Addr1
        App3 --- Addr1
        App4 --- Addr1
    end

    subgraph BenignApplicants ["Benign Applicants (Singletons Across India)"]
        Benign1(("Anand Deshmukh<br/>(Kolkata)"))
        Benign2(("Priya Deshmukh<br/>(Chennai)"))
        Benign3(("Deepak Deshmukh<br/>(Hyderabad)"))
    end
```

- **Graph Structure**: Bipartite graph connecting Applicant nodes with Identifier nodes (Phone, Account Number, Address Clusters).
- **Address Clustering**: Fuzzy grouping using RapidFuzz `token_set_ratio` >= 92.0.
- **Syndicate Policy**: Any connected component containing >= 3 applicant nodes triggers `FRAUD_RING_SUSPECTED` (Red severity, -35 score impact). 2 applicants sharing an identifier trigger `SHARED_IDENTIFIER` (Amber severity, -15 score impact).
- **Privacy Enforcement**: Network node labels and hover tooltips strictly mask all PII (e.g. `XXXXXXX001`, `XXXXXX4455`). Identifier node IDs in the underlying graph use cryptographic SHA-256 hashes of normalized strings so raw numbers never enter the HTML or client payloads.
