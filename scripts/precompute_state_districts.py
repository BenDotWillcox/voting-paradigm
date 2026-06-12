"""Fetch tract data and precompute balanced-power district plans for one state.

This is the state-parameterized version of the Kansas prototype. It keeps the
same tract-level workflow: TIGER/Line tract geometries, 2020 PL population
counts, balanced-power assignments for each cap anchor, and compact JSON
artifacts under public/data/districting/<state_fips>/.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable

import shapefile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from districting import CAP_ANCHORS, Unit, apportion_us_2020, balanced_power_diagram

SOURCE_YEAR = 2020
CENSUS_POP_URL = "https://api.census.gov/data/2020/dec/pl"

STATE_NAMES: dict[str, str] = {
    "01": "Alabama",
    "02": "Alaska",
    "04": "Arizona",
    "05": "Arkansas",
    "06": "California",
    "08": "Colorado",
    "09": "Connecticut",
    "10": "Delaware",
    "12": "Florida",
    "13": "Georgia",
    "15": "Hawaii",
    "16": "Idaho",
    "17": "Illinois",
    "18": "Indiana",
    "19": "Iowa",
    "20": "Kansas",
    "21": "Kentucky",
    "22": "Louisiana",
    "23": "Maine",
    "24": "Maryland",
    "25": "Massachusetts",
    "26": "Michigan",
    "27": "Minnesota",
    "28": "Mississippi",
    "29": "Missouri",
    "30": "Montana",
    "31": "Nebraska",
    "32": "Nevada",
    "33": "New Hampshire",
    "34": "New Jersey",
    "35": "New Mexico",
    "36": "New York",
    "37": "North Carolina",
    "38": "North Dakota",
    "39": "Ohio",
    "40": "Oklahoma",
    "41": "Oregon",
    "42": "Pennsylvania",
    "44": "Rhode Island",
    "45": "South Carolina",
    "46": "South Dakota",
    "47": "Tennessee",
    "48": "Texas",
    "49": "Utah",
    "50": "Vermont",
    "51": "Virginia",
    "53": "Washington",
    "54": "West Virginia",
    "55": "Wisconsin",
    "56": "Wyoming",
}


def main() -> None:
    args = parse_args()
    state_fips = normalize_state_fips(args.state_fips)
    state_name = STATE_NAMES[state_fips]
    caps = tuple(args.caps or CAP_ANCHORS)

    cache_dir = ROOT / ".cache" / "districting" / state_fips
    output_dir = ROOT / "public" / "data" / "districting" / state_fips
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    extract_dir = load_tiger_tracts(state_fips, cache_dir)
    populations = fetch_tract_populations(state_fips)
    features, units, lon0, lat0 = load_tract_units(
        extract_dir,
        populations,
        state_name=state_name,
    )

    seats_by_cap = apportion_us_2020
    for cap in caps:
        seats = seats_by_cap(cap)[state_fips]
        result = balanced_power_diagram(
            units,
            seats,
            seed=20200500 + int(state_fips) + cap,
            max_outer_iterations=args.max_outer_iterations,
            inner_max_iterations=args.inner_max_iterations,
        )
        write_plan(
            cap,
            seats,
            result,
            features,
            units,
            lon0,
            lat0,
            state_fips=state_fips,
            state_name=state_name,
            output_dir=output_dir,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("state_fips", help="Two-digit state FIPS code, e.g. 01")
    parser.add_argument(
        "--caps",
        nargs="+",
        type=int,
        choices=CAP_ANCHORS,
        help="Cap anchors to precompute. Defaults to all anchors.",
    )
    parser.add_argument("--max-outer-iterations", type=int, default=80)
    parser.add_argument("--inner-max-iterations", type=int, default=300)
    return parser.parse_args()


def normalize_state_fips(value: str) -> str:
    state_fips = value.zfill(2)
    if state_fips not in STATE_NAMES:
        raise SystemExit(f"Unsupported state FIPS {value!r}. Expected one of the 50 states.")
    return state_fips


def load_tiger_tracts(state_fips: str, cache_dir: Path) -> Path:
    zip_name = f"tl_2020_{state_fips}_tract.zip"
    zip_path = cache_dir / zip_name
    tiger_url = (
        "https://www2.census.gov/geo/tiger/TIGER2020/TRACT/"
        f"{zip_name}"
    )
    if not zip_path.exists():
        download(tiger_url, zip_path)

    extract_dir = cache_dir / zip_name.removesuffix(".zip")
    if not extract_dir.exists():
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    return extract_dir


def download(url: str, path: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        path.write_bytes(resp.read())


def fetch_tract_populations(state_fips: str) -> dict[str, int]:
    url = (
        f"{CENSUS_POP_URL}?get=P1_001N&for=tract:*"
        f"&in=state:{state_fips}&in=county:*"
    )
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
    *,
    state_name: str,
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
        raise RuntimeError(f"No populated {state_name} tracts were loaded.")

    lon0 = lon_sum / pop_sum
    lat0 = lat_sum / pop_sum

    features: list[dict[str, Any]] = []
    units: list[Unit] = []
    for geoid, name, lon, lat, population, shape in raw_records:
        x, y = project_equirectangular(lon, lat, lon0, lat0)
        units.append(Unit(geoid=geoid, centroid=(x, y), population=population))
        features.append(
            {
                "type": "Feature",
                "id": geoid,
                "properties": {
                    "geoid": geoid,
                    "name": name,
                    "population": population,
                },
                "geometry": shape.__geo_interface__,
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
    features: Iterable[dict[str, Any]],
    units: list[Unit],
    lon0: float,
    lat0: float,
    *,
    state_fips: str,
    state_name: str,
    output_dir: Path,
) -> None:
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
        "type": "StateDistrictPlan",
        "state_fips": state_fips,
        "state_name": state_name,
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
        "projection": {
            "kind": "state-centered-equirectangular",
            "lon0": lon0,
            "lat0": lat0,
        },
        "feature_collection": {
            "type": "FeatureCollection",
            "features": enriched_features,
        },
        "notes": [
            "Prototype tract-level plan; census blocks remain unsplit by construction only after the block-level phase.",
            f"Distances are computed in a {state_name}-centered equirectangular projection for this demo artifact.",
        ],
    }

    path = output_dir / f"cap-{cap}-seats-{seats}.json"
    path.write_text(json.dumps(output, separators=(",", ":")), encoding="utf-8")
    print(
        f"Wrote {path.relative_to(ROOT)} "
        f"districts={seats} imbalance={result.max_population_imbalance}"
    )


if __name__ == "__main__":
    main()
