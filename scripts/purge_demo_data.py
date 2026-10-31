"""
Safely purges synthetic demo data from the database to prepare for clean pilot runs.
Leaves administrative and auditor accounts intact.
Requires explicit --yes flag to execute.
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.app.db.database import SessionLocal, init_db
from backend.app.db.models import (
    Case, Applicant, Document, DocumentBlob, FlagModel, Consent,
    ChainRecord, DemoTamperLog, AuditLog, User
)

def purge_demo_data(confirm: bool = False):
    if not confirm:
        print("ERROR: Safety lock active. You must pass '--yes' to purge demo records.")
        sys.exit(1)

    init_db()
    db = SessionLocal()
    try:
        case_count = db.query(Case).count()
        appl_count = db.query(Applicant).count()
        doc_count = db.query(Document).count()
        blob_count = db.query(DocumentBlob).count()
        admin_count = db.query(User).count()

        print("==================================================")
        print("PURGING SYNTHETIC DEMO DATA")
        print("==================================================")
        print(f"Targeting {case_count} cases, {appl_count} applicants, {doc_count} documents, {blob_count} blobs.")
        print(f"Preserving {admin_count} registered user accounts.")

        db.query(DemoTamperLog).delete()
        db.query(FlagModel).delete()
        db.query(Consent).delete()
        db.query(ChainRecord).delete()
        db.query(DocumentBlob).delete()
        db.query(Document).delete()
        db.query(Case).delete()
        db.query(Applicant).delete()

        # Audit log the purge action
        db.add(AuditLog(
            action="DEMO_DATA_PURGED",
            details={"purged_cases": case_count, "purged_applicants": appl_count}
        ))

        db.commit()
        print("SUCCESS: Demo data successfully purged. Database ready for production pilot onboarding.")
        print("==================================================")
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to purge demo data: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge synthetic demo records from KYC database.")
    parser.add_argument("--yes", action="store_true", help="Explicit confirmation to proceed with purge.")
    args = parser.parse_args()

    purge_demo_data(confirm=args.yes)
