# Mayor Endorsement CRM — Spec Addendum: AI-Powered Contact Scraper

**Date:** March 16, 2026
**Extends:** Mayor CRM Program Spec v1.0

---

## Overview

A deep contact enrichment function that automatically searches the internet for each mayor's contact information and social media presence. For each mayor, the scraper attempts to find and return:

- **Work phone** (from official city website or government directory)
- **Personal phone** (from public records, campaign sites, or personal websites)
- **Work email** (from official city website — often `mayor@city.gov` or similar)
- **Personal email** (from campaign sites, personal websites, public filings)
- **Instagram** (handle, e.g., `@garcetti`)
- **Facebook** (handle or page URL)
- **Other social media** (one additional platform if found — platform name + handle, e.g., `{ platform: "Twitter/X", handle: "@garcetti" }`)

Each field should include a `source_url` so Max can verify where the info came from.

---

## Data Model Changes

Add these columns to the `cities` table (or create a separate `mayor_contacts` table if you prefer normalization):

```sql
ALTER TABLE cities ADD COLUMN mayor_work_phone VARCHAR(50);
ALTER TABLE cities ADD COLUMN mayor_work_phone_source VARCHAR(500);
ALTER TABLE cities ADD COLUMN mayor_personal_phone VARCHAR(50);
ALTER TABLE cities ADD COLUMN mayor_personal_phone_source VARCHAR(500);
ALTER TABLE cities ADD COLUMN mayor_work_email VARCHAR(255);
ALTER TABLE cities ADD COLUMN mayor_work_email_source VARCHAR(500);
ALTER TABLE cities ADD COLUMN mayor_personal_email VARCHAR(255);
ALTER TABLE cities ADD COLUMN mayor_personal_email_source VARCHAR(500);
ALTER TABLE cities ADD COLUMN mayor_instagram VARCHAR(255); -- handle, e.g. "@garcetti"
ALTER TABLE cities ADD COLUMN mayor_instagram_source VARCHAR(500);
ALTER TABLE cities ADD COLUMN mayor_facebook VARCHAR(500); -- handle or page URL
ALTER TABLE cities ADD COLUMN mayor_facebook_source VARCHAR(500);
ALTER TABLE cities ADD COLUMN mayor_other_social_platform VARCHAR(100); -- e.g. "Twitter/X", "LinkedIn", "Threads"
ALTER TABLE cities ADD COLUMN mayor_other_social_handle VARCHAR(255); -- handle or URL
ALTER TABLE cities ADD COLUMN mayor_other_social_source VARCHAR(500);
ALTER TABLE cities ADD COLUMN contact_scrape_status VARCHAR(50) DEFAULT 'not_scraped';
-- Values: not_scraped, in_progress, completed, partial, failed
ALTER TABLE cities ADD COLUMN contact_scrape_date TIMESTAMP;
ALTER TABLE cities ADD COLUMN contact_scrape_log TEXT;
-- Stores notes on what was found, what failed, what needs manual review
```

---

## Scraping Pipeline — Per Mayor

The scraper runs through the following steps in order for each mayor. Each step feeds context into the next. The whole pipeline for one mayor should take ~15-30 seconds depending on API latency.

### Step 1: Official City Website Scrape

This is the highest-confidence source. Most city websites have a "Mayor" or "City Council" page with at least a work email and phone.

**Approach:**
- The city website URL is already in the database (from the Roster)
- Fetch the homepage and look for links containing keywords: `mayor`, `council`, `city-council`, `elected-officials`, `government`, `leadership`
- Follow the most promising link (use Sonnet to pick if ambiguous)
- Fetch that page and send the full page text to **Claude Sonnet API** with this prompt:

```
I need you to extract contact information for the mayor from this city government webpage.

Mayor name: {mayor_name}
City: {city_name}

Extract any of the following that appear on the page:
- Mayor's direct phone number (NOT the general city hall number unless it's specifically listed as the mayor's line)
- Mayor's email address
- Links to the mayor's social media profiles

Return JSON:
{
  "work_phone": "...",
  "work_email": "...",
  "instagram": "@handle or null",
  "facebook": "handle or page URL or null",
  "other_social": { "platform": "...", "handle": "..." } or null,
  "notes": "any relevant context about what you found or didn't find"
}

If a field is not found, return null for that field. Do NOT guess or fabricate.
```

**Why Sonnet instead of regex:** City websites are wildly inconsistent in structure. Some put contact info in a sidebar, some in a bio paragraph, some in a separate contact page, some behind JavaScript. Sonnet can handle all of these by reading the page content semantically.

