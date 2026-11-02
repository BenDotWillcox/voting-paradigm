"""Publish display-only Michigan exploration assets beside the accepted plans.

This adapter never invokes a solver and never replaces accepted plan records,
historical proofs, existing comparison layers or the original land derivatives.
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

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import OUTPUT, digest, encoded, read_pinned, safe_path

GEOMETRY_REPORT = OUTPUT / "michigan-explorer-geometry-report.json"
DATA_REPORT = OUTPUT / "michigan-explorer-data-report.json"
REPORT = OUTPUT / "michigan-explorer-report.json"
PLAN_IDS = {"26-13", "26-18", "26-21", "26-30"}


def validate_fragment(root: Path, fragment: dict) -> None:
    """Verify every new generated asset before adding it to the server allowlist."""
    assets = fragment.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise ValueError("Michigan fragment has no generated assets")
    for key, entry in assets.items():
        if entry.get("proof") is not None or not entry["path"].startswith((OUTPUT / "assets").as_posix() + "/"):
            raise ValueError("Explorer fragments must contain only new display assets")
        compressed = read_pinned(root, entry["path"], entry["gzipSha256"])
        raw = gzip.decompress(compressed)
        if len(compressed) != entry["gzipBytes"] or len(raw) != entry["rawBytes"] or digest(raw) != entry["rawSha256"]:
            raise ValueError("Michigan explorer payload identity mismatch")
        if key.split("/", 1)[0] != entry["rawSha256"]:
            raise ValueError("Michigan explorer asset key mismatch")
        json.loads(raw)


def validate_reference(reference: dict, assets: dict) -> None:
    prefix = "/api/district-plans/"
    if not reference.get("url", "").startswith(prefix):
        raise ValueError("Michigan explorer reference is not a local asset")
    entry = assets.get(reference["url"][len(prefix):])
    if entry is None or (reference["sha256"], reference["bytes"], reference["gzipBytes"]) != (entry["rawSha256"], entry["rawBytes"], entry["gzipBytes"]):
        raise ValueError("Michigan explorer reference is not pinned by its fragment")


def decoded_reference(root: Path, reference: dict, assets: dict) -> dict:
    validate_reference(reference, assets)
    entry = assets[reference["url"].removeprefix("/api/district-plans/")]
    return json.loads(gzip.decompress(read_pinned(root, entry["path"], entry["gzipSha256"])))


def validate_plan_payloads(root: Path, record: dict, assets: dict, plan: dict, plan_id: str) -> None:
    summary = decoded_reference(root, record["summary"], assets)
    if (summary.get("planId") != plan_id or summary.get("stateFips") != "26"
            or summary.get("residentPopulation") != plan["residentPopulation"] or summary.get("blockCount") != plan["blockCount"]):
        raise ValueError("Explorer summary does not match its accepted plan")
    districts = summary.get("districts", [])
    if (len(districts) != plan["districtCount"]
            or sorted(d["districtId"] for d in districts) != list(range(plan["districtCount"]))
            or any(d["population"] != plan["districtPopulations"][d["districtId"]] for d in districts)
            or sum(d["blockCount"] for d in districts) != plan["blockCount"]):
        raise ValueError("Explorer summary district totals differ from the saved plan")
    counties = summary.get("counties", [])
    if (not counties or len({c["fips"] for c in counties}) != len(counties)
            or sum(c["population"] for c in counties) != plan["residentPopulation"]
            or sum(c["blockCount"] for c in counties) != plan["blockCount"]):
        raise ValueError("Explorer summary county totals differ from the saved plan")
    for key in ("overview", "coast", "dividers", "detailDividers"):
        document = decoded_reference(root, record[key], assets)
        if document.get("type") != "FeatureCollection" or document.get("metadata", {}).get("planId") != plan_id:
            raise ValueError("Explorer geometry does not match its accepted plan")
        features = document.get("features", [])
        if key == "overview":
            if (len(features) != plan["districtCount"]
                    or sorted(f["properties"]["district_id"] for f in features) != list(range(plan["districtCount"]))
                    or any(f["properties"]["population"] != plan["districtPopulations"][f["properties"]["district_id"]] for f in features)):
                raise ValueError("Explorer outline populations differ from the saved plan")
        elif key in ("dividers", "detailDividers"):
            for feature in features:
                ids = feature.get("properties", {}).get("district_ids")
                if (not isinstance(ids, list) or len(ids) != 2 or ids[0] == ids[1]
                        or any(type(d) is not int or not 0 <= d < plan["districtCount"] for d in ids)):
                    raise ValueError("Explorer divider has invalid district identities")


def combine_fragments(root: Path, manifest: dict, index: dict, geometry: dict, data: dict) -> tuple[dict, dict]:
    validate_fragment(root, geometry)
    validate_fragment(root, data)
    if set(geometry.get("plans", {})) != PLAN_IDS or set(data.get("plans", {})) != PLAN_IDS:
        raise ValueError("Michigan explorer must cover all four accepted plans")
    for plan_id in PLAN_IDS:
        if manifest["plans"].get(plan_id, {}).get("stateFips") != "26" or plan_id not in manifest.get("landDisplays", {}):
            raise ValueError("Michigan explorer lacks an accepted plan or land derivative")
    entries = {**geometry["assets"], **data["assets"]}
    for key in geometry["assets"].keys() & data["assets"].keys():
        if geometry["assets"][key] != data["assets"][key]:
            raise ValueError("Michigan fragments conflict")
    new_manifest, new_index = deepcopy(manifest), deepcopy(index)
    plans = {}
    for plan_id in sorted(PLAN_IDS):
        geo = geometry["plans"][plan_id]
        record = {key: geo[key] for key in ("overview", "coast", "dividers", "detailDividers")}
        record["summary"] = data["plans"][plan_id]["summary"]
        for reference in record.values():
            validate_reference(reference, entries)
        validate_plan_payloads(root, record, entries, manifest["plans"][plan_id], plan_id)
        # A later additive spatial publication survives --publish-existing.
        # A full preparation rebuild adds it again in the following step.
        spatial = manifest.get("michiganExplorer", {}).get("plans", {}).get(plan_id, {}).get("spatialIndex")
        if spatial is not None:
            spatial_document = decoded_reference(root, spatial, index["assets"])
            plan = manifest["plans"][plan_id]
            if (spatial_document.get("planId") != plan_id or spatial_document.get("stateFips") != "26"
                    or spatial_document.get("totalBlockCount") != plan["blockCount"]
                    or spatial_document.get("totalPopulation") != plan["residentPopulation"]):
                raise ValueError("Preserved spatial index differs from its accepted plan")
            record["spatialIndex"] = deepcopy(spatial)
        plans[plan_id] = record
    validate_reference(data["cities"], entries)
    cities = decoded_reference(root, data["cities"], entries)
    if (cities.get("type") != "FeatureCollection" or cities.get("metadata", {}).get("stateFips") != "26"
            or not cities.get("features") or any(f.get("geometry", {}).get("type") != "Point"
                or not str(f.get("properties", {}).get("geoid", "")).startswith("26")
                or type(f.get("properties", {}).get("population")) is not int
                or f["properties"]["population"] < 0
                or len(f["geometry"].get("coordinates", [])) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in f["geometry"]["coordinates"])
                for f in cities["features"])):
        raise ValueError("Explorer city points do not match Michigan")
    new_manifest["michiganExplorer"] = {"cities": data["cities"], "plans": plans}
    for key, entry in entries.items():
        if key in new_index["assets"] and new_index["assets"][key] != entry:
            raise ValueError("Explorer asset conflicts with a preserved resource")
        new_index["assets"][key] = entry
    return new_manifest, new_index


def publish_existing(bundle_root: Path) -> dict:
    bundle_root = bundle_root.resolve()
    index_path = safe_path(bundle_root, OUTPUT / "server-index.json")
    before_index = index_path.read_bytes()
    index = json.loads(before_index)
    before_manifest = read_pinned(bundle_root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(before_manifest)
    read_pinned(bundle_root, index["catalogPath"], index["catalogSha256"])
    geometry_raw = safe_path(bundle_root, GEOMETRY_REPORT).read_bytes()
    data_raw = safe_path(bundle_root, DATA_REPORT).read_bytes()
    geometry, data = json.loads(geometry_raw), json.loads(data_raw)
    if (geometry.get("status") != "complete" or data.get("audit", {}).get("status") != "complete"
            or geometry.get("audit", {}).get("catalog_sha256") != index["catalogSha256"]
            or data.get("audit", {}).get("catalogSha256") != index["catalogSha256"]):
        raise ValueError("Explorer fragments are not complete for this accepted catalog")
    updated, updated_index = combine_fragments(bundle_root, manifest, index, geometry, data)
    # All existing authoritative records and optional older displays survive unchanged.
    for key in ("plans", "anchors", "landDisplays", "comparisonLayers", "catalogSha256"):
        if updated.get(key) != manifest.get(key):
            raise ValueError(f"Explorer publication changed preserved {key}")
    if updated_index["proofs"] != index["proofs"]:
        raise ValueError("Explorer publication changed accepted plan evidence")
    report = {
        "schema": 1, "status": "complete", "stateFips": "26", "planIds": sorted(PLAN_IDS),
        "catalogSha256": index["catalogSha256"],
        "geometryReport": {"path": GEOMETRY_REPORT.as_posix(), "sha256": digest(geometry_raw)},
        "dataReport": {"path": DATA_REPORT.as_posix(), "sha256": digest(data_raw)},
        "preservedPlanRecordsSha256": digest(encoded(manifest["plans"])),
        "preservedProofsSha256": digest(encoded(index["proofs"])),
        "savedAssignmentsModified": 0, "solverRuns": 0,
        "assetCount": len(json.loads(geometry_raw)["assets"]) + len(json.loads(data_raw)["assets"]),
    }
    report_raw = encoded(report)
    updated_index["michiganExplorerProvenance"] = {"reportPath": REPORT.as_posix(), "reportSha256": digest(report_raw)}
    manifest_raw = encoded(updated)
    updated_index["manifestSha256"] = digest(manifest_raw)
    if index_path.read_bytes() != before_index or safe_path(bundle_root, OUTPUT / "manifest.json").read_bytes() != before_manifest:
        raise ValueError("Another process modified the bundle during publication")
    for relative, raw in ((REPORT, report_raw), (OUTPUT / "manifest.json", manifest_raw), (OUTPUT / "server-index.json", encoded(updated_index))):
        path = safe_path(bundle_root, relative)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(raw)
        temporary.replace(path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, default=Path(os.environ.get("BLOCK_PLAN_CACHE_ROOT", ROOT / ".cache")))
    parser.add_argument("--publish-existing", action="store_true", help="Publish the already validated geometry/data fragments without regenerating them")
    args = parser.parse_args()
    if not args.publish_existing:
        from scripts.build_michigan_explorer_data import build_data
        from scripts.build_michigan_explorer_geometry import build_geometry
        build_data(args.bundle_root, args.cache_root)
        build_geometry(args.bundle_root, args.cache_root)
    print(json.dumps(publish_existing(args.bundle_root), indent=2))


if __name__ == "__main__":
    main()
