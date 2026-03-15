"""
Seed the database from california_cities.json (pipeline output).
Run AFTER merge_data.py has produced the final JSON.

Usage:
  py seed.py                    # full seed (clears existing data)
  py seed.py --check            # just print counts, don't seed
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent))
from database import SessionLocal, engine
from models import Base, City, ActivityLog

PIPELINE_OUTPUT = Path(__file__).parent.parent / "pipeline" / "output" / "california_cities.json"


def seed():
    if not PIPELINE_OUTPUT.exists():
        print(f"ERROR: {PIPELINE_OUTPUT} not found — run the pipeline first")
        sys.exit(1)

    with open(PIPELINE_OUTPUT, encoding="utf-8") as f:
        cities_data = json.load(f)

    print(f"Loaded {len(cities_data)} cities from {PIPELINE_OUTPUT}")

    # Drop and recreate tables to ensure schema is current
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(City).count()
        if existing > 0:
            print(f"Found {existing} existing cities — clearing and reseeding...")
            db.query(ActivityLog).delete()
            db.query(City).delete()
            db.commit()

        field_map = {
            "city_name": "city_name",
            "county": "county",
            "population": "population",
            "incorporated_date": "incorporated_date",
            "mayor": "mayor",
            "mayor_pro_tem": "mayor_pro_tem",
            "previous_mayor": "previous_mayor",
            "mayor_needs_verification": "mayor_needs_verification",
            "council_members": "council_members",
            "city_manager": "city_manager",
            "city_clerk": "city_clerk",
            "city_attorney": "city_attorney",
            "city_address": "city_address",
            "city_phone": "city_phone",
            "city_fax": "city_fax",
            "city_website": "city_website",
            "city_email": "city_email",
            "office_hours": "office_hours",
            "congressional_district": "congressional_district",
            "state_senate_district": "state_senate_district",
            "state_assembly_district": "state_assembly_district",
            "fair_plan_policies": "fair_plan_policies",
            "fair_plan_exposure": "fair_plan_exposure",
            "is_distressed_county": "is_distressed_county",
            "has_undermarketed_zips": "has_undermarketed_zips",
            "moratorium_fires": "moratorium_fires",
            "moratorium_active": "moratorium_active",
            "wildfire_risk_tier": "wildfire_risk_tier",
            "outreach_tier": "outreach_tier",
        }

        inserted = 0
        errors = 0
        for data in cities_data:
            try:
                kwargs = {}
                for src, dst in field_map.items():
                    if src in data and data[src] is not None:
                        kwargs[dst] = data[src]

                # Determine initial outreach_status
                if kwargs.get("city_email") or kwargs.get("city_phone"):
                    kwargs["outreach_status"] = "city_contact_only"
                else:
                    kwargs["outreach_status"] = "no_contact_info"

                city = City(**kwargs)
                db.add(city)
                inserted += 1

                if inserted % 100 == 0:
                    db.commit()
                    print(f"  {inserted}/{len(cities_data)} inserted...")

            except Exception as e:
                errors += 1
                print(f"  Error on {data.get('city_name', '?')}: {e}")

        db.commit()
        print(f"\nSeed complete: {inserted} cities inserted, {errors} errors")

        # Summary stats
        from sqlalchemy import func
        tiers = db.query(City.outreach_tier, func.count()).group_by(City.outreach_tier).all()
        print("Tier counts:", {t: c for t, c in tiers})
        flagged = db.query(City).filter(City.mayor_needs_verification == True).count()
        print(f"Mayor needs verification: {flagged}")

    finally:
        db.close()


if __name__ == "__main__":
    if "--check" in sys.argv:
        db = SessionLocal()
        print(f"Cities in DB: {db.query(City).count()}")
        db.close()
    else:
        seed()
