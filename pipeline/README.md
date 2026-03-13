# Mayor CRM — Data Pipeline

Run these scripts in order to produce `output/california_cities.json`, which seeds the database.

## Prerequisites

- Python 3.10+
- Java 8+ (required by tabula-py)
- `ANTHROPIC_API_KEY` set in `../.env`
- All source PDFs in `../source_data/`

Install dependencies:
```
pip install pymupdf tabula-py pandas openpyxl anthropic python-dotenv duckduckgo-search pillow
```

---

## Step-by-step

### 1. Simple parsers (no API needed) — run first, ~1 min total

```bash
py parse_dof_population.py       # DOF E-1 population estimates
py parse_moratoriums.py          # 8 CDI moratorium bulletins
py parse_cdi_distressed.py       # CDI distressed counties & ZIPs
py parse_fair_plan_pif.py        # FAIR Plan policies by ZIP (tabula)
```

### 2. Exposure parser — ~2 min (18 Sonnet API calls)

```bash
py parse_fair_plan_exposure.py
```

### 3. Roster extraction — ~20 min (485 Sonnet API calls)

```bash
py parse_roster.py
```

Progress saves every 50 cities to `output/roster_progress.json`.
If interrupted, resume with:
```bash
py parse_roster.py --skip-extract
```

### 4. Mayor verification — ~25 min (485 DuckDuckGo searches)

Requires `roster_cities.json` from step 3.

```bash
py verify_mayors.py
```

Produces `roster_cities_verified.json`. If interrupted:
```bash
py verify_mayors.py --resume
```

### 5. Merge all sources

Requires all previous outputs.

```bash
py merge_data.py
```

Produces `output/california_cities.json` — the final dataset, ready for DB seeding.
Check `output/merge_report.json` for unmatched cities and fuzzy match warnings.

---

## Output files

| File | Description |
|------|-------------|
| `output/dof_population.json` | 488 CA cities with 2025 population |
| `output/moratoriums.json` | 8 fires, 229 ZIPs |
| `output/cdi_distressed.json` | 29 distressed counties, 662 undermarketed ZIPs |
| `output/fair_plan_pif.json` | 840 ZIPs with 5-year FAIR Plan policy counts |
| `output/fair_plan_exposure.json` | ZIPs with exposure by wildfire risk tier |
| `output/roster_raw_text.txt` | Extracted text from CA Roster PDF (debug) |
| `output/roster_cities.json` | 485 cities with all roster fields |
| `output/roster_cities_verified.json` | Same, with DuckDuckGo mayor verification applied |
| `output/verification_log.json` | What changed / was flagged during mayor verification |
| `output/california_cities.json` | **FINAL** — all sources merged, ready for DB seed |
| `output/merge_report.json` | Merge stats: unmatched cities, fuzzy matches, tier counts |
