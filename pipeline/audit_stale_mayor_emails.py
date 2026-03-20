"""
Audit high-wildfire-risk cities for stale mayor emails — emails whose local part
contains a different person's name than the current mayor.

Workflow:
  1. Query high-risk cities that have been scraped and have at least one mayor email
  2. Send batches to Haiku — it flags emails whose local part clearly belongs to
     a different person (generic emails like mayor@, office@ are always OK)
  3. Dry-run prints what would be cleared; --apply actually clears + resets scrape status
  4. Prints the scrape_contacts.py command to re-scrape affected cities

Usage:
  py pipeline/audit_stale_mayor_emails.py            # dry run
  py pipeline/audit_stale_mayor_emails.py --apply    # clear bad emails + reset status
  py pipeline/audit_stale_mayor_emails.py --all-tiers  # check all tiers, not just high-risk
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from database import SessionLocal
from models import City
from utils import get_anthropic_client

BATCH_SIZE = 20
HAIKU = "claude-haiku-4-5-20251001"


def check_batch(batch: list[dict], client) -> list[dict]:
    """
    Ask Haiku to flag emails that clearly belong to a different person.
    Returns list of {id, work_email_ok, personal_email_ok}.
    """
    lines = []
    for i, entry in enumerate(batch, 1):
        parts = [f"Mayor: {entry['mayor']}"]
        if entry.get("work_email"):
            parts.append(f"work_email: {entry['work_email']}")
        if entry.get("personal_email"):
            parts.append(f"personal_email: {entry['personal_email']}")
        lines.append(f"{i}. " + " | ".join(parts))

    prompt = f"""For each entry, decide whether each email address belongs to the current mayor or clearly belongs to a DIFFERENT person.

Rules:
- Look at the LOCAL PART of the email (before the @) for a person's name
- If the local part contains a recognizable first or last name that does NOT match the current mayor's name → "wrong"
- Generic prefixes (mayor, office, info, clerk, admin, contact, hall, city) → always "ok"
- If the local part reasonably matches the mayor's first name, last name, initials, or a combination → "ok"
- If you cannot tell → "ok" (only flag when clearly wrong)

Return ONLY a JSON array, one object per entry, in the same order:
[{{"id": 1, "work_email_ok": true, "personal_email_ok": null}}, ...]

Use null for fields that weren't provided. true = ok/keep, false = clearly wrong person.

Entries:
{chr(10).join(lines)}"""

    try:
        resp = client.messages.create(
            model=HAIKU,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
            text = text.rsplit("```", 1)[0].strip()
        results = json.loads(text)
        # Re-index by position
        out = []
        for i, entry in enumerate(batch):
            r = results[i] if i < len(results) else {}
            out.append({
                "id": entry["id"],
                "work_email_ok": r.get("work_email_ok"),
                "personal_email_ok": r.get("personal_email_ok"),
            })
        return out
    except Exception as e:
        print(f"  Haiku error: {e}")
        # On error, assume all ok (safe default)
        return [{"id": e["id"], "work_email_ok": True, "personal_email_ok": True}
                for e in batch]


def main():
    apply = "--apply" in sys.argv
    all_tiers = "--all-tiers" in sys.argv

    if not apply:
        print("[DRY RUN] Pass --apply to actually clear emails and reset scrape status.\n")

    db = SessionLocal()
    try:
        q = db.query(City).filter(
            City.contact_scrape_status.in_(["completed", "partial"]),
            (City.mayor_work_email.isnot(None)) | (City.mayor_personal_email.isnot(None)),
            City.mayor.isnot(None),
        )
        if not all_tiers:
            q = q.filter(City.wildfire_risk_tier == "high")
        cities = q.order_by(City.outreach_tier, City.fair_plan_policies.desc()).all()

        scope = "all tiers" if all_tiers else "high wildfire risk"
        print(f"Found {len(cities)} {scope} cities with scraped mayor emails\n")

        if not cities:
            return

        client = get_anthropic_client()

        # Build batch input
        entries = [
            {
                "id": c.id,
                "city_name": c.city_name,
                "mayor": c.mayor,
                "work_email": c.mayor_work_email,
                "personal_email": c.mayor_personal_email,
            }
            for c in cities
        ]

        # Map id -> city object for quick lookup
        city_map = {c.id: c for c in cities}

        flagged_ids = []
        total_batches = (len(entries) + BATCH_SIZE - 1) // BATCH_SIZE

        for b in range(0, len(entries), BATCH_SIZE):
            batch = entries[b: b + BATCH_SIZE]
            batch_num = b // BATCH_SIZE + 1
            print(f"Checking batch {batch_num}/{total_batches} ({len(batch)} cities)...")
            results = check_batch(batch, client)

            for r in results:
                city = city_map[r["id"]]
                issues = []

                if r.get("work_email_ok") is False and city.mayor_work_email:
                    issues.append(f"work_email: {city.mayor_work_email}")
                if r.get("personal_email_ok") is False and city.mayor_personal_email:
                    issues.append(f"personal_email: {city.mayor_personal_email}")

                if issues:
                    print(f"  STALE  {city.city_name} (mayor: {city.mayor}) — {', '.join(issues)}")
                    flagged_ids.append(r["id"])
                    if apply:
                        if r.get("work_email_ok") is False:
                            city.mayor_work_email = None
                            city.mayor_work_email_source = None
                        if r.get("personal_email_ok") is False:
                            city.mayor_personal_email = None
                            city.mayor_personal_email_source = None
                        city.contact_scrape_status = "not_scraped"

            if b + BATCH_SIZE < len(entries):
                time.sleep(0.5)

        print(f"\n{'=' * 50}")
        print(f"Flagged: {len(flagged_ids)} cities with stale emails")

        if flagged_ids:
            id_str = ",".join(str(i) for i in flagged_ids)
            if apply:
                db.commit()
                print(f"Cleared bad emails and reset scrape status for {len(flagged_ids)} cities.")
                print(f"\nNow re-scrape them:")
                print(f"  py pipeline/scrape_contacts.py --city-ids {id_str}")
            else:
                print(f"\nRe-run with --apply to clear, then:")
                print(f"  py pipeline/scrape_contacts.py --city-ids {id_str}")
        else:
            print("No stale emails found — all emails match the current mayor.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
