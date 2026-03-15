# Mayor Endorsement CRM — Full Program Specification

**Project:** Ben Allen for California Insurance Commissioner — Mayoral Endorsement Outreach System
**Author:** Max Riley
**Date:** March 12, 2026
**Version:** 1.0

---

## 1. Overview

### What this is
A full-stack CRM for managing endorsement outreach to all 483 California city mayors for Ben Allen's Insurance Commissioner campaign. It combines a structured database of mayor/city data, AI-powered email drafting with city-specific insurance research, Gmail integration for email tracking, and a pipeline management interface.

### Why it exists
Max needs to pursue endorsements from every California mayor. This is a massive outreach operation that requires:
- A database of all 483 cities with mayor names, contact info, and insurance relevance data
- A pipeline to track outreach status from initial contact through endorsement
- AI-generated personalized emails that reference each city's specific insurance challenges
- Two-tier contact collection (city general contact → mayor direct contact)
- Gmail integration to see all email threads attached to each city record
- Batch operations to generate and send outreach at scale
- Mobile accessibility for pipeline checks, status updates, and email reading on the go

### Who uses it
Max Riley — sole user. This is an internal campaign tool, not multi-user.

---

## 2. Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Backend | FastAPI (Python) | Same stack as the endorsement questionnaire drafter |
| Frontend | React | Responsive PWA for mobile support |
| Database | PostgreSQL | Hosted on Railway |
| Deployment | Railway | Same pattern as the endorsement questionnaire drafter |
| AI Engine | Claude API (Sonnet for bulk, Opus for complex) | Anthropic API — no key needed in artifacts |
| Email | Gmail API | Dedicated campaign outreach email account |
| Search | DuckDuckGo API | For mayor verification and city research |

---

## 3. Data Pipeline — Initial Setup

Before the app is usable, it needs to be seeded with data from several PDF sources that Max will provide. See the companion document "Data Shopping List & Parsing Guide" for download URLs and detailed parsing instructions.

### ⚠️ CRITICAL: PDF Parsing Warning

**These PDFs are weirdly shaped and will fight you.** Do not spend 20,000 tokens building a custom PDF parser that doesn't work. Follow the parsing strategy ladder:

1. **Try simplest extraction first** (PyMuPDF text, tabula-py for tables)
2. **If it doesn't work in 2-3 attempts, use the Claude API** — send raw text or page images to Sonnet for extraction
3. **If still stuck, ask Max for help** — he can provide data in alternative formats
4. **Log failures and move on** — don't let one broken record block 482 good ones

**It is ALWAYS better to spend $0.50 in API calls than 20,000 tokens building a broken parser.**

### Data sources to ingest (in order)

#### 3.1 California Roster — Cities & Towns (PRIMARY)
- **File:** `cities-towns.pdf` from CA Secretary of State
- **Contains:** All 483 incorporated cities with mayor, mayor pro tem, council, city contact info, legislative districts
- **Parsing pipeline:**
  1. **Column separation:** PDF is two-column layout. Use PyMuPDF to extract text blocks with coordinates. Split by x-midpoint. Write left column then right column per page to plaintext file. Do NOT use pdftotext default mode — it interleaves columns.
  2. **Chunk extraction → Sonnet API:** Split plaintext on city header patterns (`City of ...` / `Town of ...`). Send each chunk to Claude Sonnet API with a structured extraction prompt. Return JSON per city. Batch in groups of 10-20. Log unparseable chunks for manual review.
  3. **Mayor verification via DuckDuckGo:** For each city, search `"[City Name] California mayor 2026"`. Compare to Roster data. If different, check if new mayor matches the mayor pro tem (common rotation pattern). Update or flag as `mayor_needs_verification`. Run as background job — don't block initial import.
- **Output:** `california_cities.json` — array of all city objects

#### 3.2 CA Department of Finance E-1 Population Estimates
- **File:** Auto-download from `https://dof.ca.gov/forecasting/demographics/estimates-e1/`
- **Format:** Excel (.xlsx)
- **Contains:** All cities with Jan 2025 population estimate and county
- **Join on:** city_name + county → merge population into city records

