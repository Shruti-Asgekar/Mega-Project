"""
FastAPI Backend Application Entrypoint.
Runs on port 8000.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import BACKEND_PORT
from backend.app.db import init_db
from backend.app.api.routes import router as api_router
from backend.app.api.ui_routes import ui_router

# Initialize database tables on load
init_db()

app = FastAPI(
    title="Intelligent KYC & Loan Document Verification Platform",
    description="Automated 10-module verification, anti-fraud detection, and cryptographic hash chain ledger.",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(api_router, prefix="/api", tags=["API"])
app.include_router(ui_router, tags=["Web UI"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=BACKEND_PORT, reload=True)
