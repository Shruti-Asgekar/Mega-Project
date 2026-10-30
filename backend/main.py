"""
FastAPI Backend Application Entrypoint.
Runs on port 8000 (or $PORT from environment).
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

# Starlette compatibility
FastAPI.max_body_size = None

from backend.app.core.config import BACKEND_PORT, SEED_ON_START, DEMO_MODE, STORAGE_BACKEND, ML_MODE
from backend.app.db import init_db
from backend.app.db.database import SessionLocal
from backend.app.db.models import Case
from backend.app.api.routes import router as api_router
from backend.app.api.ui_routes import ui_router

logger = logging.getLogger("kyc.backend")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

def _run_background_seeder():
    """Runs database demo seeding asynchronously in background without blocking server startup."""
    try:
        # Give Uvicorn 2 seconds to bind port and answer initial Render health checks
        time.sleep(2)
        db = SessionLocal()
        try:
            case_count = db.query(Case).count()
            if case_count == 0:
                print("[Startup:Background] Database is empty and SEED_ON_START=true. Executing synthetic demo seeder...", flush=True)
                data_gen_path = Path(__file__).resolve().parent.parent / "data-generator"
                if str(data_gen_path) not in sys.path:
                    sys.path.insert(0, str(data_gen_path))
                from generate import seed_database
                seed_database(reset=False, benign_count=2)
                print("[Startup:Background] Seeding complete! Database ready for demo visitors.", flush=True)
            else:
                print(f"[Startup:Background] Found {case_count} existing case(s). Skipping auto-seeding.", flush=True)
        except Exception as e:
            print(f"[Startup:Background] Error during background seeding: {e}", flush=True)
        finally:
            db.close()
    except Exception as e:
        print(f"[Startup:Background] Fatal background thread error: {e}", flush=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize DB schema with retry (fast)
    init_db()

    # 2. Trigger non-blocking background seeding so Uvicorn binds port immediately
    if SEED_ON_START:
        t = threading.Thread(target=_run_background_seeder, daemon=True)
        t.start()

    yield

app = FastAPI(
    title="Intelligent KYC & Loan Document Verification Platform",
    description="Automated 10-module verification, anti-fraud detection, and cryptographic hash chain ledger.",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Prevents leaking stack traces in public production responses."""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    if DEMO_MODE:
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal verification error occurred. Details recorded to system logs."}
        )
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/ui")

# Register Routers
app.include_router(api_router, prefix="/api", tags=["API"])
app.include_router(ui_router, tags=["Web UI"])

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", os.environ.get("BACKEND_PORT", 8000)))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, workers=1)
