"""Prepare Michigan navigation summaries and Census city labels, never new plans.

County shares are resident shares of the full saved county, not area shares or
shares of the selected district. Every saved block, including zero-population
and water-only blocks, contributes to the count reconciliation. City points are
representative 2020 Gazetteer coordinates; they do not describe city boundaries
or assign all city residents to the district containing the point.

The returned fragment is published by the explorer bundle orchestrator. This
module deliberately does not modify the shared manifest or server index.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import (
    BundleBuilder, CATALOG, OUTPUT, digest, encoded, read_pinned,
    resource_path, safe_path, validate_catalog,
)

CITY_SOURCES = (
    {
        "kind": "coordinates", "filename": "2020_gaz_place_26.txt",
        "url": "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_gaz_place_26.txt",
        "sourcePage": "https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2020.html",
        "bytes": 149936, "sha256": "6718bbd6151a13e91e516706f4495967ce144f140ad9f1b219b0040eccce9875",
        "vintage": "2020 Census Gazetteer places",
    },
    {
        "kind": "population", "filename": "tigerweb_2020_michigan_incorporated_places.html",
        "url": "https://tigerweb.geo.census.gov/tigerwebmain/Files/acs25/tigerweb_acs25_incplace_2020_tab20_mi.html",
        "sourcePage": "https://tigerweb.geo.census.gov/tigerwebmain/Files/acs25/tigerweb_acs25_incplace_2020_tab20_mi.html",
        "bytes": 464138, "sha256": "371f7ce22e3c6c3e424e26a1d7a7300da7d3035a5dcc95b0235ce17a96badf67",
        "vintage": "2020 Census incorporated places, data as of January 1, 2020; POP100",
    },
)
CITY_MINIMUM_POPULATION = 10000


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch_city_sources(directory: Path) -> dict[str, bytes]:
    """Reuse only matching pinned source bytes; never overwrite a mismatch."""
    result = {}
    for spec in CITY_SOURCES:
        target = directory / spec["filename"]
        if not target.exists():
            directory.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(spec["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read(spec["bytes"] + 1)
            if len(raw) != spec["bytes"] or digest(raw) != spec["sha256"]:
                raise ValueError(f"Downloaded city source differs from its pin: {spec['filename']}")
            descriptor, temporary_name = tempfile.mkstemp(prefix=".cities-", dir=directory)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    pass  # A racing writer is still subject to the same pin below.
            finally:
                temporary.unlink(missing_ok=True)
        raw = target.read_bytes()
        if len(raw) != spec["bytes"] or digest(raw) != spec["sha256"]:
            raise ValueError(f"City source differs from its pin: {spec['filename']}")
        result[spec["kind"]] = raw
    return result


def parse_gazetteer(raw: bytes) -> dict[str, dict[str, Any]]:
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t")
    if not rows.fieldnames:
        raise ValueError("Missing Gazetteer header")
    rows.fieldnames = [value.strip() for value in rows.fieldnames]
    if not {"USPS", "GEOID", "NAME", "LSAD", "INTPTLAT", "INTPTLONG"}.issubset(rows.fieldnames):
        raise ValueError("Unexpected Gazetteer fields")
    result = {}
    for raw_row in rows:
        row = {key: value.strip() for key, value in raw_row.items() if key is not None and value is not None}
        geoid = row["GEOID"]
        latitude, longitude = float(row["INTPTLAT"]), float(row["INTPTLONG"])
        if (not re.fullmatch(r"26\d{5}", geoid) or geoid in result or row["USPS"] != "MI"
                or not row["NAME"] or not math.isfinite(latitude) or not math.isfinite(longitude)
                or not 41 <= latitude <= 49 or not -91 <= longitude <= -82):
            raise ValueError("Invalid or duplicate Michigan Gazetteer place")
        result[geoid] = {"name": row["NAME"], "lsad": row["LSAD"], "coordinate": [longitude, latitude]}
    if not result:
        raise ValueError("Empty Michigan Gazetteer")
    return result


class TableParser(HTMLParser):
    """Read table text only; source HTML is never executed or used as instructions."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("th", "td") and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_place_populations(raw: bytes) -> dict[str, dict[str, Any]]:
    text = raw.decode("utf-8-sig")
    if "2020 Census - Data as of January 1, 2020" not in text:
        raise ValueError("Place population table is not the required 2020 vintage")
    parser = TableParser()
    parser.feed(text)
    if not parser.rows or not {"GEOID", "STATE", "BASENAME", "NAME", "LSADC", "POP100"}.issubset(parser.rows[0]):
        raise ValueError("Unexpected incorporated-place population fields")
    header, result = parser.rows[0], {}
    for cells in parser.rows[1:]:
        if len(cells) != len(header):
            raise ValueError("Malformed incorporated-place row")
        row = dict(zip(header, cells))
        geoid = row["GEOID"]
        if (not re.fullmatch(r"26\d{5}", geoid) or row["STATE"] != "26" or geoid in result
                or not re.fullmatch(r"\d+", row["POP100"]) or not row["NAME"] or not row["BASENAME"]):
            raise ValueError("Invalid or duplicate incorporated-place population")
        result[geoid] = {"population": int(row["POP100"]), "name": row["NAME"], "baseName": row["BASENAME"], "lsad": row["LSADC"]}
    if not result:
        raise ValueError("Empty incorporated-place population table")
    return result


