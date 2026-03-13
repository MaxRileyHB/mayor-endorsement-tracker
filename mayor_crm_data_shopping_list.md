# Mayor Endorsement CRM — Data Shopping List & Parsing Guide

**Last updated:** March 12, 2026
**Purpose:** Everything Max needs to download before building the CRM in Claude Code, plus technical parsing instructions.

---

## Downloads: What Max Needs to Grab

### Source 1: California Roster — Cities & Towns Section
- **What:** The single most important file. Contains every incorporated city with mayor name, mayor pro tem, city address, phone, fax, email, website, council members, city manager, city clerk, and legislative districts.
- **URL:** `https://admin.cdn.sos.ca.gov/ca-roster/2026/cities-towns.pdf`
- **Format:** PDF, two-column layout, ~483 city entries
- **Caveat:** Published 2025. Some mayors will have rotated, especially in council-manager cities where the mayor title rotates annually among council members. The parsing pipeline includes a verification step to catch this.

### Source 2: FAIR Plan Residential Policies in Force by ZIP Code
- **What:** Number of FAIR Plan residential policies per ZIP code, 5-year trend. This is the core "how reliant is this city on the insurer of last resort" metric.
- **URL:** `https://www.cfpnet.com/wp-content/uploads/2025/11/CFP-5-yr-PIF-Zip-FY25-DWE-251114.pdf`
- **Format:** PDF, tabular

### Source 3: FAIR Plan Residential Exposure by Category (ZIP, County, Risk Score, Distressed Status)
- **What:** Residential exposure broken down by ZIP code, county, wildfire risk score, AND distressed ZIP code status. The "distressed ZIP" flag is key.
- **URL:** `https://www.cfpnet.com/wp-content/uploads/2025/12/Exposure-by-category-DWE-as-of-250930-DL-251211v003.pdf`
- **Format:** PDF, tabular

### Source 4: CDI Distressed ZIP Codes & Counties List (March 2025)
- **What:** Official CDI designation of insurance-distressed areas. Lists 29 distressed counties and individual "undermarketed" ZIP codes based on wildfire risk + FAIR Plan concentration + affordability.
- **URL:** `https://www.insurance.ca.gov/01-consumers/180-climate-change/upload/catastrophe-modeling-and-ratemaking-insurer-commitments-to-increase-writing-of-policies-in-high-risk-wildfire-areas-list-of-distressed-counties-and-undermarketed-zip-codes-residential-property-insurance-commitments.pdf`
- **Format:** PDF

### Source 5: Moratorium Bulletins (8 PDFs — recent wildfire-impacted ZIP codes)
Download from: `https://www.insurance.ca.gov/01-consumers/140-catastrophes/MandatoryOneYearMoratoriumNonRenewals.cfm`

| # | Fire | Date | Counties | Status |
|---|------|------|----------|--------|
| 1 | Palisades/Eaton/Hurst/Lidia/Sunset/Woodley | Jan 7, 2025 (amended Jan 17) | LA, Ventura | Expired Jan 2026, still politically relevant |
| 2 | Hughes | Jan 7, 2025 | LA | Expired Jan 2026 |
| 3 | Franklin | Jun 18, 2025 | LA | Active |
| 4 | TCU September Lightning Complex | Sep 19, 2025 | Calaveras, Tuolumne | Active |
| 5 | Pack | Dec 9, 2025 | Mono | Active |
| 6 | Gifford | Dec 23, 2025 | Santa Barbara, San Luis Obispo | Active |
| 7 | Mountain | Nov 7, 2024 | Ventura | Expired Nov 2025 |
| 8 | Bear | Nov 1, 2024 | Sierra | Expired Nov 2025 |

**Skip all older moratorium bulletins — expired and less politically relevant.**

### Automated by Claude Code (no download needed)
- CA Department of Finance E-1 population estimates (Excel from dof.ca.gov)
- ZIP code to city mapping (HUD USPS crosswalk)
- City geographic coordinates (Census TIGER/Line)

---

## ⚠️ PDF Parsing — Read This First

**These PDFs are weirdly shaped and will fight you.** Do not spend 20,000 tokens building a custom PDF parser that doesn't work. The California Roster is a two-column government PDF with irregular formatting. The FAIR Plan files are tabular but inconsistently structured. The moratorium bulletins are formatted legal documents with embedded ZIP code lists.

