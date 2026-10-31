# Deployment Guide: Render Docker Runtime & Neon Serverless PostgreSQL

This guide provides instructions to deploy the **Intelligent KYC & Loan Document Verification Platform** to Render's free tier with Neon free PostgreSQL for an always-available, $0-cost public deployment.

---

## 1. Architecture Overview

| Component | Technology | Rationale on Free Tier |
| :--- | :--- | :--- |
| **Runtime** | Docker (`python:3.11-slim`) | Packages Tesseract OCR, English models, and Poppler utilities directly |
| **Web Service** | FastAPI + Uvicorn (`--workers 1`) | Runs safely within Render's 512 MB memory boundary |
| **ML Analysis** | In-process Python (`ML_MODE=inprocess`) | Consolidates backend + OCR + CV analysis into a single service |
| **Database** | Neon Serverless PostgreSQL | Always-available, free PostgreSQL that does not expire after 30 days |
| **File Storage** | Encrypted PostgreSQL BYTEA (`STORAGE_BACKEND=db`) | Persistent across Render container restarts (no lost files) |
| **Privacy Compliance** | DPDP Act + UIDAI Redaction | Full Aadhaar masked in memory; HMAC keyed fingerprinting |

---

## 2. Step 1: Create Free Neon PostgreSQL Database

1. Open [https://neon.tech](https://neon.tech) and sign up / sign in (GitHub authentication supported).
2. Click **Create Project**:
   - **Project Name:** `mega-project-kyc`
   - **Postgres Version:** `16`
   - **Region:** `Asia Pacific (Singapore)` *(matches Render service region for lowest latency)*
3. Click **Create Project**.
4. In the project dashboard, locate the **Connection Details** widget:
   - Ensure the connection type dropdown is set to **Pooled connection**.
   - Copy the connection string. It looks like:
     ```text
     postgres://neondb_owner:password@ep-sample-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
     ```

---

## 3. Step 2: Deploy to Render via Blueprint

1. Open [https://dashboard.render.com](https://dashboard.render.com) and log in.
2. Click **New +** (top right) &rarr; Select **Blueprint**.
3. Connect your repository: `https://github.com/Shruti-Asgekar/Mega-Project`.
4. Render detects `render.yaml` automatically:
   - **Service Name:** `mega-project-kyc`
   - **Runtime:** `docker`
   - **Region:** `Singapore`
   - **Plan:** `Free`
5. Supply Environment Variables:
   - `DATABASE_URL`: Paste the Neon connection string copied from Step 1.
   - `APP_ENV`: `production` (or `development`)
   - `DEMO_MODE`: `false` (for production pilot) or `true` (for demo with synthetic data)
   - `SEED_ON_START`: `false` (for clean database) or `true` (for auto-seeded demo)
   - `ADMIN_EMAIL`: `admin@kyc-verification.internal`
   - `ADMIN_PASSWORD`: Enter a strong password for initial admin login.
6. Click **Apply**.
   - Render builds the Docker image, installs Tesseract OCR and dependencies, and deploys the container.

---

## 4. Step 3: Transitioning from Demo to Pilot

When ready to switch from synthetic demo cases to a clean production pilot:

1. **Purge Demo Data:**
   Run the purge script against your Neon database:
   ```bash
   DATABASE_URL="postgres://neondb_owner:password@..." python scripts/purge_demo_data.py --yes
   ```
2. **Update Render Environment:**
   In Render Dashboard &rarr; Service &rarr; **Environment**:
   - `APP_ENV`: `production`
   - `DEMO_MODE`: `false`
   - `SEED_ON_START`: `false`
3. Click **Save Changes**. The service redeploys in protected pilot mode with zero demo data and privacy banners enabled.
