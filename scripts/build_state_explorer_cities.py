"""Build pinned 2020 Census place points for all state explorers.

Place population is POP100 from the Census TIGERweb 2020 attribute tables;
representative coordinates come from the 2020 Gazetteer, joined by GEOID.
Incorporated places and CDPs are both included, so Hawaii is not mislabeled as
having no cities. These points never assign an entire place to a district.

The existing Michigan city asset is reused byte-for-byte, with its original
narrower selection disclosed. This script adds a fragment and immutable assets;
it never publishes the shared manifest or modifies any saved district plan.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import csv
import gzip
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
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import BundleBuilder, CATALOG, OUTPUT, digest, encoded, read_pinned, safe_path, validate_catalog
from scripts.build_michigan_explorer_data import CITY_SOURCES, TableParser, read_asset

STATES = dict(pair.split(":") for pair in (
    "01:AL 02:AK 04:AZ 05:AR 06:CA 08:CO 09:CT 10:DE 12:FL 13:GA "
    "15:HI 16:ID 17:IL 18:IN 19:IA 20:KS 21:KY 22:LA 23:ME 24:MD "
    "25:MA 26:MI 27:MN 28:MS 29:MO 30:MT 31:NE 32:NV 33:NH 34:NJ "
    "35:NM 36:NY 37:NC 38:ND 39:OH 40:OK 41:OR 42:PA 44:RI 45:SC "
    "46:SD 47:TN 48:TX 49:UT 50:VT 51:VA 53:WA 54:WV 55:WI 56:WY"
).split())
MINIMUM_POPULATION = 10000
PINS_PATH = OUTPUT / "state-explorer-city-source-pins.json"
REPORT_PATH = OUTPUT / "state-explorer-city-report.json"
GAZETTEER_PAGE = "https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2020.html"
GAZETTEER_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_place_national.zip"
SOURCE_LIMIT = 20 * 1024 * 1024


def source_specs() -> list[dict[str, Any]]:
    result = [{"kind": "coordinates", "filename": "2020_Gaz_place_national.zip", "url": GAZETTEER_URL,
               "sourcePage": GAZETTEER_PAGE, "label": "2020 Census Gazetteer places",
               "vintage": "2020 Census", "stateFips": None}]
    for fips, abbreviation in STATES.items():
        if fips == "26":
            continue  # Reuse the original pinned Michigan asset and its source evidence.
        for kind in ("incplace", "cdp"):
            filename = f"tigerweb_acs25_{kind}_2020_tab20_{abbreviation.lower()}.html"
            url = f"https://tigerweb.geo.census.gov/tigerwebmain/Files/acs25/{filename}"
            result.append({"kind": kind, "filename": filename, "url": url, "sourcePage": url,
                           "label": "2020 incorporated-place populations" if kind == "incplace" else "2020 census-designated-place populations",
                           "vintage": "2020 Census; data as of January 1, 2020; POP100", "stateFips": fips})
    return result


def fetch_source(directory: Path, spec: dict, *, capture: bool = False) -> tuple[bytes, dict]:
    """First capture is explicit; later builds cannot silently refresh pinned data."""
    path = directory / spec["filename"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", spec["filename"]):
        raise ValueError("Unsafe source filename")
    if not capture and (not re.fullmatch(r"[0-9a-f]{64}", spec.get("sha256", ""))
                        or type(spec.get("bytes")) is not int or not 0 < spec["bytes"] <= SOURCE_LIMIT):
        raise ValueError("Missing source pin")
    if path.exists():
        raw = path.read_bytes()
    else:
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read(SOURCE_LIMIT + 1)
        if not raw or len(raw) > SOURCE_LIMIT:
            raise ValueError("Unexpected source size")
        if not capture and (len(raw) != spec["bytes"] or digest(raw) != spec["sha256"]):
            raise ValueError(f"Downloaded source differs from its pin: {spec['filename']}")
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".place-source-", dir=directory)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
        if path.read_bytes() != raw:
            raise ValueError("Concurrent source write differs")
    if not raw or len(raw) > SOURCE_LIMIT:
        raise ValueError("Unexpected cached source size")
    if not capture and (len(raw) != spec["bytes"] or digest(raw) != spec["sha256"]):
        raise ValueError(f"Cached source differs from its pin: {spec['filename']}")
    return raw, {**spec, "bytes": len(raw), "sha256": digest(raw)}


def parse_gazetteer(raw: bytes, *, zipped: bool = True) -> dict[str, dict]:
    if zipped:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if archive.namelist() != ["2020_Gaz_place_national.txt"]:
                raise ValueError("Unexpected national Gazetteer archive")
            info = archive.getinfo("2020_Gaz_place_national.txt")
            if info.file_size > SOURCE_LIMIT:
                raise ValueError("Gazetteer content is too large")
            raw = archive.read(info)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t")
    if not reader.fieldnames:
        raise ValueError("Missing Gazetteer header")
    reader.fieldnames = [name.strip() for name in reader.fieldnames]
    if not {"USPS", "GEOID", "NAME", "LSAD", "INTPTLAT", "INTPTLONG"}.issubset(reader.fieldnames):
        raise ValueError("Unexpected Gazetteer fields")
    result = {}
    for source_row in reader:
        row = {key: value.strip() for key, value in source_row.items() if key is not None and value is not None}
        geoid = row["GEOID"]
        if not re.fullmatch(r"\d{7}", geoid):
            raise ValueError("Invalid Gazetteer place GEOID")
        fips = geoid[:2]
        if fips not in STATES:
            continue
        latitude, longitude = float(row["INTPTLAT"]), float(row["INTPTLONG"])
        if (geoid in result or row["USPS"] != STATES[fips] or not row["NAME"]
                or not re.fullmatch(r"[A-Z0-9]{2}", row["LSAD"])
                or not math.isfinite(latitude) or not math.isfinite(longitude)
                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
            raise ValueError("Invalid or duplicate Gazetteer place")
        result[geoid] = {"stateFips": fips, "name": row["NAME"], "lsad": row["LSAD"], "coordinate": [longitude, latitude]}
    if not result:
        raise ValueError("Empty Gazetteer")
    return result


def parse_population_table(raw: bytes, state_fips: str, kind: str) -> dict[str, dict]:
    if state_fips not in STATES or kind not in {"incplace", "cdp"}:
        raise ValueError("Unknown state or place table")
    text = raw.decode("utf-8-sig")
    if "2020 Census - Data as of January 1, 2020" not in text:
        raise ValueError("Place population table is not the required 2020 vintage")
    parser = TableParser()
    parser.feed(text)
    if not parser.rows or not {"GEOID", "STATE", "BASENAME", "NAME", "LSADC", "POP100", "MTFCC"}.issubset(parser.rows[0]):
        raise ValueError("Unexpected population table fields")
    if parser.rows[1:] == [["No data available"]]:
        return {}
    header, result = parser.rows[0], {}
    for cells in parser.rows[1:]:
        if len(cells) != len(header):
            raise ValueError("Malformed population table row")
        row = dict(zip(header, cells))
        geoid = row["GEOID"]
        if (not re.fullmatch(state_fips + r"\d{5}", geoid) or row["STATE"] != state_fips or geoid in result
                or not re.fullmatch(r"\d+", row["POP100"]) or not row["NAME"] or not row["BASENAME"]
                or row["MTFCC"] != ("G4110" if kind == "incplace" else "G4210")):
            raise ValueError("Invalid, duplicate or wrong-state population record")
        result[geoid] = {"population": int(row["POP100"]), "name": row["NAME"], "baseName": row["BASENAME"],
                         "lsad": row["LSADC"], "kind": "incorporated-place" if kind == "incplace" else "census-designated-place"}
    return result


def place_collection(gazetteer: dict, populations: dict, state_fips: str, sources: list[dict], minimum: int = MINIMUM_POPULATION) -> dict:
    if state_fips not in STATES or type(minimum) is not int or minimum < 0:
        raise ValueError("Invalid place selection")
    features = []
    expected_geoids = {geoid for geoid, value in gazetteer.items() if value["stateFips"] == state_fips}
    if set(populations) != expected_geoids:
        missing, extra = sorted(expected_geoids - populations.keys()), sorted(populations.keys() - expected_geoids)
        raise ValueError(f"Incomplete Gazetteer/population join for {state_fips}: missing={missing[:15]}, extra={extra[:15]}")
    for geoid, row in populations.items():
        coordinate = gazetteer[geoid]
        if coordinate["name"] != row["name"] or coordinate["lsad"] != row["lsad"]:
            raise ValueError(f"Place-source name/LSAD join mismatch: {geoid}: {coordinate['name']} vs {row['name']}")
        if row["population"] < minimum:
            continue
        longitude, latitude = coordinate["coordinate"]
        if state_fips == "02" and longitude > 0:
            longitude -= 360
        features.append({"type": "Feature", "properties": {"geoid": geoid, "name": row["baseName"],
                         "fullName": row["name"], "population": row["population"], "kind": row["kind"], "year": 2020},
                         "geometry": {"type": "Point", "coordinates": [longitude, latitude]}})
    features.sort(key=lambda feature: (-feature["properties"]["population"], feature["properties"]["geoid"]))
    for rank, feature in enumerate(features, start=1):
        feature["properties"]["rank"] = rank
    return {"type": "FeatureCollection", "features": features, "metadata": {"stateFips": state_fips,
            "vintage": 2020, "minimumPopulation": minimum,
            "coordinateFrame": "alaska-continuous" if state_fips == "02" else "source",
            "selection": "2020 incorporated places and census-designated places, sorted by POP100 then GEOID",
            "coordinateMeaning": "2020 Gazetteer representative internal point; not a place boundary or place-wide district assignment",
            "sources": sources}}


def build_cities(bundle_root: Path, cache_root: Path, *, capture_source_pins: bool = False) -> dict:
    started = time.perf_counter()
    root, cache_root = bundle_root.resolve(), cache_root.resolve()
    index_raw = safe_path(root, OUTPUT / "server-index.json").read_bytes()
    index = json.loads(index_raw)
    manifest_raw = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(manifest_raw)
    catalog_raw = read_pinned(root, CATALOG, index["catalogSha256"])
    validate_catalog(json.loads(catalog_raw))
    if {p["stateFips"] for p in manifest["plans"].values()} != set(STATES) or manifest["catalogSha256"] != digest(catalog_raw):
        raise ValueError("Place labels require the accepted 50-state catalog")
    pins_path = safe_path(root, PINS_PATH)
    specs = source_specs()
    if pins_path.exists():
        pins = json.loads(pins_path.read_bytes())
        if [{k: row[k] for k in spec} for row, spec in zip(pins["sources"], specs)] != specs or len(pins["sources"]) != len(specs):
            raise ValueError("Source pin set does not match the declared sources")
        specs = pins["sources"]
        capture_source_pins = False
    elif not capture_source_pins:
        raise ValueError("Missing place-source pins; explicitly capture and validate the first source snapshot")
    sources_directory = cache_root / "block-main-port" / "state-explorer-city-sources-v1"
    with ThreadPoolExecutor(max_workers=4) as executor:
        fetched = list(executor.map(lambda spec: fetch_source(sources_directory, spec, capture=capture_source_pins), specs))
    raw_sources = {spec["filename"]: raw for raw, spec in fetched}
    pinned_sources = [spec for _, spec in fetched]
    gazetteer = parse_gazetteer(raw_sources[pinned_sources[0]["filename"]])
    builder = BundleBuilder(root, cache_root=cache_root)
    result: dict[str, Any] = {"status": "complete", "catalogSha256": digest(catalog_raw), "states": {}, "assets": {}, "audit": {"states": {}}}
    preserved = {}
    for fips in STATES:
        if fips == "26":
            asset = manifest["michiganExplorer"]["cities"]
            cities = read_asset(root, cache_root, index, asset, preserved)
            if (cities.get("metadata", {}).get("stateFips") != "26" or len(cities.get("features", [])) != 91):
                raise ValueError("Existing Michigan city asset changed")
            key = asset["url"].removeprefix("/api/district-plans/")
            builder.assets[key] = deepcopy(index["assets"][key])
            sources = [{**source, "label": source["kind"].capitalize()} for source in CITY_SOURCES]
            description = "91 incorporated Michigan cities with at least 10,000 residents in the 2020 Census. Original Michigan selection preserved; villages and CDPs are excluded."
            result["audit"]["states"][fips] = {"source": "reused-original-michigan-asset", "featureCount": 91, "assetSha256": asset["sha256"]}
        else:
            sources = [spec for spec in pinned_sources if spec["stateFips"] in (None, fips)]
            populations = {}
            counts = {}
            for source in sources[1:]:
                rows = parse_population_table(raw_sources[source["filename"]], fips, source["kind"])
                if populations.keys() & rows.keys():
                    raise ValueError(f"Duplicate place across population sources in {fips}")
                counts[source["kind"]] = len(rows)
                populations.update(rows)
            cities = place_collection(gazetteer, populations, fips, sources)
            if not cities["features"]:
                raise ValueError(f"No places met the declared threshold in {fips}")
            asset = builder.generated(cities, f"{fips}-explorer-places.geojson")
            description = "2020 Census incorporated places and census-designated places with at least 10,000 residents. Representative points do not show place boundaries or assign a whole place to one district."
            result["audit"]["states"][fips] = {"sourcePlaceCount": len(populations), "sourceKinds": counts,
                "matchedGazetteerCount": len(populations), "featureCount": len(cities["features"]),
                "minimumPopulation": MINIMUM_POPULATION, "assetSha256": asset["sha256"],
                "selectedPopulationSum": sum(f["properties"]["population"] for f in cities["features"])}
        metadata = {"label": "City points" if fips == "26" else "Cities & places", "description": description,
                    "featureCount": len(cities["features"]), "minimumPopulation": MINIMUM_POPULATION,
                    "vintage": "2020 Census", "coordinateMeaning": cities["metadata"]["coordinateMeaning"], "sources": sources}
        result["states"][fips] = {"cities": asset, "cityMetadata": metadata}
        print(f"{fips} {STATES[fips]}: {len(cities['features'])} place points", flush=True)
    for source in pinned_sources:
        if digest((sources_directory / source["filename"]).read_bytes()) != source["sha256"]:
            raise ValueError("Place source changed during generation")
    # The first pin snapshot is committed only after every source and join passes.
    if capture_source_pins:
        pin_document = {"schemaVersion": 1, "vintage": "2020 Census", "sources": pinned_sources}
        with pins_path.open("xb") as stream:
            stream.write(encoded(pin_document))
    for path, expected in preserved.items():
        if digest(path.read_bytes()) != expected:
            raise ValueError("Preserved Michigan asset changed during place generation")
    for relative, raw in ((OUTPUT / "manifest.json", manifest_raw), (OUTPUT / "server-index.json", index_raw), (CATALOG, catalog_raw)):
        if safe_path(root, relative).read_bytes() != raw:
            raise ValueError("Accepted bundle changed during city fragment generation")
    result["assets"] = builder.assets
    result["audit"].update({"status": "complete", "catalogSha256": digest(catalog_raw), "stateCount": len(STATES),
        "featureCount": sum(state["cityMetadata"]["featureCount"] for state in result["states"].values()),
        "sourcePins": {"path": PINS_PATH.as_posix(), "sha256": digest(pins_path.read_bytes())},
        "sourceSnapshotBytes": sum(source["bytes"] for source in pinned_sources),
        "preservedPlansSha256": digest(encoded(manifest["plans"])), "preservedProofsSha256": digest(encoded(index["proofs"])),
        "savedAssignmentsModified": 0, "solverRuns": 0, "runtimeSeconds": time.perf_counter() - started,
        "populationMeaning": "Population of each selected Census place, not residents assigned to its point's district"})
    safe_path(root, REPORT_PATH).write_bytes(encoded(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--capture-source-pins", action="store_true")
    args = parser.parse_args()
    result = build_cities(args.bundle_root, args.cache_root, capture_source_pins=args.capture_source_pins)
    print(json.dumps({"status": result["status"], "states": len(result["states"]), "features": result["audit"]["featureCount"],
                      "runtimeSeconds": result["audit"]["runtimeSeconds"]}, indent=2))


if __name__ == "__main__":
    main()
