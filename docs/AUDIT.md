# Phase 0 Architecture & Scaffold Audit

## 1. Executive Summary & Inventory
This audit documents the state of the `Mega-Project` repository prior to the implementation of the 10 Verification Modules.

### Component Breakdown
| Component | Language | Framework / Stack | Package Manager | Intended Entrypoint | Ports |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **backend** | Python 3.11 | FastAPI + SQLAlchemy 2 + Uvicorn | pip / pyproject | `backend/main.py` | 8000 |
| **ml-service** | Python 3.11 | FastAPI + OpenCV + pikepdf + pdfplumber | pip | `ml-service/main.py` | 8001 |
| **frontend** | React / TypeScript / HTML5 + Jinja2 Fallback | Next.js / Vite / Server-rendered Jinja2 | npm / static | `frontend/` or `backend/templates` (`/ui`) | 3000 / 5173 / 8000 |
| **data-generator** | Python 3.11 | ReportLab, Pillow, pikepdf, Faker | pip | `data-generator/generate.py` | CLI |
| **database** | SQL | PostgreSQL 16 (with SQLite auto-fallback) | Docker / SQLite | `kyc_db` / `kyc.db` | 5432 |

---

## 2. Docker & Infrastructure Configuration
From `docker-compose.yml` and `.env.example`:
- **Database (`postgres`)**: PostgreSQL 16 on port `5432`. User: `kyc_user`, Database: `kyc_db`.
- **Backend (`backend`)**: Exposed on port `8000` (bridged from internal `8000`), depends on `postgres`. Env vars: `PORT`, `DATABASE_URL`, `ML_SERVICE_URL=http://ml-service:8001`, `SECRET_KEY`, `FERNET_KEY`, `UPLOAD_DIR`.
- **ML Service (`ml-service`)**: Exposed on port `8001`. Env vars: `PORT=8001`, `X_INTERNAL_KEY`, `BLUR_THRESHOLD=100`.
- **Frontend (`frontend`)**: Next.js / Vite client on port `3000` / `5173`, calling backend API.

---

## 3. Existing Routes, Tests & CI Steps
### Scaffold State:
- **Git base commit**: `154bc6bd3c895cd08b6ddd83a62416ceef863f2c` (`chore: initial project scaffold`).
- **Backend**: An experimental untracked Express/Prisma scaffold existed without offline node_modules or database migrations. Per Master Prompt Rule 1 & Section 1/2/5/9, conforming to Python FastAPI + SQLAlchemy 2 stack with `pytest` suite ensures full compatibility with RapidFuzz, NetworkX, Fernet, Jinja2, and in-process ML fallback.
- **ML-Service**: Existing Flask app with basic OCR. Conformed to FastAPI endpoint specifications for Module 2 (blur detection), Module 6 (pikepdf metadata, salary slip arithmetic, ELA), and structured `ExtractedFields`.
- **CI Workflow (`.github/workflows/ci.yml`)**: Configured to run backend tests (`pytest`), ml-service tests (`pytest`), frontend lint/build checks.

---

## 4. Inter-Service Communication Contract
1. **Frontend -> Backend**:
   - REST API calls to `/api/cases`, `/api/cases/{id}`, `/api/graph`, `/api/integrity/verify`, `/api/health`.
   - Multipart file upload with mandatory consent payload.
2. **Backend -> ML Service**:
   - HTTP POST with `X-Internal-Key` to `http://ml-service:8001/analyze` (or modular `/blur`, `/forgery`, `/extract`).
   - Resilient client with timeout (5s) and automatic retry.
   - If ML-Service is down or unreachable: backend executes graceful in-process fallback import and emits amber `DOC_ANALYSIS_DEGRADED` flag without crashing.
3. **Database Fallback Protocol**:
   - Backend attempts connection to PostgreSQL.
   - If connection fails or `DATABASE_URL` specifies SQLite, smoothly activates SQLite (`kyc.db`) with identical schema and transactions.
