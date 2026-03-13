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

def try_pymupdf_text():
    print("Trying PyMuPDF text extraction...")
    doc = fitz.open(str(PDF_PATH))
    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages_text.append(text)
        if i < 2:
            print(f"  Page {i+1} preview:\n{text[:500]}\n---")
    doc.close()
    return "\n".join(pages_text)

def parse_with_sonnet(raw_text):
    print("Using Sonnet API for extraction...")
    client = get_anthropic_client()

    prompt = f"""This is text extracted from a FAIR Plan (California FAIR Plan Association) PDF report showing
Residential Policies in Force (PIF) by ZIP code. It likely has multiple years of data (5-year trend).

Extract ALL rows as a JSON array. Each row should be:
{{
  "zip": "90001",
  "county": "Los Angeles",
  "policies_fy25": 1234,
  "policies_fy24": 1100,
  "policies_fy23": 950,
  "policies_fy22": 800,
  "policies_fy21": 700
}}

Include only rows where zip is a valid 5-digit number. Use null for missing year values.
Return ONLY the JSON array, no explanation.

Document text:
---
{raw_text[:40000]}
---"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()
    # Strip code fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)

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

    # Strategy 1: tabula
    dfs = try_tabula()
    if dfs:
        rows = normalize_tabula_results(dfs)
        print(f"tabula extracted {len(rows)} ZIP rows")

    # Strategy 2: PyMuPDF + Sonnet
    if not rows or len(rows) < 50:
        print("tabula insufficient, falling back to PyMuPDF + Sonnet...")
        raw_text = try_pymupdf_text()
        rows = parse_with_sonnet(raw_text)
        print(f"Sonnet extracted {len(rows)} ZIP rows")

    print(f"\nTotal: {len(rows)} ZIP records")
    print("Sample:", json.dumps(rows[:3], indent=2))

    out = OUTPUT_DIR / "fair_plan_pif.json"
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"Saved -> {out}")