#### 3.3 FAIR Plan Residential Policies in Force by ZIP Code
- **File:** `CFP-5-yr-PIF-Zip-FY25-DWE-251114.pdf`
- **Contains:** FAIR Plan residential policy counts per ZIP, 5-year trend
- **Parsing:** Try tabula-py first. If tables are messy, render pages to images and send to Sonnet API with "extract this table as CSV" prompt.
- **Post-processing:** Map ZIP → city using HUD USPS crosswalk (auto-download). Aggregate to city level.

#### 3.4 FAIR Plan Residential Exposure by Category
- **File:** `Exposure-by-category-DWE-as-of-250930-DL-251211v003.pdf`
- **Contains:** Exposure by ZIP, county, wildfire risk score, distressed ZIP status
- **Parsing:** Same approach as 3.3
- **Post-processing:** Map to cities. Extract distressed ZIP flags.

#### 3.5 CDI Distressed ZIP Codes & Counties List
- **File:** CDI distressed areas PDF (March 2025)
- **Contains:** 29 distressed county names + list of undermarketed ZIP codes
- **Parsing:** Simple text extraction should work. Fall back to Sonnet API if needed.
- **Post-processing:** Tag cities with `is_distressed_county` and `has_undermarketed_zips`

#### 3.6 Moratorium Bulletins (8 PDFs)
- **Files:** 8 moratorium bulletins from CDI (2024-2025 fires)
- **Contains:** ZIP codes covered by mandatory moratorium on insurance non-renewals
- **Parsing:** Basic text extraction to find ZIP code lists. These are legal docs, ZIP codes should be easy to regex out.
- **Post-processing:** Tag cities with `moratorium_fires` array and `moratorium_active` bool

#### 3.7 ZIP Code → City Mapping
- **Source:** HUD USPS ZIP Crosswalk (auto-download from `https://www.huduser.gov/portal/datasets/usps_crosswalk.html`)
- **Needed to:** Map all ZIP-level insurance data to city records

#### 3.8 Tier Assignment (computed)
After all data is loaded, auto-assign outreach tiers:
- **Tier 1:** Population > 50,000, OR is_distressed_county, OR fair_plan_policies > 500, OR moratorium_active. These are the priority targets.
- **Tier 2:** Population 15,000-50,000, OR has_undermarketed_zips, OR fair_plan_policies > 100
- **Tier 3:** Everything else
- Tiers can be manually overridden by Max in the UI

---

## 4. Database Schema

### `cities` table

