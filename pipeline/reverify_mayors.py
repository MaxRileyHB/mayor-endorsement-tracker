"""
Re-verify current mayors against live web search, updating the DB in place.

Strategy per city (in priority order):
  1. Fetch the city's official website (city_website field) — council/leadership pages
  2. DDG search biased toward .gov and official city domains
  3. Fetch top search result URLs

Uses Sonnet for extraction with full awareness of CA mayoral rotation.
Conservative by design: only commits changes on HIGH confidence; flags everything else.

Usage:
  py reverify_mayors.py                     # verify all cities
  py reverify_mayors.py --resume            # resume from partial progress
  py reverify_mayors.py --test 20           # test on first 20, print verbose (no DB writes)
  py reverify_mayors.py --flagged-only      # only re-check cities with mayor_needs_verification=True
  py reverify_mayors.py --review-flags      # interactively review flagged cities from the last run
"""
import sys
import json
import re
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from database import SessionLocal
from models import City
from utils import OUTPUT_DIR, Progress, get_anthropic_client

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

PROGRESS_FILE = OUTPUT_DIR / "reverify_progress.json"
LOG_FILE = OUTPUT_DIR / "reverify_log.json"

FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

SYSTEM_PROMPT = """You are a careful research assistant helping verify who is the current mayor of a California city.

IMPORTANT CONTEXT about California mayors:
- Most California cities use a "council-manager" form of government. The mayor is typically a ROTATING title held by an elected city council member, usually for a one-year term.
- The mayor is often selected from among sitting council members and rotates on a set schedule — commonly at the start of each calendar year or each fiscal year.
- The previous mayor usually stays on the city council as a regular member (they are NOT gone or out of office).
- A "mayor pro tem" or "vice mayor" is typically next in the rotation and may have already become mayor.
- Because of this rotation, mayoral changes happen frequently and are entirely normal. A name you do not recognize is not suspicious.
- Official city websites (city.cityname.ca.gov, cityname.gov, cityname.org) are the most authoritative source.
- News articles from 2024 or 2025 are reliable. Older articles should be treated with caution.

Your job: given web content about a city, determine who is the CURRENT mayor with high confidence. Be conservative — if the content is ambiguous or outdated, say so."""


COUNCIL_LINK_KEYWORDS = [
    "city council", "city-council", "citycouncil",
    "town council", "town-council",
    "mayor", "elected officials", "elected-officials",
    "council members", "councilmembers", "council member",
    "city government", "city-government",
    "leadership", "your council", "meet the council",
    "governing body", "representatives",
    "/council", "/mayor", "/elected", "/government/city",
]

# Nav-like div class names to also search
NAV_CLASS_PATTERNS = re.compile(
    r"\b(nav|menu|navigation|header|masthead|topbar|top-bar|site-header)\b", re.I
)


