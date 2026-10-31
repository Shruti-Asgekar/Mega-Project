# Privacy, Cryptographic Security & DPDP Compliance Architecture

## 1. Statutory Compliance Context

This platform processes Indian financial identity verification documents (Aadhaar, PAN, Salary Slips, Bank Statements) for credit underwriting and customer due diligence. It adheres strictly to:
- **Digital Personal Data Protection (DPDP) Act, 2023** (Act No. 22 of 2023)
- **UIDAI Regulations & Aadhaar Act (Amendment)** (Prohibition on storing raw 12-digit Aadhaar)
- **RBI Master Direction on KYC** (Customer Due Diligence and Tamper-evident Auditability)

---

## 2. Privacy-by-Design Architectural Safeguards

### 2.1. Zero Plaintext Aadhaar Persistence
- **In-Memory Redaction:** When Aadhaar documents are scanned or parsed, any detected 12-digit Aadhaar number is immediately masked to `XXXX-XXXX-1234` in application memory.
- **Keyed Cryptographic Fingerprint:** To detect duplicate applications and syndicate fraud rings across multiple loan cases without persisting the raw Aadhaar number, the platform computes a keyed HMAC:
  $$\text{Fingerprint} = \text{HMAC-SHA256}(K_{\text{salt}}, \text{Aadhaar Number})$$
  The raw 12-digit identity is mathematically irreversible from this fingerprint.
- **Log Scrubbing Filter:** A global logging filter (`LogScrubbingFilter`) intercepts all Python logging streams and redacts 12-digit Aadhaar patterns and PAN patterns before strings reach stdout, file handles, or observability collectors.

### 2.2. At-Rest Cryptographic Encryption
- **PII Storage:** Applicant telephone numbers, residential addresses, and bank account numbers are encrypted at rest using AES-128-CBC via Fernet keys (`FERNET_KEY`).
- **Encrypted Document Blobs:** Document payloads stored in the `document_blobs` PostgreSQL table are encrypted with Fernet keys prior to insertion (`DocumentBlob.data`).
- **Plaintext SHA-256 Anchoring:** The cryptographic ledger ledger computes SHA-256 over original unencrypted document bytes *before* storage encryption, enabling verification audits without exposing unencrypted document payloads.

### 2.3. Cryptographic Hash Chain & DPDP Tombstoning
Every verified document is sequenced into a cryptographic hash chain:
$$H_n = \text{SHA-256}(H_{n-1} \,\|\, \text{DocSHA256} \,\|\, \text{DocType} \,\|\, \text{Timestamp})$$
- Under DPDP statutory data retention guidelines (`RETENTION_DAYS`, default 30 days), document payloads are periodically purged.
- Rather than breaking the cryptographic linkage of subsequent blocks, purged records are marked as `is_tombstone = True` with `tombstone_reason = "DPDP_RETENTION_EXPIRY"`.
- Ledger verification verifies the header chain ($H_{n-1} \to H_n$) while acknowledging valid data minimisation deletions.

---

## 3. Role-Based Access Control (RBAC) Matrix

| Operation / Endpoint | Anonymous (Demo) | Applicant | Officer | Admin |
| :--- | :---: | :---: | :---: | :---: |
| Submit Application (`POST /api/cases`) | Yes (Demo) | Yes (Own) | Yes | Yes |
| View Case List (`GET /api/cases`) | All (Demo) | Own Cases Only | All Cases | All Cases |
| View Case Detail (`GET /api/cases/{id}`) | All (Demo) | Own Case Only | All Cases | All Cases |
| Trigger Pipeline Rerun (`POST /cases/{id}/run`) | Yes (Demo) | Own Case Only | All Cases | All Cases |
| Record Decision (`POST /api/cases/{id}/decision`) | No | No | Yes (Mandatory Note) | Yes |
| Inspect Fraud Graph (`GET /api/graph/data`) | Yes (Masked) | Yes (Masked) | Yes (Masked) | Yes (Masked) |
| Verify Ledger (`GET /api/integrity/verify`) | Yes | Yes | Yes | Yes |
| Inspect Audit Logs (`GET /api/admin/audit`) | No | No | No | Yes |
| Trigger Retention Sweep (`POST /admin/retention-sweep`) | No | No | No | Yes |
| Download Own Data (`GET /api/auth/download-data`) | No | Yes (Own DPDP Export) | Yes | Yes |
| Erasure / Delete Account (`POST /api/auth/delete-account`) | No | Yes (Own Record) | Yes | Yes |

---

## 4. Session Security & CSRF Defense
1. **Argon2id Password Hashing:** User passwords are encrypted with `argon2-cffi` (memory-hard, resistant to GPU/ASIC cracking). Weak and dictionary passwords are automatically rejected.
2. **Brute-Force Lockout:** Five consecutive failed authentication attempts automatically lock the target account for 15 minutes.
3. **Double-Submit CSRF Cookie:** State-changing requests (`POST`, `PUT`, `DELETE`) require matching `csrf_token` cookie and `X-CSRF-Token` headers.
4. **HttpOnly & SameSite=Lax:** Authentication session cookies are inaccessible to malicious JavaScript, mitigating XSS and session hijacking.