def city_collection(gazetteer: dict, populations: dict, minimum: int = CITY_MINIMUM_POPULATION) -> dict:
    if type(minimum) is not int or minimum < 0:
        raise ValueError("Invalid minimum city population")
    features = []
    for geoid, row in populations.items():
        coordinate = gazetteer.get(geoid)
        if coordinate is None or coordinate["name"] != row["name"] or coordinate["lsad"] != row["lsad"]:
            raise ValueError(f"2020 city-source join mismatch: {geoid}")
        # Michigan's legal-statistical area descriptor 25 denotes a city.
        # Villages and CDPs are intentionally not described as cities here.
        if row["lsad"] != "25" or row["population"] < minimum:
            continue
        features.append({"type": "Feature", "properties": {
            "geoid": geoid, "name": row["baseName"], "fullName": row["name"],
            "population": row["population"], "kind": "incorporated-city", "year": 2020,
        }, "geometry": {"type": "Point", "coordinates": coordinate["coordinate"]}})
    features.sort(key=lambda feature: (-feature["properties"]["population"], feature["properties"]["geoid"]))
    for rank, feature in enumerate(features, start=1):
        feature["properties"]["rank"] = rank
    return {"type": "FeatureCollection", "features": features, "metadata": {
        "stateFips": "26", "vintage": 2020, "minimumPopulation": minimum,
        "selection": "Michigan incorporated cities (LSAD 25), sorted by 2020 POP100, then GEOID",
        "coordinateMeaning": "2020 Gazetteer representative internal point; not a city boundary or city-wide district assignment",
        "sources": list(CITY_SOURCES),
    }}


def read_asset(root: Path, cache_root: Path, index: dict, asset: dict, preserved: dict[Path, str]) -> dict:
    prefix = "/api/district-plans/"
    if not isinstance(asset.get("url"), str) or not asset["url"].startswith(prefix):
        raise ValueError("Invalid explorer input asset URL")
    key = asset["url"][len(prefix):]
    entry = index["assets"].get(key)
    if entry is None or any(asset.get(public) != entry.get(private) for public, private in (
            ("sha256", "rawSha256"), ("bytes", "rawBytes"), ("gzipBytes", "gzipBytes"))):
        raise ValueError("Explorer input asset does not match its allowlist")
    path = resource_path(root, entry["path"], cache_root)
    compressed = path.read_bytes()
    raw = gzip.decompress(compressed)
    if (digest(compressed) != entry["gzipSha256"] or len(compressed) != entry["gzipBytes"]
            or digest(raw) != entry["rawSha256"] or len(raw) != entry["rawBytes"]):
        raise ValueError("Explorer input payload hash or byte count changed")
    preserved[path] = entry["gzipSha256"]
    return json.loads(raw)


