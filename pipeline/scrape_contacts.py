#!/usr/bin/env python3
"""
Mayor contact scraper — runs locally, writes directly to the Railway PostgreSQL database.

Steps per mayor:
  1. Fetch official city website → find mayor/council page → Sonnet extracts contact info
  2. DuckDuckGo web searches → fetch top results → Sonnet extracts contact info
  3. Targeted social media search (Instagram, Facebook, Twitter/X) if still missing
  4. Consolidate, classify work vs personal, write results + scrape log to DB

Usage:
    python scrape_contacts.py                       # all not_scraped cities, Tier 1 first
    python scrape_contacts.py --tier 1              # Tier 1 only
    python scrape_contacts.py --city-ids 1,2,3      # specific cities
    python scrape_contacts.py --limit 50            # cap at N cities
    python scrape_contacts.py --skip-scraped        # skip completed/partial cities
    python scrape_contacts.py --redo-failed         # only redo cities marked failed

Requirements (add to pip if missing):
    pip install requests beautifulsoup4
    (anthropic, python-dotenv, duckduckgo-search, sqlalchemy already in pipeline deps)
"""

import os
import sys
import time
import json
import argparse
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
import anthropic
from sqlalchemy import create_engine, text
from utils import get_anthropic_client

# ── Load environment ──────────────────────────────────────────────────────────
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

DATABASE_URL = os.getenv('DATABASE_URL', '')
if not DATABASE_URL:
    sys.exit('ERROR: DATABASE_URL not set in .env')
# SQLAlchemy requires postgresql:// not postgres://
DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)
client = get_anthropic_client()

SONNET = 'claude-sonnet-4-6'
FETCH_TIMEOUT = 10          # seconds per web request
MAX_PAGE_CHARS = 5_000      # chars sent to Sonnet per page
DDG_DELAY = 1.5             # seconds between DuckDuckGo queries
FETCH_DELAY = 1.0           # seconds between page fetches

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
}

# Thread safety
PRINT_LOCK = threading.Lock()
DDG_LOCK   = threading.Lock()   # one DDG query at a time across all workers

def _print(*args, **kwargs):
    with PRINT_LOCK:
        print(*args, **kwargs)

SKIP_DOMAINS = {
    'whitepages.com', 'spokeo.com', 'beenverified.com', 'intelius.com',
    'peoplefinder.com', 'truepeoplesearch.com', 'fastpeoplesearch.com',
    'radaris.com', 'instantcheckmate.com', 'mylife.com', 'zabasearch.com',
}

# Statuses that are already past the "no contact" stage — don't auto-advance
PRE_OUTREACH_STATUSES = {'no_contact_info', 'city_contact_only', 'info_requested'}


# ── Database helpers ───────────────────────────────────────────────────────────