def collect_nav_links(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    """
    Collect all (link_text, absolute_url) pairs from nav-like areas of the page.
    Returns deduplicated list, nav/header links first.
    """
    from urllib.parse import urljoin

    priority_roots = soup.find_all(["nav", "header"])
    for tag in soup.find_all(["div", "ul", "section"], class_=True):
        classes = " ".join(tag.get("class", []))
        if NAV_CLASS_PATTERNS.search(classes):
            priority_roots.append(tag)

    all_roots = priority_roots + [soup]
    seen_urls = set()
    links = []

    for root in all_roots:
        for a in root.find_all("a", href=True):
            href = a["href"]
            if not href or href.startswith("#") or href.startswith("mailto:"):
                continue
            text = a.get_text(" ", strip=True)
            if not text:
                continue
            full = urljoin(base_url, href)
            if full in seen_urls:
                continue
            seen_urls.add(full)
            links.append((text, full))

    return links


def find_council_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """
    Fast keyword-based filter: return URLs whose link text or href contains
    obvious council/mayor keywords. Used as a first pass before Haiku.
    """
    results = []
    for text, url in collect_nav_links(soup, base_url):
        combined = (text + " " + url).lower()
        if any(kw in combined for kw in COUNCIL_LINK_KEYWORDS):
            results.append((text, url))

    # Sort by keyword quality
    def score(item):
        t = (item[0] + " " + item[1]).lower()
        if "city council" in t or "town council" in t:
            return 0
        if "mayor" in t and "pro" not in t:
            return 1
        if "elected" in t or "council member" in t:
            return 2
        return 3

    results.sort(key=score)
    return [url for _, url in results]


def find_council_link_haiku(soup: BeautifulSoup, base_url: str, city_name: str, client) -> str | None:
    """
    Ask Haiku to pick the best council/mayor link from the page's navigation.
    Used as a fallback when keyword matching finds nothing.
    """
    all_links = collect_nav_links(soup, base_url)
    if not all_links:
        return None

    # Limit to first 60 links to keep the prompt small
    link_list = "\n".join(
        f"{i + 1}. {text}" for i, (text, _) in enumerate(all_links[:60])
    )

    prompt = f"""You are looking at the navigation menu of the official website for {city_name}, California.

Here are the navigation links on the page:
{link_list}

Which single link is most likely to lead to a page listing the current mayor or city council members? Reply with ONLY the number. If none seem relevant, reply with "none"."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.content[0].text.strip().lower()
        if answer == "none":
            return None
        m = re.match(r"\d+", answer)
        if m:
            idx = int(m.group()) - 1
            if 0 <= idx < len(all_links):
                return all_links[idx][1]
    except Exception:
        pass

    return None


def extract_text(soup: BeautifulSoup, city_bare: str, on_official_domain: bool = False) -> str | None:
    """Strip boilerplate and return mayor-focused text, or None if not useful.

    Strips nav/header elements before extracting text so that "mayor" appearing
    as a menu link label doesn't fool the window into returning navigation content.
    When on the official city domain we skip the city-name check.
    """
    # Work on a copy so we don't destroy the soup for link-finding later
    soup = BeautifulSoup(str(soup), "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    # Also strip nav-like divs by class
    for tag in soup.find_all(["div", "ul", "section"], class_=True):
        if NAV_CLASS_PATTERNS.search(" ".join(tag.get("class", []))):
            tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    if "mayor" not in text.lower():
        return None
    if not on_official_domain and city_bare not in text.lower():
        return None
    idx = text.lower().find("mayor")
    start = max(0, idx - 200)
    return text[start: start + 5000]


def fetch_official_site(city_website: str, city_name: str, client=None) -> tuple[str | None, str | None]:
    """
    1. Fetch the city homepage and collect all council/mayor candidate links.
    2. Try each candidate link in priority order.
    3. If a candidate page has further council/mayor links, follow one level deeper.
    4. Fall back to the homepage itself if nothing better is found.
    Returns (text_content, url_used) or (None, None).
    """
    if not city_website:
        return None, None

    base = city_website.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    from urllib.parse import urlparse

    city_bare = re.sub(r'^(City|Town)\s+of\s+', '', city_name, flags=re.I).strip().lower()
    official_domain = urlparse(base).netloc.lower()

    def is_official(url: str) -> bool:
        return urlparse(url).netloc.lower() == official_domain

    try:
        r = requests.get(base, timeout=10, headers=FETCH_HEADERS, allow_redirects=True)
        if not r.ok:
            return None, None
        homepage_soup = BeautifulSoup(r.content, "html.parser")
    except Exception:
        return None, None

    candidate_urls = find_council_links(homepage_soup, base)

    # If keyword matching found nothing, ask Haiku to pick from the nav links
    if not candidate_urls and client:
        haiku_url = find_council_link_haiku(homepage_soup, base, city_name, client)
        if haiku_url:
            candidate_urls = [haiku_url]

    # Always include the homepage as final fallback
    all_targets = candidate_urls + [base]
    visited = set()

    for url in all_targets:
        if url in visited:
            continue
        visited.add(url)

        try:
            if url == base:
                soup = homepage_soup
            else:
                time.sleep(0.3)
                r2 = requests.get(url, timeout=10, headers=FETCH_HEADERS, allow_redirects=True)
                if not r2.ok:
                    continue
                soup = BeautifulSoup(r2.content, "html.parser")

            text = extract_text(soup, city_bare, on_official_domain=is_official(url))
            if text:
                return text, url

            # Page loaded but no mayor info — look one level deeper for a sub-link
            deeper_urls = find_council_links(soup, url)
            if not deeper_urls and client:
                haiku_url = find_council_link_haiku(soup, url, city_name, client)
                if haiku_url:
                    deeper_urls = [haiku_url]
            for deep_url in deeper_urls[:3]:
                if deep_url in visited:
                    continue
                visited.add(deep_url)
                try:
                    time.sleep(0.3)
                    r3 = requests.get(deep_url, timeout=10, headers=FETCH_HEADERS, allow_redirects=True)
                    if not r3.ok:
                        continue
                    deep_soup = BeautifulSoup(r3.content, "html.parser")
                    deep_text = extract_text(deep_soup, city_bare, on_official_domain=is_official(deep_url))
                    if deep_text:
                        return deep_text, deep_url
                except Exception:
                    continue

        except Exception:
            continue

    return None, None


def search_ddg(city_name: str, city_website: str | None, ddgs) -> tuple[str | None, list[str]]:
    """
    Search DuckDuckGo for the current mayor, biased toward official sources.
    Returns (snippets_text, result_urls).
    """
    # General web search — fetch_official_site already handles direct site access
    queries = [f"{city_name} California current mayor city council"]

    for query in queries:
        try:
            results = list(ddgs.text(query, max_results=6, region="us-en"))
            if results:
                # Sort: official/gov URLs first
                def score(r):
                    href = r.get("href", "")
                    if city_website and city_website in href:
                        return 0
                    if ".gov" in href or ".ca.gov" in href:
                        return 1
                    if "city" in href.lower() and city_name.split()[-1].lower() in href.lower():
                        return 2
                    return 3

                results.sort(key=score)
                snippets = "\n".join(
                    f"[{r.get('href', '')}] {r.get('title', '')} — {r.get('body', '')}"
                    for r in results
                )
                urls = [r["href"] for r in results if r.get("href")]
                return snippets, urls
        except Exception as e:
            if "ratelimit" in str(e).lower() or "202" in str(e):
                print(f"    DDG rate limit — waiting 30s...")
                time.sleep(30)
            else:
                print(f"    DDG error for {city_name}: {e}")

    return None, []


def fetch_url_text(url: str, city_name: str, max_chars: int = 5000) -> str | None:
    city_bare = re.sub(r'^(City|Town)\s+of\s+', '', city_name, flags=re.I).strip().lower()
    try:
        r = requests.get(url, timeout=10, headers=FETCH_HEADERS, allow_redirects=True)
        if not r.ok:
            return None
        soup = BeautifulSoup(r.content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        if city_bare not in text.lower() or "mayor" not in text.lower():
            return None
        idx = text.lower().find("mayor")
        start = max(0, idx - 200)
        return text[start: start + max_chars]
    except Exception:
        return None


def extract_mayor_with_sonnet(content: str, city_name: str, current_mayor: str, pro_tem: str,
                               client, source: str = "search results") -> dict:
    """
    Ask Sonnet to identify the current mayor with a confidence rating.
    Returns: {choice: 1|2|3|4, name: str|None, confidence: "high"|"medium"|"low", reasoning: str}
      1 = stored mayor confirmed current
      2 = pro tem is now mayor (rotation)
      3 = someone else entirely (name provided)
      4 = cannot determine
    """
    user_prompt = f"""Here is content from {source} about {city_name}, California:

---
{content[:4500]}
---

The mayor currently stored in our database is: {current_mayor}
The mayor pro tem / vice mayor is: {pro_tem or "unknown"}

Based on this content, who is the CURRENT mayor of {city_name}?

Choose one:
1. {current_mayor} — our stored mayor is still current
2. {pro_tem or "N/A"} — the pro tem has rotated into the mayor role
3. Someone else — provide their full name (common in rotation cities)
4. Cannot determine — content is too ambiguous or outdated to be sure

Reply in this exact format (nothing else):
CHOICE: <1, 2, 3, or 4>
NAME: <full name, or blank if choice is 4>
CONFIDENCE: <high, medium, or low>
REASONING: <one sentence explaining what the source said>"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )
        text = response.content[0].text.strip()

        choice = 4
        name = None
        confidence = "low"
        reasoning = ""

        for line in text.splitlines():
            line = line.strip()
            if line.startswith("CHOICE:"):
                val = line.split(":", 1)[1].strip()
                choice = int(val[0]) if val and val[0].isdigit() else 4
            elif line.startswith("NAME:"):
                name = line.split(":", 1)[1].strip() or None
            elif line.startswith("CONFIDENCE:"):
                confidence = line.split(":", 1)[1].strip().lower()
            elif line.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()

        # Override name for choices 1 and 2
        if choice == 1:
            name = current_mayor
        elif choice == 2:
            name = pro_tem or name

        return {"choice": choice, "name": name, "confidence": confidence, "reasoning": reasoning}

    except Exception as e:
        return {"choice": 4, "name": None, "confidence": "low", "reasoning": f"API error: {e}"}


def verify_city_from_db(city, ddgs, client) -> dict:
    city_name = city.city_name
    current_mayor = city.mayor or ""
    pro_tem = city.mayor_pro_tem or ""
    city_website = city.city_website or ""

    result = {
        "city_id": city.id,
        "city_name": city_name,
        "stored_mayor": current_mayor,
        "pro_tem": pro_tem,
        "action": None,
        "new_mayor": None,
        "search_found": None,
        "confidence": None,
        "reasoning": None,
        "notes": None,
        "source": None,
    }

    sonnet = None

    # ── Step 1: Try official city website ──────────────────────────────────────
    official_text, official_url = fetch_official_site(city_website, city_name, client=client)
    if official_text:
        sonnet = extract_mayor_with_sonnet(
            official_text, city_name, current_mayor, pro_tem, client,
            source=f"official city website ({official_url})"
        )
        result["source"] = official_url

    # ── Step 2: DDG search (always run; use best result if official failed or was low-confidence) ──
    if sonnet is None or sonnet["confidence"] == "low":
        snippets, urls = search_ddg(city_name, city_website, ddgs)

        if snippets:
            sonnet_ddg = extract_mayor_with_sonnet(
                snippets, city_name, current_mayor, pro_tem, client,
                source="DuckDuckGo search snippets"
            )
            # Use DDG result if we had no result yet, or if DDG is more confident
            if sonnet is None or sonnet_ddg["confidence"] in ("high", "medium") and sonnet["confidence"] == "low":
                sonnet = sonnet_ddg
                result["source"] = "ddg_snippets"

            # ── Step 3: Fetch top URLs if still uncertain ──────────────────────
            if sonnet is None or sonnet["confidence"] == "low":
                for url in urls[:3]:
                    page_text = fetch_url_text(url, city_name)
                    if page_text:
                        sonnet_page = extract_mayor_with_sonnet(
                            page_text, city_name, current_mayor, pro_tem, client,
                            source=f"page {url}"
                        )
                        if sonnet_page["confidence"] in ("high", "medium"):
                            sonnet = sonnet_page
                            result["source"] = url
                            break
                    time.sleep(0.5)
        elif sonnet is None:
            result["action"] = "no_results"
            result["notes"] = "No results from official site or DDG"
            return result

    # ── Interpret result ───────────────────────────────────────────────────────
    if sonnet is None:
        result["action"] = "flagged"
        result["notes"] = "All sources exhausted with no usable content"
        return result

    result["search_found"] = sonnet["name"]
    result["confidence"] = sonnet["confidence"]
    result["reasoning"] = sonnet["reasoning"]

    choice = sonnet["choice"]
    confidence = sonnet["confidence"]

    if choice == 1:
        result["action"] = "confirmed"
        result["notes"] = sonnet["reasoning"]

    elif choice in (2, 3):
        new_name = sonnet["name"]
        if confidence == "high":
            # Commit the change
            result["action"] = "pro_tem_rotated" if choice == 2 else "updated"
            result["new_mayor"] = new_name
            result["notes"] = sonnet["reasoning"]
        else:
            # Medium/low confidence on a change → flag for Max to review
            result["action"] = "flagged"
            result["new_mayor"] = new_name  # store the candidate name for review
            result["notes"] = f"Possible change to '{new_name}' ({confidence} confidence) — needs review. {sonnet['reasoning']}"

    else:  # choice == 4
        result["action"] = "flagged"
        result["notes"] = f"Could not determine current mayor. {sonnet['reasoning']}"

    return result


def apply_to_db(db, city, ver_result: dict):
    action = ver_result["action"]

    if action in ("pro_tem_rotated", "updated"):
        city.previous_mayor = city.mayor
        city.mayor = ver_result["new_mayor"]
        city.mayor_needs_verification = False
    elif action in ("flagged", "no_results"):
        city.mayor_needs_verification = True
    elif action == "confirmed":
        city.mayor_needs_verification = False

    db.commit()


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"processed_ids": [], "log": []}


