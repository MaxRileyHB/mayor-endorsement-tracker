"""
Mayor verification via DuckDuckGo search.

For each city in roster_cities.json, search for the current mayor and compare
to the Roster data. Updates mayor if rotation has occurred, flags uncertain cases.

Run AFTER parse_roster.py has produced roster_cities.json.

Output: output/roster_cities_verified.json — same format with updated mayor data
        output/verification_log.json — full log of what changed / was flagged

Usage:
  py verify_mayors.py                    # verify all cities
  py verify_mayors.py --resume           # resume from partial progress
  py verify_mayors.py --test 20          # test on first 20 cities and print results
"""
import json
import re
import time
import sys
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from utils import OUTPUT_DIR, Progress, get_anthropic_client

INPUT_FILE = OUTPUT_DIR / "roster_cities.json"
OUTPUT_FILE = OUTPUT_DIR / "roster_cities_verified.json"
LOG_FILE = OUTPUT_DIR / "verification_log.json"
PROGRESS_FILE = OUTPUT_DIR / "verification_progress.json"

FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def search_current_mayor(city_name, ddgs):
    """
    Search DuckDuckGo for the current mayor of a CA city.
    Returns (snippets_text, result_urls) or (None, []).
    """
    query = f"{city_name} California mayor"
    try:
        results = list(ddgs.text(query, max_results=5, region="us-en"))
        if results:
            snippets = "\n".join(
                f"{r.get('title', '')} {r.get('body', '')}" for r in results
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


def fetch_url_text(url, city_name, max_chars=4000):
    """
    Fetch a URL and return visible text content.
    Returns None if the page doesn't appear to be about the right city.
    """
    # Normalize city name for sanity check (strip "City of" / "Town of")
    city_bare = re.sub(r'^(City|Town)\s+of\s+', '', city_name, flags=re.I).strip().lower()

    try:
        r = requests.get(url, timeout=10, headers=FETCH_HEADERS, allow_redirects=True)
        if not r.ok:
            return None
        soup = BeautifulSoup(r.content, "html.parser")
        # Remove nav/footer/script clutter
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)

        # Sanity check: page must mention the city name
        if city_bare not in text.lower():
            return None

        # Focus on the part of the page mentioning mayor
        idx = text.lower().find("mayor")
        if idx != -1:
            start = max(0, idx - 300)
            return text[start : start + max_chars]
        return text[:max_chars]
    except Exception:
        return None