def get_cities(tier=None, city_ids=None, wildfire_risk=None, skip_scraped=False, redo_failed=False, limit=None):
    conditions = []
    params = {}

    if city_ids:
        conditions.append('id = ANY(:ids)')
        params['ids'] = city_ids
    if tier:
        conditions.append('outreach_tier = :tier')
        params['tier'] = tier
    if wildfire_risk:
        conditions.append('wildfire_risk_tier = :wildfire_risk')
        params['wildfire_risk'] = wildfire_risk

    if redo_failed:
        conditions.append("contact_scrape_status = 'failed'")
    elif skip_scraped:
        conditions.append("contact_scrape_status NOT IN ('completed', 'partial')")
    else:
        conditions.append(
            "(contact_scrape_status IS NULL OR contact_scrape_status = 'not_scraped')"
        )

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    lim = f'LIMIT {limit}' if limit else ''

    sql = f"""
        SELECT id, city_name, county, mayor, city_website, city_email,
               outreach_status, outreach_tier,
               mayor_work_email, mayor_work_phone,
               mayor_personal_email, mayor_personal_phone,
               mayor_instagram, mayor_facebook
        FROM cities
        {where}
        ORDER BY
            CASE wildfire_risk_tier WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            outreach_tier ASC,
            fair_plan_policies DESC NULLS LAST
        {lim}
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [dict(r._mapping) for r in rows]


def save_results(city_id, results, log_lines, status):
    """Write scraped results to the cities table. Returns True if city was auto-advanced."""
    scrape_log = '\n'.join(log_lines)
    now = datetime.now(timezone.utc)

    fields = {
        'contact_scrape_status': status,
        'contact_scrape_date': now,
        'contact_scrape_log': scrape_log,
    }

    # Map scraper result keys → DB column pairs (value + source)
    field_map = [
        ('work_email',       'mayor_work_email',       'mayor_work_email_source'),
        ('work_phone',       'mayor_work_phone',       'mayor_work_phone_source'),
        ('personal_email',   'mayor_personal_email',   'mayor_personal_email_source'),
        ('personal_phone',   'mayor_personal_phone',   'mayor_personal_phone_source'),
        ('instagram',        'mayor_instagram',         'mayor_instagram_source'),
        ('facebook',         'mayor_facebook',          'mayor_facebook_source'),
    ]
    for key, col, src_col in field_map:
        if results.get(key):
            fields[col] = results[key]
        if results.get(f'{key}_source'):
            fields[src_col] = results[f'{key}_source']

    if results.get('other_social_platform'):
        fields['mayor_other_social_platform'] = results['other_social_platform']
        fields['mayor_other_social_handle'] = results.get('other_social_handle', '')
        fields['mayor_other_social_source'] = results.get('other_social_source')

    set_clauses = ', '.join(f'{k} = :{k}' for k in fields)
    params = {'city_id': city_id, **fields}

    advanced = False
    with engine.begin() as conn:
        conn.execute(text(f'UPDATE cities SET {set_clauses} WHERE id = :city_id'), params)

        # Auto-advance to ready_for_outreach if a mayor email was found
        if results.get('work_email') or results.get('personal_email'):
            row = conn.execute(
                text('SELECT outreach_status FROM cities WHERE id = :id'),
                {'id': city_id}
            ).fetchone()
            if row and row[0] in PRE_OUTREACH_STATUSES:
                email_type = 'work email' if results.get('work_email') else 'personal email'
                conn.execute(
                    text("UPDATE cities SET outreach_status = 'ready_for_outreach' WHERE id = :id"),
                    {'id': city_id}
                )
                conn.execute(
                    text("""
                        INSERT INTO activity_log (city_id, action, details, created_at)
                        VALUES (:city_id, 'auto_advanced', :details, now())
                    """),
                    {
                        'city_id': city_id,
                        'details': (
                            f"Moved to ready_for_outreach — mayor {email_type} "
                            f"found via contact scraper."
                        ),
                    }
                )
                advanced = True

    return advanced


# ── Web fetching ───────────────────────────────────────────────────────────────

def fetch_page(url):
    """
    Fetch a URL, return (content, resolved_url) or (None, url) on failure.

    Content = visible page text (capped) + a reference block of mailto: links
    and social media profile links extracted from raw HTML. This ensures
    emails/social handles that only appear inside <a href="..."> attributes
    (not as visible text) are still visible to Sonnet.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        # ── Extract mailto: links before stripping HTML ──────────────────────
        mailto_entries = []
        for m in re.finditer(r'<a\s[^>]*href="mailto:([^"]+)"[^>]*>(.*?)</a>',
                             html, re.IGNORECASE | re.DOTALL):
            email_addr = m.group(1).strip()
            link_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            entry = email_addr
            if link_text and link_text.lower() != email_addr.lower():
                entry += f' (link text: "{link_text}")'
            mailto_entries.append(entry)

        # ── Extract social media profile links ───────────────────────────────
        social_entries = []
        for m in re.finditer(
            r'<a\s[^>]*href="(https?://(?:www\.)?'
            r'(?:instagram|facebook|twitter|x|linkedin)\.com/[^"]+)"[^>]*>(.*?)</a>',
            html, re.IGNORECASE | re.DOTALL
        ):
            social_url = m.group(1).strip()
            link_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            entry = social_url
            if link_text:
                entry += f' (link text: "{link_text}")'
            social_entries.append(entry)

        # ── Build visible text ───────────────────────────────────────────────
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        visible = soup.get_text(separator=' ', strip=True)
        visible = re.sub(r'\s+', ' ', visible)[:MAX_PAGE_CHARS]

        # ── Append reference block if anything was found ─────────────────────
        extra_lines = []
        if mailto_entries:
            extra_lines.append('[mailto links found on page]')
            extra_lines.extend(mailto_entries)
        if social_entries:
            extra_lines.append('[social media links found on page]')
            extra_lines.extend(social_entries)

        content = visible
        if extra_lines:
            content += '\n\n' + '\n'.join(extra_lines)

        return content, str(resp.url)
    except Exception:
        return None, url


