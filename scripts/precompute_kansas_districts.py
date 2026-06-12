"""Fetch Kansas tract data and precompute balanced-power district plans.

This script intentionally starts at the tract level. Census blocks are the
eventual legal-grade input, but tracts are small enough for quick iteration and
large enough to validate the end-to-end algorithm, cache shape, and UI.
"""

from __future__ import annotations

import json
import math
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import shapefile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from districting import CAP_ANCHORS, Unit, apportion_us_2020, balanced_power_diagram

STATE_FIPS = "20"
STATE_NAME = "Kansas"
SOURCE_YEAR = 2020

CACHE_DIR = ROOT / ".cache" / "districting" / "kansas"
OUTPUT_DIR = ROOT / "public" / "data" / "districting" / STATE_FIPS
TIGER_URL = (
    "https://www2.census.gov/geo/tiger/TIGER2020/TRACT/"
    "tl_2020_20_tract.zip"
)
CENSUS_POP_URL = "https://api.census.gov/data/2020/dec/pl"


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    zip_path = CACHE_DIR / "tl_2020_20_tract.zip"
    if not zip_path.exists():
        download(TIGER_URL, zip_path)

    extract_dir = CACHE_DIR / "tl_2020_20_tract"
    if not extract_dir.exists():
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

    populations = fetch_tract_populations()
    features, units, lon0, lat0 = load_tract_units(extract_dir, populations)

    seats_by_cap = apportion_us_2020
    for cap in CAP_ANCHORS:
        seats = seats_by_cap(cap)[STATE_FIPS]
        result = balanced_power_diagram(
            units,
            seats,
            seed=20200520 + cap,
            max_outer_iterations=80,
            inner_max_iterations=300,
        )
        write_plan(cap, seats, result, features, units, lon0, lat0)


def download(url: str, path: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        path.write_bytes(resp.read())


def fetch_tract_populations() -> dict[str, int]:
    url = f"{CENSUS_POP_URL}?get=P1_001N&for=tract:*&in=state:20&in=county:*"
    print(f"Fetching population data from {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        rows = json.loads(resp.read().decode("utf-8"))

    header = rows[0]
    pop_idx = header.index("P1_001N")
    state_idx = header.index("state")
    county_idx = header.index("county")
    tract_idx = header.index("tract")

    populations: dict[str, int] = {}
    for row in rows[1:]:
        geoid = row[state_idx] + row[county_idx] + row[tract_idx]
        populations[geoid] = int(row[pop_idx])
    return populations


def load_tract_units(
    extract_dir: Path,
    populations: dict[str, int],
) -> tuple[list[dict[str, Any]], list[Unit], float, float]:
    shp_path = next(extract_dir.glob("*.shp"))
    reader = shapefile.Reader(str(shp_path))
    fields = [f[0] for f in reader.fields[1:]]
    geoid_idx = fields.index("GEOID")
    name_idx = fields.index("NAMELSAD")
    intptlon_idx = fields.index("INTPTLON")
    intptlat_idx = fields.index("INTPTLAT")

    raw_records: list[tuple[str, str, float, float, int, Any]] = []
    lon_sum = 0.0
    lat_sum = 0.0
    pop_sum = 0

    for sr in reader.iterShapeRecords():
        record = list(sr.record)
        geoid = str(record[geoid_idx])
        population = populations.get(geoid, 0)
        if population <= 0:
            continue
        lon = float(record[intptlon_idx])
        lat = float(record[intptlat_idx])
        raw_records.append((geoid, str(record[name_idx]), lon, lat, population, sr.shape))
        lon_sum += lon * population
        lat_sum += lat * population
        pop_sum += population

    if not raw_records or pop_sum <= 0:
        raise RuntimeError("No populated Kansas tracts were loaded.")

    lon0 = lon_sum / pop_sum
    lat0 = lat_sum / pop_sum

    features: list[dict[str, Any]] = []
    units: list[Unit] = []
    for geoid, name, lon, lat, population, shape in raw_records:
        x, y = project_equirectangular(lon, lat, lon0, lat0)
        units.append(Unit(geoid=geoid, centroid=(x, y), population=population))
        geometry = shape.__geo_interface__
        features.append(
            {
                "type": "Feature",
                "id": geoid,
                "properties": {
                    "geoid": geoid,
                    "name": name,
                    "population": population,
                },
                "geometry": geometry,
            }
        )
    return features, units, lon0, lat0


def project_equirectangular(
    lon: float,
    lat: float,
    lon0: float,
    lat0: float,
) -> tuple[float, float]:
    earth_radius_m = 6_371_000.0
    x = math.radians(lon - lon0) * earth_radius_m * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * earth_radius_m
    return x, y


def write_plan(
    cap: int,
    seats: int,
    result,
    features,
    units: list[Unit],
    lon0: float,
    lat0: float,
) -> None:
    by_geoid = {u.geoid: u for u in units}
    target = round(sum(u.population for u in units) / seats)
    enriched_features = []
    for feature in features:
        geoid = feature["id"]
        district_id = result.assignments[geoid]
        enriched_features.append(
            {
                **feature,
                "properties": {
                    **feature["properties"],
                    "district_id": district_id,
                },
            }
        )

    populations = {str(k): int(v) for k, v in result.populations.items()}
    output = {
        "type": "KansasDistrictPlan",
        "state_fips": STATE_FIPS,
        "state_name": STATE_NAME,
        "source_year": SOURCE_YEAR,
        "unit": "tract",
        "cap": cap,
        "seats": seats,
        "target_population": target,
        "total_population": sum(u.population for u in units),
        "district_populations": populations,
        "max_population_imbalance": result.max_population_imbalance,
        "iterations": result.iterations,
        "converged": result.converged,
        "centers": [
            {
                "district_id": c.district_id,
                "x": c.x,
                "y": c.y,
                "weight": c.weight,
            }
            for c in result.centers
        ],
        "feature_collection": {
            "type": "FeatureCollection",
            "features": enriched_features,
        },
        "notes": [
            "Prototype tract-level plan; census blocks remain unsplit by construction only after the block-level phase.",
            "Distances are computed in a Kansas-centered equirectangular projection for this demo artifact.",
        ],
    }
    _ = by_geoid

    path = OUTPUT_DIR / f"cap-{cap}-seats-{seats}.json"
    path.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    print(
        f"Wrote {path.relative_to(ROOT)} "
        f"districts={seats} imbalance={result.max_population_imbalance}"
    )


if __name__ == "__main__":
    main()
