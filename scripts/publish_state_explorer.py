"""Validate and publish the complete 50-state explorer, preserving accepted plans.

Builders write independent resumable fragments. Publication waits for all 181
accepted plans; it only adds display assets and an optional manifest section.
The old manifest/index are saved by content hash before the index is switched.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import gzip
import hashlib
from itertools import islice
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import OUTPUT, digest, encoded, read_pinned, resource_path, safe_path

REPORT = OUTPUT / "state-explorer-publication-report.json"
BLOCKS = OUTPUT / "state-explorer-blocks-v1"
GEOMETRY = OUTPUT / "state-explorer-geometry-report.json"
CITIES = OUTPUT / "state-explorer-city-report.json"
PREFIX = "/api/district-plans/"


def validate_anchors(manifest: dict) -> list[str]:
    plans = manifest["plans"]
    states = sorted({p["stateFips"] for p in plans.values()})
    sizes = {435, 574, 692, 1000}
    anchors = manifest["anchors"]
    if (len(states) != 50 or len(manifest["houseSizes"]) != 4 or set(manifest["houseSizes"]) != sizes
            or len(anchors) != 4 or {a["houseSize"] for a in anchors} != sizes):
        raise ValueError("Publication requires the complete four-anchor, 50-state catalog")
    membership = {key: set() for key in plans}
    for anchor in anchors:
        ids = anchor["planIds"]
        if len(ids) != 50 or len(set(ids)) != 50 or any(key not in plans for key in ids):
            raise ValueError("Anchor must contain 50 unique accepted plans")
        if sorted(plans[key]["stateFips"] for key in ids) != states:
            raise ValueError("Anchor must contain exactly one plan per state")
        if sum(plans[key]["districtCount"] for key in ids) != anchor["houseSize"]:
            raise ValueError("Anchor district counts do not sum to its House size")
        for key in ids:
            membership[key].add(anchor["houseSize"])
    if any(p["id"] != key or len(p["houseSizes"]) != len(membership[key]) or set(p["houseSizes"]) != membership[key]
           or not membership[key] for key, p in plans.items()):
        raise ValueError("Plan House-size membership differs from the four anchors")
    return states


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def merge_assets(target: dict, additions: dict) -> None:
    for key, entry in additions.items():
        if key in target and target[key] != entry:
            raise ValueError(f"Explorer asset conflicts with preserved entry: {key}")
        target[key] = entry


def reference_entry(reference: dict, assets: dict) -> dict:
    url = reference.get("url", "")
    if not url.startswith(PREFIX) or url.removeprefix(PREFIX) not in assets:
        raise ValueError("Explorer reference is not in the server allowlist")
    entry = assets[url.removeprefix(PREFIX)]
    if (reference["sha256"], reference["bytes"], reference["gzipBytes"]) != (entry["rawSha256"], entry["rawBytes"], entry["gzipBytes"]):
        raise ValueError("Explorer reference differs from its content-addressed asset")
    return entry


def read_reference(root: Path, cache: Path, reference: dict, assets: dict) -> dict:
    entry = reference_entry(reference, assets)
    raw = gzip.decompress(read_pinned(root, entry["path"], entry["gzipSha256"], cache))
    if len(raw) != entry["rawBytes"] or digest(raw) != entry["rawSha256"]:
        raise ValueError("Explorer decoded payload identity mismatch")
    return json.loads(raw)


def validate_summary(summary: dict, plan: dict) -> None:
    if (summary["planId"] != plan["id"] or summary["stateFips"] != plan["stateFips"]
            or summary.get("coordinateFrame", plan["coordinateFrame"]) != plan["coordinateFrame"]
            or summary["residentPopulation"] != plan["residentPopulation"] or summary["blockCount"] != plan["blockCount"]):
        raise ValueError("State summary identity differs from the saved plan")
    counties, districts = summary["counties"], summary["districts"]
    if len({c["fips"] for c in counties}) != len(counties) or not counties:
        raise ValueError("Missing or duplicate county summary")
    if sum(c["population"] for c in counties) != plan["residentPopulation"] or sum(c["blockCount"] for c in counties) != plan["blockCount"]:
        raise ValueError("County summaries do not reconcile")
    people, blocks, membership = [0] * plan["districtCount"], [0] * plan["districtCount"], [set() for _ in range(plan["districtCount"])]
    for county in counties:
        seen, p, b = set(), 0, 0
        for share in county["districtShares"]:
            d = share["districtId"]
            if type(d) is not int or not 0 <= d < plan["districtCount"] or d in seen:
                raise ValueError("Invalid county district membership")
            seen.add(d)
            expected = share["population"] / county["population"] * 100 if county["population"] else 0
            if abs(expected - share["percent"]) > 1e-6:
                raise ValueError("County share is not a resident population share")
            people[d] += share["population"]
            blocks[d] += share["blockCount"]
            membership[d].add(county["fips"])
            p += share["population"]
            b += share["blockCount"]
        if (p, b) != (county["population"], county["blockCount"]):
            raise ValueError("County share totals differ")
    if people != plan["districtPopulations"] or sorted(d["districtId"] for d in districts) != list(range(plan["districtCount"])):
        raise ValueError("District summary differs from accepted populations")
    for district in districts:
        d = district["districtId"]
        if (district["population"], district["blockCount"], sorted(district["countyFips"])) != (people[d], blocks[d], sorted(membership[d])):
            raise ValueError("District summary membership differs")


def validate_spatial(spatial: dict, summary: dict, plan: dict, assets: dict) -> None:
    if (spatial.get("schemaVersion") not in (1, 2) or spatial["planId"] != plan["id"] or spatial["stateFips"] != plan["stateFips"]
            or spatial.get("coordinateFrame", plan["coordinateFrame"]) != plan["coordinateFrame"]
            or spatial["totalPopulation"] != plan["residentPopulation"] or spatial["totalBlockCount"] != plan["blockCount"]):
        raise ValueError("Spatial index identity differs from accepted plan")
    chunks = spatial["chunks"]
    if not chunks or len({c["chunkId"] for c in chunks}) != len(chunks):
        raise ValueError("Missing or duplicate spatial chunk")
    if sum(c["blockCount"] for c in chunks) != plan["blockCount"] or sum(c["population"] for c in chunks) != plan["residentPopulation"]:
        raise ValueError("Spatial index totals differ from the plan")
    expected = sorted((c["fips"], c["population"], c["blockCount"]) for c in summary["counties"])
    if sorted((c["fips"], c["population"], c["blockCount"]) for c in spatial["counties"]) != expected:
        raise ValueError("Spatial counties differ from summary")
    for chunk in chunks:
        reference_entry(chunk["asset"], assets)
        if spatial["schemaVersion"] == 2:
            reference_entry(chunk["assignments"], assets)
        elif "assignments" in chunk:
            raise ValueError("Unexpected assignments in original spatial index")


def validate_geometry(document: dict, plan: dict, kind: str) -> None:
    if document.get("type") != "FeatureCollection" or document.get("metadata", {}).get("planId") != plan["id"]:
        raise ValueError("Geometry belongs to a different plan")
    if document["metadata"].get("coordinateFrame", plan["coordinateFrame"]) != plan["coordinateFrame"]:
        raise ValueError("Geometry coordinate frame changed")
    if document["metadata"].get("stateFips", plan["stateFips"]) != plan["stateFips"]:
        raise ValueError("Geometry state changed")
    if kind in ("overview", "detail"):
        features = document["features"]
        if sorted(f["properties"]["district_id"] for f in features) != list(range(plan["districtCount"])):
            raise ValueError("Display geometry lost a district")
        if any(f["properties"]["population"] != plan["districtPopulations"][f["properties"]["district_id"]] for f in features):
            raise ValueError("Display geometry changed saved populations")


def validate_assignments(document: dict, plan: dict, chunk: dict) -> list[int]:
    expected = {"schemaVersion": 1, "planId": plan["id"], "stateFips": plan["stateFips"],
                "coordinateFrame": plan["coordinateFrame"], "chunkId": chunk["chunkId"],
                "geometrySha256": chunk["asset"]["sha256"]}
    if any(document.get(key) != value for key, value in expected.items()):
        raise ValueError("Assignment sidecar identity or geometry binding differs")
    ids = document.get("districtIds")
    if not isinstance(ids, list) or len(ids) != chunk["blockCount"] or any(type(d) is not int or not 0 <= d < plan["districtCount"] for d in ids):
        raise ValueError("Assignment sidecar has invalid district IDs or block count")
    return ids


def validate_plan_assignments(root: Path, cache: Path, spatial: dict, plan: dict, summary: dict, assets: dict) -> None:
    """Read bounded sidecar batches; reconcile their IDs on the caller thread."""
    counts = [0] * plan["districtCount"]
    chunks = iter(spatial["chunks"])
    with ThreadPoolExecutor(max_workers=8) as executor:
        while batch := tuple(islice(chunks, 256)):
            results = executor.map(lambda chunk: validate_assignments(
                read_reference(root, cache, chunk["assignments"], assets), plan, chunk), batch)
            # map yields in source order. Counts and validation decisions have
            # one owner; worker threads only read and validate pinned payloads.
            for ids in results:
                for district in ids:
                    counts[district] += 1
    expected = [district["blockCount"] for district in sorted(summary["districts"], key=lambda district: district["districtId"])]
    if counts != expected:
        raise ValueError("Assignment sidecars do not reconcile to district block counts")


def _validate_asset(root: Path, cache: Path, key: str, entry: dict) -> None:
    if key.split("/", 1)[0] != entry["rawSha256"]:
        raise ValueError("Generated asset key is not content addressed")
    path = resource_path(root, entry["path"], cache)
    if path.stat().st_size != entry["gzipBytes"] or file_hash(path) != entry["gzipSha256"]:
        raise ValueError(f"Compressed explorer asset changed: {key}")
    h, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            h.update(chunk)
    if size != entry["rawBytes"] or h.hexdigest() != entry["rawSha256"]:
        raise ValueError(f"Decoded explorer asset changed: {key}")


def validate_assets(root: Path, cache: Path, assets: dict) -> None:
    """Check every payload with eight readers and at most 256 queued assets.

    Batches bound futures independently of catalog size. Each reader retains
    only a 1 MiB decompression buffer, and failures stop before the next batch.
    Both compressed and decoded identities are checked exactly as in serial.
    """
    items = iter(assets.items())
    verified = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        while batch := tuple(islice(items, 256)):
            for _ in executor.map(lambda item: _validate_asset(root, cache, *item), batch):
                verified += 1
                if verified % 10000 == 0:
                    print(f"Verified {verified:,}/{len(assets):,} explorer assets", flush=True)


def atomic_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(encoded(value))
    temp.replace(path)


def publish(root: Path, cache: Path, *, write: bool = False) -> dict:
    started = time.perf_counter()
    root, cache = root.resolve(), cache.resolve()
    index_path = safe_path(root, OUTPUT / "server-index.json")
    before_index = index_path.read_bytes()
    index = json.loads(before_index)
    before_manifest = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(before_manifest)
    read_pinned(root, index["catalogPath"], index["catalogSha256"], cache)
    states = validate_anchors(manifest)
    fragments, report_inputs = [], []
    for relative in (CITIES, GEOMETRY, *(BLOCKS / f"{state}.json" for state in states if state != "26")):
        raw = safe_path(root, relative).read_bytes()
        fragment = json.loads(raw)
        if fragment.get("status") != "complete" or fragment.get("catalogSha256") != index["catalogSha256"]:
            raise ValueError(f"Incomplete or mismatched explorer fragment: {relative}")
        fragments.append(fragment)
        report_inputs.append({"path": relative.as_posix(), "sha256": digest(raw)})
    cities, geometry, *block_fragments = fragments
    if set(cities["states"]) != set(states) or set(geometry["plans"]) != set(manifest["plans"]):
        raise ValueError("Explorer fragments do not cover the accepted catalog")
    additions, data_plans, preserved = {}, {}, {}
    def preserve(path: str, sha: str) -> None:
        if path in preserved and preserved[path] != sha:
            raise ValueError("Inconsistent source preservation identity")
        preserved[path] = sha
    if (cities["audit"]["preservedPlansSha256"] != digest(encoded(manifest["plans"]))
            or cities["audit"]["preservedProofsSha256"] != digest(encoded(index["proofs"]))):
        raise ValueError("City generation used different saved plans or proofs")
    pins = cities["audit"]["sourcePins"]
    pin_data = json.loads(read_pinned(root, pins["path"], pins["sha256"]))
    preserve(pins["path"], pins["sha256"])
    for source in pin_data["sources"]:
        preserve(f".cache/block-main-port/state-explorer-city-sources-v1/{source['filename']}", source["sha256"])
    for path, sha in geometry["audit"]["runtimeHashes"].items():
        # Geometry reports retain the builder's script-basename convention;
        # block fragments instead record repository-relative runtime paths.
        relative = f"scripts/{path}" if Path(path).name == path else path
        if file_hash(safe_path(root, relative)) != sha:
            raise ValueError("Geometry builder changed since generation")
        preserve(relative, sha)
    for audit in geometry["audit"]["plans"].values():
        for source in audit["preservedFiles"]:
            preserve(source["path"], source["sha256"])
    for fragment in fragments:
        merge_assets(additions, fragment["assets"])
    for fragment in block_fragments:
        state = fragment["stateFips"]
        plans = sorted((p for p in manifest["plans"].values() if p["stateFips"] == state), key=lambda p: p["districtCount"])
        if set(fragment["plans"]) != {p["id"] for p in plans} or fragment["audit"]["preservedPlansSha256"] != digest(encoded(plans)):
            raise ValueError("Spatial fragment does not preserve its accepted plan records")
        for path, sha in fragment["runtimeHashes"].items():
            if file_hash(safe_path(root, path)) != sha:
                raise ValueError("Spatial builder changed since generation")
            preserve(path, sha)
        for source in fragment["audit"]["preservedFiles"]:
            preserve(source["path"], source["sha256"])
        data_plans.update(fragment["plans"])
    for plan_id, record in manifest["michiganExplorer"]["plans"].items():
        data_plans[plan_id] = {key: record[key] for key in ("summary", "spatialIndex")}
    if set(data_plans) != set(manifest["plans"]):
        raise ValueError("Spatial data does not cover every saved plan")
    assets = dict(index["assets"])
    merge_assets(assets, additions)
    validate_assets(root, cache, additions)
    explorers, checks = {}, {}
    for state in states:
        places = cities["states"][state]
        place_data = read_reference(root, cache, places["cities"], assets)
        if place_data.get("metadata", {}).get("stateFips") != state or len(place_data["features"]) != places["cityMetadata"]["featureCount"]:
            raise ValueError("City points differ from their state metadata")
        seen_places = set()
        for feature in place_data["features"]:
            p, g = feature["properties"], feature["geometry"]
            xy = g.get("coordinates", [])
            if (g["type"] != "Point" or len(xy) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in xy)
                    or not (-360 <= xy[0] <= 180 and -90 <= xy[1] <= 90)
                    or not str(p["geoid"]).startswith(state) or p["geoid"] in seen_places
                    or p["population"] < places["cityMetadata"]["minimumPopulation"]):
                raise ValueError("Invalid or duplicate city point")
            seen_places.add(p["geoid"])
        explorers[state] = {**places, "plans": {}}
        for plan_id, plan in manifest["plans"].items():
            if plan["stateFips"] != state:
                continue
            record = {**geometry["plans"][plan_id], **data_plans[plan_id]}
            summary = read_reference(root, cache, record["summary"], assets)
            spatial = read_reference(root, cache, record["spatialIndex"], assets)
            validate_summary(summary, plan)
            validate_spatial(spatial, summary, plan, assets)
            if spatial["schemaVersion"] == 2:
                validate_plan_assignments(root, cache, spatial, plan, summary, assets)
            for key in ("overview", "coast", "dividers", "detailDividers", "detail"):
                if key in record:
                    validate_geometry(read_reference(root, cache, record[key], assets), plan, key)
            explorers[state]["plans"][plan_id] = record
            checks[plan_id] = {"stateFips": state, "houseSizes": plan["houseSizes"], "districtCount": plan["districtCount"],
                "population": plan["residentPopulation"], "blockCount": plan["blockCount"], "spatialChunks": len(spatial["chunks"]),
                "spatialSchema": spatial["schemaVersion"], "coordinateFrame": plan["coordinateFrame"],
                "recordedLinks": plan["recordedLinkCount"], "recordedConnectionsSha256": plan["assets"].get("connections", {}).get("sha256"),
                "overviewGzipBytes": record["overview"]["gzipBytes"], "cityGzipBytes": places["cities"]["gzipBytes"]}
        print(f"Validated state {state}: {len(explorers[state]['plans'])} accepted plans", flush=True)
    for path, sha in preserved.items():
        if file_hash(resource_path(root, path, cache)) != sha:
            raise ValueError(f"Original saved evidence changed: {path}")
    updated = deepcopy(manifest)
    updated["stateExplorers"] = explorers
    for key, value in manifest.items():
        if key != "stateExplorers" and updated[key] != value:
            raise ValueError(f"Publication changed preserved manifest field: {key}")
    report = {"schemaVersion": 1, "status": "complete", "catalogSha256": index["catalogSha256"],
        "states": len(states), "plans": len(checks), "anchorStatePairs": sum(len(p["houseSizes"]) for p in checks.values()),
        "checks": checks, "inputs": report_inputs, "generatedAssetCount": len(additions),
        "generatedGzipBytes": sum(e["gzipBytes"] for e in additions.values()), "preservedSourceFiles": len(preserved),
        "preservedPlanRecordsSha256": digest(encoded(manifest["plans"])), "preservedProofsSha256": digest(encoded(index["proofs"])),
        "preservedMichiganSha256": digest(encoded(manifest["michiganExplorer"])), "preservedAnchorsSha256": digest(encoded(manifest["anchors"])),
        "savedAssignmentsModified": 0, "solverRuns": 0,
        "coverageNote": geometry["audit"]["limitation"], "runtimeSeconds": time.perf_counter() - started}
    if not write:
        return report
    if index_path.read_bytes() != before_index or safe_path(root, OUTPUT / "manifest.json").read_bytes() != before_manifest:
        raise ValueError("Bundle changed during publication; refusing stale write")
    for source in report_inputs:
        if file_hash(safe_path(root, source["path"])) != source["sha256"]:
            raise ValueError("Explorer fragment changed during publication")
    backup = safe_path(root, OUTPUT / "publication-history")
    backup.mkdir(exist_ok=True)
    for label, raw in (("manifest", before_manifest), ("server-index", before_index)):
        path = backup / f"{label}-{digest(raw)}.json"
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("Publication backup identity conflict")
        if not path.exists():
            path.write_bytes(raw)
    updated_index = deepcopy(index)
    updated_index["assets"] = assets
    updated_index["manifestSha256"] = digest(encoded(updated))
    updated_index["stateExplorerProvenance"] = {"reportPath": REPORT.as_posix(), "reportSha256": digest(encoded(report))}
    atomic_json(safe_path(root, REPORT), report)
    atomic_json(safe_path(root, OUTPUT / "manifest.json"), updated)
    atomic_json(index_path, updated_index)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, default=Path(os.environ.get("BLOCK_PLAN_CACHE_ROOT", ROOT / ".cache")))
    parser.add_argument("--publish", action="store_true", help="Publish after full validation; otherwise check only")
    args = parser.parse_args()
    report = publish(args.bundle_root, args.cache_root, write=args.publish)
    print(json.dumps({key: report[key] for key in ("status", "states", "plans", "anchorStatePairs", "generatedAssetCount", "runtimeSeconds")}, indent=2))


if __name__ == "__main__":
    main()
