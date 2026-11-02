"""Prepare shared, whole saved-block geometry and per-plan district assignments.

This publishes isolated per-state fragments, never the browser manifest or the
server allowlist. Geography is shared only after every accepted anchor has been
checked against it. Restoring district_id must reproduce each complete saved
Feature. Existing plans, recorded connections and evidence remain read-only.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import BundleBuilder, OUTPUT, digest, encoded, read_pinned, resource_path, safe_path, validate_catalog
from scripts.build_michigan_explorer_data import read_asset
from scripts.build_michigan_spatial_blocks import SavedBlock, canonical_feature, spatial_groups, union_bounds

FRAGMENTS = OUTPUT / "state-explorer-blocks-v1"
GRID_DEGREES = 0.125
MAX_BLOCKS = 256
MAX_RAW_BYTES = 512 * 1024
MINIMUM_FREE_BYTES = 2 * 1024**3
RUNTIME_FILES = (
    "scripts/build_state_explorer_blocks.py", "scripts/build_block_plan_bundle.py",
    "scripts/build_michigan_explorer_data.py", "scripts/build_michigan_spatial_blocks.py",
)
VALUE_TYPES = np.frompyfunc(type, 1, 1)


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def geometry_bounds(geometry: dict, frame: str = "source") -> tuple[float, float, float, float]:
    if frame not in ("source", "alaska-continuous"):
        raise ValueError("Unknown coordinate frame")
    if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("Expected saved Polygon or MultiPolygon")
    polygons = geometry.get("coordinates")
    if geometry["type"] == "Polygon":
        polygons = [polygons]
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("Empty saved geometry")
    west = south = math.inf
    east = north = -math.inf
    minimum_longitude = -360 if frame == "alaska-continuous" else -180
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("Empty saved polygon")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError("Invalid saved ring")
            if len(ring) >= 16:
                # Preserve strict JSON-number validation, including rejecting
                # bools, before converting. Large shoreline rings otherwise
                # spend most of preparation time in repeated Python min/max.
                objects = np.asarray(ring, dtype=object)
                if objects.ndim != 2 or objects.shape[1] < 2:
                    raise ValueError("Invalid source coordinate shape")
                types = VALUE_TYPES(objects)
                if not np.all((types == int) | (types == float)):
                    raise ValueError("Invalid source coordinate type")
                numbers = objects.astype(np.float64)
                if (not np.isfinite(numbers).all() or (numbers[:, 0] < minimum_longitude).any()
                        or (numbers[:, 0] > 180).any() or (numbers[:, 1] < -90).any() or (numbers[:, 1] > 90).any()):
                    raise ValueError("Invalid source coordinate or coordinate frame")
                west, south = min(west, float(numbers[:, 0].min())), min(south, float(numbers[:, 1].min()))
                east, north = max(east, float(numbers[:, 0].max())), max(north, float(numbers[:, 1].max()))
                continue
            for point in ring:
                if (not isinstance(point, list) or len(point) < 2
                        or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
                        or not minimum_longitude <= point[0] <= 180 or not -90 <= point[1] <= 90):
                    raise ValueError("Invalid source coordinate or coordinate frame")
                x, y = point[:2]
                west, south, east, north = min(west, x), min(south, y), max(east, x), max(north, y)
    if west >= east or south >= north:
        raise ValueError("Degenerate saved block bounds")
    return west, south, east, north


def without_assignment(feature: dict) -> dict:
    """Copy only the property mapping; never mutate source geometry or fields."""
    result = dict(feature)
    result["properties"] = {k: v for k, v in feature["properties"].items() if k != "district_id"}
    return result


def same_json_metadata(left: object, right: object) -> bool:
    """JSON booleans must not compare equal to population/area numbers."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_json_metadata(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_json_metadata(a, b) for a, b in zip(left, right))
    return left == right