def save_progress(processed_ids: set, log: list):
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"processed_ids": list(processed_ids), "log": log}, f, indent=2)


def review_flags(db, client):
    """
    1. Re-runs verification on all flagged cities from the last log.
    2. Interactively steps through whatever is still unresolved.
    """
    if not LOG_FILE.exists():
        print(f"No log found at {LOG_FILE} — run a verification pass first.")
        return

    with open(LOG_FILE, encoding="utf-8") as f:
        log = json.load(f)

    flagged = [r for r in log if r["action"] in ("flagged", "no_results")]
    if not flagged:
        print("No flagged cities in the last run.")
        return

    # ── Pass 1: re-verify flagged cities ──────────────────────────────────────
    print(f"\nRe-verifying {len(flagged)} flagged cities before manual review...\n")
    still_flagged = []

    with DDGS() as ddgs:
        for r in flagged:
            city = db.query(City).filter(City.id == r["city_id"]).first()
            if not city:
                continue
            print(f"  Checking {city.city_name}...", end=" ", flush=True)
            ver = verify_city_from_db(city, ddgs, client)
            if ver["action"] in ("flagged", "no_results"):
                still_flagged.append(ver)
                print(f"still flagged")
            else:
                apply_to_db(db, city, ver)
                if ver["action"] == "confirmed":
                    print(f"confirmed ({city.mayor})")
                else:
                    print(f"updated -> {ver['new_mayor']}")
            time.sleep(2)

    print(f"\nRe-verification done. {len(still_flagged)} still need manual review.\n")

    if not still_flagged:
        print("All flags resolved automatically.")
        return

    print(f"\n{'═' * 60}")
    print(f"  FLAG REVIEW — {len(still_flagged)} cities")
    print(f"  Commands: [k]eep  [a]ccept candidate  [e]nter name  [s]kip")
    print(f"{'═' * 60}\n")

    resolved = 0
    for i, r in enumerate(still_flagged, 1):
        city = db.query(City).filter(City.id == r["city_id"]).first()
        if not city:
            continue

        print(f"[{i}/{len(flagged)}]  {r['city_name']}")
        print(f"  Stored mayor:   {r['stored_mayor']}")
        if r.get("new_mayor"):
            print(f"  Candidate:      {r['new_mayor']}")
        if r.get("reasoning"):
            print(f"  Reasoning:      {r['reasoning']}")
        if r.get("notes") and r["notes"] != r.get("reasoning"):
            print(f"  Note:           {r['notes']}")
        if r.get("source"):
            print(f"  Source:         {r['source']}")
        print()

        while True:
            options = "[k]eep"
            if r.get("new_mayor"):
                options += f"  [a]ccept '{r['new_mayor']}'"
            options += "  [e]nter name  [s]kip"
            choice = input(f"  {options}: ").strip().lower()

            if choice == "k":
                city.mayor_needs_verification = False
                db.commit()
                print(f"  Kept: {r['stored_mayor']}\n")
                resolved += 1
                break

            elif choice == "a" and r.get("new_mayor"):
                city.previous_mayor = city.mayor
                city.mayor = r["new_mayor"]
                city.mayor_needs_verification = False
                db.commit()
                print(f"  Updated: {r['stored_mayor']} -> {r['new_mayor']}\n")
                resolved += 1
                break

            elif choice == "e":
                name = input("  Enter correct mayor name: ").strip()
                if name:
                    city.previous_mayor = city.mayor
                    city.mayor = name
                    city.mayor_needs_verification = False
                    db.commit()
                    print(f"  Updated: {r['stored_mayor']} -> {name}\n")
                    resolved += 1
                    break
                else:
                    print("  (name was blank, try again)")

            elif choice == "s":
                print(f"  Skipped — still flagged in DB\n")
                break

            else:
                print("  Unrecognised — try again")

    print(f"{'═' * 60}")
    print(f"Review complete: {resolved}/{len(still_flagged)} resolved.")