def summarize_county(collection: dict, county: dict, name: str, district_count: int, seen: set[str]) -> dict:
    if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
        raise ValueError("County detail is not a FeatureCollection")
    if not re.fullmatch(r"\d{3}", county["fips"]) or not name:
        raise ValueError("Invalid named county identity")
    totals: dict[int, dict[str, int]] = {}
    for feature in collection["features"]:
        props = feature.get("properties", {})
        geoid, district, population = props.get("geoid"), props.get("district_id"), props.get("population")
        if (not isinstance(geoid, str) or not re.fullmatch(r"\d{15}", geoid)
                or not geoid.startswith("26" + county["fips"]) or geoid in seen
                or type(district) is not int or not 0 <= district < district_count
                or type(population) is not int or population < 0):
            raise ValueError("Invalid, duplicate, or wrong-county saved block")
        seen.add(geoid)
        values = totals.setdefault(district, {"population": 0, "blockCount": 0})
        values["population"] += population
        values["blockCount"] += 1
    population = sum(values["population"] for values in totals.values())
    count = sum(values["blockCount"] for values in totals.values())
    bbox = county.get("bbox")
    if (not isinstance(bbox, list) or len(bbox) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in bbox)
            or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]):
        raise ValueError("Invalid saved county bounding box")
    if population != county["population"] or count != county["blockCount"]:
        raise ValueError("County block population/count does not reconcile with its saved index")
    return {"fips": county["fips"], "name": name, "population": population, "blockCount": count, "bbox": bbox,
            "districtShares": [{"districtId": district, **values,
                                "percent": 100 * values["population"] / population if population else 0}
                               for district, values in sorted(totals.items())]}


def plan_summary(plan: dict, counties: list[dict]) -> dict:
    if len({county["fips"] for county in counties}) != len(counties):
        raise ValueError("Duplicate county summary")
    districts = [{"districtId": district, "population": 0, "blockCount": 0, "countyFips": []}
                 for district in range(plan["districtCount"])]
    for county in counties:
        for share in county["districtShares"]:
            district = districts[share["districtId"]]
            district["population"] += share["population"]
            district["blockCount"] += share["blockCount"]
            district["countyFips"].append(county["fips"])
    for district in districts:
        district["countyFips"].sort()
    if (sum(county["population"] for county in counties) != plan["residentPopulation"]
            or sum(county["blockCount"] for county in counties) != plan["blockCount"]
            or [d["population"] for d in districts] != plan["districtPopulations"]):
        raise ValueError("County/district summaries do not reconcile to the saved plan")
    return {"planId": plan["id"], "stateFips": "26", "residentPopulation": plan["residentPopulation"],
            "blockCount": plan["blockCount"], "counties": sorted(counties, key=lambda row: row["fips"]),
            "districts": districts}