def source_features(collection: dict, county: dict, plan: dict) -> dict[str, dict]:
    if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
        raise ValueError("Saved county must be a FeatureCollection")
    if not re.fullmatch(r"\d{2}", plan["stateFips"]) or not re.fullmatch(r"\d{3}", county["fips"]):
        raise ValueError("Invalid state/county identity")
    features = {}
    for feature in collection["features"]:
        if not isinstance(feature, dict) or feature.get("type") != "Feature" or not isinstance(feature.get("properties"), dict):
            raise ValueError("Invalid saved Feature")
        props = feature["properties"]
        geoid, population, district = props.get("geoid"), props.get("population"), props.get("district_id")
        if (not isinstance(geoid, str) or not re.fullmatch(plan["stateFips"] + county["fips"] + r"\d{10}", geoid)
                or geoid in features or type(population) is not int or population < 0
                or type(district) is not int or not 0 <= district < plan["districtCount"]):
            raise ValueError("Invalid, duplicate or wrong-county saved block")
        features[geoid] = feature
    if len(features) != county["blockCount"] or sum(f["properties"]["population"] for f in features.values()) != county["population"]:
        raise ValueError("Saved county totals do not reconcile")
    return features


def base_records(features: dict[str, dict], frame: str) -> list[SavedBlock]:
    result = []
    for geoid, feature in sorted(features.items()):
        shared = without_assignment(feature)
        canonical = canonical_feature(shared)
        result.append(SavedBlock(shared, geoid, feature["properties"]["population"], feature["properties"]["district_id"],
            geometry_bounds(feature.get("geometry"), frame), len(canonical), digest(canonical)))
    return result


def reconcile_geometry(features: dict[str, dict], records: list[SavedBlock]) -> dict[str, int]:
    if set(features) != {b.geoid for b in records}:
        raise ValueError("Saved anchors have different block coverage")
    assignments = {}
    for block in records:
        feature = features[block.geoid]
        original_props = feature["properties"]
        # The pinned input is compared in full, including additional source
        # fields (Alaska's land/water areas, for example). Neither geography nor
        # any non-assignment property may differ across shared anchors.
        unassigned = without_assignment(feature)
        if unassigned != block.feature or not same_json_metadata(unassigned["properties"], block.feature["properties"]):
            raise ValueError(f"Saved anchors differ beyond district_id: {block.geoid}")
        restored = dict(block.feature)
        restored["properties"] = {**block.feature["properties"], "district_id": original_props["district_id"]}
        if restored != feature:
            raise ValueError("Restoring district assignment changed a saved Feature")
        assignments[block.geoid] = original_props["district_id"]
    return assignments


def shared_chunk(state: str, frame: str, chunk_id: str, records: list[SavedBlock]) -> dict:
    return {"type": "FeatureCollection", "metadata": {"schemaVersion": 2, "stateFips": state,
        "coordinateFrame": frame, "chunkId": chunk_id, "wholeSavedBlocks": True,
        "sharedAcrossPlans": True, "assignmentField": "district_id"}, "features": [b.feature for b in records]}


def assignment_document(plan: dict, chunk_id: str, geometry: dict, records: list[SavedBlock], assignments: dict[str, int]) -> dict:
    return {"schemaVersion": 1, "planId": plan["id"], "stateFips": plan["stateFips"],
        "coordinateFrame": plan["coordinateFrame"], "chunkId": chunk_id, "geometrySha256": geometry["sha256"],
        "districtIds": [assignments[b.geoid] for b in records]}


def validate_reconstruction(shared: dict, assignment: dict, descriptor: dict, plan: dict, expected: dict[str, dict], seen: set[str]) -> None:
    metadata = shared.get("metadata", {})
    if (shared.get("type") != "FeatureCollection" or metadata.get("schemaVersion") != 2
            or metadata.get("stateFips") != plan["stateFips"] or metadata.get("coordinateFrame") != plan["coordinateFrame"]
            or metadata.get("chunkId") != descriptor["chunkId"] or metadata.get("assignmentField") != "district_id"
            or assignment.get("schemaVersion") != 1 or assignment.get("planId") != plan["id"]
            or assignment.get("stateFips") != plan["stateFips"] or assignment.get("coordinateFrame") != plan["coordinateFrame"]
            or assignment.get("chunkId") != descriptor["chunkId"] or assignment.get("geometrySha256") != descriptor["asset"]["sha256"]):
        raise ValueError("Shared chunk or assignment identity mismatch")
    features, ids = shared.get("features", []), assignment.get("districtIds", [])
    if len(features) != len(ids) or len(ids) != descriptor["blockCount"]:
        raise ValueError("Shared geometry/assignment lengths differ")
    population = 0
    for feature, district in zip(features, ids):
        geoid = feature.get("properties", {}).get("geoid")
        if (geoid not in expected or geoid in seen or "district_id" in feature["properties"]
                or type(district) is not int or not 0 <= district < plan["districtCount"]):
            raise ValueError("Invalid, duplicate or invented reconstructed block")
        restored = dict(feature)
        restored["properties"] = {**feature["properties"], "district_id": district}
        if restored != expected[geoid] or not same_json_metadata(restored["properties"], expected[geoid]["properties"]):
            raise ValueError("Reconstructed Feature differs from its saved source")
        seen.add(geoid)
        population += feature["properties"]["population"]
    if population != descriptor["population"]:
        raise ValueError("Chunk population does not reconcile")


