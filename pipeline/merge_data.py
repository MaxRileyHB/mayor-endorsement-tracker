"""
Merge all parsed data sources into a single california_cities.json.

Sources (all from pipeline/output/ unless noted):
  roster_cities_verified.json  (or roster_cities.json as fallback)
  dof_population.json
  fair_plan_pif.json
  fair_plan_exposure.json
  cdi_distressed.json
  moratoriums.json
  source_data/uszips.csv       (ZIP -> city crosswalk)

Output: output/california_cities.json — one record per city, ready for DB seeding
        output/merge_report.json — match stats and unmatched cities for review
"""
import json
import re
import csv
from pathlib import Path
from utils import DATA_DIR, OUTPUT_DIR

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def normalize_city_name(name):
    """Strip 'City of', 'Town of', extra whitespace; lowercase for comparison."""
    if not name:
        return ""
    name = re.sub(r'^(city|town)\s+of\s+', '', name.strip(), flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip().lower()
    return name

def best_match(target, candidates, threshold=0.85):
    """
    Find the best matching string from candidates using token overlap.
    Returns (matched_key, score) or (None, 0) if no match above threshold.
    """
    target_norm = normalize_city_name(target)
    target_tokens = set(target_norm.split())

    best_key, best_score = None, 0.0
    for cand in candidates:
        cand_norm = normalize_city_name(cand)
        cand_tokens = set(cand_norm.split())

        if target_norm == cand_norm:
            return cand, 1.0

        if not target_tokens or not cand_tokens:
            continue

        overlap = len(target_tokens & cand_tokens) / max(len(target_tokens), len(cand_tokens))
        if overlap > best_score:
            best_score = overlap
            best_key = cand

    return (best_key, best_score) if best_score >= threshold else (None, best_score)

# ─────────────────────────────────────────────
# Load all data sources
# ─────────────────────────────────────────────

def load_sources():
    print("Loading data sources...")
    sources = {}

    # Roster — prefer verified version
    verified = OUTPUT_DIR / "roster_cities_verified.json"
    base = OUTPUT_DIR / "roster_cities.json"
    roster_path = verified if verified.exists() else base
    with open(roster_path, encoding="utf-8") as f:
        sources["roster"] = json.load(f)
    print(f"  Roster: {len(sources['roster'])} cities (from {roster_path.name})")

    # DOF population
    with open(OUTPUT_DIR / "dof_population.json") as f:
        dof_list = json.load(f)
    # Index by normalized city name + county for fast lookup
    sources["dof"] = {}
    for row in dof_list:
        key = normalize_city_name(row["city"])
        sources["dof"][key] = row
    print(f"  DOF population: {len(sources['dof'])} records")

    # FAIR Plan PIF
    with open(OUTPUT_DIR / "fair_plan_pif.json") as f:
        pif_list = json.load(f)
    sources["pif"] = {row["zip"]: row for row in pif_list}
    print(f"  FAIR Plan PIF: {len(sources['pif'])} ZIPs")

    # FAIR Plan Exposure
    with open(OUTPUT_DIR / "fair_plan_exposure.json") as f:
        exp_list = json.load(f)
    sources["exposure"] = {row["zip"]: row for row in exp_list}
    print(f"  FAIR Plan Exposure: {len(sources['exposure'])} ZIPs")

    # CDI distressed
    with open(OUTPUT_DIR / "cdi_distressed.json") as f:
        cdi = json.load(f)
    sources["distressed_counties"] = set(normalize_city_name(c) for c in cdi["counties"])
    sources["undermarketed_zips"] = set(cdi["undermarketed_zips"])
    print(f"  CDI distressed: {len(sources['distressed_counties'])} counties, {len(sources['undermarketed_zips'])} ZIPs")

    # Moratoriums — build ZIP -> fires index
    with open(OUTPUT_DIR / "moratoriums.json") as f:
        morat_list = json.load(f)
    sources["moratorium_by_zip"] = {}
    for fire in morat_list:
        for z in fire["zips"]:
            if z not in sources["moratorium_by_zip"]:
                sources["moratorium_by_zip"][z] = []
            sources["moratorium_by_zip"][z].append({
                "fire": fire["fire"],
                "status": fire["status"],
                "date": fire["date"],
            })
    print(f"  Moratoriums: {len(sources['moratorium_by_zip'])} ZIPs covered")

    # ZIP crosswalk — CA only
    zip_path = DATA_DIR / "uszips.csv"
    sources["zip_to_cities"] = {}   # normalized city name -> list of ZIPs
    sources["zip_to_city_raw"] = {} # zip -> raw city name (for reverse lookup)
    with open(zip_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("state_id") != "CA":
                continue
            z = row["zip"].zfill(5)
            city_raw = row["city"]
            city_norm = normalize_city_name(city_raw)
            sources["zip_to_city_raw"][z] = city_raw
            if city_norm not in sources["zip_to_cities"]:
                sources["zip_to_cities"][city_norm] = []
            sources["zip_to_cities"][city_norm].append(z)
    print(f"  ZIP crosswalk: {len(sources['zip_to_cities'])} CA city names, {len(sources['zip_to_city_raw'])} CA ZIPs")

    return sources

# ─────────────────────────────────────────────
# ZIP lookup for a city
# ─────────────────────────────────────────────

def get_city_zips(city_name, county, sources):
    """
    Find all CA ZIPs that map to this city.
    Tries exact match first, then fuzzy match.
    """
    norm = normalize_city_name(city_name)
    zip_map = sources["zip_to_cities"]

    # Exact match
    if norm in zip_map:
        return zip_map[norm]

    # Fuzzy match
    matched_key, score = best_match(city_name, list(zip_map.keys()), threshold=0.7)
    if matched_key:
        return zip_map[matched_key]

    return []

# ─────────────────────────────────────────────
# Aggregate insurance data for a city's ZIPs
# ─────────────────────────────────────────────

def aggregate_insurance(city_name, county, sources):
    """Aggregate all insurance metrics for a city from its ZIPs."""
    zips = get_city_zips(city_name, county, sources)

    total_policies = 0
    total_exposure = 0
    has_undermarketed_zips = False
    moratorium_fires_set = {}  # fire name -> fire info
    risk_scores = []           # for deriving wildfire tier

    for z in zips:
        # FAIR Plan PIF
        if z in sources["pif"]:
            total_policies += sources["pif"][z].get("policies_fy25") or 0

        # FAIR Plan Exposure
        if z in sources["exposure"]:
            exp = sources["exposure"][z]
            total_exposure += exp.get("exposure") or 0
            tier = exp.get("wildfire_risk_tier", "low")
            risk_scores.append({"high": 3, "medium": 2, "low": 1}.get(tier, 1))

        # CDI undermarketed ZIPs
        if z in sources["undermarketed_zips"]:
            has_undermarketed_zips = True

        # Moratoriums
        if z in sources["moratorium_by_zip"]:
            for fire_info in sources["moratorium_by_zip"][z]:
                fire_name = fire_info["fire"]
                if fire_name not in moratorium_fires_set:
                    moratorium_fires_set[fire_name] = fire_info

    # Derive wildfire risk tier (use highest tier seen across ZIPs)
    if risk_scores:
        max_score = max(risk_scores)
        wildfire_risk_tier = {3: "high", 2: "medium", 1: "low"}[max_score]
    else:
        wildfire_risk_tier = None

    moratorium_fires = list(moratorium_fires_set.keys())
    moratorium_active = any(
        f["status"] == "active" for f in moratorium_fires_set.values()
    )

    return {
        "fair_plan_policies": total_policies,
        "fair_plan_exposure": total_exposure,
        "has_undermarketed_zips": has_undermarketed_zips,
        "moratorium_fires": moratorium_fires,
        "moratorium_active": moratorium_active,
        "wildfire_risk_tier": wildfire_risk_tier,
        "_zips": zips,  # keep for debugging, strip before final output
    }

# ─────────────────────────────────────────────
# Assign outreach tier
# ─────────────────────────────────────────────

def assign_tier(city_data):
    """
    Tier 1: pop > 50k OR distressed county OR fair_plan_policies > 500 OR moratorium_active
    Tier 2: pop 15k-50k OR has_undermarketed_zips OR fair_plan_policies > 100
    Tier 3: everything else
    """
    pop = city_data.get("population") or 0
    policies = city_data.get("fair_plan_policies") or 0
    distressed = city_data.get("is_distressed_county", False)
    moratorium = city_data.get("moratorium_active", False)
    undermarketed = city_data.get("has_undermarketed_zips", False)

    if pop > 50000 or distressed or policies > 500 or moratorium:
        return 1
    if 15000 <= pop <= 50000 or undermarketed or policies > 100:
        return 2
    return 3

# ─────────────────────────────────────────────
# Build one merged city record
# ─────────────────────────────────────────────

def merge_city(roster_city, sources, report):
    city_name = roster_city.get("city_name", "")
    county_raw = roster_city.get("county", "")
    county = re.sub(r'^county\s+of\s+', '', county_raw.strip(), flags=re.IGNORECASE).strip()

    # Population from DOF
    norm = normalize_city_name(city_name)
    population = None
    dof_match = sources["dof"].get(norm)
    if not dof_match:
        # Try fuzzy
        matched_key, score = best_match(city_name, list(sources["dof"].keys()), threshold=0.8)
        if matched_key:
            dof_match = sources["dof"][matched_key]
            report["dof_fuzzy_matches"].append({"city": city_name, "matched": matched_key, "score": round(score, 2)})
    if dof_match:
        population = dof_match.get("population_2025")
    else:
        report["dof_unmatched"].append(city_name)

    # Insurance data
    ins = aggregate_insurance(city_name, county, sources)
    debug_zips = ins.pop("_zips", [])
    if not debug_zips:
        report["no_zips"].append(city_name)

    # Distressed county check
    county_norm = normalize_city_name(county)
    is_distressed_county = county_norm in sources["distressed_counties"]

    city_data = {
        # Identity
        "city_name": city_name,
        "county": county,
        "population": population,
        "incorporated_date": roster_city.get("incorporated_date"),

        # Officials
        "mayor": roster_city.get("mayor"),
        "mayor_pro_tem": roster_city.get("mayor_pro_tem"),
        "previous_mayor": roster_city.get("previous_mayor"),
        "mayor_needs_verification": roster_city.get("mayor_needs_verification", False),
        "council_members": roster_city.get("council_members") or [],
        "city_manager": roster_city.get("city_manager"),
        "city_clerk": roster_city.get("city_clerk"),
        "city_attorney": roster_city.get("city_attorney"),

        # Contact — City
        "city_address": roster_city.get("address"),
        "city_phone": roster_city.get("phone"),
        "city_fax": roster_city.get("fax"),
        "city_website": roster_city.get("website"),
        "city_email": roster_city.get("email"),
        "office_hours": roster_city.get("office_hours"),

        # Contact — Mayor direct (empty until collected)
        "mayor_email": None,
        "mayor_phone": None,
        "mayor_contact_source": None,

        # Political
        "congressional_district": roster_city.get("congressional_district"),
        "state_senate_district": roster_city.get("state_senate_district"),
        "state_assembly_district": roster_city.get("state_assembly_district"),
        "party_affiliation": None,  # populated later

        # Insurance
        "fair_plan_policies": ins["fair_plan_policies"],
        "fair_plan_exposure": ins["fair_plan_exposure"],
        "is_distressed_county": is_distressed_county,
        "has_undermarketed_zips": ins["has_undermarketed_zips"],
        "moratorium_fires": ins["moratorium_fires"],
        "moratorium_active": ins["moratorium_active"],
        "wildfire_risk_tier": ins["wildfire_risk_tier"],

        # Pipeline defaults
        "outreach_status": "no_contact_info",
        "outreach_tier": None,  # filled in below
        "last_contacted": None,
        "next_action": None,
        "next_action_date": None,
        "notes": None,
    }

    city_data["outreach_tier"] = assign_tier(city_data)
    return city_data

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    sources = load_sources()

    report = {
        "dof_unmatched": [],
        "dof_fuzzy_matches": [],
        "no_zips": [],
        "tier_counts": {},
    }

    print(f"\nMerging {len(sources['roster'])} cities...")
    merged = []
    for i, city in enumerate(sources["roster"]):
        merged_city = merge_city(city, sources, report)
        merged.append(merged_city)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(sources['roster'])}...")

    # Tier summary
    for city in merged:
        t = city["outreach_tier"]
        report["tier_counts"][t] = report["tier_counts"].get(t, 0) + 1

    # Output
    out = OUTPUT_DIR / "california_cities.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"\nSaved -> {out} ({len(merged)} cities)")

    report_out = OUTPUT_DIR / "merge_report.json"
    with open(report_out, "w") as f:
        json.dump(report, f, indent=2)

    # Summary
    print(f"\n=== Merge Summary ===")
    print(f"Total cities: {len(merged)}")
    print(f"Tier 1: {report['tier_counts'].get(1, 0)} | Tier 2: {report['tier_counts'].get(2, 0)} | Tier 3: {report['tier_counts'].get(3, 0)}")
    print(f"DOF population unmatched: {len(report['dof_unmatched'])}")
    print(f"Cities with no ZIPs found: {len(report['no_zips'])}")
    print(f"DOF fuzzy matches (review): {len(report['dof_fuzzy_matches'])}")
    print(f"\nFull report -> {report_out}")

    if report["dof_unmatched"]:
        print(f"\nDOF unmatched ({len(report['dof_unmatched'])}):")
        for c in report["dof_unmatched"][:10]:
            print(f"  {c}")
        if len(report["dof_unmatched"]) > 10:
            print(f"  ... and {len(report['dof_unmatched']) - 10} more (see merge_report.json)")

    if report["no_zips"]:
        print(f"\nNo ZIPs found ({len(report['no_zips'])}):")
        for c in report["no_zips"][:10]:
            print(f"  {c}")
