"""
Automated Demo Screenshot Capture Script using Playwright + System Edge.
Captures all required verification views into docs/screenshots/.
"""

import os
import sys
import time
import subprocess
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "data-generator"))

from backend.app.core.security import decrypt_value
from backend.app.db.database import SessionLocal
from backend.app.db.models import Case
from generate import seed_database
import uvicorn
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = PROJECT_ROOT / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
TAMPER_SCRIPT = PROJECT_ROOT / "data-generator" / "tamper_demo.py"

class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.config = uvicorn.Config("backend.main:app", host="127.0.0.1", port=8000, log_level="warning")
        self.server = uvicorn.Server(self.config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def main():
    print("1. Seeding fresh database scenarios...")
    seed_database(reset=True)

    db = SessionLocal()
    cases = db.query(Case).all()
    case_map = {}
    for c in cases:
        app_name = decrypt_value(c.applicant.name_encrypted) if c.applicant else ""
        case_map[app_name] = c.id
    db.close()

    print("Discovered Cases:")
    for name, cid in case_map.items():
        print(f"  {name}: {cid}")

    print("2. Starting background Uvicorn server...")
    server = ServerThread()
    server.start()
    time.sleep(2)

    base_url = "http://127.0.0.1:8000"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=EDGE_PATH, headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 950})

            # 1. Dashboard
            page.goto(f"{base_url}/ui")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(SCREENSHOTS_DIR / "dashboard.png"))
            print("Captured: dashboard.png")

            # 2. Clean Case (AUTO_CLEAR)
            clean_name = "Suresh Sharma" if "Suresh Sharma" in case_map else "Priya Sharma"
            if clean_name in case_map:
                page.goto(f"{base_url}/ui/cases/{case_map[clean_name]}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(SCREENSHOTS_DIR / "auto_clear.png"))
                print("Captured: auto_clear.png")

            # 3. Typo PAN Case (OFFICER_REVIEW)
            if "Amit Roy" in case_map:
                page.goto(f"{base_url}/ui/cases/{case_map['Amit Roy']}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(SCREENSHOTS_DIR / "officer_review.png"))
                print("Captured: officer_review.png")

            # 4. Blurry / Missing Case (DOC_ANALYSIS_DEGRADED)
            if "Rohit Verma" in case_map:
                page.goto(f"{base_url}/ui/cases/{case_map['Rohit Verma']}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(SCREENSHOTS_DIR / "doc_degraded.png"))
                print("Captured: doc_degraded.png")

            # 5. Name Mismatch Case
            if "Ramesh Kumar" in case_map:
                page.goto(f"{base_url}/ui/cases/{case_map['Ramesh Kumar']}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(SCREENSHOTS_DIR / "cross_doc.png"))
                print("Captured: cross_doc.png")

            # 6. Income Mismatch Case
            if "Manoj Patil" in case_map:
                page.goto(f"{base_url}/ui/cases/{case_map['Manoj Patil']}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(SCREENSHOTS_DIR / "income_mismatch.png"))
                print("Captured: income_mismatch.png")

            # 7. Forged Slip Case (ESCALATE)
            if "Vikram Singh" in case_map:
                page.goto(f"{base_url}/ui/cases/{case_map['Vikram Singh']}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(SCREENSHOTS_DIR / "escalate.png"))
                print("Captured: escalate.png")

            # 8. Fraud Ring Graph
            page.goto(f"{base_url}/ui/graph")
            time.sleep(2.0)  # allow vis.js physics to settle
            page.screenshot(path=str(SCREENSHOTS_DIR / "fraud_ring.png"))
            print("Captured: fraud_ring.png")

            # 9. Integrity Green
            page.goto(f"{base_url}/ui/integrity")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(SCREENSHOTS_DIR / "integrity_green.png"))
            print("Captured: integrity_green.png")

            # 10. Tamper demo
            print("3. Executing tamper demo...")
            subprocess.run([sys.executable, str(TAMPER_SCRIPT)], check=True)
            page.goto(f"{base_url}/ui/integrity")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(SCREENSHOTS_DIR / "integrity_red.png"))
            print("Captured: integrity_red.png")

            # 11. Restore demo
            print("4. Restoring ledger integrity...")
            subprocess.run([sys.executable, str(TAMPER_SCRIPT), "--restore"], check=True)
            page.goto(f"{base_url}/ui/integrity")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(SCREENSHOTS_DIR / "integrity_restored.png"))
            print("Captured: integrity_restored.png")

            browser.close()
            print("All 11 screenshots successfully captured!")
    finally:
        server.stop()
        server.join(timeout=3)

if __name__ == "__main__":
    main()