def extract_mayor_with_haiku(content, city_name, roster_mayor, roster_pro_tem, client, source="search snippets"):
    """
    Ask Haiku to identify the current mayor from search content.
    Returns dict: {choice: 1|2|3|4, name: str|None}
      1 = roster mayor confirmed
      2 = pro tem is now mayor
      3 = someone else (name provided)
      4 = can't determine
    """
    prompt = f"""The following is {source} about {city_name}, California:

---
{content[:4000]}
---

Based on this, who is the CURRENT mayor of {city_name}?

1. {roster_mayor} (the roster mayor)
2. {roster_pro_tem or "N/A"} (the mayor pro tem / vice mayor)
3. Someone else — give their full name
4. Cannot determine from this content

Reply with ONLY the number (1, 2, 3, or 4). If 3, also give the name on the same line, e.g.: 3 Karen Bass"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        first = text[0]
        if first == "1":
            return {"choice": 1, "name": roster_mayor}
        elif first == "2":
            return {"choice": 2, "name": roster_pro_tem}
        elif first == "3":
            name = re.sub(r'^3[\s\.\:]+', '', text).strip()
            return {"choice": 3, "name": name if name else None}
        else:
            return {"choice": 4, "name": None}
    except Exception:
        return {"choice": 4, "name": None}


def verify_city(city, ddgs, client):
    """
    Verify the mayor for one city.
    Strategy:
      1. DDG search -> Haiku
      2. If choice==4, fetch the top search result URL -> Haiku again
    """
    city_name = city.get("city_name", "")
    roster_mayor = city.get("mayor", "")
    roster_pro_tem = city.get("mayor_pro_tem", "")

    result = {
        "city_name": city_name,
        "roster_mayor": roster_mayor,
        "roster_pro_tem": roster_pro_tem,
        "action": None,
        "new_mayor": None,
        "search_found": None,
        "notes": None,
        "source": None,
    }

    # Step 1: DDG search
    snippets, urls = search_current_mayor(city_name, ddgs)

    if not snippets:
        result["action"] = "no_results"
        result["notes"] = "DuckDuckGo returned no results"
        return result

    haiku = extract_mayor_with_haiku(snippets, city_name, roster_mayor, roster_pro_tem, client, source="search snippets")
    result["source"] = "ddg_snippets"

    # Step 2: If snippets weren't enough, fetch the top URL
    if haiku["choice"] == 4 and urls:
        for url in urls[:2]:  # try top 2 results
            page_text = fetch_url_text(url, city_name)
            if page_text:
                haiku2 = extract_mayor_with_haiku(page_text, city_name, roster_mayor, roster_pro_tem, client, source=f"page content from {url}")
                if haiku2["choice"] != 4:
                    haiku = haiku2
                    result["source"] = url
                    break
            time.sleep(0.5)

    result["search_found"] = haiku["name"]

    if haiku["choice"] == 1:
        result["action"] = "confirmed"

    elif haiku["choice"] == 2:
        result["action"] = "pro_tem_rotated"
        result["new_mayor"] = haiku["name"]
        result["notes"] = f"Pro tem '{roster_pro_tem}' is now mayor"

    elif haiku["choice"] == 3:
        result["action"] = "updated"
        result["new_mayor"] = haiku["name"]
        result["notes"] = f"Found '{haiku['name']}' — different from roster"

    else:
        result["action"] = "flagged"
        result["notes"] = "Could not determine current mayor from search or page fetch"

    return result


def apply_verification(city, ver_result):
    """Apply a verification result to a city record."""
    city = dict(city)
    action = ver_result["action"]

    if action in ("pro_tem_rotated", "updated"):
        city["previous_mayor"] = city.get("mayor")
        city["mayor"] = ver_result["new_mayor"]
        city["mayor_needs_verification"] = False

    elif action in ("flagged", "no_results"):
        city["mayor_needs_verification"] = True

    elif action == "confirmed":
        city["mayor_needs_verification"] = False

    return city


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"verified_cities": [], "log": [], "last_index": 0}


def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


if __name__ == "__main__":
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found — run parse_roster.py first")
        exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        cities = json.load(f)

    test_mode = "--test" in sys.argv
    resume = "--resume" in sys.argv

    # Test mode: run on first N cities and print verbose results
    if test_mode:
        idx = sys.argv.index("--test")
        n = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit() else 20
        print(f"TEST MODE: verifying first {n} cities\n")
        client = get_anthropic_client()
        with DDGS() as ddgs:
            for city in cities[:n]:
                ver = verify_city(city, ddgs, client)
                icon = {"confirmed": "OK", "pro_tem_rotated": "ROTATED", "updated": "UPDATED", "flagged": "FLAG", "no_results": "?"}.get(ver["action"], ver["action"])
                print(f"[{icon}] {ver['city_name']}")
                print(f"      roster: {ver['roster_mayor']}  |  found: {ver['search_found']}")
                if ver["notes"]:
                    print(f"      note: {ver['notes']}")
                print(f"      source: {ver['source']}")
                print()
                time.sleep(2)
        exit(0)

    # Full run
    progress = load_progress() if resume else {"verified_cities": [], "log": [], "last_index": 0}
    start_index = progress["last_index"]

    if resume and start_index > 0:
        print(f"Resuming from city {start_index + 1}/{len(cities)}")
        verified_cities = progress["verified_cities"]
        log = progress["log"]
    else:
        verified_cities = []
        log = []

    cities_to_verify = cities[start_index:]
    print(f"Verifying {len(cities_to_verify)} cities via DuckDuckGo...")
    print("Saves every 25 cities  |  Resume with --resume\n")

    stats = {"confirmed": 0, "pro_tem_rotated": 0, "updated": 0, "flagged": 0, "no_results": 0}
    bar = Progress(len(cities), label="Mayor verification")
    bar.update(start_index, suffix="resuming..." if start_index else "")

    client = get_anthropic_client()

    with DDGS() as ddgs:
        for i, city in enumerate(cities_to_verify):
            global_i = start_index + i
            city_name = city.get("city_name", f"city_{global_i}")

            ver = verify_city(city, ddgs, client)
            updated_city = apply_verification(city, ver)

            verified_cities.append(updated_city)
            log.append(ver)
            action = ver["action"]
            stats[action] = stats.get(action, 0) + 1

            icons = {"confirmed": "OK", "pro_tem_rotated": "ROTATED", "updated": "UPDATED", "flagged": "FLAG", "no_results": "?"}
            bar.update(global_i + 1, suffix=f"{city_name} [{icons.get(action, action)}]")

            if action in ("flagged", "no_results"):
                print(f"\n!FLAG  {city_name}  |  roster: {ver['roster_mayor']}  |  {ver['notes'] or ''}")

            if (global_i + 1) % 25 == 0:
                progress = {"verified_cities": verified_cities, "log": log, "last_index": global_i + 1}
                save_progress(progress)

            time.sleep(2)

    bar.done()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(verified_cities, f, indent=2, ensure_ascii=False)
    print(f"\nSaved -> {OUTPUT_FILE}")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    print(f"Log -> {LOG_FILE}")

    print(f"\nVerification complete:")
    print(f"  Confirmed (no change):    {stats.get('confirmed', 0)}")
    print(f"  Pro tem rotated:          {stats.get('pro_tem_rotated', 0)}")
    print(f"  Updated (new mayor):      {stats.get('updated', 0)}")
    print(f"  Flagged for review:       {stats.get('flagged', 0)}")
    print(f"  No search results:        {stats.get('no_results', 0)}")
