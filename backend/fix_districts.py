"""
One-time script to normalize district strings in the DB to plain numbers.

"21st"                     -> "21"
"9th District"             -> "9"
"37th Senate District"     -> "37"
"34th and 27th"            -> "34, 27"
"59th, 67th, and 68th"     -> "59, 67, 68"
"District 1"               -> "1"
"2nd SD"                   -> "2"
"""

import re
import sys
sys.path.append(".")
from database import SessionLocal
from models import City


def normalize(s):
    if not s:
        return None
    nums = re.findall(r'\d+', s)
    return ', '.join(nums) if nums else None


def main():
    db = SessionLocal()
    try:
        cities = db.query(City).all()
        changed = 0
        for city in cities:
            sd = normalize(city.state_senate_district)
            ad = normalize(city.state_assembly_district)
            cd = normalize(city.congressional_district)

            if (sd != city.state_senate_district or
                    ad != city.state_assembly_district or
                    cd != city.congressional_district):
                print(f"{city.city_name}: SD '{city.state_senate_district}' -> '{sd}'  AD '{city.state_assembly_district}' -> '{ad}'  CD '{city.congressional_district}' -> '{cd}'")
                city.state_senate_district = sd
                city.state_assembly_district = ad
                city.congressional_district = cd
                changed += 1

        db.commit()
        print(f"\nDone. {changed}/{len(cities)} cities updated.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
