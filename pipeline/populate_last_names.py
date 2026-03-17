"""
Populate mayor_last_name for all cities using Haiku.

Skips cities with no mayor or an already-populated last name.
Sends names in batches to avoid rate limits.

Usage:
  py populate_last_names.py           # populate all missing
  py populate_last_names.py --redo    # repopulate all, even existing
"""
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from database import SessionLocal
from models import City
from utils import Progress, get_anthropic_client

BATCH_SIZE = 20  # names per API call


def extract_last_names_batch(names: list[str], client) -> list[str | None]:
    """
    Ask Haiku to extract last names for a batch of full names in one call.
    Returns a list of last names in the same order, or None for any it can't determine.
    """
    numbered = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names))
    prompt = f"""Extract the last name from each of the following people's full names. Reply with a numbered list in the same order, one last name per line, nothing else.

{numbered}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        lines = response.content[0].text.strip().splitlines()
        results = []
        for line in lines:
            # Strip leading "1. " / "1) " etc.
            cleaned = line.strip().lstrip("0123456789").lstrip(".").lstrip(")").strip()
            results.append(cleaned if cleaned else None)
        # Pad or trim to match input length
        while len(results) < len(names):
            results.append(None)
        return results[:len(names)]
    except Exception as e:
        print(f"  API error: {e}")
        return [None] * len(names)


if __name__ == "__main__":
    redo = "--redo" in sys.argv

    db = SessionLocal()
    try:
        if redo:
            cities = db.query(City).filter(City.mayor.isnot(None), City.mayor != "").order_by(City.id).all()
            print(f"Redo mode: repopulating {len(cities)} cities with mayors")
        else:
            cities = db.query(City).filter(
                City.mayor.isnot(None),
                City.mayor != "",
                (City.mayor_last_name.is_(None)) | (City.mayor_last_name == "")
            ).order_by(City.id).all()
            print(f"Populating last names for {len(cities)} cities (skipping already populated)")

        if not cities:
            print("Nothing to do.")
            sys.exit(0)

        client = get_anthropic_client()
        bar = Progress(len(cities), label="Last name extraction")
        done = 0
        errors = 0

        for i in range(0, len(cities), BATCH_SIZE):
            batch = cities[i: i + BATCH_SIZE]
            names = [c.mayor for c in batch]

            last_names = extract_last_names_batch(names, client)

            for city, last_name in zip(batch, last_names):
                if last_name:
                    city.mayor_last_name = last_name
                    done += 1
                else:
                    errors += 1
                    print(f"\n  Could not extract last name for: {city.city_name} — {city.mayor}")

            db.commit()
            bar.update(min(i + BATCH_SIZE, len(cities)), suffix=f"batch {i // BATCH_SIZE + 1}")

            if i + BATCH_SIZE < len(cities):
                time.sleep(0.5)  # gentle rate limiting

        bar.done()
        print(f"\nDone. Populated: {done}  |  Failed: {errors}")

    finally:
        db.close()
