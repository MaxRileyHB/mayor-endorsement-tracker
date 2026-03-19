"""
Safely update insurance fields in the cities table WITHOUT touching any CRM data.

Fields updated per city (matched by city_name):
  - fair_plan_policies
  - fair_plan_exposure
  - wildfire_risk_tier

Fields NEVER touched:
  outreach_tier, outreach_status, notes, contacts, emails, mayor fields, last_contacted, drafts, etc.

Usage:
  py pipeline/update_insurance_data.py           # update insurance fields
  py pipeline/update_insurance_data.py --dry-run # print what would change, don't write
"""
import json
import sys
from pathlib import Path

# Allow running from either project root or pipeline/
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from database import SessionLocal
from models import City

PIPELINE_OUTPUT = Path(__file__).parent / "output" / "california_cities.json"


def normalize(name: str) -> str:
    """Lowercase, strip 'city of ' prefix, collapse whitespace."""
    n = name.lower().strip()
    if n.startswith("city of "):
        n = n[8:]
    return " ".join(n.split())


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("[DRY RUN] No changes will be written.")

    if not PIPELINE_OUTPUT.exists():
        print(f"ERROR: {PIPELINE_OUTPUT} not found — run merge_data.py first")
        sys.exit(1)

    with open(PIPELINE_OUTPUT, encoding="utf-8") as f:
        source = json.load(f)

    # Build lookup: normalized_name -> source record
    by_name = {normalize(r["city_name"]): r for r in source}
    print(f"Loaded {len(by_name)} cities from pipeline output")

    db = SessionLocal()
    try:
        cities = db.query(City).all()
        print(f"Found {len(cities)} cities in DB")

        updated = 0
        skipped = 0
        unmatched = []

        for city in cities:
            key = normalize(city.city_name)
            src = by_name.get(key)
            if src is None:
                unmatched.append(city.city_name)
                skipped += 1
                continue

            new_policies  = src.get("fair_plan_policies") or 0
            new_exposure  = src.get("fair_plan_exposure") or 0
            new_tier_name = src.get("wildfire_risk_tier") or "low"

            changed = (
                city.fair_plan_policies != new_policies  or
                city.fair_plan_exposure != new_exposure  or
                city.wildfire_risk_tier != new_tier_name
            )

            if not changed:
                skipped += 1
                continue

            if dry_run:
                print(
                    f"  {city.city_name}: "
                    f"policies {city.fair_plan_policies}->{new_policies}  "
                    f"exposure {city.fair_plan_exposure}->{new_exposure}  "
                    f"risk {city.wildfire_risk_tier}->{new_tier_name}"
                )
            else:
                city.fair_plan_policies = new_policies
                city.fair_plan_exposure = new_exposure
                city.wildfire_risk_tier = new_tier_name

            updated += 1

        if not dry_run:
            db.commit()
            print(f"\nCommitted. Updated: {updated}  Unchanged/skipped: {skipped}")
        else:
            print(f"\nDry run complete. Would update: {updated}  Unchanged/skipped: {skipped}")

        if unmatched:
            print(f"\nUnmatched DB cities ({len(unmatched)}) — no pipeline record found:")
            for name in unmatched[:20]:
                print(f"  {name}")
            if len(unmatched) > 20:
                print(f"  ... and {len(unmatched) - 20} more")

    finally:
        db.close()


if __name__ == "__main__":
    main()