**General rules:**
1. **Try the simplest extraction first.** If it works, move on. If it doesn't, escalate — don't iterate on a broken approach.
2. **Use the Claude API as a parsing tool.** If a PDF chunk is messy, just send the raw extracted text (or even a base64 image of the page) to the Sonnet API and ask it to extract the structured data. This is faster, cheaper, and more reliable than writing a custom parser. You have API access — use it.
3. **Ask Max for help if stuck.** If a PDF is truly uncooperative after 2-3 attempts, stop and ask. Max can open the PDF manually, try a different extraction tool, or provide the data in another format. Do not spin wheels.
4. **Log failures, don't crash.** If one city entry or one ZIP code row fails to parse, log it and move on. Don't let one broken record block 482 good ones.

**Recommended parsing strategy ladder (try in order, escalate as needed):**

| Strategy | When to use | How |
|----------|------------|-----|
| **1. PyMuPDF text extraction** | First attempt for any PDF | `fitz.open()` → extract text blocks with coordinates. Works well for simple layouts. |
| **2. PyMuPDF with coordinate-based column splitting** | Two-column PDFs like the Roster | Extract blocks with `page.get_text("dict")`, split by x-coordinate, reassemble in reading order. |
| **3. tabula-py / camelot** | Tabular PDFs like FAIR Plan data | `tabula.read_pdf()` with lattice or stream mode. Good for tables with visible gridlines. |
| **4. Page-to-image → Claude Vision API** | When text extraction produces garbage | Render PDF page to PNG with `pdf2image` or PyMuPDF, send as base64 image to Sonnet with extraction prompt. This is the nuclear option but it works on basically anything. |
| **5. Send raw messy text → Claude Sonnet API** | When text extracts but is jumbled/irregular | Extract whatever text you can, send the raw chunk to Sonnet with a structured extraction prompt. Let the LLM figure out the structure instead of writing regex. |

**For the California Roster specifically:** Strategy 2 (coordinate-based column split) → Strategy 5 (Sonnet API for each city chunk) is the recommended path. Do NOT try to regex-parse the city entries yourself — they are irregularly shaped and Sonnet will handle them in one shot.

**For the FAIR Plan tabular PDFs:** Start with Strategy 3 (tabula-py). If the tables are messy, fall back to Strategy 4 (render pages to images, send to Sonnet with "extract this table as CSV" prompt).

**For the moratorium bulletins:** Strategy 1 (basic text extraction) should work since you're just looking for ZIP code lists. If not, Strategy 5.

**Budget check:** It is ALWAYS better to spend $0.50 in Sonnet API calls to parse a PDF correctly than to spend 20 minutes and 20,000 tokens building a parser that produces wrong data. The API is a tool — use it aggressively for parsing.

---

## Parsing Instructions for Claude Code

### California Roster PDF (Source 1) — Critical, requires special handling

The Roster PDF uses a **two-column layout** that standard PDF text extraction tools mangle. Each city entry is shaped irregularly (varying numbers of council members, some fields present/absent). Use the following three-step pipeline:

#### Step 1: Column separation → plaintext

Split each page into left and right columns and write all text sequentially to a plaintext file. Approach:
- Use a PDF library (e.g., PyMuPDF/fitz) to extract text blocks with coordinates
- For each page, determine the midpoint x-coordinate
- Assign each text block to left column (x < midpoint) or right column (x >= midpoint)
- Sort left column blocks top-to-bottom, then right column blocks top-to-bottom
- Write to a single plaintext file, left column first, then right column, page by page
- Insert page markers between pages for debugging

**Do NOT use pdftotext or pdfplumber in default mode — they will interleave the columns.**

#### Step 2: Chunk extraction → Sonnet API for structured parsing

Parse the plaintext file to identify each city's chunk of text. City entries typically start with "City of [Name]" or "Town of [Name]" followed by "(County of [Name])". However, the boundaries between entries can be irregular. Strategy:
- Use regex to split on city header patterns: `City of ...` / `Town of ...`
- Send each chunk to the **Claude Sonnet API** for structured extraction
- Sonnet prompt should extract the following fields and return JSON:

```json
{
  "city_name": "Adelanto",
  "county": "San Bernardino",
  "address": "11600 Air Expressway, Adelanto CA 92301",
  "phone": "(760) 246-2300",
  "fax": "(442) 249-1121",
  "website": "https://adelantoca.gov/",
  "email": "jflores@adelantoca.gov",
  "office_hours": "Monday-Thursday from 7:00 a.m. to 6:00 p.m.",
  "mayor": "Gabriel Reyes",
  "mayor_pro_tem": "Daniel Ramos",
  "council_members": ["Stevevonna Evans", "Angelo Meza", "Amanda Uptergrove"],
  "council_meeting_schedule": "Wednesdays at 11:00 a.m.",
  "city_attorney": "Todd Litfin",
  "city_manager": "Jessie Flores",
  "city_clerk": "Brenda Lopez",
  "police_chief": "Kenneth Lutz",
  "fire_chief": "Kelly Anderson",
  "school_superintendent": "Dr. Terry Walker",
  "incorporated_date": "12/22/1970",
  "congressional_district": "23",
  "state_senate_district": "21",
  "state_assembly_district": "33"
}
```

