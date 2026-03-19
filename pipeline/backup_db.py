"""
Dump the entire cities table to a timestamped JSON backup file.

Usage:
  py pipeline/backup_db.py                    # saves to pipeline/backups/cities_YYYYMMDD_HHMMSS.json
  py pipeline/backup_db.py --out my_file.json # custom output path
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from database import SessionLocal
from models import City

BACKUP_DIR = Path(__file__).parent / "backups"


def city_to_dict(c: City) -> dict:
    return {col.name: getattr(c, col.name) for col in c.__table__.columns}


def main():
    # Resolve output path
    if "--out" in sys.argv:
        idx = sys.argv.index("--out")
        out_path = Path(sys.argv[idx + 1])
    else:
        BACKUP_DIR.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = BACKUP_DIR / f"cities_{ts}.json"

    db = SessionLocal()
    try:
        cities = db.query(City).order_by(City.id).all()
        data = [city_to_dict(c) for c in cities]
    finally:
        db.close()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)  # default=str handles datetime/date

    print(f"Backed up {len(data)} cities -> {out_path}")


if __name__ == "__main__":
    main()
