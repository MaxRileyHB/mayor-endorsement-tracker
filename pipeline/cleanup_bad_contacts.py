"""
Clean up placeholder/garbage contact data:
  - Emails containing asterisks (*)
  - Social handles that are "@popular" (or just "popular")

Run from the backend directory:
  py ../pipeline/cleanup_bad_contacts.py
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
from models import City

EMAIL_COLS   = ["mayor_work_email", "mayor_personal_email", "mayor_email", "city_email"]
SOCIAL_COLS  = ["mayor_instagram", "mayor_facebook", "mayor_other_social_handle"]

def is_bad_email(val):
    return val and "*" in val

def is_bad_social(val):
    if not val:
        return False
    normalized = val.strip().lstrip("@").lower()
    return normalized == "popular"

db = SessionLocal()
try:
    cities = db.query(City).all()
    email_cleared = []
    social_cleared = []

    for city in cities:
        for col in EMAIL_COLS:
            val = getattr(city, col)
            if is_bad_email(val):
                email_cleared.append(f"  {city.city_name} — {col}: {val!r}")
                setattr(city, col, None)

        for col in SOCIAL_COLS:
            val = getattr(city, col)
            if is_bad_social(val):
                social_cleared.append(f"  {city.city_name} — {col}: {val!r}")
                setattr(city, col, None)

    if email_cleared:
        print(f"Clearing {len(email_cleared)} bad emails:")
        print("\n".join(email_cleared))
    else:
        print("No bad emails found.")

    if social_cleared:
        print(f"\nClearing {len(social_cleared)} bad socials:")
        print("\n".join(social_cleared))
    else:
        print("No bad socials found.")

    if email_cleared or social_cleared:
        db.commit()
        print(f"\nDone. {len(email_cleared) + len(social_cleared)} fields cleared.")
    else:
        print("\nNothing to do.")

finally:
    db.close()
