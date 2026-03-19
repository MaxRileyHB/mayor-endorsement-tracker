"""
Parse FAIR Plan Residential Policies in Force (PIF) by ZIP code.
Output: output/fair_plan_pif.json — list of {zip, policies_fy25, ...}
"""
import json
import re
import fitz
import tabula
import pandas as pd
from utils import DATA_DIR, OUTPUT_DIR, get_anthropic_client

PDF_PATH = DATA_DIR / "fair_plan_pif_by_zip.pdf"

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
        for i, df in enumerate(dfs):
            print(f"  Table {i}: {df.shape} — cols: {list(df.columns)}")
        return dfs
    except Exception as e:
        print(f"  tabula failed: {e}")
        return None

def try_pymupdf_pages():
    print("Trying PyMuPDF text extraction (page by page)...")
    doc = fitz.open(str(PDF_PATH))
    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages_text.append(text)
        if i < 1:
            print(f"  Page {i+1} preview:\n{text[:500]}\n---")
    doc.close()
    print(f"  Extracted {len(pages_text)} pages")

    raw_out = OUTPUT_DIR / "fair_plan_pif_raw_text.json"
    with open(raw_out, "w", encoding="utf-8") as f:
        json.dump(pages_text, f, indent=2, ensure_ascii=False)
    print(f"  Raw text saved -> {raw_out}")

    return pages_text

def parse_pages_with_sonnet(pages_text):
    """Send each PDF page to Sonnet individually and aggregate results."""
    import time
    client = get_anthropic_client()
    all_rows = []

    print(f"  Sending {len(pages_text)} pages to Sonnet (1 page/call)...")

    for page_num, page_text in enumerate(pages_text):
        prompt = f"""This is one page from a California FAIR Plan Residential Policies in Force (PIF) report by ZIP code.
It has 5 years of policy count data.

Extract every ZIP code data row from this page. For each, return:
{{
  "zip": "90001",
  "county": "Los Angeles",
  "policies_fy25": 1234,
  "policies_fy24": 1100,
  "policies_fy23": 950,
  "policies_fy22": 800,
  "policies_fy21": 700
}}

Rules:
- zip: valid 5-digit string
- county: county name if visible on this page (may be a section header), else null
- policies_fy*: integer policy counts, null if missing
- Skip header rows, total/subtotal rows, page title rows
- Return ONLY a JSON array, no explanation, no code fences

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
                time.sleep(3)
                break
            except json.JSONDecodeError as e:
                print(f"  Page {page_num+1} JSON error: {e} — skipping")
                break
            except Exception as e:
                if "rate_limit" in str(e).lower():
                    wait = 30 * (attempt + 1)
                    print(f"  Rate limit hit — waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  Page {page_num+1} error: {e} — skipping")
                    break

    return all_rows

def normalize_tabula_results(dfs):
    """Try to find the ZIP/policy data in tabula output."""
    all_rows = []
    for df in dfs:
        if df.empty:
            continue
        # Look for a column that looks like ZIP codes
        zip_col = None
        for col in df.columns:
            sample = df[col].dropna().astype(str)
            zip_like = sample.str.match(r'^\d{5}$').sum()
            if zip_like > 5:
                zip_col = col
                break
        if zip_col is None:
            continue

        print(f"  Found ZIP column: '{zip_col}' in table with cols {list(df.columns)}")
        # Find numeric columns (policy counts)
        numeric_cols = []
        for col in df.columns:
            if col == zip_col:
                continue
            try:
                cleaned = df[col].astype(str).str.replace(',', '').str.replace(' ', '')
                pd.to_numeric(cleaned, errors='raise')
                numeric_cols.append(col)
            except Exception:
                # Try partial conversion
                converted = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
                if converted.notna().sum() > 5:
                    numeric_cols.append(col)

        print(f"  Numeric cols: {numeric_cols}")

        for _, row in df.iterrows():
            zip_val = str(row[zip_col]).strip()
            if not re.match(r'^\d{5}$', zip_val):
                continue
            entry = {"zip": zip_val}
            # Map up to 5 years of data — label by position (most recent first)
            year_labels = ["policies_fy25", "policies_fy24", "policies_fy23", "policies_fy22", "policies_fy21"]
            for i, col in enumerate(numeric_cols[:5]):
                label = year_labels[i] if i < len(year_labels) else f"col_{i}"
                try:
                    val = int(str(row[col]).replace(',', '').strip())
                    entry[label] = val
                except (ValueError, AttributeError):
                    entry[label] = None
            all_rows.append(entry)

    return all_rows

def extract_county_from_text(raw_text):
    """Build a zip->county map from the raw text where counties act as headers."""
    zip_county = {}
    current_county = None
    for line in raw_text.split('\n'):
        line = line.strip()
        # County headers are typically standalone county names
        county_match = re.match(r'^([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s*$', line)
        if county_match and len(line) < 40:
            current_county = county_match.group(1)
        zip_match = re.match(r'^(\d{5})', line)
        if zip_match and current_county:
            zip_county[zip_match.group(1)] = current_county
    return zip_county

if __name__ == "__main__":
    rows = None

    # tabula only captures ~850 rows on this PDF regardless of settings — skip it
    if False:
        dfs = try_tabula()
        if dfs:
            rows = normalize_tabula_results(dfs)
            print(f"tabula extracted {len(rows)} ZIP rows")

    # PyMuPDF + Sonnet (page by page)
    if not rows or len(rows) < 50:
        print("tabula insufficient, falling back to PyMuPDF + Sonnet (page by page)...")
        pages_text = try_pymupdf_pages()
        rows = parse_pages_with_sonnet(pages_text)
        print(f"Sonnet extracted {len(rows)} ZIP rows total")

    # Deduplicate by ZIP (keep highest policies_fy25 entry)
    by_zip = {}
    for row in rows:
        z = row.get("zip")
        if not z:
            continue
        existing = by_zip.get(z)
        if not existing or (row.get("policies_fy25") or 0) > (existing.get("policies_fy25") or 0):
            by_zip[z] = row
    rows = list(by_zip.values())

    total = sum((r.get("policies_fy25") or 0) for r in rows)
    print(f"\nTotal: {len(rows)} unique ZIP records")
    print(f"Total policies_fy25: {total:,}")
    print("Sample:", json.dumps(rows[:3], indent=2))

    out = OUTPUT_DIR / "fair_plan_pif.json"
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"Saved -> {out}")
