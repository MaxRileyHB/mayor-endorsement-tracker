"""
Trigger an immediate full sync to Google Sheets.
Run once after setup, or any time you want to force a refresh.

Usage:
  py pipeline/initial_sheets_sync.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / "backend" / ".env")
except ImportError:
    pass

from database import SessionLocal
from sheets_sync import sync_to_sheets

if __name__ == "__main__":
    db = SessionLocal()
    try:
        sync_to_sheets(db)
    finally:
        db.close()