def county_summary(records: list[SavedBlock], assignments: dict[str, int], county: dict, name: str) -> dict:
    totals = defaultdict(lambda: {"population": 0, "blockCount": 0})
    for block in records:
        row = totals[assignments[block.geoid]]
        row["population"] += block.population
        row["blockCount"] += 1
    population = sum(b.population for b in records)
    return {"fips": county["fips"], "name": name, "population": population, "blockCount": len(records),
        "bbox": union_bounds(records), "districtShares": [{"districtId": district, **row,
            "percent": 100 * row["population"] / population if population else 0}
            for district, row in sorted(totals.items())]}


def plan_summary(plan: dict, counties: list[dict], expected_counts: list[int]) -> dict:
    districts = [{"districtId": i, "population": 0, "blockCount": 0, "countyFips": []} for i in range(plan["districtCount"])]
    if len({c["fips"] for c in counties}) != len(counties):
        raise ValueError("Duplicate county summary")
    for county in counties:
        for share in county["districtShares"]:
            row = districts[share["districtId"]]
            row["population"] += share["population"]
            row["blockCount"] += share["blockCount"]
            row["countyFips"].append(county["fips"])
    if ([d["population"] for d in districts] != plan["districtPopulations"]
            or [d["blockCount"] for d in districts] != expected_counts
            or sum(c["population"] for c in counties) != plan["residentPopulation"]
            or sum(c["blockCount"] for c in counties) != plan["blockCount"]):
        raise ValueError("State/county/district totals differ from the accepted plan")
    return {"planId": plan["id"], "stateFips": plan["stateFips"], "coordinateFrame": plan["coordinateFrame"],
        "residentPopulation": plan["residentPopulation"], "blockCount": plan["blockCount"],
        "counties": sorted(counties, key=lambda c: c["fips"]), "districts": districts}


def atomic_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_bytes(encoded(document))
    temporary.replace(path)