if __name__ == "__main__":
    test_mode = "--test" in sys.argv
    resume = "--resume" in sys.argv
    flagged_only = "--flagged-only" in sys.argv
    review_mode = "--review-flags" in sys.argv

    db = SessionLocal()
    try:
        if review_mode:
            client = get_anthropic_client()
            review_flags(db, client)
            db.close()
            sys.exit(0)

        if flagged_only:
            cities = db.query(City).filter(City.mayor_needs_verification == True).order_by(City.id).all()
            print(f"Flagged-only mode: {len(cities)} cities to re-check")
        else:
            cities = db.query(City).order_by(City.id).all()
            print(f"Full pass: {len(cities)} cities")

        client = get_anthropic_client()

        # ── Test mode: verbose output, no DB writes ────────────────────────────
        if test_mode:
            idx = sys.argv.index("--test")
            n = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit() else 20
            cities = cities[:n]
            print(f"TEST MODE: first {n} cities (no DB writes)\n")
            with DDGS() as ddgs:
                for city in cities:
                    ver = verify_city_from_db(city, ddgs, client)
                    icon = {
                        "confirmed": "OK", "pro_tem_rotated": "ROTATED",
                        "updated": "UPDATED", "flagged": "FLAG", "no_results": "?"
                    }.get(ver["action"], ver["action"])
                    print(f"[{icon}] {ver['city_name']}  ({ver.get('confidence', '?')} confidence)")
                    print(f"      stored: {ver['stored_mayor']}  |  found: {ver['search_found']}")
                    print(f"      source: {ver['source']}")
                    if ver.get("reasoning"):
                        print(f"      reason: {ver['reasoning']}")
                    if ver["notes"] and ver["notes"] != ver.get("reasoning"):
                        print(f"      note:   {ver['notes']}")
                    print()
                    time.sleep(2)
            db.close()
            sys.exit(0)

        # ── Full run ───────────────────────────────────────────────────────────
        progress = load_progress() if resume else {"processed_ids": [], "log": []}
        processed_ids = set(progress["processed_ids"])
        log = progress["log"]

        if resume and processed_ids:
            cities_to_process = [c for c in cities if c.id not in processed_ids]
            print(f"Resuming — {len(processed_ids)} done, {len(cities_to_process)} remaining")
        else:
            cities_to_process = cities
            log = []
            processed_ids = set()

        print("Saves every 10 cities  |  Resume with --resume")
        print("Only HIGH-confidence changes are written; everything else is flagged.\n")

        stats = {"confirmed": 0, "pro_tem_rotated": 0, "updated": 0, "flagged": 0, "no_results": 0}
        bar = Progress(len(cities), label="Mayor re-verification")
        bar.update(len(processed_ids), suffix="resuming..." if processed_ids else "")

        with DDGS() as ddgs:
            for city in cities_to_process:
                ver = verify_city_from_db(city, ddgs, client)
                apply_to_db(db, city, ver)

                action = ver["action"]
                stats[action] = stats.get(action, 0) + 1
                processed_ids.add(city.id)
                log.append(ver)

                icons = {
                    "confirmed": "OK", "pro_tem_rotated": "ROTATED",
                    "updated": "UPDATED", "flagged": "FLAG", "no_results": "?"
                }
                bar.update(len(processed_ids), suffix=f"{city.city_name} [{icons.get(action, action)}]")

                if action in ("updated", "pro_tem_rotated"):
                    print(f"\n  CHANGE  {city.city_name}: '{ver['stored_mayor']}' -> '{ver['new_mayor']}'")
                    print(f"          {ver.get('reasoning', '')}")
                elif action in ("flagged", "no_results"):
                    candidate = f" -> candidate: '{ver['new_mayor']}'" if ver.get("new_mayor") else ""
                    print(f"\n  FLAG    {city.city_name} | stored: {ver['stored_mayor']}{candidate}")
                    print(f"          {ver['notes']}")

                if len(processed_ids) % 10 == 0:
                    save_progress(processed_ids, log)

                time.sleep(2)

        bar.done()

        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
        print(f"\nLog -> {LOG_FILE}")

        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()

        print(f"\nRe-verification complete:")
        print(f"  Confirmed (no change):         {stats.get('confirmed', 0)}")
        print(f"  Updated — high confidence:     {stats.get('updated', 0) + stats.get('pro_tem_rotated', 0)}")
        print(f"  Flagged for manual review:     {stats.get('flagged', 0)}")
        print(f"  No results:                    {stats.get('no_results', 0)}")

        flagged = [r for r in log if r["action"] in ("flagged", "no_results")]
        if flagged:
            print(f"\n{'─' * 60}")
            print(f"FLAGGED FOR REVIEW ({len(flagged)} cities):")
            print(f"{'─' * 60}")
            for r in flagged:
                candidate = f"  ->  candidate: {r['new_mayor']}" if r.get("new_mayor") else ""
                print(f"  {r['city_name']}")
                print(f"      stored:  {r['stored_mayor']}{candidate}")
                if r.get("notes"):
                    print(f"      reason:  {r['notes']}")
            print(f"{'─' * 60}")
            print(f"These cities have mayor_needs_verification=True in the DB.")

    finally:
        db.close()