def build_data(bundle_root: Path, cache_root: Path) -> dict:
    started = time.perf_counter()
    root, cache_root = bundle_root.resolve(), cache_root.resolve()
    index_path, manifest_path, catalog_path = (safe_path(root, OUTPUT / "server-index.json"),
                                               safe_path(root, OUTPUT / "manifest.json"), safe_path(root, CATALOG))
    index_raw = index_path.read_bytes()
    index = json.loads(index_raw)
    manifest_raw = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(manifest_raw)
    catalog_raw = read_pinned(root, CATALOG, index["catalogSha256"])
    catalog = json.loads(catalog_raw)
    validate_catalog(catalog)
    if manifest["catalogSha256"] != digest(catalog_raw):
        raise ValueError("Explorer manifest and catalog differ")
    preserved = {index_path: digest(index_raw), manifest_path: digest(manifest_raw), catalog_path: digest(catalog_raw)}
    plans = sorted((p for p in manifest["plans"].values() if p["stateFips"] == "26"), key=lambda p: p["districtCount"])
    if [p["districtCount"] for p in plans] != [13, 18, 21, 30]:
        raise ValueError("Unexpected Michigan accepted plans")
    county_reference = read_asset(root, cache_root, index, manifest["comparisonLayers"]["26"]["counties"]["asset"], preserved)
    names = {}
    for feature in county_reference["features"]:
        props = feature["properties"]
        geoid = props.get("geoid")
        if not isinstance(geoid, str) or not re.fullmatch(r"26\d{3}", geoid) or geoid[2:] in names or not props.get("name"):
            raise ValueError("Invalid or duplicate Michigan county name")
        names[geoid[2:]] = props["name"]
    if len(names) != 83:
        raise ValueError("Michigan reference must contain all 83 counties")
    builder = BundleBuilder(root)
    result = {"plans": {}, "assets": {}, "audit": {"plans": {}}}
    for plan in plans:
        print(f"Summarizing {plan['id']}: verifying all county block payloads", flush=True)
        detail = read_asset(root, cache_root, index, plan["assets"]["detailIndex"], preserved)
        if detail["planId"] != plan["id"] or {county["fips"] for county in detail["counties"]} != set(names):
            raise ValueError("Michigan county index does not match its plan/name coverage")
        seen: set[str] = set()
        counties = [summarize_county(read_asset(root, cache_root, index, county["asset"], preserved),
                                    county, names[county["fips"]], plan["districtCount"], seen)
                    for county in detail["counties"]]
        summary = plan_summary(plan, counties)
        accepted = next(p for p in catalog["plans"] if p["plan_id"] == plan["id"])
        if [district["blockCount"] for district in summary["districts"]] != accepted["validation"]["district_block_counts"]:
            raise ValueError("District block totals differ from the accepted catalog")
        result["plans"][plan["id"]] = {"summary": builder.generated(summary, f"{plan['id']}-explorer-summary.json")}
        result["audit"]["plans"][plan["id"]] = {"countyCount": len(counties), "blockCount": len(seen),
            "residentPopulation": summary["residentPopulation"], "districtPopulations": [d["population"] for d in summary["districts"]],
            "districtBlockCounts": [d["blockCount"] for d in summary["districts"]],
            "kent": next(county for county in counties if county["fips"] == "081")}
    sources_directory = safe_path(root, ".cache/block-main-port/michigan-explorer-sources")
    sources = fetch_city_sources(sources_directory)
    cities = city_collection(parse_gazetteer(sources["coordinates"]), parse_place_populations(sources["population"]))
    if not cities["features"]:
        raise ValueError("No cities met the declared source selection")
    result["cities"] = builder.generated(cities, "26-explorer-cities.geojson")
    result["assets"] = builder.assets
    for spec in CITY_SOURCES:
        preserved[sources_directory / spec["filename"]] = spec["sha256"]
    for path, original in preserved.items():
        if file_hash(path) != original:
            raise ValueError(f"Preserved input changed during explorer data preparation: {path}")
    result["audit"].update({"status": "complete", "catalogSha256": digest(catalog_raw),
        "sourceFilesModified": 0, "savedAssignmentsModified": 0,
        "cityCount": len(cities["features"]), "citySources": list(CITY_SOURCES),
        "cityPopulationMinimum": CITY_MINIMUM_POPULATION,
        "populationShareBasis": "All resident population of each whole county from saved block assignments, not area or block share",
        "preservedFiles": [{"path": str(path), "sha256": value} for path, value in sorted(preserved.items())],
        "runtimeSeconds": time.perf_counter() - started})
    safe_path(root, OUTPUT / "michigan-explorer-data-report.json").write_bytes(encoded(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_data(args.bundle_root, args.cache_root)
    print(json.dumps({"status": result["audit"]["status"], "cities": result["audit"]["cityCount"],
                      "plans": list(result["plans"]), "runtimeSeconds": result["audit"]["runtimeSeconds"]}, indent=2))


if __name__ == "__main__":
    main()
