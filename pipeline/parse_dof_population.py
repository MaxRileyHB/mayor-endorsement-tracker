"""
Parse DOF E-1 2025 population estimates Excel file.
Output: output/dof_population.json — list of {city, county, population_2025}

Structure of E-1 CityCounty2025 sheet:
  Row 4: headers — State/County/City | 1/1/2024 | 1/1/2025 | Percent Change
  Row 5: California (state total — skip)
  Row 6: <County name> (county total — marks start of group, capture as current_county)
  Row 7+: <City name> (city rows — capture)
  ...
  Row N: Balance of County (skip — marks end of group)
  Row N+1: <Next county name>
"""
import json
import pandas as pd
from utils import DATA_DIR, OUTPUT_DIR

def parse_dof_population():
    path = DATA_DIR / "dof_e1_population_2025.xlsx"
    print(f"Reading {path.name}...")

    df = pd.read_excel(path, sheet_name="E-1 CityCounty2025", header=None)

    # Row 4 is the header; data starts at row 5
    col_name = 0      # "State/County/City"
    col_pop_2025 = 2  # "1/1/2025"

    results = []
    current_county = None
    is_first_in_group = False  # True right after we set a new county

    for i in range(5, len(df)):
        row = df.iloc[i]
        name = str(row[col_name]).strip()

        if not name or name.lower() == "nan":
            continue

        # Skip state total
        if name.lower() == "california":
            continue

        # Skip balance-of-county rows
        if "balance" in name.lower():
            is_first_in_group = True  # next non-balance row will be a county header
            continue

        # The first real row after a "Balance of County" (or at the very start) is a county header
        if is_first_in_group or current_county is None:
            current_county = name
            is_first_in_group = False
            continue  # county row itself is not a city

        # Skip footer/metadata rows (non-city text appearing after all data)
        if any(skip in name.lower() for skip in ["released", "department of finance", "demographic", "report", "population and housing"]):
            continue

        # Everything else is a city
        try:
            pop = int(str(row[col_pop_2025]).replace(",", "").split(".")[0])
        except (ValueError, AttributeError):
            pop = None

        results.append({
            "city": name,
            "county": current_county,
            "population_2025": pop,
        })

    return results

if __name__ == "__main__":
    cities = parse_dof_population()
    print(f"Extracted {len(cities)} city records")
    print("Sample:", json.dumps(cities[:5], indent=2))

    out = OUTPUT_DIR / "dof_population.json"
    with open(out, "w") as f:
        json.dump(cities, f, indent=2)
    print(f"Saved -> {out}")
