"""
Parse the California Roster — Cities & Towns PDF.
Three-step pipeline:
  1. PyMuPDF coordinate-based column split -> plaintext
  2. Split on city headers -> send chunks to Sonnet API for structured extraction
  3. DuckDuckGo mayor verification (run separately via verify_mayors.py)

Output: output/roster_cities.json — array of city objects
"""
import json
import re
import time
import fitz  # PyMuPDF
from utils import DATA_DIR, OUTPUT_DIR, get_anthropic_client, Progress

PDF_PATH = DATA_DIR / "cities_roster.pdf"

# ─────────────────────────────────────────────
# STEP 1: Column-aware text extraction
# ─────────────────────────────────────────────

def extract_two_column_text(pdf_path):
    """
    Extract text from a two-column PDF layout, preserving reading order.
    Writes both a debug plaintext file and returns the full text.
    """
    doc = fitz.open(str(pdf_path))
    all_text = []

    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict")["blocks"]
        page_width = page.rect.width
        midpoint = page_width / 2

        left_blocks = []
        right_blocks = []

        for block in blocks:
            if block["type"] != 0:  # skip non-text blocks
                continue
            # Use x0 of the block's bbox to assign to column
            x0 = block["bbox"][0]
            y0 = block["bbox"][1]
            # Gather all text in this block
            lines = []
            for line in block.get("lines", []):
                line_text = " ".join(span["text"] for span in line.get("spans", []))
                if line_text.strip():
                    lines.append(line_text.strip())
            if not lines:
                continue
            text = "\n".join(lines)

            if x0 < midpoint:
                left_blocks.append((y0, text))
            else:
                right_blocks.append((y0, text))

        # Sort each column top-to-bottom
        left_blocks.sort(key=lambda x: x[0])
        right_blocks.sort(key=lambda x: x[0])

        all_text.append(f"\n=== PAGE {page_num + 1} ===\n")
        for _, text in left_blocks:
            all_text.append(text)
        for _, text in right_blocks:
            all_text.append(text)

    doc.close()

    full_text = "\n".join(all_text)

    # Save plaintext for debugging
    debug_path = OUTPUT_DIR / "roster_raw_text.txt"
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"Raw text saved to {debug_path} ({len(full_text)} chars)")

    return full_text

# ─────────────────────────────────────────────
# STEP 2: Split into city chunks
# ─────────────────────────────────────────────

CITY_HEADER_PATTERN = re.compile(
    r'(?:^|\n)((?:City|Town)\s+of\s+[A-Z][^\n]+)',
    re.MULTILINE
)

def split_into_city_chunks(full_text):
    """Split the full plaintext into per-city chunks."""
    matches = list(CITY_HEADER_PATTERN.finditer(full_text))
    print(f"Found {len(matches)} city/town headers")

    chunks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        chunk_text = full_text[start:end].strip()
        city_header = match.group(1).strip()
        chunks.append({"header": city_header, "text": chunk_text})

    return chunks

# ─────────────────────────────────────────────
# STEP 3: Sonnet extraction per chunk
# ─────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are extracting structured data from California city roster entries.
Each entry contains contact information, officials, and legislative districts for one California city.
Extract all available fields and return valid JSON only — no explanation, no code fences."""

EXTRACTION_USER_PROMPT = """Extract all available fields from this California city roster entry and return as JSON:

{{
  "city_name": "",
  "county": "",
  "address": "",
  "phone": "",
  "fax": "",
  "website": "",
  "email": "",
  "office_hours": "",
  "mayor": "",
  "mayor_pro_tem": "",
  "council_members": [],
  "council_meeting_schedule": "",
  "city_attorney": "",
  "city_manager": "",
  "city_clerk": "",
  "police_chief": "",
  "fire_chief": "",
  "school_superintendent": "",
  "incorporated_date": "",
  "congressional_district": "",
  "state_senate_district": "",
  "state_assembly_district": ""
}}

Use null for any field not found. Return ONLY the JSON object.