**Fallback if the website doesn't have a clear mayor page:**
- Try fetching `/mayor`, `/city-council`, `/elected-officials`, `/about/mayor` as common URL patterns
- If none work, search the site via DuckDuckGo: `site:{city_website} mayor contact`

### Step 2: DuckDuckGo Web Search

Search for the mayor by name + city to find additional contact info that isn't on the official site.

**Queries to run (in order, stop when you have enough):**
1. `"{mayor_name}" "{city_name}" California email phone contact`
2. `"{mayor_name}" "{city_name}" mayor email`
3. `"{mayor_name}" "{city_name}" Instagram OR Facebook OR Twitter OR LinkedIn`

**For each query:**
- Grab the top 5-8 results
- Filter out irrelevant results (news articles about unrelated topics, etc.)
- For promising results, fetch the page and send to Sonnet API for extraction:

```
I'm looking for contact information and social media accounts for {mayor_name}, 
Mayor of {city_name}, California.

Here is content from a webpage that may contain their info:
---
{page_content}
---

Extract any of the following:
- Phone numbers (distinguish work vs personal if possible)
- Email addresses (distinguish work vs personal if possible — personal is gmail, 
  yahoo, outlook etc.; work is @city domain or official government domain)
- Instagram handle (e.g., @handle)
- Facebook page or handle
- Any other social media profile (one only — platform name + handle)

Return JSON:
{
  "phones": [{ "number": "...", "type": "work|personal|unknown", "context": "..." }],
  "emails": [{ "address": "...", "type": "work|personal|unknown", "context": "..." }],
  "instagram": "@handle or null",
  "facebook": "handle or page URL or null",
  "other_social": { "platform": "...", "handle": "..." } or null,
  "confidence": "high|medium|low",
  "notes": "..."
}

IMPORTANT: Only return information you are confident belongs to this specific person. 
Many people share common names. If you're not sure, set confidence to "low" and explain 
in notes. Do NOT fabricate any information.
```

**Sources to prioritize in results:**
- Official city/government pages (highest confidence)
- Campaign websites or candidate pages (high confidence, may have personal contact)
- LinkedIn profiles (high confidence for identity, sometimes has email)
- Local news articles that mention the mayor with contact info
- Community organization pages where the mayor serves on a board
- Ballotpedia pages (sometimes have social media links)

**Sources to deprioritize or skip:**
- Whitepages/Spokeo/BeenVerified type sites (privacy concern, often inaccurate)
- Random social media accounts that might not be the right person
- Outdated pages (check dates if visible)

### Step 3: Direct Social Media Search

If Instagram or Facebook weren't found in Steps 1-2, do targeted searches:

**Priority searches (Instagram and Facebook first):**
- `site:instagram.com "{mayor_name}" {city_name}`
- `site:facebook.com "{mayor_name}" mayor {city_name}`

**If the "other" slot is still empty, try:**
- `site:twitter.com OR site:x.com "{mayor_name}" {city_name}`
- `site:linkedin.com "{mayor_name}" {city_name} mayor`

**Verification is critical here.** Many people share names. Use Sonnet to verify by checking:
- Does the bio mention the city or "mayor"?
- Is the profile picture consistent with a public official?
- Does the account post about city business?

If verification is uncertain, flag as `needs_verification` and include the link for Max to check manually.

### Step 4: Consolidation & Deduplication

After all steps complete, consolidate findings:

- **Merge duplicates:** Same phone/email found on multiple pages → keep the highest-confidence source
- **Classify work vs personal:**
  - Emails on `@city.gov`, `@cityof__.org`, etc. → work
  - Emails on `@gmail.com`, `@yahoo.com`, `@outlook.com`, etc. → personal
  - Emails on `@campaign__.com` or personal domain → personal
- **Social media priority:** Instagram and Facebook get their own dedicated fields. If more than one other platform is found (e.g., Twitter AND LinkedIn), pick the one that appears more active or more relevant for political outreach — typically Twitter/X over LinkedIn for elected officials. The other gets dropped.
- **Write results to database** with source URLs for each field

---

## API Endpoints

### Trigger scraping
```
POST /api/contacts/scrape
Body: { city_ids: [1, 2, 3, ...] }
```
- Starts async scraping job for specified cities
- Returns `{ job_id: "...", city_count: N, estimated_time_seconds: N * 20 }`
- Each city takes ~15-30 seconds, so batch of 50 ≈ 15 minutes

