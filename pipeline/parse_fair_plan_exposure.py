"""
Parse FAIR Plan Residential Exposure by Category (ZIP, County, Wildfire Risk, Distressed Status).
Output: output/fair_plan_exposure.json — list of {zip, county, exposure, wildfire_risk_tier, is_distressed_zip}
"""
import json
import re
import fitz
import tabula
import pandas as pd
from utils import DATA_DIR, OUTPUT_DIR, get_anthropic_client

PDF_PATH = DATA_DIR / "residential_policy_exposure_by_zip.pdf"

def try_tabula():
    print("Trying tabula-py extraction...")
    try:
        dfs = tabula.read_pdf(
            str(PDF_PATH),
            pages="all",
            multiple_tables=True,
            pandas_options={"dtype": str},
            lattice=True,
        )
        if not dfs or all(df.empty for df in dfs):
            dfs = tabula.read_pdf(
                str(PDF_PATH),
                pages="all",
                multiple_tables=True,
                pandas_options={"dtype": str},
                stream=True,
            )
        print(f"  tabula found {len(dfs)} tables")
        for i, df in enumerate(dfs[:5]):
            print(f"  Table {i}: {df.shape} — cols: {list(df.columns)}")
            print(df.head(3).to_string())
            print()
        return dfs
    except Exception as e:
        print(f"  tabula failed: {e}")
        return None

def try_pymupdf_text():
    print("Trying PyMuPDF text extraction...")
    doc = fitz.open(str(PDF_PATH))
    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages_text.append(text)
        if i < 1:
            print(f"  Page {i+1} preview:\n{text[:600]}\n---")
    doc.close()
    print(f"  Extracted {len(pages_text)} pages")
    return pages_text

def parse_pages_with_sonnet(pages_text):
    """Send PDF pages to Sonnet one at a time, return all rows."""
    import time
    client = get_anthropic_client()
    all_rows = []

    print(f"  Sending {len(pages_text)} pages to Sonnet (1 page/call)...")

    for page_num, page_text in enumerate(pages_text):
        prompt = f"""This is one page from a California FAIR Plan residential exposure report.
Each data row has: ZIP code, County, Is Distressed Area (0 or 1), Region, then dollar exposure amounts
broken into wildfire risk tiers (Low, Medium, High) and property types.

Extract every ZIP code data row from this page. For each, return:
{{
  "zip": "90001",
  "county": "Los Angeles",
  "is_distressed_zip": false,
  "exposure_low": 1000000,
  "exposure_medium": 500000,
  "exposure_high": 250000
}}

Rules:
- is_distressed_zip: true if Is Distressed Area = 1, false if 0
- exposure values: sum ALL property type dollar amounts within each risk tier (Low/Medium/High), as integers (strip $ and commas)
- Skip header rows, subtotal rows, page title rows
- Return ONLY a JSON array (no explanation, no code fences)

Page text:
---
{page_text}
---"""

        for attempt in range(3):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text.strip()
                text = re.sub(r'^```(?:json)?\s*', '', text)
                text = re.sub(r'\s*```$', '', text)
                page_rows = json.loads(text)
                print(f"  Page {page_num+1}/{len(pages_text)}: {len(page_rows)} rows")
                all_rows.extend(page_rows)
                time.sleep(3)  # ~3k tokens/page * 20 pages/min = 60k tokens/min; 3s gives headroom
                break
            except json.JSONDecodeError as e:
                print(f"  Page {page_num+1} JSON error: {e} — skipping")
                break
            except Exception as e:
                if "rate_limit" in str(e).lower():
                    wait = 30 * (attempt + 1)
                    print(f"  Rate limit hit — waiting {wait}s before retry...")
                    time.sleep(wait)
                else:
                    print(f"  Page {page_num+1} error: {e} — skipping")
                    break

    return all_rows

def normalize_tabula_results(dfs):
    all_rows = []
    for df in dfs:
        if df.empty:
            continue
        # Find ZIP column
        zip_col = None
        for col in df.columns:
            sample = df[col].dropna().astype(str)
            if sample.str.match(r'^\d{5}$').sum() > 5:
                zip_col = col
                break
        if zip_col is None:
            continue

        print(f"  ZIP column: '{zip_col}' | all cols: {list(df.columns)}")

        # Find exposure column (large numbers)
        exposure_col = None
        risk_col = None
        county_col = None
        distressed_col = None

        for col in df.columns:
            if col == zip_col:
                continue
            col_lower = str(col).lower()
            if "county" in col_lower:
                county_col = col
            elif "distress" in col_lower or "under" in col_lower:
                distressed_col = col
            elif "risk" in col_lower or "tier" in col_lower or "score" in col_lower:
                risk_col = col
            elif "exposure" in col_lower or "amount" in col_lower or "value" in col_lower:
                exposure_col = col

        for _, row in df.iterrows():
            zip_val = str(row[zip_col]).strip()
            if not re.match(r'^\d{5}$', zip_val):
                continue

            entry = {"zip": zip_val}

            if county_col:
                entry["county"] = str(row[county_col]).strip()

            if exposure_col:
                try:
                    entry["exposure"] = int(str(row[exposure_col]).replace(',', '').replace('$', '').strip())
                except (ValueError, AttributeError):
                    entry["exposure"] = None

            if risk_col:
                entry["wildfire_risk_tier"] = str(row[risk_col]).strip().lower()

            if distressed_col:
                val = str(row[distressed_col]).strip().lower()
                entry["is_distressed_zip"] = val in ("yes", "true", "1", "x", "distressed")

            all_rows.append(entry)

    return all_rows

def derive_risk_tier(row):
    """Determine wildfire risk tier from which tier has the most exposure."""
    low = row.get("exposure_low") or 0
    med = row.get("exposure_medium") or 0
    high = row.get("exposure_high") or 0
    total = low + med + high
    if total == 0:
        return "low"
    if high / total > 0.3:
        return "high"
    if med / total > 0.3:
        return "medium"
    return "low"

if __name__ == "__main__":
    rows = None

    # Tabula hangs on this PDF's complex multi-level headers — skip straight to Sonnet
    if False:
        dfs = try_tabula()
        if dfs:
            rows = normalize_tabula_results(dfs)
            print(f"tabula extracted {len(rows)} ZIP rows")

    if not rows or len(rows) < 50:
        print("tabula insufficient, falling back to PyMuPDF + Sonnet (page by page)...")
        pages_text = try_pymupdf_text()
        rows = parse_pages_with_sonnet(pages_text)
        print(f"Sonnet extracted {len(rows)} ZIP rows total")

    # Derive wildfire_risk_tier and compute total exposure
    for row in rows:
        row["wildfire_risk_tier"] = derive_risk_tier(row)
        row["exposure"] = (row.get("exposure_low") or 0) + (row.get("exposure_medium") or 0) + (row.get("exposure_high") or 0)

    # Deduplicate by ZIP (keep highest exposure entry)
    by_zip = {}
    for row in rows:
        z = row["zip"]
        if z not in by_zip or row["exposure"] > by_zip[z]["exposure"]:
            by_zip[z] = row
    rows = list(by_zip.values())

    print(f"\nTotal: {len(rows)} unique ZIP records")
    print("Sample:", json.dumps(rows[:3], indent=2))

    out = OUTPUT_DIR / "fair_plan_exposure.json"
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"Saved -> {out}")