def find_mayor_page(base_url, city_name, mayor_name):
    """
    Try to find the mayor/council page on a city website.
    Returns (page_text, resolved_url).
    """
    # Step 1: Parse homepage links for mayor/council keywords
    try:
        resp = requests.get(base_url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        keywords = ['mayor', 'council', 'elected', 'official', 'government', 'leadership']
        best_link = None
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            if any(k in href for k in keywords):
                full = urljoin(base_url, a['href'])
                if urlparse(full).netloc == urlparse(base_url).netloc:
                    best_link = full
                    break  # take the first promising link
        if best_link:
            time.sleep(FETCH_DELAY)
            content, resolved = fetch_page(best_link)
            if content and len(content) > 200:
                return content, resolved
    except Exception:
        pass

    # Step 2: Try common URL patterns
    patterns = [
        '/mayor', '/city-council', '/council', '/elected-officials',
        '/government/mayor', '/government/city-council', '/about/mayor',
        '/your-government/mayor', '/city-hall/mayor', '/leadership',
    ]
    for pattern in patterns:
        time.sleep(0.5)
        url = base_url.rstrip('/') + pattern
        content, resolved = fetch_page(url)
        if content and len(content) > 200:
            return content, resolved

    # Step 3: Fall back to homepage text
    text, resolved = fetch_page(base_url)
    return text, resolved


# ── Sonnet extraction ──────────────────────────────────────────────────────────

def _parse_sonnet_json(raw):
    """Strip markdown fences and parse JSON."""
    raw = raw.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'```\s*$', '', raw)
    return json.loads(raw.strip())


def sonnet_extract_city_page(page_text, mayor_name, city_name, source_url):
    """Extract contact info from an official city website page."""
    prompt = f"""You are extracting contact information for a political outreach campaign. \
Your job is to find every usable piece of contact info on this page. Be thorough and aggressive — \
missing a real piece of contact info is a worse mistake than flagging something for review.

Mayor name: {mayor_name}
City: {city_name}

Page content:
---
{page_text}
---

Extract ALL of the following that appear anywhere on the page:

EMAILS — look everywhere: mailto: links, contact forms, staff directories, \
"Email the Mayor" buttons, footer text, sidebar bios. If you see any email address \
associated with the mayor or their office, capture it.

PHONE NUMBERS — look for any number labeled as the mayor's direct line, \
cell, or office. If the only number on the page is the general city hall line \
but it's the only way to reach the mayor, capture it anyway and note it in work_phone.

SOCIAL MEDIA — look for profile links, icons with href attributes, \
"Follow us" sections, bio pages. Capture Instagram, Facebook, Twitter/X, LinkedIn.

Return ONLY valid JSON:
{{
  "work_phone": "phone number or null",
  "work_email": "email address or null",
  "instagram": "@handle or null",
  "facebook": "handle or full page URL or null",
  "other_social": {{"platform": "platform name", "handle": "handle or URL"}} or null,
  "notes": "what you found and where, or what was missing"
}}

If a field is genuinely not present anywhere on the page, use null. \
Do NOT fabricate — but do not be overly cautious either. \
A real email address you spotted is always worth returning."""

    try:
        resp = client.messages.create(
            model=SONNET, max_tokens=400,
            messages=[{'role': 'user', 'content': prompt}]
        )
        data = _parse_sonnet_json(resp.content[0].text)
        result = {}
        if data.get('work_phone'):
            result['work_phone'] = data['work_phone']
            result['work_phone_source'] = source_url
        if data.get('work_email'):
            result['work_email'] = data['work_email']
            result['work_email_source'] = source_url
        if data.get('instagram'):
            result['instagram'] = data['instagram']
            result['instagram_source'] = source_url
        if data.get('facebook'):
            result['facebook'] = data['facebook']
            result['facebook_source'] = source_url
        if data.get('other_social') and data['other_social'].get('platform'):
            result['other_social_platform'] = data['other_social']['platform']
            result['other_social_handle'] = data['other_social'].get('handle', '')
            result['other_social_source'] = source_url
        return result, data.get('notes', '')
    except Exception as e:
        return {}, f'Sonnet error: {e}'


PERSONAL_DOMAINS = {
    'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com',
    'icloud.com', 'me.com', 'aol.com', 'protonmail.com',
}