### Check scraping status
```
GET /api/contacts/scrape/{job_id}
```
- Returns progress: `{ total: 50, completed: 23, failed: 2, in_progress: 1 }`

### Get contact results for a city
```
GET /api/cities/{id}/contacts
```
- Returns all scraped contact fields with sources

### Manual override
```
PATCH /api/cities/{id}/contacts
Body: { mayor_work_email: "...", mayor_work_email_source: "manual entry", ... }
```
- Max can always manually add/correct contact info

---

## Frontend Integration

### City Detail Panel — Contact Section Update

Replace the current two-column contact layout with a richer version:

**City contact (left column):** Same as before — general email, clerk, phone.

**Mayor contact (right column):** Now shows:
- Work email (with source link icon)
- Personal email (with source link icon)
- Work phone (with source link icon)
- Personal phone (with source link icon)
- Social media: Instagram handle (with IG icon, clickable), Facebook handle/page (with FB icon, clickable), other platform if present (with label + handle)
- Last scraped date
- "Re-scrape" button to refresh
- "Edit" button to manually correct any field

If a field is empty, show it grayed out with "Not found" — don't hide it. Max should always see what's missing.

If `contact_scrape_status` is `partial`, show a yellow indicator: "Some contact info may be incomplete — re-scrape or add manually."

### Batch Scraping from Pipeline View

Add to the batch action bar (appears when cities are selected):
- **"Scrape contacts"** button — triggers contact scraping for all selected cities
- Shows a progress toast/banner while scraping runs: "Scraping contacts: 23/50 complete..."
- When done, shows summary: "Found work email for 38/50, personal email for 12/50, Instagram for 22/50, Facebook for 29/50"

### Contact Completeness Indicators on Cards

In the kanban cards and table rows, add small indicator dots or icons:
- Green dot = has mayor direct email
- Half dot = has city contact only
- No dot = no contact info at all
This gives Max a quick visual scan of contact coverage across the pipeline.

---

## Rate Limiting & Cost Management

### DuckDuckGo
- Rate limit searches to ~1 per second
- Max 3-4 search queries per mayor
- For 483 mayors: ~1,500-2,000 searches total, spread over ~30-40 minutes

### Web fetching
- Rate limit page fetches to ~1 per second per domain (be polite to city websites)
- Timeout after 10 seconds per page
- Skip pages larger than 1MB (probably not useful)

### Claude API (Sonnet)
- Estimated 3-5 API calls per mayor (1 for city website, 1-2 for search results, 1 for social media, 1 for consolidation)
- For 483 mayors: ~1,500-2,500 API calls
- Use Sonnet (not Opus) — this is extraction work, not complex reasoning
- Estimated cost: $2-5 total for all 483 mayors (Sonnet is cheap for short extraction tasks)

### Suggested batch strategy
Don't scrape all 483 at once. Recommended approach:
1. **Tier 1 cities first** (~80-100 cities) — scrape, review results, tune prompts if needed
2. **Tier 2 cities** (~150 cities) — scrape next batch
3. **Tier 3 cities** (~250 cities) — scrape remainder
This lets Max verify quality on a small batch before committing to the full run.

---

## Resilience to Blanks & Partial Results

**Expect most records to be incomplete.** Out of 483 mayors, a realistic outcome might look like:

- Work email found: ~60-70% (many city websites list this)
- Work phone found: ~50-60% (often just the city hall main line)
- Personal email found: ~10-20% (only if they have a campaign site or public filing)
- Personal phone found: ~5-10% (rare, and should be used carefully)
- Instagram found: ~20-30% (mostly larger cities and younger mayors)
- Facebook found: ~30-40% (more common with local officials than Instagram)
- Other social found: ~15-25%

**This is fine.** A record with just a work email and a Facebook page is still vastly more useful than what Max started with. The system must treat partial data as the norm, not the exception.

### Design rules for handling blanks:

1. **Never mark a scrape as "failed" just because fields are empty.** A completed scrape that found nothing is `status: "completed"` with a log note saying what was searched. `status: "failed"` is reserved for technical errors (website down, API error, timeout).

2. **Use `"partial"` status generously.** If the scraper found a work email but nothing else, that's `"partial"` — which is a success, not a failure. The status values mean:
   - `completed` — all steps ran, found 3+ fields
   - `partial` — all steps ran, found 1-2 fields
   - `failed` — technical error prevented the scrape from running
   - `not_scraped` — hasn't been attempted yet

3. **Null fields stay null.** Don't fill blanks with "Not found" strings or placeholder text in the database. Use actual `NULL` values. The frontend handles display of empty fields.