def load_context(root: Path, cache_root: Path) -> tuple[dict, dict, dict]:
    index = json.loads(safe_path(root, OUTPUT / "server-index.json").read_bytes())
    manifest = json.loads(read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"]))
    catalog = json.loads(read_pinned(root, index["catalogPath"], index["catalogSha256"]))
    validate_catalog(catalog)
    if manifest["catalogSha256"] != index["catalogSha256"]:
        raise ValueError("Manifest/catalog identity differs")
    return manifest, index, catalog


def runtime_hashes(root: Path) -> dict:
    return {name: file_hash(safe_path(root, name)) for name in RUNTIME_FILES}


def verify_file_inventory(root: Path, cache_root: Path, inventory: list[dict]) -> None:
    for row in inventory:
        path = resource_path(root, row["path"], cache_root)
        if file_hash(path) != row["sha256"]:
            raise ValueError(f"Preserved input changed: {row['path']}")


def relative_resource(root: Path, cache_root: Path, path: Path) -> str:
    if path.is_relative_to(root):
        return path.relative_to(root).as_posix()
    if path.is_relative_to(cache_root):
        return ".cache/" + path.relative_to(cache_root).as_posix()
    raise ValueError("Preserved input lies outside allowed roots")


def verify_fragment(root: Path, cache_root: Path, fragment: dict, plans: list[dict], index: dict) -> None:
    if (fragment.get("status") != "complete" or fragment.get("catalogSha256") != index["catalogSha256"]
            or fragment.get("runtimeHashes") != runtime_hashes(root)
            or fragment["audit"].get("preservedPlansSha256") != digest(encoded(plans))):
        raise ValueError("Existing fragment is incompatible; preserve it and use a new namespace")
    verify_file_inventory(root, cache_root, fragment["audit"]["preservedFiles"])
    for entry in fragment["assets"].values():
        raw = gzip.decompress(read_pinned(root, entry["path"], entry["gzipSha256"], cache_root))
        if digest(raw) != entry["rawSha256"] or len(raw) != entry["rawBytes"]:
            raise ValueError("Existing fragment output hash differs")


def build_state(bundle_root: str | Path, cache: str | Path, state: str) -> dict:
    started = time.perf_counter()
    root, cache_root = Path(bundle_root).resolve(), Path(cache).resolve()
    frozen_runtime_hashes = runtime_hashes(root)
    manifest, index, catalog = load_context(root, cache_root)
    plans = sorted((p for p in manifest["plans"].values() if p["stateFips"] == state), key=lambda p: p["districtCount"])
    if not plans or state == "26":
        raise ValueError("Select an accepted state other than the preserved Michigan explorer")
    fragment_path = safe_path(root, FRAGMENTS / f"{state}.json")
    if fragment_path.exists():
        fragment = json.loads(fragment_path.read_bytes())
        verify_fragment(root, cache_root, fragment, plans, index)
        print(f"Reused verified state {state}", flush=True)
        return {"stateFips": state, "path": fragment_path.relative_to(root).as_posix(), "sha256": file_hash(fragment_path), "reused": True}
    if shutil.disk_usage(root).free < MINIMUM_FREE_BYTES:
        raise OSError("Insufficient free space for spatial derivatives; saved data was not changed")
    preserved: dict[Path, str] = {}
    accepted = {p["plan_id"]: p for p in catalog["plans"]}
    details = {}
    for plan in plans:
        proof = index["proofs"][plan["id"]]
        for name, hash_key in (("reportPath", "reportSha256"), ("manifestPath", "manifestSha256")):
            read_pinned(root, proof[name], proof[hash_key], cache_root)
            preserved[resource_path(root, proof[name], cache_root)] = proof[hash_key]
        if proof["reportSha256"] != accepted[plan["id"]]["report_sha256"]:
            raise ValueError("Saved report differs from accepted catalog")
        detail = read_asset(root, cache_root, index, plan["assets"]["detailIndex"], preserved)
        if detail.get("planId") != plan["id"] or detail.get("coordinateFrame") != plan["coordinateFrame"]:
            raise ValueError("Saved county index identity/frame mismatch")
        details[plan["id"]] = {c["fips"]: c for c in detail["counties"]}
        if len(details[plan["id"]]) != len(detail["counties"]):
            raise ValueError("Duplicate source counties")
    reference = read_asset(root, cache_root, index, manifest["comparisonLayers"][state]["counties"]["asset"], preserved)
    names = {}
    for feature in reference["features"]:
        props = feature["properties"]
        geoid = props.get("geoid")
        if not isinstance(geoid, str) or not re.fullmatch(state + r"\d{3}", geoid) or geoid[2:] in names or not props.get("name"):
            raise ValueError("Invalid or duplicate county reference")
        names[geoid[2:]] = props["name"]
    if any(set(d) != set(names) for d in details.values()):
        raise ValueError("Named county coverage differs from saved blocks")
    builder = BundleBuilder(root, cache_root=cache_root)
    all_chunks = {p["id"]: [] for p in plans}
    all_counties = {p["id"]: [] for p in plans}
    semantic_digests = {p["id"]: hashlib.sha256() for p in plans}
    source_audit = {p["id"]: [] for p in plans}
    shared_geometry_bytes = assignment_bytes = shared_chunk_count = 0
    source_count = 0
    frame = plans[0]["coordinateFrame"]
    for position, fips in enumerate(sorted(names), 1):
        if shutil.disk_usage(root).free < MINIMUM_FREE_BYTES:
            raise OSError("Insufficient free space during spatial derivatives; completed fragments remain resumable")
        base_plan = plans[0]
        base_county = details[base_plan["id"]][fips]
        base_source = source_features(read_asset(root, cache_root, index, base_county["asset"], preserved), base_county, base_plan)
        records = base_records(base_source, frame)
        groups = list(spatial_groups(records, fips))
        generated = []
        for chunk_id, values in groups:
            document = shared_chunk(state, frame, chunk_id, values)
            asset = builder.generated(document, f"{state}-shared-spatial-{chunk_id}.geojson")
            if len(values) > MAX_BLOCKS or (asset["bytes"] > MAX_RAW_BYTES and len(values) != 1):
                raise ValueError("Shared chunk exceeded whole-block limits")
            decoded = read_asset(root, cache_root, {"assets": builder.assets}, asset, {})
            if decoded != document:
                raise ValueError("Shared compressed geometry changed after writing")
            # The decoded bytes were verified equal above. Retain the original
            # reference-sharing document so a large county's geometry is not
            # duplicated in memory for the remaining anchor comparisons.
            generated.append(({"chunkId": chunk_id, "bbox": union_bounds(values), "blockCount": len(values),
                "population": sum(b.population for b in values), "asset": asset}, values, document))
            shared_geometry_bytes += asset["gzipBytes"]
        shared_chunk_count += len(groups)
        source_count += len(records)
        for plan in plans:
            county = details[plan["id"]][fips]
            features = base_source if plan["id"] == base_plan["id"] else source_features(read_asset(root, cache_root, index, county["asset"], preserved), county, plan)
            assignments = reconcile_geometry(features, records)
            seen: set[str] = set()
            for descriptor, values, decoded in generated:
                payload = assignment_document(plan, descriptor["chunkId"], descriptor["asset"], values, assignments)
                asset = builder.generated(payload, f"{plan['id']}-spatial-{descriptor['chunkId']}-assignments.json")
                assignment_bytes += asset["gzipBytes"]
                restored_assignment = read_asset(root, cache_root, {"assets": builder.assets}, asset, {})
                validate_reconstruction(decoded, restored_assignment, descriptor, plan, features, seen)
                all_chunks[plan["id"]].append({**descriptor, "assignments": asset})
            if seen != set(features):
                raise ValueError("Chunk reconstruction lost a saved block")
            for block in records:
                semantic_digests[plan["id"]].update(f"{block.geoid}:{block.fingerprint}:{assignments[block.geoid]}\n".encode("ascii"))
            all_counties[plan["id"]].append(county_summary(records, assignments, county, names[fips]))
            source_audit[plan["id"]].append({"fips": fips, "sourceAsset": county["asset"], "blockCount": len(features),
                "population": county["population"], "chunkCount": len(groups)})
        progress = {"status": "running", "stateFips": state, "completedCounties": position, "countyCount": len(names),
            "sharedChunkCount": shared_chunk_count, "blockCount": source_count, "runtimeSeconds": time.perf_counter() - started}
        atomic_json(safe_path(root, FRAGMENTS / f"{state}.progress.json"), progress)
        print(f"State {state}: {position}/{len(names)} counties, {source_count:,} blocks, {shared_chunk_count:,} shared chunks", flush=True)
        del base_source, features, records, groups, generated, decoded
    result = {"schemaVersion": 1, "status": "complete", "stateFips": state, "catalogSha256": index["catalogSha256"],
        "runtimeHashes": frozen_runtime_hashes, "plans": {}, "assets": builder.assets,
        "audit": {"plans": {}, "sharedGeometryGzipBytes": shared_geometry_bytes, "assignmentGzipBytes": assignment_bytes,
            "sharedChunkCount": shared_chunk_count, "uniqueStateBlockCount": source_count,
            "featureIdentity": "Pinned saved Features equal reconstructed shared Feature plus typed integer district_id; canonical base Feature SHA256 plus district_id binds per-plan semantic identity",
            "partition": {"gridDegrees": GRID_DEGREES, "maximumBlocks": MAX_BLOCKS, "maximumRawBytes": MAX_RAW_BYTES,
                "bounds": "Full unchanged geometry extent, including Alaska continuous longitudes and multipart/water blocks",
                "oversizePolicy": "Individual source blocks remain whole even above the normal size cap"},
            "savedAssignmentsModified": 0, "solverRuns": 0, "preservedPlansSha256": digest(encoded(plans)),
            "preservedFiles": [{"path": relative_resource(root, cache_root, path), "sha256": sha} for path, sha in sorted(preserved.items())]}}
    for plan in plans:
        plan_id = plan["id"]
        summary = plan_summary(plan, all_counties[plan_id], accepted[plan_id]["validation"]["district_block_counts"])
        chunks = all_chunks[plan_id]
        if sum(c["blockCount"] for c in chunks) != plan["blockCount"] or sum(c["population"] for c in chunks) != plan["residentPopulation"]:
            raise ValueError("Spatial index totals differ from the saved plan")
        spatial = {"schemaVersion": 2, "planId": plan_id, "stateFips": state, "coordinateFrame": plan["coordinateFrame"],
            "totalBlockCount": plan["blockCount"], "totalPopulation": plan["residentPopulation"],
            "counties": [{k: c[k] for k in ("fips", "blockCount", "population")} for c in summary["counties"]], "chunks": chunks}
        result["plans"][plan_id] = {"summary": builder.generated(summary, f"{plan_id}-state-explorer-summary.json"),
            "spatialIndex": builder.generated(spatial, f"{plan_id}-state-spatial-index.json")}
        result["audit"]["plans"][plan_id] = {"blockCount": plan["blockCount"], "population": plan["residentPopulation"],
            "districtPopulations": [d["population"] for d in summary["districts"]],
            "districtBlockCounts": [d["blockCount"] for d in summary["districts"]],
            "chunkCount": len(chunks), "canonicalBaseAndAssignmentSha256": semantic_digests[plan_id].hexdigest(),
            "counties": source_audit[plan_id]}
    verify_file_inventory(root, cache_root, result["audit"]["preservedFiles"])
    if runtime_hashes(root) != frozen_runtime_hashes:
        raise ValueError("Runtime source changed during preparation; no completed fragment was published")
    result["audit"]["runtimeSeconds"] = time.perf_counter() - started
    atomic_json(fragment_path, result)
    atomic_json(safe_path(root, FRAGMENTS / f"{state}.progress.json"), {"status": "complete", "stateFips": state,
        "runtimeSeconds": result["audit"]["runtimeSeconds"], "fragment": fragment_path.relative_to(root).as_posix()})
    return {"stateFips": state, "path": fragment_path.relative_to(root).as_posix(), "sha256": file_hash(fragment_path),
        "reused": False, "runtimeSeconds": result["audit"]["runtimeSeconds"], "uniqueBlocks": source_count,
        "geometryGzipBytes": shared_geometry_bytes, "assignmentGzipBytes": assignment_bytes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, default=Path(os.environ.get("BLOCK_PLAN_CACHE_ROOT", ROOT / ".cache")))
    parser.add_argument("--states", nargs="+", help="Two-digit state FIPS; default all except already-preserved Michigan")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    root, cache = args.bundle_root.resolve(), args.cache_root.resolve()
    manifest, index, _ = load_context(root, cache)
    states = sorted(set(args.states or [p["stateFips"] for p in manifest["plans"].values() if p["stateFips"] != "26"]))
    if any(not re.fullmatch(r"\d{2}", s) or s == "26" for s in states):
        parser.error("States must be two-digit FIPS other than preserved Michigan")
    started = time.perf_counter()
    results = []
    name = "all-states" if not args.states else "states-" + "-".join(states)
    run_path = safe_path(root, FRAGMENTS / f"{name}.run.json")
    run = {"status": "running", "pid": os.getpid(), "states": states, "workers": args.workers,
        "catalogSha256": index["catalogSha256"], "completed": [], "activeState": None}
    atomic_json(run_path, run)
    try:
        if args.workers == 1:
            for state in states:
                run["activeState"] = state
                atomic_json(run_path, run)
                result = build_state(root, cache, state)
                results.append(result)
                run["completed"] = [r["stateFips"] for r in results]
                atomic_json(run_path, run)
                print(json.dumps(result), flush=True)
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(build_state, root, cache, state): state for state in states}
                for future in as_completed(futures):
                    run["activeState"] = futures[future]
                    result = future.result()
                    results.append(result)
                    run["completed"] = [r["stateFips"] for r in results]
                    atomic_json(run_path, run)
                    print(json.dumps(result), flush=True)
    except BaseException as error:
        run.update(status="failed", error=f"{type(error).__name__}: {error}", runtimeSeconds=time.perf_counter() - started)
        atomic_json(run_path, run)
        raise
    report = {"status": "complete", "catalogSha256": index["catalogSha256"], "states": sorted(results, key=lambda r: r["stateFips"]),
        "runtimeSeconds": time.perf_counter() - started, "workers": args.workers, "savedAssignmentsModified": 0, "solverRuns": 0}
    atomic_json(safe_path(root, FRAGMENTS / f"{name}.json"), report)
    run.update(status="complete", activeState=None, runtimeSeconds=report["runtimeSeconds"])
    atomic_json(run_path, run)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