def sonnet_extract_search_result(page_text, mayor_name, city_name, source_url):
    """Extract contact info from a general web page found via search."""
    prompt = f"""You are extracting contact information for a political outreach campaign. \
Your job is to find every usable email address, phone number, and social media account \
for this specific person. Be thorough — missing a real contact is worse than flagging \
something as medium confidence.

Target: {mayor_name}, Mayor of {city_name}, California.

Content (may include webpage text, search snippets, or PDF excerpts):
---
{page_text}
---

Extract everything that plausibly belongs to this person:

EMAILS — capture any email address associated with this mayor. \
Work emails typically end in a city/gov domain. Personal emails are gmail/yahoo/etc \
or campaign domains. If you see an email that might be theirs, return it — \
don't skip it just because you're not 100% sure.

PHONE NUMBERS — capture any number that could be this mayor's direct line, \
cell, campaign phone, or city office. If you see a number near their name, capture it.

SOCIAL MEDIA — Instagram, Facebook, Twitter/X, LinkedIn handles or profile URLs.

IDENTITY CHECK — many people share names. Before returning anything, confirm \
the content is about this specific person (e.g., mentions {city_name}, "mayor", \
or other identifying details). If it's clearly a different person, return confidence "low". \
If it's probably the right person but not 100% certain, return confidence "medium" — \
still return the data.

Return ONLY valid JSON:
{{
  "phones": [{{"number": "...", "type": "work|personal|unknown", "context": "where you saw it"}}],
  "emails": [{{"address": "...", "type": "work|personal|unknown", "context": "where you saw it"}}],
  "instagram": "@handle or null",
  "facebook": "handle or page URL or null",
  "other_social": {{"platform": "...", "handle": "..."}} or null,
  "confidence": "high|medium|low",
  "notes": "brief summary of what you found"
}}

Do NOT fabricate. But do return real data you spotted even if confidence is medium."""

    try:
        resp = client.messages.create(
            model=SONNET, max_tokens=500,
            messages=[{'role': 'user', 'content': prompt}]
        )
        data = _parse_sonnet_json(resp.content[0].text)

        if data.get('confidence') == 'low':
            return {}, f'Skipped (low confidence, likely wrong person): {source_url}'

        result = {}

        for phone_obj in (data.get('phones') or []):
            number = phone_obj.get('number')
            if not number:
                continue
            ptype = phone_obj.get('type', 'unknown')
            if ptype == 'work' and not result.get('work_phone'):
                result['work_phone'] = number
                result['work_phone_source'] = source_url
            elif ptype == 'personal' and not result.get('personal_phone'):
                result['personal_phone'] = number
                result['personal_phone_source'] = source_url
            elif ptype == 'unknown' and not result.get('work_phone'):
                result['work_phone'] = number
                result['work_phone_source'] = source_url

        for email_obj in (data.get('emails') or []):
            address = email_obj.get('address')
            if not address or '@' not in address:
                continue
            domain = address.split('@')[-1].lower()
            etype = email_obj.get('type', 'unknown')
            if etype == 'work' and not result.get('work_email'):
                result['work_email'] = address
                result['work_email_source'] = source_url
            elif etype == 'personal' and not result.get('personal_email'):
                result['personal_email'] = address
                result['personal_email_source'] = source_url
            elif etype == 'unknown':
                if domain in PERSONAL_DOMAINS and not result.get('personal_email'):
                    result['personal_email'] = address
                    result['personal_email_source'] = source_url
                elif not result.get('work_email'):
                    result['work_email'] = address
                    result['work_email_source'] = source_url

        if data.get('instagram') and not result.get('instagram'):
            result['instagram'] = data['instagram']
            result['instagram_source'] = source_url
        if data.get('facebook') and not result.get('facebook'):
            result['facebook'] = data['facebook']
            result['facebook_source'] = source_url
        if (data.get('other_social') and data['other_social'].get('platform')
                and not result.get('other_social_platform')):
            result['other_social_platform'] = data['other_social']['platform']
            result['other_social_handle'] = data['other_social'].get('handle', '')
            result['other_social_source'] = source_url

        return result, data.get('notes', '')
    except Exception as e:
        return {}, f'Sonnet error: {e}'


# ── Result merging ─────────────────────────────────────────────────────────────

def merge(base, new):
    """Merge new findings into base without overwriting existing values."""
    merged = dict(base)
    for k, v in new.items():
        if v and not merged.get(k):
            merged[k] = v
    return merged


