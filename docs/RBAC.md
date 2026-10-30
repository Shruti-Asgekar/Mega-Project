# Role-Based Access Control (RBAC) Specification

## Module 4 Permission Matrix

| Action | Applicant | Officer | Manager | Fraud Analyst | Auditor | Admin |
|---|---|---|---|---|---|---|
| **Upload documents** | own only | no | no | no | no | no |
| **View own application** | yes | no | no | no | no | no |
| **View applications** | no | assigned | all | flagged | read-only | no |
| **See risk score and flags** | no | yes | yes | yes | yes | no |
| **Recommend decision** | no | yes | yes | no | no | no |
| **Final approve or reject** | no | no | yes | no | no | no |
| **Fraud graph** | no | no | yes | yes | yes | no |
| **Mark fraud or false positive** | no | no | yes | yes | no | no |
| **View audit logs** | no | no | no | no | yes | yes |
| **Manage users and roles** | no | no | no | no | no | yes |

## Security Rules

1. **Maker-Checker Hard Rule**:
   - A `FINAL` decision is rejected if the same user submitted the `RECOMMENDATION` on that application.
   - Even if a user holds both roles, separation of duties is strictly enforced.

2. **Admin Safeguards**:
   - Admin cannot approve loans.
   - Admin cannot grant themselves the `MANAGER` role.
   - All role modifications are recorded in the audit log.

3. **Backend Middleware Enforcement**:
   - `authenticate`: Validates short-lived JWT stored in httpOnly cookie; attaches `req.user`.
   - `authorize(...roles)`: Verifies role membership, rejecting with `401 Unauthorized` or `403 Forbidden`.
   - `ownsApplication`: Guards applicant routes so applicants cannot access records belonging to other users.

4. **Default Masking**:
   - Aadhaar numbers formatted as `XXXX-XXXX-1234`.
   - PAN numbers formatted as `ABCXX1234X`.
   - Sensitive fields masked across all staff views, API JSON responses, and audit logs.