City roster entry:
---
{chunk_text}
---"""

def extract_city_with_sonnet(client, chunk, chunk_num, total):
    """Send one city chunk to Sonnet and return parsed JSON."""
    prompt = EXTRACTION_USER_PROMPT.format(chunk_text=chunk["text"][:3000])

    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text.strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            data = json.loads(text)
            return data

        except json.JSONDecodeError as e:
            print(f"  [{chunk_num}/{total}] JSON error for '{chunk['header']}': {e}")
            return {"city_name": chunk["header"], "_parse_error": str(e), "_raw": chunk["text"][:500]}

        except Exception as e:
            if "rate_limit" in str(e).lower():
                wait = 30 * (attempt + 1)
                print(f"  Rate limit — waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  [{chunk_num}/{total}] API error for '{chunk['header']}': {e}")
                return {"city_name": chunk["header"], "_api_error": str(e)}

    return {"city_name": chunk["header"], "_error": "max retries exceeded"}

def extract_all_cities(chunks, save_interval=50):
    """Extract all city chunks, saving progress periodically."""
    client = get_anthropic_client()
    results = []
    errors = []

    # Check for partial progress
    progress_path = OUTPUT_DIR / "roster_progress.json"
    if progress_path.exists():
        with open(progress_path) as f:
            results = json.load(f)
        print(f"Resuming from {len(results)} previously extracted cities")
        chunks = chunks[len(results):]

    total = len(chunks) + len(results)
    print(f"Extracting {len(chunks)} remaining cities from {total} total...")
    print(f"Rate: ~24 cities/min  |  Saves every {save_interval} cities to roster_progress.json\n")

    bar = Progress(total, label="Roster extraction")
    bar.update(len(results), suffix="resuming..." if len(results) else "")

    for i, chunk in enumerate(chunks):
        chunk_num = len(results) + i + 1  # start_offset + loop index + 1
        # NOTE: use start_index + i + 1 for display (not len(results) which grows with i)
        display_num = (total - len(chunks)) + i + 1
        city_label = chunk["header"].replace("City of", "").replace("Town of", "").strip()

        data = extract_city_with_sonnet(client, chunk, display_num, total)

        if "_parse_error" in data or "_api_error" in data or "_error" in data:
            errors.append({"chunk_num": display_num, "header": chunk["header"], **data})
        else:
            results.append(data)

        bar.update(display_num, suffix=city_label)

        time.sleep(2.5)

        if display_num % save_interval == 0:
            with open(progress_path, "w") as f:
                json.dump(results, f, indent=2)

    bar.done(f"Done. {len(results)} cities extracted, {len(errors)} errors.")
    return results, errors

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Allow resuming from existing raw text (skip PDF extraction)
    raw_text_path = OUTPUT_DIR / "roster_raw_text.txt"

    if "--skip-extract" in sys.argv and raw_text_path.exists():
        print(f"Loading existing raw text from {raw_text_path}")
        with open(raw_text_path, encoding="utf-8") as f:
            full_text = f.read()
    else:
        print("Step 1: Extracting text from PDF...")
        full_text = extract_two_column_text(PDF_PATH)

    print("\nStep 2: Splitting into city chunks...")
    chunks = split_into_city_chunks(full_text)
    print(f"  {len(chunks)} city chunks found")

    # Show first few chunks for sanity check
    for chunk in chunks[:3]:
        print(f"\n--- {chunk['header']} ---")
        print(chunk["text"][:300])
        print("...")

    if "--dry-run" in sys.argv:
        print("\nDry run complete. Run without --dry-run to extract all cities via API.")
        exit(0)

    print(f"\nStep 3: Extracting {len(chunks)} cities via Sonnet API...")
    print("  Estimated time: ~20 minutes (2.5s/city × 483 cities)")
    print("  Progress is saved every 50 cities — safe to interrupt and resume with --skip-extract")

    results, errors = extract_all_cities(chunks)

    print(f"\nExtraction complete: {len(results)} cities, {len(errors)} errors")

    # Save final results
    out = OUTPUT_DIR / "roster_cities.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved -> {out}")

    if errors:
        err_out = OUTPUT_DIR / "roster_errors.json"
        with open(err_out, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        print(f"Errors saved -> {err_out} ({len(errors)} items need manual review)")
