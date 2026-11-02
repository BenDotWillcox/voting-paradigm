"""Prepare shared-edge display meshes for every accepted state explorer.

This writes new, content-addressed display assets and a fragment for the bundle
publisher. It never publishes the app manifest, changes a saved assignment, or
replaces a historical report. Michigan's proven land-focused display is reused.
Other states retain their saved census footprint, including water; no land mask
or artificial link is inferred. Alaska stays in its accepted continuous frame.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import json
import math
import os
from pathlib import Path
import sys
import time

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import BundleBuilder, CATALOG, OUTPUT, digest, encoded, read_pinned, resource_path, safe_path, validate_catalog
from scripts.build_block_state_outlines import read_full_outlines
from scripts.build_michigan_explorer_geometry import boundary_layers, read_asset
from scripts.build_michigan_land_display import file_digest, polygon_parts, simplify_display

REPORT = OUTPUT / "state-explorer-geometry-report.json"
FRAGMENTS = OUTPUT / "state-explorer-geometry-fragments"
OVERVIEW_TOLERANCE = 0.002
DETAIL_TOLERANCE = 0.0001
GEOMETRY_KEYS = ("overview", "coast", "dividers", "detailDividers")


def runtime_hashes() -> dict[str, str]:
    return {name: file_digest(ROOT / "scripts" / name) for name in (
        "build_state_explorer_geometry.py", "build_michigan_explorer_geometry.py",
        "build_michigan_land_display.py", "build_block_state_outlines.py", "build_block_plan_bundle.py",
    )}


def validate_collection(collection: dict, plan: dict) -> None:
    """Keep populations/IDs/frame independent of cartographic simplification."""
    if collection.get("type") != "FeatureCollection" or len(collection.get("features", [])) != plan["districtCount"]:
        raise ValueError("Explorer geometry has an unexpected district count")
    seen = set()
    for feature in collection["features"]:
        props = feature.get("properties", {})
        district = props.get("district_id")
        if type(district) is not int or district in seen or not 0 <= district < plan["districtCount"]:
            raise ValueError("Explorer geometry has an invalid district identity")
        if props.get("population") != plan["districtPopulations"][district]:
            raise ValueError("Explorer geometry population differs from saved plan")
        seen.add(district)
        geometry = shape(feature["geometry"])
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Explorer geometry must retain valid nonempty polygons")
        if any(not math.isfinite(value) for value in geometry.bounds):
            raise ValueError("Explorer geometry contains invalid bounds")
        minx, miny, maxx, maxy = geometry.bounds
        if not -90 <= miny <= maxy <= 90 or not -360 <= minx <= maxx <= 360:
            raise ValueError("Explorer geometry is outside geographic coordinates")
        # A wrapped Alaska export could turn an Aleutian component into a map-
        # spanning polygon. The accepted working-frame bbox is authoritative.
        if plan["coordinateFrame"] == "alaska-continuous":
            west, south, east, north = plan["bbox"]
            if minx < west - 1e-6 or maxx > east + 1e-6 or miny < south - 1e-6 or maxy > north + 1e-6:
                raise ValueError("Alaska geometry escaped its continuous longitude frame")


def prepare_layers(collection: dict, plan: dict) -> tuple[dict, dict]:
    validate_collection(collection, plan)
    source = deepcopy(collection)
    source.setdefault("metadata", {}).update({
        "purpose": "display-only", "planId": plan["id"], "stateFips": plan["stateFips"],
        "coordinateFrame": plan["coordinateFrame"], "coverage": "census",
        "method": "Joint coverage simplification of saved full census districts; retain all islands and holes.",
        "population_basis": "All saved census blocks; source census water extent is retained.",
    })
    overview = simplify_display(source, OVERVIEW_TOLERANCE, full_collection=source)
    detail = simplify_display(source, DETAIL_TOLERANCE, full_collection=source)
    for item in (overview, detail):
        validate_collection(item, plan)
        if [f["properties"] for f in item["features"]] != [f["properties"] for f in source["features"]]:
            raise ValueError("Display simplification changed saved district properties")
    coast, dividers, overview_audit = boundary_layers(overview, plan["id"])
    _, detail_dividers, detail_audit = boundary_layers(detail, plan["id"])
    for item in (coast, dividers, detail_dividers):
        item["metadata"].update({"stateFips": plan["stateFips"], "coordinateFrame": plan["coordinateFrame"], "coverage": "census"})
        for feature in item["features"]:
            if "state_fips" in feature["properties"]:
                feature["properties"]["state_fips"] = plan["stateFips"]
    counts = lambda value: {
        "polygonParts": sum(len(polygon_parts(shape(f["geometry"]))) for f in value["features"]),
        "holes": sum(len(p.interiors) for f in value["features"] for p in polygon_parts(shape(f["geometry"]))),
    }
    audit = {"coverage": "census", "sourceTopology": counts(source), "overviewTopology": counts(overview),
             "detailTopology": counts(detail), "overviewDividers": overview_audit, "detailDividers": detail_audit,
             "savedDistrictPropertiesUnchanged": True, "artificialConnectionsAdded": 0,
             "coordinateFrame": plan["coordinateFrame"], "coordinateWrappingApplied": False,
             "overviewToleranceDegrees": OVERVIEW_TOLERANCE, "detailToleranceDegrees": DETAIL_TOLERANCE}
    return {"overview": overview, "coast": coast, "dividers": dividers, "detailDividers": detail_dividers, "detail": detail}, audit


def checked_entry(root: Path, cache: Path, asset: dict, entries: dict) -> tuple[str, dict]:
    key = asset["url"].removeprefix("/api/district-plans/")
    if not asset["url"].startswith("/api/district-plans/") or key not in entries:
        raise ValueError("Geometry fragment references an unlisted asset")
    entry = entries[key]
    compressed = read_pinned(root, entry["path"], entry["gzipSha256"], cache)
    raw = gzip.decompress(compressed)
    if (len(compressed) != asset["gzipBytes"] or len(raw) != asset["bytes"]
            or digest(raw) != asset["sha256"] or digest(raw) != entry["rawSha256"]
            or entry["rawBytes"] != len(raw) or entry["gzipBytes"] != len(compressed)):
        raise ValueError("Geometry fragment asset identity mismatch")
    json.loads(raw)
    return key, entry


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def build_geometry(bundle_root: Path, cache_root: Path, states: set[str] | None = None) -> dict:
    started = time.perf_counter()
    root, cache = bundle_root.resolve(), cache_root.resolve()
    catalog_raw = safe_path(root, CATALOG).read_bytes()
    catalog = json.loads(catalog_raw)
    validate_catalog(catalog)
    catalog_sha = digest(catalog_raw)
    index_path = safe_path(root, OUTPUT / "server-index.json")
    index_raw = index_path.read_bytes()
    index = json.loads(index_raw)
    manifest_raw = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(manifest_raw)
    if manifest["catalogSha256"] != catalog_sha or index["catalogSha256"] != catalog_sha:
        raise ValueError("Explorer geometry must use the accepted catalog")
    selected = sorted((p for p in catalog["plans"] if states is None or p["state_fips"] in states), key=lambda p: p["plan_id"])
    if not selected or (states is not None and {p["state_fips"] for p in selected} != states):
        raise ValueError("Requested geometry states are not in the accepted catalog")
    hashes = runtime_hashes()
    plans, assets, audits, preserved = {}, {}, {}, {}
    for accepted in selected:
        plan_id = accepted["plan_id"]
        plan = manifest["plans"][plan_id]
        plan_started = time.perf_counter()
        identity = {"catalogSha256": catalog_sha, "acceptedPlanSha256": digest(encoded(accepted)),
                    "appPlanSha256": digest(encoded(plan)), "runtimeHashes": hashes}
        fragment_path = safe_path(root, FRAGMENTS / f"{plan_id}.json")
        if fragment_path.exists():
            fragment = json.loads(fragment_path.read_bytes())
            if fragment.get("identity") == identity and fragment.get("status") == "complete":
                for reference in fragment["record"].values():
                    if isinstance(reference, dict) and "url" in reference:
                        checked_entry(root, cache, reference, fragment["assets"])
                for source in fragment["audit"]["preservedFiles"]:
                    read_pinned(root, source["path"], source["sha256"], cache)
                print(f"Reused explorer geometry {plan_id}", flush=True)
                plans[plan_id], audits[plan_id] = fragment["record"], fragment["audit"]
                assets.update(fragment["assets"])
                preserved.update({item["path"]: item["sha256"] for item in fragment["audit"]["preservedFiles"]})
                continue
        print(f"Preparing explorer geometry {plan_id}", flush=True)
        builder = BundleBuilder(root, cache_root=cache)
        sources = {}
        if plan["stateFips"] == "26":
            original = manifest["michiganExplorer"]["plans"][plan_id]
            record = {key: deepcopy(original[key]) for key in GEOMETRY_KEYS}
            record.update({"coverage": "land-focused", "coordinateFrame": "source"})
            for key in GEOMETRY_KEYS:
                asset_key, entry = checked_entry(root, cache, record[key], index["assets"])
                builder.assets[asset_key] = deepcopy(entry)
                sources[entry["path"]] = entry["gzipSha256"]
            audit = {"coverage": "land-focused", "reusedMichiganDerivative": True,
                     "savedDistrictPropertiesUnchanged": True, "artificialConnectionsAdded": 0,
                     "coordinateFrame": "source", "coordinateWrappingApplied": False}
        else:
            full, proof = read_full_outlines(root, accepted, cache_root=cache)
            sources[proof["path"]] = proof["gzip_sha256"]
            layers, audit = prepare_layers(full, plan)
            record = {key: builder.generated(value, f"{plan_id}-state-explorer-{key}.geojson") for key, value in layers.items()}
            record.update({"coverage": "census", "coordinateFrame": plan["coordinateFrame"]})
            audit["fullSource"] = proof
        if plan["assets"].get("connections"):
            key, entry = checked_entry(root, cache, plan["assets"]["connections"], index["assets"])
            sources[entry["path"]] = entry["gzipSha256"]
            audit["recordedConnectionsSha256"] = plan["assets"]["connections"]["sha256"]
            audit["recordedLinkCount"] = plan["recordedLinkCount"]
        for path, sha in sources.items():
            read_pinned(root, path, sha, cache)
        audit.update({"residentPopulation": plan["residentPopulation"], "blockCount": plan["blockCount"],
                      "runtimeSeconds": time.perf_counter() - plan_started,
                      "preservedFiles": [{"path": path, "sha256": sha} for path, sha in sources.items()]})
        fragment = {"schemaVersion": 1, "status": "complete", "identity": identity,
                    "record": record, "assets": builder.assets, "audit": audit}
        atomic_json(fragment_path, fragment)
        plans[plan_id], audits[plan_id] = record, audit
        assets.update(builder.assets)
        preserved.update(sources)
        print(f"Prepared explorer geometry {plan_id}: {audit['runtimeSeconds']:.2f}s", flush=True)
    if (safe_path(root, CATALOG).read_bytes() != catalog_raw or index_path.read_bytes() != index_raw
            or safe_path(root, OUTPUT / "manifest.json").read_bytes() != manifest_raw):
        raise ValueError("Authoritative bundle metadata changed while geometry was prepared")
    for path, sha in preserved.items():
        read_pinned(root, path, sha, cache)
    result = {"schemaVersion": 1, "status": "complete", "catalogSha256": catalog_sha,
              "plans": plans, "assets": assets,
              "audit": {"plans": audits, "savedPlansModified": 0, "solverRuns": 0,
                        "sourceFilesPreserved": len(preserved), "runtimeHashes": hashes,
                        "limitation": "Michigan reuses verified land-focused coverage. All other states retain saved census water extent; no shoreline clipping or new water links are inferred."},
              "runtimeSeconds": time.perf_counter() - started}
    report_path = REPORT if states is None else OUTPUT / ("state-explorer-geometry-report-" + "-".join(sorted(states)) + ".json")
    atomic_json(safe_path(root, report_path), result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, default=Path(os.environ.get("BLOCK_PLAN_CACHE_ROOT", ROOT / ".cache")))
    parser.add_argument("--states", nargs="+", help="Optional FIPS subset for a pilot; writes a separate subset report")
    args = parser.parse_args()
    result = build_geometry(args.bundle_root, args.cache_root, set(args.states) if args.states else None)
    print(json.dumps({"status": result["status"], "plans": len(result["plans"]), "assets": len(result["assets"]), "runtimeSeconds": result["runtimeSeconds"]}))


if __name__ == "__main__":
    main()