def has_all_key_fields(r):
    return all(r.get(k) for k in ['work_email', 'work_phone', 'instagram', 'facebook'])


# ── Per-city scrape pipeline ───────────────────────────────────────────────────

def scrape_city(city, on_step=None):
    city_name = city['city_name']
    mayor_name = city['mayor'] or 'Unknown'
    city_website = city.get('city_website') or ''
    results = {}
    log = []

    def step(desc):
        if on_step:
            on_step(desc)

    # ── Step 1: Official city website ─────────────────────────────────────────
    if city_website:
        log.append(f'Step 1: City website ({city_website})')
        step('step 1: city website')
        page_text, resolved_url = find_mayor_page(city_website, city_name, mayor_name)
        time.sleep(FETCH_DELAY)
        if page_text:
            extracted, notes = sonnet_extract_city_page(page_text, mayor_name, city_name, resolved_url)
            results = merge(results, extracted)
            found = [k for k in ['work_phone', 'work_email', 'instagram', 'facebook'] if extracted.get(k)]
            log.append(f'  Found: {", ".join(found) if found else "nothing"}' +
                       (f' — {notes}' if notes else ''))
        else:
            log.append('  Website unreachable or returned no content — falling back to search')
    else:
        log.append('Step 1: No city website in DB — skipped')

    # ── Step 2: DuckDuckGo web search ─────────────────────────────────────────
    log.append('Step 2: DuckDuckGo search')
    step('step 2: web search')
    ddg_queries = [
        f'"{mayor_name}" "{city_name}" California email phone contact',
        f'"{mayor_name}" "{city_name}" mayor email',
    ]
    if not (results.get('instagram') and results.get('facebook')):
        ddg_queries.append(
            f'"{mayor_name}" "{city_name}" Instagram OR Facebook OR Twitter'
        )

    seen_urls = set()

    for query in ddg_queries:
        if has_all_key_fields(results):
            log.append('  All key fields found — stopping DDG searches early')
            break

        with DDG_LOCK:
            time.sleep(DDG_DELAY)
            try:
                ddg_results = list(DDGS().text(query, max_results=6))
            except Exception as e:
                log.append(f'  DDG error on query "{query[:60]}": {e}')
                continue

        log.append(f'  "{query[:70]}" → {len(ddg_results)} results')

        for r in ddg_results:
            url = r.get('href', '')
            if not url or url in seen_urls:
                continue
            domain = urlparse(url).netloc.lower().lstrip('www.')
            if any(domain.endswith(s) for s in SKIP_DOMAINS):
                continue
            seen_urls.add(url)

            # Always capture the DDG snippet — it often contains emails from PDFs
            # or pages we can't otherwise parse
            snippet_text = '\n'.join(filter(None, [r.get('title', ''), r.get('body', '')]))

            if url.lower().endswith('.pdf'):
                # Don't try to fetch PDFs — use the snippet alone
                content, resolved = snippet_text, url
            else:
                time.sleep(FETCH_DELAY)
                page_text, resolved = fetch_page(url)
                # Prepend page content, append snippet as fallback context
                if page_text:
                    content = page_text + '\n\n[search snippet]\n' + snippet_text
                else:
                    content = snippet_text  # snippet is better than nothing

            if not content.strip():
                continue

            extracted, notes = sonnet_extract_search_result(
                content, mayor_name, city_name, resolved
            )
            if extracted:
                results = merge(results, extracted)
                found = [k for k in
                         ['work_email', 'personal_email', 'work_phone', 'personal_phone',
                          'instagram', 'facebook']
                         if extracted.get(k)]
                if found:
                    log.append(f'    {domain}: found {", ".join(found)}')

    # ── Step 3: Targeted social media search ──────────────────────────────────
    social_targets = []
    if not results.get('instagram'):
        social_targets.append(('instagram', f'site:instagram.com "{mayor_name}" {city_name}'))
    if not results.get('facebook'):
        social_targets.append(('facebook', f'site:facebook.com "{mayor_name}" mayor {city_name}'))
    if not results.get('other_social_platform'):
        social_targets.append(('twitter', f'site:twitter.com OR site:x.com "{mayor_name}" {city_name} mayor'))

    if social_targets:
        log.append('Step 3: Direct social media search')
        step('step 3: social search')
        for field, query in social_targets:
            with DDG_LOCK:
                time.sleep(DDG_DELAY)
                try:
                    ddg_results = list(DDGS().text(query, max_results=3))
                except Exception as e:
                    log.append(f'  DDG error: {e}')
                    continue

            for r in ddg_results:
                url = r.get('href', '')
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                # Quick identity check using snippet before fetching full page
                snippet = (r.get('body', '') + ' ' + r.get('title', '')).lower()
                last_name = mayor_name.split()[-1].lower() if mayor_name else ''
                if city_name.lower() not in snippet and last_name not in snippet:
                    continue

                if field == 'instagram' and 'instagram.com' in url:
                    m = re.search(r'instagram\.com/([^/?#]+)', url)
                    if m and m.group(1) not in ('p', 'reel', 'explore', 'stories'):
                        results['instagram'] = '@' + m.group(1)
                        results['instagram_source'] = url
                        log.append(f'  Instagram: @{m.group(1)} (unverified — check manually)')
                        break

                elif field == 'facebook' and 'facebook.com' in url:
                    results['facebook'] = url
                    results['facebook_source'] = url
                    log.append(f'  Facebook: {url} (unverified — check manually)')
                    break

                elif field == 'twitter':
                    for pattern in [r'twitter\.com/([^/?#]+)', r'x\.com/([^/?#]+)']:
                        m = re.search(pattern, url)
                        if m and m.group(1) not in ('i', 'home', 'search', 'hashtag', 'intent'):
                            results['other_social_platform'] = 'Twitter/X'
                            results['other_social_handle'] = '@' + m.group(1)
                            results['other_social_source'] = url
                            log.append(f'  Twitter/X: @{m.group(1)} (unverified — check manually)')
                            break
    else:
        log.append('Step 3: Skipped — Instagram and Facebook already found')

    # ── Step 3b: Targeted email search if still no email ──────────────────────
    if not results.get('work_email') and not results.get('personal_email'):
        step('step 3b: email search')
        log.append('Step 3b: Targeted email search (no email found yet)')
        email_queries = [
            f'"{mayor_name}" {city_name} California mayor email',
            f'"{mayor_name}" {city_name} "@" contact',
        ]
        for query in email_queries:
            if results.get('work_email') or results.get('personal_email'):
                break
            with DDG_LOCK:
                time.sleep(DDG_DELAY)
                try:
                    ddg_results = list(DDGS().text(query, max_results=8))
                except Exception as e:
                    log.append(f'  DDG error: {e}')
                    continue

            log.append(f'  "{query[:70]}" → {len(ddg_results)} results')
            for r in ddg_results:
                url = r.get('href', '')
                if not url or url in seen_urls:
                    continue
                domain = urlparse(url).netloc.lower().lstrip('www.')
                if any(domain.endswith(s) for s in SKIP_DOMAINS):
                    continue
                seen_urls.add(url)

                snippet_text = '\n'.join(filter(None, [r.get('title', ''), r.get('body', '')]))

                # Quick regex scan of snippet for email addresses before fetching
                quick_emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', snippet_text)
                if quick_emails:
                    log.append(f'  Snippet email hit on {domain}: {quick_emails[0]}')

                if url.lower().endswith('.pdf'):
                    content, resolved = snippet_text, url
                else:
                    time.sleep(FETCH_DELAY)
                    page_text, resolved = fetch_page(url)
                    content = (page_text + '\n\n[search snippet]\n' + snippet_text) if page_text else snippet_text

                if not content.strip():
                    continue

                extracted, notes = sonnet_extract_search_result(
                    content, mayor_name, city_name, resolved
                )
                if extracted:
                    results = merge(results, extracted)
                    found = [k for k in ['work_email', 'personal_email'] if extracted.get(k)]
                    if found:
                        log.append(f'    {domain}: found {", ".join(found)}')
                        break  # got an email — stop scanning results for this query

    # ── Step 4: Determine status ───────────────────────────────────────────────
    found_fields = [
        k for k in ['work_email', 'personal_email', 'work_phone', 'personal_phone',
                    'instagram', 'facebook', 'other_social_platform']
        if results.get(k)
    ]
    n = len(found_fields)

    if n == 0:
        status = 'completed'
        log.append('Result: No contact info found after full search. Status: completed.')
    elif n <= 2:
        status = 'partial'
        log.append(f'Result: {n} field(s) found ({", ".join(found_fields)}). Status: partial.')
    else:
        status = 'completed'
        log.append(f'Result: {n} fields found ({", ".join(found_fields)}). Status: completed.')

    return results, log, status


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Scrape mayor contact info into the CRM database'
    )
    parser.add_argument('--tier', type=int, choices=[1, 2, 3],
                        help='Only scrape cities of this tier')
    parser.add_argument('--city-ids',
                        help='Comma-separated city IDs to scrape')
    parser.add_argument('--limit', type=int,
                        help='Stop after N cities')
    parser.add_argument('--skip-scraped', action='store_true',
                        help='Skip cities already marked completed or partial')
    parser.add_argument('--wildfire-risk', choices=['high', 'medium', 'low'],
                        help='Only scrape cities with this wildfire risk tier')
    parser.add_argument('--redo-failed', action='store_true',
                        help='Only redo cities marked as failed')
    parser.add_argument('--workers', type=int, default=3,
                        help='Parallel workers (default 3; use 1 for sequential)')
    args = parser.parse_args()

    city_ids = (
        [int(x.strip()) for x in args.city_ids.split(',')]
        if args.city_ids else None
    )

    cities = get_cities(
        tier=args.tier,
        city_ids=city_ids,
        wildfire_risk=args.wildfire_risk,
        skip_scraped=args.skip_scraped,
        redo_failed=args.redo_failed,
        limit=args.limit,
    )

    if not cities:
        print('No cities to scrape (all may already be scraped — use --skip-scraped to re-run).')
        return

    total = len(cities)
    workers = min(args.workers, total)
    print(f'Scraping contact info for {total} cities  '
          f'[{workers} worker{"s" if workers > 1 else ""},'
          f' high-wildfire-risk first]')
    print('Results write to DB after each city — safe to interrupt with Ctrl+C.\n')

    stats = {'completed': 0, 'partial': 0, 'failed': 0, 'advanced': 0}
    field_counts = {
        'work_email': 0, 'personal_email': 0,
        'work_phone': 0, 'personal_phone': 0,
        'instagram': 0, 'facebook': 0,
    }
    completed_count = 0
    WIDTH = 28
    pad = len(str(total))

    def process(city):
        city_col = city['city_name'][:WIDTH].ljust(WIDTH)

        if workers == 1:
            # Sequential mode: live step updates on same line
            prefix = f'[{cities.index(city)+1:>{pad}}/{total}]'

            def on_step(desc, _p=prefix, _c=city_col):
                print(f'\r{_p} {_c}  {desc:<32}', end='', flush=True)

            on_step('starting...')
        else:
            on_step = None
            _print(f'  → starting  {city_col}')

        results, log, status = scrape_city(city, on_step=on_step)
        advanced = save_results(city['id'], results, log, status)

        found_fields = [f for f in ['work_email', 'personal_email', 'work_phone',
                                    'personal_phone', 'instagram', 'facebook']
                        if results.get(f)]
        result_str = ', '.join(found_fields) if found_fields else 'nothing found'
        adv_str = '  ↑ advanced' if advanced else ''

        nonlocal completed_count
        with PRINT_LOCK:
            completed_count += 1
            prefix = f'[{completed_count:>{pad}}/{total}]'
            print(f'\r{prefix} {city_col}  {status}: {result_str}{adv_str}')

        return results, status, advanced

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process, city): city for city in cities}
        try:
            for future in as_completed(futures):
                try:
                    results, status, advanced = future.result()
                    stats[status] = stats.get(status, 0) + 1
                    if advanced:
                        stats['advanced'] += 1
                    for field in field_counts:
                        if results.get(field):
                            field_counts[field] += 1
                except Exception as e:
                    city = futures[future]
                    save_results(city['id'], {}, [f'Unexpected error: {e}'], 'failed')
                    stats['failed'] = stats.get('failed', 0) + 1
                    _print(f'  ERROR {city["city_name"]}: {e}')
        except KeyboardInterrupt:
            _print('\n\nInterrupted — results so far have been saved to DB.')

    print(f'\n{"=" * 50}')
    print(f'Scrape complete: {total} cities')
    print(f'  Completed: {stats.get("completed", 0)}  '
          f'Partial: {stats.get("partial", 0)}  '
          f'Failed: {stats.get("failed", 0)}')
    print(f'  Auto-advanced to ready_for_outreach: {stats["advanced"]}')
    print()
    for field, count in field_counts.items():
        label = field.replace('_', ' ').title()
        pct = count * 100 // total if total else 0
        print(f'  {label:<20} {count}/{total} ({pct}%)')


if __name__ == '__main__':
    main()
