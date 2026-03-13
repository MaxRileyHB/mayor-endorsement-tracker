"""
Parse all 8 CDI moratorium bulletins to extract ZIP codes covered.
Output: output/moratoriums.json — list of {fire, date, status, zips: [...]}
"""
import json
import re
import fitz  # PyMuPDF
from utils import DATA_DIR, OUTPUT_DIR

MORATORIUM_FILES = [
    {
        "file": "Jan 2025 Fires.pdf",
        "fire": "Palisades/Eaton/Hurst/Lidia/Sunset/Woodley",
        "date": "2025-01-07",
        "status": "expired",  # Expired Jan 2026
    },
    {
        "file": "Hughes Fire.pdf",
        "fire": "Hughes",
        "date": "2025-01-07",
        "status": "expired",
    },
    {
        "file": "Franklin Fire.pdf",
        "fire": "Franklin",
        "date": "2025-06-18",
        "status": "active",
    },
    {
        "file": "Lightning Complex.pdf",
        "fire": "TCU September Lightning Complex",
        "date": "2025-09-19",
        "status": "active",
    },
    {
        "file": "Pack Fire.pdf",
        "fire": "Pack",
        "date": "2025-12-09",
        "status": "active",
    },
    {
        "file": "Gifford Fire.pdf",
        "fire": "Gifford",
        "date": "2025-12-23",
        "status": "active",
    },
    {
        "file": "Mountain Fire.pdf",
        "fire": "Mountain",
        "date": "2024-11-07",
        "status": "expired",
    },
    {
        "file": "Bear Fire.pdf",
        "fire": "Bear",
        "date": "2024-11-01",
        "status": "expired",
    },
]

def extract_zips_from_pdf(path):
    """Extract all 5-digit ZIP codes from a PDF."""
    doc = fitz.open(str(path))
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()

    # Find all 5-digit ZIP codes
    zips = re.findall(r"\b(\d{5})\b", full_text)
    # Filter to CA ZIPs (90000-96199), deduplicate, and exclude CDI's Sacramento office ZIP
    CDI_OFFICE_ZIPS = {"95814"}  # appears in every bulletin header — not a coverage ZIP
    ca_zips = []
    seen = set()
    for z in zips:
        if 90000 <= int(z) <= 96199 and z not in seen and z not in CDI_OFFICE_ZIPS:
            ca_zips.append(z)
            seen.add(z)

    return ca_zips

def parse_moratoriums():
    moratorium_dir = DATA_DIR / "Moratoriums"
    results = []

    for entry in MORATORIUM_FILES:
        path = moratorium_dir / entry["file"]
        if not path.exists():
            print(f"  MISSING: {entry['file']}")
            results.append({**entry, "zips": [], "error": "file not found"})
            continue

        zips = extract_zips_from_pdf(path)
        print(f"  {entry['fire']}: {len(zips)} ZIPs extracted")

        results.append({
            "fire": entry["fire"],
            "date": entry["date"],
            "status": entry["status"],
            "zips": zips,
        })

    return results

if __name__ == "__main__":
    print("Parsing moratorium bulletins...")
    results = parse_moratoriums()

    total_zips = sum(len(r["zips"]) for r in results)
    print(f"\nTotal: {len(results)} fires, {total_zips} ZIP codes")

    for r in results:
        print(f"  {r['fire']} ({r['status']}): {len(r['zips'])} ZIPs — {r['zips'][:5]}{'...' if len(r['zips']) > 5 else ''}")

    out = OUTPUT_DIR / "moratoriums.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved -> {out}")
