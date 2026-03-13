"""
Parse CDI distressed ZIP codes & counties list.
Output: output/cdi_distressed.json — {counties: [...], undermarketed_zips: [...]}
"""
import json
import re
import fitz  # PyMuPDF
from utils import DATA_DIR, OUTPUT_DIR, get_anthropic_client

def extract_text(path):
    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)

def parse_with_sonnet(raw_text):
    """Use Claude Sonnet to extract the structured lists from the CDI document."""
    client = get_anthropic_client()

    prompt = f"""This is text extracted from a California Department of Insurance (CDI) document listing:
1. Distressed counties (29 California counties designated as insurance-distressed)
2. Undermarketed ZIP codes (individual ZIP codes designated as undermarketed for residential property insurance)

Please extract both lists and return them as JSON in this exact format:
{{
  "counties": ["County Name 1", "County Name 2", ...],
  "undermarketed_zips": ["90001", "90002", ...]
}}

Only include the county name (no "County" suffix), and only 5-digit ZIP codes.

Here is the document text:
---
{raw_text[:15000]}
---"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text
    # Extract JSON from response
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        raise ValueError(f"No JSON found in Sonnet response:\n{text}")
    return json.loads(match.group())

def parse_cdi_distressed():
    path = DATA_DIR / "doi_distressed_counties_zip_codes.pdf"
    print(f"Extracting text from {path.name}...")
    raw_text = extract_text(path)
    print(f"Extracted {len(raw_text)} chars across the document")
    print("--- First 2000 chars ---")
    print(raw_text[:2000])
    print("---")

    # Counties are listed as numbered items: "1. Alpine\n2. Amador\n..."
    county_matches = re.findall(r'^\s*\d+\.\s+([A-Za-z][A-Za-z ]+?)\s*$', raw_text, re.MULTILINE)
    # Filter to known California county name patterns (drop any noise)
    county_matches = [c.strip() for c in county_matches if 2 <= len(c.strip()) <= 30]

    # ZIP codes: all CA ZIPs in the document, excluding CDI's office ZIP
    CDI_OFFICE_ZIPS = {"95814"}
    zip_matches = re.findall(r'\b(9[0-6]\d{3})\b', raw_text)
    zips = sorted(set(z for z in zip_matches if z not in CDI_OFFICE_ZIPS))

    print(f"\nRegex found: {len(county_matches)} counties, {len(zips)} ZIPs")
    return {"counties": county_matches, "undermarketed_zips": zips}

if __name__ == "__main__":
    result = parse_cdi_distressed()

    print(f"\nCounties ({len(result['counties'])}):")
    for c in result['counties']:
        print(f"  {c}")

    print(f"\nUndermarketed ZIPs ({len(result['undermarketed_zips'])}):")
    print(f"  {result['undermarketed_zips'][:20]}{'...' if len(result['undermarketed_zips']) > 20 else ''}")

    out = OUTPUT_DIR / "cdi_distressed.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved -> {out}")
