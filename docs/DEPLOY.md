# Deployment Guide: Render (Free Tier) & Neon (Free PostgreSQL)

This guide provides exact click-by-click instructions to deploy the **Intelligent KYC & Loan Document Verification Platform** to Render's free tier with Neon free PostgreSQL for an always-available, $0-cost public demonstration.

---

## Architecture Overview for Render Free Tier

| Component | Technology | Rationale on Free Tier |
|---|---|---|
| **Web Service** | FastAPI + Uvicorn (`--workers 1`) | Runs within Render 512 MB memory boundary |
| **ML Analysis** | In-process Python (`ML_MODE=inprocess`) | Consolidates backend + CV/PDF analysis into a single service |
| **Database** | Neon Serverless PostgreSQL | Always-available, free PostgreSQL that does not expire after 30 days |
| **File Storage** | Database BYTEA (`STORAGE_BACKEND=db`) | Persistent across Render container restarts (no lost files) |
| **Auto-Seeding** | In-process generator (`SEED_ON_START=true`) | Instantly seeds all 7 demo scenarios on empty database |

---

## Step 1: Create Free Neon PostgreSQL Database

1. Open [https://neon.tech](https://neon.tech) and sign up / sign in (GitHub authentication supported).
2. Click **Create Project**:
   - **Project Name:** `mega-project-kyc`
   - **Postgres Version:** `16`
   - **Region:** `Asia Pacific (Singapore)` *(matches Render service region for low latency)*
3. Click **Create Project**.
4. On the project dashboard, locate the **Connection Details** widget:
   - Ensure the connection type dropdown is set to **Pooled connection**.
   - Copy the connection string. It has the format:
     ```text
     postgres://neondb_owner:password@ep-cool-sample-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
     ```
   *(Keep this connection string ready for Step 2; the platform automatically normalizes it to SQLAlchemy syntax).*

---

## Step 2: Deploy to Render via Blueprint

1. Open [https://dashboard.render.com](https://dashboard.render.com) and log in.
2. Click **New +** (top right) &rarr; Select **Blueprint**.
3. Connect your GitHub repository:
   - Select `Shruti-Asgekar/Mega-Project` (or enter `https://github.com/Shruti-Asgekar/Mega-Project`).
   - Branch: `main`.
4. Render will read `render.yaml` automatically and display the blueprint parameters.
5. In the prompted environment variable:
   - **`DATABASE_URL`**: Paste your Neon connection string from Step 1.
6. Click **Apply**.
7. Render will provision the web service, build the Python 3.11 environment, install dependencies from `requirements.txt`, and start the service with Uvicorn.

---

## Step 3: Verify Public Deployment

Once the build finishes and shows **Live**:

1. Click the service URL: `https://<service-name>.onrender.com/ui`
2. **Dashboard**: Observe seeded cases with trust score badges (`AUTO_CLEAR`, `OFFICER_REVIEW`, `ESCALATE`).
3. **Fraud Graph**: Navigate to `/ui/graph` to interact with the 4-node syndicate ring.
4. **Ledger Integrity**: Navigate to `/ui/integrity`:
   - Click **Verify Integrity** &rarr; Green status banner displays.
   - Click **Simulate Tampering (Flip 1 Byte)** &rarr; Red tamper alert highlights block alteration.
   - Click **Restore Original** &rarr; Ledger returns to verified green status.
5. **API Health**: Verify `https://<service-name>.onrender.com/api/health` returns HTTP 200 with `storage_mode: db`.

---

## Step 4: Optional Keep-Alive Monitor (UptimeRobot)

Render free web services enter sleep mode after 15 minutes of inactivity. The initial cold start takes approximately 30–50 seconds.

To keep the demo service awake:
1. Create a free account at [https://uptimerobot.com](https://uptimerobot.com).
2. Click **Add New Monitor**:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `Mega-Project KYC Demo`
   - **URL:** `https://<service-name>.onrender.com/api/health`
   - **Monitoring Interval:** Every `5 minutes`
3. Click **Create Monitor**.
*(Render provides 750 free instance hours per calendar month, which accommodates one continuously running service).*

---

## Troubleshooting Reference

| Symptom | Likely Root Cause | Solution |
|---|---|---|
| **Build fails during pip install** | Missing binary wheel or compiler | `requirements.txt` specifies `opencv-python-headless` and `psycopg2-binary`. Ensure Python 3.11 is selected via `.python-version`. |
| **500 Internal Error / DB Connection Refused** | Missing `sslmode=require` or sleeping Neon compute | The application automatically appends `sslmode=require` and retries connections 5 times with 3s backoff. Verify the database credentials in Neon. |
| **Empty Dashboard (No Cases)** | `SEED_ON_START` was false on initial boot | Call `POST /api/demo/reseed` with header `X-Demo-Key: <DEMO_ADMIN_KEY>`, or set `SEED_ON_START=true` in Render environment and restart. |
| **Ledger shows red after container restart** | Documents stored exclusively on ephemeral filesystem | Ensure `STORAGE_BACKEND=db`. In DB mode, document payloads are preserved in PostgreSQL `document_blobs`. |
| **Initial request times out (>50s)** | Render free-tier cold start | Wait 45 seconds for container allocation; subsequent page transitions respond in <200ms. |