```sql
CREATE TABLE cities (
  id SERIAL PRIMARY KEY,
  city_name VARCHAR(255) NOT NULL,
  county VARCHAR(255),
  population INTEGER,
  incorporated_date VARCHAR(50),

  -- Officials
  mayor VARCHAR(255),
  mayor_pro_tem VARCHAR(255),
  previous_mayor VARCHAR(255),
  mayor_needs_verification BOOLEAN DEFAULT FALSE,
  council_members JSONB, -- array of names
  city_manager VARCHAR(255),
  city_clerk VARCHAR(255),
  city_attorney VARCHAR(255),

  -- Contact: City-level
  city_address TEXT,
  city_phone VARCHAR(50),
  city_fax VARCHAR(50),
  city_website VARCHAR(500),
  city_email VARCHAR(255),
  office_hours VARCHAR(255),

  -- Contact: Mayor direct (populated later)
  mayor_email VARCHAR(255),
  mayor_phone VARCHAR(50),
  mayor_contact_source VARCHAR(255), -- e.g. "city website", "clerk response", "manual entry"

  -- Political
  congressional_district VARCHAR(10),
  state_senate_district VARCHAR(10),
  state_assembly_district VARCHAR(10),
  party_affiliation VARCHAR(50), -- D, R, NP, Unknown

  -- Insurance relevance
  fair_plan_policies INTEGER DEFAULT 0,
  fair_plan_exposure BIGINT DEFAULT 0,
  is_distressed_county BOOLEAN DEFAULT FALSE,
  has_undermarketed_zips BOOLEAN DEFAULT FALSE,
  moratorium_fires JSONB, -- array of fire names, e.g. ["Palisades", "Eaton"]
  moratorium_active BOOLEAN DEFAULT FALSE,
  wildfire_risk_tier VARCHAR(10), -- high, medium, low

  -- Pipeline
  outreach_status VARCHAR(50) DEFAULT 'no_contact_info',
  outreach_tier INTEGER DEFAULT 3, -- 1, 2, or 3
  last_contacted TIMESTAMP,
  next_action TEXT,
  next_action_date DATE,

  -- Notes
  notes TEXT,

  -- Timestamps
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### `emails` table

```sql
CREATE TABLE emails (
  id SERIAL PRIMARY KEY,
  city_id INTEGER REFERENCES cities(id),
  gmail_message_id VARCHAR(255),
  gmail_thread_id VARCHAR(255),
  direction VARCHAR(10), -- 'inbound' or 'outbound'
  from_address VARCHAR(255),
  to_address VARCHAR(255),
  subject TEXT,
  body_preview TEXT, -- first ~200 chars
  sent_at TIMESTAMP,
  is_draft BOOLEAN DEFAULT FALSE,
  draft_type VARCHAR(50), -- 'info_request', 'endorsement_outreach', 'follow_up'
  draft_status VARCHAR(50), -- 'pending_review', 'approved', 'sent', 'rejected'
  created_at TIMESTAMP DEFAULT NOW()
);
```

### `drafts` table (for batch review queue)

```sql
CREATE TABLE drafts (
  id SERIAL PRIMARY KEY,
  city_id INTEGER REFERENCES cities(id),
  draft_type VARCHAR(50) NOT NULL, -- 'info_request' or 'endorsement_outreach'
  to_address VARCHAR(255),
  subject TEXT,
  body TEXT,
  status VARCHAR(50) DEFAULT 'pending_review', -- pending_review, approved, edited, rejected, sent
  batch_id VARCHAR(50), -- groups drafts from same batch operation
  research_context JSONB, -- city research data used to generate this draft
  created_at TIMESTAMP DEFAULT NOW(),
  reviewed_at TIMESTAMP,
  sent_at TIMESTAMP
);
```

### `activity_log` table

```sql
CREATE TABLE activity_log (
  id SERIAL PRIMARY KEY,
  city_id INTEGER REFERENCES cities(id),
  action VARCHAR(100), -- e.g. 'status_changed', 'email_sent', 'note_added', 'mayor_verified'
  details TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 5. Pipeline Stages

Outreach status values, in order:

| Stage | Description | Card color hint |
|-------|-------------|-----------------|
| `no_contact_info` | No city or mayor contact info yet | Gray |
| `city_contact_only` | Have city general contact but no mayor direct | Light gray |
| `info_requested` | Sent email to city asking for mayor contact | Amber |
| `ready_for_outreach` | Have mayor direct contact, ready to pitch | Blue |
| `outreach_sent` | Endorsement outreach email sent | Blue |
| `in_conversation` | Mayor has replied, active back-and-forth | Purple |
| `call_scheduled` | Phone call or meeting is scheduled | Purple |
| `endorsed` | Mayor has endorsed Ben Allen | Green |
| `declined` | Mayor declined to endorse | Red |
| `follow_up` | Needs follow-up (went cold, need to re-engage) | Amber |
| `not_pursuing` | Decided not to pursue (wrong party, hostile, etc.) | Gray |

---

## 6. API Endpoints

### Cities
- `GET /api/cities` — List all cities (supports filtering, sorting, pagination)
  - Query params: `status`, `tier`, `county`, `search`, `sort_by`, `sort_order`, `page`, `per_page`
- `GET /api/cities/{id}` — City detail with full data
- `PATCH /api/cities/{id}` — Update city fields (status, notes, contact info, tier override, etc.)
- `POST /api/cities/batch-update` — Batch update status or tier for multiple cities
- `GET /api/cities/stats` — Dashboard stats (counts by status, by tier, etc.)

### Drafts & AI Generation
- `POST /api/drafts/generate` — Generate drafts for selected cities
  - Body: `{ city_ids: [1, 2, 3], draft_type: "info_request" | "endorsement_outreach" }`
  - This is an async operation. Returns a `batch_id` immediately, drafts generate in background.
- `GET /api/drafts?batch_id=xxx` — List drafts for a batch
- `PATCH /api/drafts/{id}` — Update draft (edit body, approve, reject)
- `POST /api/drafts/send` — Send approved drafts via Gmail
  - Body: `{ draft_ids: [1, 2, 3] }` or `{ batch_id: "xxx", status: "approved" }`

### Emails
- `GET /api/cities/{id}/emails` — Get email thread for a city
- `POST /api/emails/sync` — Trigger Gmail sync (pulls new emails, matches to cities by domain/address)
- `POST /api/emails/send` — Send a single email (for individual replies)

### Activity
- `GET /api/cities/{id}/activity` — Activity log for a city

---

## 7. AI Drafting Engine

### 7.1 Info Request Email Generation

When Max selects cities with no mayor direct contact and hits "Generate info request emails," the system:

1. For each city, compose a prompt with:
   - City name, county, general contact email
   - Mayor name (if known from Roster)
   - Any insurance relevance flags
2. Send to Claude Sonnet API with system prompt:

```
You are writing a brief, professional email on behalf of Max Riley from State Senator Ben Allen's campaign for California Insurance Commissioner. The email is being sent to a city's general email address to request the mayor's direct contact information.

Keep it to 3-4 short paragraphs. Be warm but professional. Mention one specific reason you want to connect with the mayor that is relevant to their city (e.g., wildfire risk, FAIR Plan reliance, insurance affordability). Sign off as Max Riley, Ben Allen for Insurance Commissioner.

Do NOT use overly formal language. Do NOT use "Dear Sir/Madam." Do use the mayor's name if known.
```

3. Draft lands in the review queue with status `pending_review`

### 7.2 Endorsement Outreach Email Generation

When Max selects cities with direct mayor contact and hits "Generate outreach emails," the system:

1. For each city, gather context:
   - City name, population, county, mayor name
   - FAIR Plan policy count and exposure
   - Distressed county/ZIP status
   - Moratorium fire history
   - Any existing notes or prior email exchanges
2. (Optional) Use DuckDuckGo API to search for recent news: `"[City Name] insurance" OR "[City Name] wildfire" OR "[Mayor Name]"`
3. Send all context to Claude Sonnet API with system prompt:

```
You are writing a personalized endorsement outreach email on behalf of Max Riley from State Senator Ben Allen's campaign for California Insurance Commissioner. The email is to a city mayor requesting their endorsement.

You will receive data about the city including insurance metrics, wildfire history, and any recent relevant news. Use this to make the email specific and compelling — not generic.

Key messaging pillars for Ben Allen:
- FAIR Plan reform and stabilization
- Insurance affordability and availability for homeowners
- Wildfire resilience and community preparedness
- Consumer protection and rate transparency
- Ben's legislative record on insurance and environmental issues as a State Senator

Keep it to 4-5 short paragraphs. Be warm, direct, and specific. Reference concrete data about the city's insurance situation. Make a clear ask for the endorsement. Offer a phone call to discuss further.

Do NOT be wonky or overly policy-heavy. DO make it feel personal and specific to their city.
Sign off as Max Riley, Ben Allen for Insurance Commissioner.
```

4. Draft lands in review queue

### 7.3 Follow-Up Email Generation

Similar to outreach but references prior communication:
- Include summary of previous email exchange
- Reference any scheduled calls or prior interest
- Shorter, more conversational tone

---

## 8. Gmail Integration

> **See full plan:** [`gmail_integration_plan.md`](./gmail_integration_plan.md)
>
> That document contains the complete architecture, phased build plan, manual Google Cloud setup steps, feature roadmap, risk register, and API endpoint summary. This section is a brief summary only.

### Setup
- Google Workspace account (`@benallenca.com`) — "Internal" app type, skips Google verification
- OAuth2 credentials stored in Railway env vars (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`)
- OAuth tokens (refresh + access) stored in the `settings` DB table — not env vars — so rotated tokens are automatically persisted
- From name on all outreach: `Max Riley - Ben Allen for Insurance Commissioner`

### Email Sync
- On app load and periodically (every 5 minutes via setInterval), call `POST /api/emails/sync`
- City matching priority: (1) Gmail thread_id match, (2) exact address match on `city_email`/`mayor_email`, (3) domain match against `city_website`
- Unmatched emails stored with `city_id=NULL` and visible in an unmatched inbox for manual assignment
- Synced emails appear in the city detail Timeline alongside call logs

### Sending
- All sends go through the Gmail API (not SMTP)
- Every send requires explicit user action — the "Send N approved" button in the Review Queue
- After sending: draft marked `sent`, email logged to `emails` table, city `last_contacted` updated
- Auto-advance city status: `info_request` sent → `info_requested`; `endorsement_outreach` sent → `outreach_sent`

### Build Phases
- **Phase 1 (core):** Auth flow + `POST /api/drafts/send` + Review Queue send button
- **Phase 2 (sync):** `POST /api/emails/sync` + Timeline population + auto-sync on load
- **Phase 3 (reply):** Compose/reply from city detail panel

---

## 9. Frontend — Views & Components

### 9.1 Main View: Pipeline Board (Kanban) + Table Toggle

**Default view is kanban.** Toggle switch in top-right for table view.

**Top bar:**
- Title: "Mayor endorsement tracker"
- Subtitle: dynamic stats — "[X] cities · [Y] contacted · [Z] endorsed"
- Board/Table toggle
- Search bar (searches city names, mayor names, counties)
- Filter button (opens filter panel: county, tier, status, insurance flags)

**Kanban columns:** One per pipeline stage. Each column header shows stage name + count.
- "Select all" checkbox in column header for batch operations
- Cards are dense: city name (bold), mayor name, population + county (small), tier badge (T1/T2/T3 colored), insurance flag badges (wildfire zone, FAIR Plan, distressed, moratorium)
- Cards show date of last action if applicable
- "+ N more" at bottom of long columns, scrollable
- Click card → opens city detail panel

**Table view:** Sortable/filterable table with columns:
- Checkbox, City, Mayor, County, Pop., Tier, Status, FAIR Plan Policies, Last Contacted, Next Action
- Click row → opens city detail panel
- Bulk select via checkboxes

**Batch action bar:** Appears at bottom when any cards/rows are selected.
- Shows "[X] cities selected"
- Buttons: "Generate info request emails", "Generate outreach emails", "Move to stage" (dropdown), "Clear selection"

### 9.2 City Detail Panel

Opens as a slide-over panel (right side on desktop, full screen on mobile) when clicking a city card/row.

**Header:** City name (large), mayor name + population + county (subtitle), tier badge
- "Draft outreach" button (blue)
- "Draft info request" button (amber)
- Status dropdown (change pipeline stage)

**Metric cards row (3 across):**
- Pipeline status
- Party / Tier
- Insurance flags (FAIR Plan count, distressed, moratorium fires)

**Two-column contact section:**
- Left: City contact (general email, clerk, phone)
- Right: Mayor direct (email, phone, source) — shows "Not yet collected" if empty, with "Request contact" button

**Email thread section:**
- Chronological list of all emails exchanged with this city
- Each email shows: direction arrow, from/to, date, subject, body preview
- "Compose" button to write a new email directly
- Expandable email bodies

**Notes section:**
- Free-text notes field
- Shows timestamped note history
- Quick-add note (e.g., "Just talked to Mayor X — interested, follow up Thursday")

**Activity log:** Collapsible section showing all status changes, emails sent, notes added

### 9.3 Review Queue

Accessed after a batch generate operation, or from a "Review drafts" link in the nav.

**Header:** "[X] drafts generated · [Y] approved · [Z] edited · [W] rejected"

**Filter bar:** "Show all", "Pending", "Approved", "Edited", "Rejected"
- "Approve all" button (green) — for low-stakes batches like info requests

**Draft cards (stacked vertically):**
- Header: City name, tier badge, insurance flag badges
- Subheader: To address, subject line
- Body: Full draft text in a lightly shaded box, editable inline
- Action buttons: Approve (green), Edit (default), Skip (red outline)
- Edit mode: draft body becomes a textarea, save/cancel buttons appear

**Send bar (fixed at bottom):**
- "Ready to send: [X] approved"
- "Send [X] approved" button (green)
- All sends require this explicit button press — nothing auto-sends

### 9.4 Mobile Responsiveness (PWA)

The app should be a responsive web app that works in mobile browsers. Key mobile adaptations:

- **Kanban → single column list** with dropdown to filter by stage
- **City detail → full-screen stacked layout**
- **Table view → simplified card list** (full table doesn't work on mobile)
- **Review queue → swipe-friendly cards** (swipe right = approve, swipe left = skip)
- **Bottom nav bar** on mobile: Pipeline, Search, Drafts, Settings

**Mobile-critical flows:**
1. Check pipeline status (glance at counts per stage)
2. Update a record after a call/text (open city → add note → change status)
3. Read and reply to emails (open city → read thread → compose reply)

---

## 10. Design & Styling

### Visual approach
- Dense and information-rich — show data, minimize clicks
- Clean flat surfaces, minimal borders
- Professional but not corporate — this is a campaign tool

### Color system
- **Tier badges:** T1 = blue, T2 = amber, T3 = muted red/gray
- **Status badges:** Use semantic colors — green for endorsed, red for declined, blue for active outreach stages, amber for waiting stages, gray for inactive
- **Insurance flag badges:** Amber/orange for wildfire-related flags (wildfire zone, FAIR Plan, distressed), with text labels

### Typography
- System font stack (or Inter/similar)
- City names: 14px semibold
- Mayor names: 12px regular, secondary color
- Metadata (population, county): 11px, tertiary color
- Dense but readable — 13px base for body text

---

## 11. Deployment

### Railway setup
- **Backend service:** FastAPI app
- **Database:** PostgreSQL add-on
- **Environment variables:**
  - `DATABASE_URL` (auto from Railway Postgres)
  - `ANTHROPIC_API_KEY`
  - `GMAIL_CLIENT_ID`
  - `GMAIL_CLIENT_SECRET`
  - `GMAIL_REFRESH_TOKEN`
  - `DUCKDUCKGO_API_KEY` (if using paid API; otherwise use free search)

### Initial setup flow
1. Deploy backend + database to Railway
2. Run data pipeline (parse PDFs → seed database)
3. Connect Gmail OAuth
4. Deploy frontend
5. Max verifies data, adjusts tiers, starts outreach

---

## 12. Future Enhancements (Not in V1)

These are ideas that came up but should NOT be built in the first version:

- **Map view** with geographic overlay of wildfire zones and FAIR Plan concentration
- **Calendar integration** for scheduling calls with mayors
- **Endorsement tracker public page** (list of endorsements for campaign website)
- **SMS integration** for text-based outreach
- **Multi-user support** if campaign staff grows
- **Auto-detection of new mayor rotations** (periodic web scraping)
- **Analytics dashboard** (outreach velocity, conversion rates by tier/county/flag)

---

## 13. File Manifest

Max will provide these files in the project directory:

```
/data/
  cities-towns.pdf              # CA Roster — cities section
  CFP-5-yr-PIF-Zip-FY25-DWE-251114.pdf   # FAIR Plan PIF by ZIP
  Exposure-by-category-DWE-as-of-250930-DL-251211v003.pdf  # FAIR Plan exposure
  cdi-distressed-zips.pdf       # CDI distressed areas list
  /moratorium/
    bulletin-palisades-eaton.pdf
    bulletin-hughes.pdf
    bulletin-franklin.pdf
    bulletin-tcu-lightning.pdf
    bulletin-pack.pdf
    bulletin-gifford.pdf
    bulletin-mountain.pdf
    bulletin-bear.pdf
```

Total: 12 PDF files.

---

## 14. Summary of Key Principles

1. **The API is a tool — use it for parsing.** Don't spend tokens building custom parsers when Sonnet can extract data from messy PDFs in one shot.
2. **Nothing sends without Max's approval.** Every email goes through the review queue. No auto-sending ever.
3. **Dense UI, minimal clicks.** Max is managing 483 records. Every extra click multiplied by 483 is a problem.
4. **Phone-friendly for the three things Max does on mobile:** check pipeline, update after calls, read emails.
5. **Graceful degradation on data.** Not every city will have complete data. The system should work with partial records and flag what's missing.
6. **Insurance data is the secret weapon.** The AI drafting engine should heavily leverage FAIR Plan data, distressed designations, and moratorium history to make every outreach email specific and compelling.