4. **Don't retry aggressively.** If a mayor has no online presence, searching 10 different ways won't change that. The pipeline should run once, log what it tried, and move on. Max can manually add info later if he gets it through outreach.

5. **The scrape log should say what was attempted, not just what failed.** For example:
   ```
   Scraped 2026-03-16:
   - City website (cityofadelanto.gov): Found work phone, no mayor-specific email or social
   - DuckDuckGo search "Gabriel Reyes Adelanto mayor": No relevant results
   - Instagram search: No account found
   - Facebook search: No account found
   Result: 1 field populated (work phone). Status: partial.
   ```
   This way Max knows the search was thorough even though results were sparse — he won't waste time re-scraping a city that simply has nothing to find.

6. **Batch summary stats should normalize blanks.** After a batch scrape of 50 cities, the summary should read something like:
   ```
   Scrape complete: 50 cities
   - Work email: 34 found (68%)
   - Work phone: 28 found (56%)
   - Personal email: 7 found (14%)
   - Instagram: 12 found (24%)
   - Facebook: 19 found (38%)
   - 3 cities had no results at all
   - 0 technical failures
   ```
   This sets expectations that partial coverage is the norm.

7. **UI should distinguish "not found" from "not yet searched."** In the city detail panel:
   - Field not yet scraped → show grayed out with "Not yet searched"
   - Field scraped but not found → show grayed out with "Not found" and the last scrape date
   - Field found → show the value with source link
   This prevents Max from thinking a blank means "needs scraping" when it actually means "we looked and there's nothing there."

8. **Contact completeness score.** Each city gets a simple completeness indicator:
   - 🟢 **Strong** — has mayor direct email + at least one phone or social
   - 🟡 **Partial** — has at least one direct contact method (email OR phone OR social)
   - 🔴 **Minimal** — city contact only, no mayor-specific info
   - ⚪ **None** — nothing at all
   This shows on kanban cards and table rows so Max can visually scan coverage.

9. **Auto-advance pipeline status when a mayor email is found.** If the scraper finds any email address for the mayor (work or personal), and the city's current `outreach_status` is before `ready_for_outreach` in the pipeline (i.e., `no_contact_info`, `city_contact_only`, or `info_requested`), automatically advance the city to `ready_for_outreach`. Log the status change in `activity_log` with action `"auto_advanced"` and details like `"Moved to ready_for_outreach — mayor work email found via contact scraper."` This means a batch scrape of 50 cities in the "no contact info" column could instantly populate the "ready for outreach" column with every city where an email was found, without Max having to manually move each one.

---

## Edge Cases & Failure Handling

| Scenario | Handling |
|----------|----------|
| City website is down or unreachable | Log failure, skip to Step 2, flag for manual review |
| City website has no mayor page | Try common URL patterns, then fall back to DuckDuckGo search |
| Mayor name is very common (e.g., "John Smith") | Add city name to all searches, use Sonnet to verify identity, flag low-confidence results |
| Mayor was recently replaced (Roster is stale) | If scraping reveals a different current mayor, log this as a finding and flag `mayor_needs_verification` |
| Social media account is ambiguous | Flag as `needs_verification`, include link for Max to check |
| No contact info found at all | Set `contact_scrape_status: "completed"` with `contact_scrape_log: "No contact info found after full search"` — this is a valid outcome, don't keep retrying |
| Page content is behind JavaScript rendering | If basic fetch returns minimal content, note in log. Do NOT try to spin up a headless browser — it's not worth the complexity for this use case. |
| Rate limited by a website | Back off exponentially, skip after 3 retries, log for manual follow-up |

---

## Privacy & Ethics Notes

- **Only collect publicly available information.** Do not use paid people-search databases, data brokers, or scrape private directories.
- **Personal phone numbers should be flagged clearly.** Max should use professional judgment about whether to use personal vs. work contact info for outreach.
- **Do not scrape personal social media content** — only collect the account handle/URL for Max's reference. The CRM should not store posts, photos, or other social media content.
- **Source everything.** Every piece of contact info should have a source URL so Max can verify it and so there's a clear provenance trail.

---

## ⚠️ PDF Parsing Reminder (Applies Here Too)

The web pages this scraper fetches will be messy, inconsistent, and sometimes broken. The same principle applies: **use the Claude API to extract data from messy content.** Don't write elaborate regex patterns to parse city website HTML. Fetch the page, grab the text, send it to Sonnet, get structured data back. Simple.