- Use batch processing to avoid rate limits — send chunks in batches of 10-20
- Log any chunks Sonnet flags as unparseable for manual review

#### Step 3: Mayor verification via DuckDuckGo web search

Many California cities use a council-manager system where the mayor rotates annually. The Roster was published in 2025, so some mayors have changed. Verification step:

- For each city, query the **DuckDuckGo API** with: `"[City Name] California mayor 2026"` or `"[City Name] California current mayor"`
- Compare the search result to the Roster's mayor name
- If the search indicates a different current mayor:
  - Check if the new mayor matches the Roster's **mayor pro tem** (common rotation pattern — the pro tem frequently becomes the next mayor)
  - Update the mayor field to the new name
  - Move the old mayor to a `previous_mayor` field
  - Log the change with source URL
- If the search is inconclusive, flag the city as `mayor_needs_verification: true`
- Save the mayor pro tem regardless — useful for both verification and future rotation tracking
- Rate limit search queries to avoid throttling (e.g., 1 request per second, or batch with delays)
- Prioritize verification for Tier 1 cities (largest population / highest insurance relevance) first

Output: `california_mayors.json` — array of all city objects with verified/flagged mayor data.

### FAIR Plan PDFs (Sources 2-3) — Tabular extraction

These are straightforward tabular PDFs. Use standard extraction:
- PyMuPDF or tabula-py for table extraction
- Each row = one ZIP code with policy count / exposure data
- Output as CSV, then map ZIP → city using the HUD crosswalk
- Aggregate ZIP-level data to city level (sum policies, sum exposure)
- Flag cities where FAIR Plan policies exceed a threshold (e.g., >500 policies or >10% of housing units)

### CDI Distressed List (Source 4) — Simple extraction

Two lists in one PDF:
- List of 29 distressed counties (just county names)
- List of undermarketed ZIP codes (ZIP + criteria)
- Extract both, cross-reference to cities
- Tag each city with `is_distressed_county: true/false` and `has_undermarketed_zips: true/false`

### Moratorium Bulletins (Source 5) — ZIP code extraction

Each bulletin contains a list of ZIP codes covered by the moratorium.
- Extract all ZIP codes from each bulletin
- Tag with fire name, date, and active/expired status
- Map to cities
- Tag each city with `moratorium_fires: ["Palisades", "Eaton"]` etc.

---

## Final Database Fields Per City

After all parsing and enrichment, each city record should contain:

**Identity:** city_name, county, population (from DOF E-1), incorporated_date

**Officials:** mayor, mayor_pro_tem, previous_mayor, mayor_needs_verification, council_members, city_manager, city_clerk

**Contact — City:** address, phone, fax, website, email, office_hours

**Contact — Mayor Direct:** mayor_email, mayor_phone, contact_source (populated later via scraping + outreach)

**Political:** congressional_district, state_senate_district, state_assembly_district, party_affiliation (populated later)

**Insurance Relevance:**
- fair_plan_policies (count, from FAIR Plan PIF data)
- fair_plan_exposure (dollars, from FAIR Plan exposure data)
- is_distressed_county (bool, from CDI list)
- has_undermarketed_zips (bool, from CDI list)
- moratorium_fires (array of fire names)
- moratorium_active (bool)
- wildfire_risk_tier (high/medium/low, derived)

**Pipeline:** outreach_status, outreach_tier (T1/T2/T3), last_contacted, next_action, notes

**Email Thread:** (populated via Gmail integration at runtime)

---

## Architecture Notes for Claude Code

- **Backend:** FastAPI + PostgreSQL on Railway
- **Frontend:** React (responsive PWA for mobile)
- **Gmail:** Dedicated campaign outreach email, connected via Gmail API
- **AI Engine:** Claude Sonnet for bulk drafts + research, Opus for complex cases
- **Deployment:** Railway (same pattern as endorsement questionnaire drafter)
- **Views:** Hybrid kanban/table with city detail panel, batch selection, review queue
- **Mobile-critical:** Pipeline status, record updates after calls, email reading/replying
