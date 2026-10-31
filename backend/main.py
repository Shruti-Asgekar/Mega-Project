"""
FastAPI Backend Application Entrypoint.
Runs on port 8000 (or $PORT from environment).
Integrates Request-ID tracing, PII log scrubbing, global JSON error handlers,
static file serving, authentication, and asynchronous demo seeding.
"""

import os
import sys
import time
import uuid
import logging
import threading
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# Starlette compatibility
FastAPI.max_body_size = None

from backend.app.core import config
from backend.app.core.config import BACKEND_PORT, SEED_ON_START, DEMO_MODE, STORAGE_BACKEND, ML_MODE, IS_PRODUCTION
from backend.app.core.security import LogScrubbingFilter
from backend.app.core.auth import bootstrap_admin_user
from backend.app.db import init_db
from backend.app.db.database import SessionLocal
from backend.app.db.models import Case
from backend.app.api.routes import router as api_router
from backend.app.api.auth_routes import router as auth_router
from backend.app.api.ui_routes import ui_router

# Setup logger with PII scrubber
logger = logging.getLogger("kyc.backend")
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
handler.addFilter(LogScrubbingFilter())
root_logger.handlers = [handler]

def _run_background_seeder():
    """Runs database demo seeding asynchronously in background without blocking server startup."""
    try:
        # Never run background seeder during automated tests
        if "pytest" in sys.modules or os.environ.get("TESTING") == "1":
            return

        # Give Uvicorn 2 seconds to bind port and answer initial Render health checks
        time.sleep(2)
        if IS_PRODUCTION or not DEMO_MODE:
            print("[Startup:Background] Running in production/pilot mode: skipping demo seeding.", flush=True)
            return

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
    # 1. Initialize DB schema with retry and safe column migrations
    init_db()

    # 2. Bootstrap primary admin user if configured
    bootstrap_admin_user()

    # 3. Trigger non-blocking background seeding if demo mode enabled (not during tests)
    if SEED_ON_START and DEMO_MODE and not IS_PRODUCTION and "pytest" not in sys.modules and os.environ.get("TESTING") != "1":
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

# --------------------------------------------------------------------------
# Request-ID Middleware
# --------------------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = req_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response

# --------------------------------------------------------------------------
# Global Exception Handlers (Always JSON on /api/*)
# --------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", None)
    if request.url.path.startswith("/api/"):
        msg = exc.detail if isinstance(exc.detail, (str, dict)) else str(exc.detail)
        code = "HTTP_ERROR"
        if isinstance(exc.detail, dict):
            code = exc.detail.get("error", "HTTP_ERROR")
            msg = exc.detail.get("message", str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": code, "message": msg, "request_id": req_id}
        )
    # UI routes redirect to login if 401/403
    if exc.status_code == 401:
        return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)})

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", None)
    logger.error(f"[Req {req_id}] Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)

    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred. Please try again shortly.",
                "request_id": req_id
            }
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."}
    )

# --------------------------------------------------------------------------
# Static Assets Mount
# --------------------------------------------------------------------------
static_dir = Path(__file__).resolve().parent / "app" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/ui")

# --------------------------------------------------------------------------
# Register Routers
# --------------------------------------------------------------------------
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(api_router, prefix="/api", tags=["API"])
app.include_router(ui_router, tags=["Web UI"])

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", os.environ.get("BACKEND_PORT", 8000)))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, workers=1)
