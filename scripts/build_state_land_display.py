"""Prepare additive, pinned land-focused display fragments for one state.

Assignments, population totals, source geometry and recorded policy links are
read-only. Only source blocks whose ALAND20 equals zero are hidden. Small
enclosed overview holes use the saved district ownership; mixed land/water
blocks and all genuine islands remain. No solver or manifest publication runs.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import time
from zipfile import ZipFile

import numpy as np
import shapefile
from shapely import STRtree, transform
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import BundleBuilder, CATALOG, OUTPUT, digest, encoded, read_pinned, resource_path, safe_path, validate_catalog
from scripts.build_block_state_outlines import read_full_outlines
from scripts.build_michigan_explorer_geometry import boundary_layers, clean_overview_partition, read_asset
from scripts.build_michigan_land_display import METHOD, checked_assignments, file_digest, remove_water_only, simplify_display
from scripts.build_state_explorer_geometry import atomic_json, checked_entry, validate_collection
from scripts.state_land_candidate_graph import load_state_candidate_graph

NAMESPACE = OUTPUT / "state-land-display-v1"
OVERVIEW_TOLERANCE = 0.002
DETAIL_TOLERANCE = 0.0001
RUNTIME_FILES = (
    "scripts/build_state_land_display.py", "scripts/state_land_water_paths.py", "scripts/michigan_water_paths.py",
    "scripts/state_land_candidate_graph.py",
    "scripts/build_michigan_explorer_geometry.py", "scripts/build_michigan_land_display.py",
    "scripts/build_state_explorer_geometry.py", "scripts/build_block_state_outlines.py",
    "scripts/build_block_plan_bundle.py",
)


def runtime_hashes() -> dict[str, str]:
    return {path: file_digest(ROOT / path) for path in RUNTIME_FILES}


def source_archive_relative(state: str) -> Path:
    """Kansas predates the national suite and retains its original source cache."""
    if len(state) != 2 or not state.isdigit():
        raise ValueError("Source archive needs a two-digit state FIPS")
    if state == "20":
        return Path(".cache/kansas-block-benchmark/source/tl_2020_20_tabblock20.zip")
    return Path(f".cache/state-block-benchmark/source/{state}/tl_2020_{state}_tabblock20.zip")


def working_geometry(geometry, frame: str):
    """Match Alaska's accepted continuous working frame, without wrapping."""
    if frame not in ("source", "alaska-continuous"):
        raise ValueError("Unknown coordinate frame")
    if frame == "alaska-continuous":
        def translate(points):
            result = points.copy()
            result[:, 0] = np.where(result[:, 0] > 0, result[:, 0] - 360, result[:, 0])
            return result
        geometry = transform(geometry, translate)
    if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Source block is not a valid polygon in its accepted frame")
    return geometry


@contextmanager
def source_reader(archive_path: Path, source: dict, state: str):
    """Check the full archive pin, plus extracted pins when provided historically."""
    if file_digest(archive_path) != source["archive_sha256"]:
        raise ValueError("Source archive identity mismatch")
    if "archive_bytes" in source and archive_path.stat().st_size != source["archive_bytes"]:
        raise ValueError("Source archive length mismatch")
    prefix = f"tl_2020_{state}_tabblock20"
    pins = source.get("extracted_file_sha256", {})
    with ZipFile(archive_path) as archive, tempfile.TemporaryFile() as shp:
        checksum = hashlib.sha256()
        with archive.open(prefix + ".shp") as original:
            for chunk in iter(lambda: original.read(2 ** 20), b""):
                checksum.update(chunk)
                shp.write(chunk)
        if pins and checksum.hexdigest() != pins.get(prefix + ".shp"):
            raise ValueError("Source SHP identity mismatch")
        pieces = {suffix: archive.read(prefix + suffix) for suffix in (".shx", ".dbf")}
        if pins and any(digest(value) != pins.get(prefix + suffix) for suffix, value in pieces.items()):
            raise ValueError("Source DBF/SHX identity mismatch")
        shp.seek(0)
        reader = shapefile.Reader(shp=shp, shx=io.BytesIO(pieces[".shx"]), dbf=io.BytesIO(pieces[".dbf"]))
        try:
            yield reader, shp, pieces[".shx"]
        finally:
            reader.close()


def source_attributes(reader, state: str) -> tuple[list[str], np.ndarray, np.ndarray]:
    geoids, population, land = [], [], []
    for row in reader.iterRecords(fields=["GEOID20", "POP20", "ALAND20"]):
        geoid = row["GEOID20"]
        if not isinstance(geoid, str) or len(geoid) != 15 or not geoid.isdigit() or not geoid.startswith(state):
            raise ValueError("Unexpected source GEOID")
        geoids.append(geoid)
        population.append(int(row["POP20"]))
        land.append(int(row["ALAND20"]))
    if len(set(geoids)) != len(geoids) or min(population, default=0) < 0 or min(land, default=0) < 0:
        raise ValueError("Duplicate source identity or negative attributes")
    return geoids, np.asarray(population, dtype=np.int64), np.asarray(land, dtype=np.int64)


def source_bounds(shp, shx: bytes, count: int, geometry, frame: str) -> list[tuple]:
    """Read SHP polygon bounds without allocating every source coordinate array.

    These boxes are only broad candidates. The path auditor rechecks every
    source Polygon-part shared edge. A dateline-spanning Alaska box is recomputed
    from its transformed coordinates rather than translating its extremes.
    """
    if len(shx) != 100 + count * 8:
        raise ValueError("SHP/DBF record counts differ")
    result = []
    for index in range(count):
        offset, length = struct.unpack_from(">ii", shx, 100 + index * 8)
        if offset < 50 or length < 22:
            raise ValueError("Invalid SHX record")
        shp.seek(offset * 2)
        record_number, actual_length = struct.unpack(">ii", shp.read(8))
        if record_number != index + 1 or actual_length != length:
            raise ValueError("SHP/SHX record identity mismatch")
        raw = shp.read(36)
        kind, west, south, east, north = struct.unpack("<i4d", raw)
        if kind not in (5, 15, 25) or not all(math.isfinite(v) for v in (west, south, east, north)) or west >= east or south >= north:
            raise ValueError("Invalid source polygon bounds")
        if frame == "alaska-continuous":
            if west > 0:
                west, east = west - 360, east - 360
            elif east > 0:
                west, south, east, north = geometry(index).bounds
        result.append((west, south, east, north))
    return result


def prepare_land_layers(exact: dict, full: dict, plan: dict) -> tuple[dict, dict]:
    """Apply the Michigan overview method with a state-local display threshold."""
    metadata = {"purpose": "display-only", "planId": plan["id"], "stateFips": plan["stateFips"],
                "coordinateFrame": plan["coordinateFrame"], "coverage": "land-focused",
                "method": METHOD, "population_basis": "All saved assigned blocks, including hidden zero-land blocks."}
    exact = deepcopy(exact)
    exact.setdefault("metadata", {}).update(metadata)
    if any(feature.get("geometry") is None for feature in exact["features"]):
        raise ValueError("An accepted district contains only hidden water; no land-focused display can be published")
    validate_collection(exact, plan)
    latitude = (plan["bbox"][1] + plan["bbox"][3]) / 2
    scale = 111_320.0 ** 2 * math.cos(math.radians(latitude))
    clean, clean_audit = clean_overview_partition(exact, full, area_scale_m2=scale)
    clean_audit["area_method"] = f"Longitude/latitude area scaled by 111320^2*cos({latitude:.8f} degrees); approximate display threshold only"
    clean_audit["reference_latitude_degrees"] = latitude
    clean["metadata"]["overview_water_detail"] = clean_audit
    overview = simplify_display(clean, OVERVIEW_TOLERANCE, full_collection=full)
    detail = simplify_display(exact, DETAIL_TOLERANCE, full_collection=full)
    for collection in (overview, detail):
        collection["metadata"].update({key: value for key, value in metadata.items() if key != "method"})
        validate_collection(collection, plan)
        if [f["properties"] for f in collection["features"]] != [f["properties"] for f in full["features"]]:
            raise ValueError("Display geometry changed saved district properties")
    coast, dividers, overview_audit = boundary_layers(overview, plan["id"])
    _, detail_dividers, detail_audit = boundary_layers(detail, plan["id"])
    for collection in (coast, dividers, detail_dividers):
        collection["metadata"].update(metadata)
        for feature in collection["features"]:
            if "state_fips" in feature["properties"]:
                feature["properties"]["state_fips"] = plan["stateFips"]
    return {"overview": overview, "detail": detail, "coast": coast, "dividers": dividers, "detailDividers": detail_dividers}, {
        "overview": clean_audit, "overviewDividers": overview_audit, "detailDividers": detail_audit,
        "coordinateFrame": plan["coordinateFrame"], "coordinateWrappingApplied": False,
        "savedDistrictPropertiesUnchanged": True, "overviewToleranceDegrees": OVERVIEW_TOLERANCE,
        "detailToleranceDegrees": DETAIL_TOLERANCE,
    }


def verify_fragment(root: Path, cache: Path, fragment: dict, identity: dict) -> None:
    if fragment.get("status") != "complete" or fragment.get("identity") != identity:
        raise ValueError("Land fragment identity differs; preserve it and use a new namespace for changed runtime")
    if fragment["audit"]["waterPaths"].get("all_components_explained") is not True:
        raise ValueError("Land fragment has unexplained components")
    for record in (fragment["landDisplay"], fragment["geometryPlan"]):
        for reference in record.values():
            if isinstance(reference, dict) and "url" in reference:
                checked_entry(root, cache, reference, fragment["assets"])
    for item in fragment["audit"]["preservedFiles"]:
        if file_digest(resource_path(root, item["path"], cache)) != item["sha256"]:
            raise ValueError("Preserved source identity changed")


def build_state_land_display(bundle_root: Path, cache_root: Path, state: str, district_count: int | None = None) -> dict:
    from scripts.state_land_water_paths import derive_state_water_paths

    started = time.perf_counter()
    root, cache = bundle_root.resolve(), cache_root.resolve()
    if len(state) != 2 or not state.isdigit() or state == "26":
        raise ValueError("Select one non-Michigan state; Michigan's accepted display is reused unchanged")
    catalog_raw = safe_path(root, CATALOG).read_bytes()
    catalog = json.loads(catalog_raw)
    validate_catalog(catalog)
    index_path = safe_path(root, OUTPUT / "server-index.json")
    index_raw = index_path.read_bytes()
    index = json.loads(index_raw)
    manifest_raw = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(manifest_raw)
    catalog_sha = digest(catalog_raw)
    if manifest["catalogSha256"] != catalog_sha or index["catalogSha256"] != catalog_sha:
        raise ValueError("Source and app catalog identities differ")
    selected = sorted((p for p in catalog["plans"] if p["state_fips"] == state and (district_count is None or p["district_count"] == district_count)), key=lambda p: p["district_count"])
    if not selected:
        raise ValueError("Requested state/plan is not accepted")
    source = selected[0]["source"]
    if any(p["source"]["archive_sha256"] != source["archive_sha256"] for p in selected):
        raise ValueError("State plans use different source archives")
    archive_relative = source_archive_relative(state)
    archive = resource_path(root, archive_relative, cache)
    hashes = runtime_hashes()
    base_identity = {"manifestSha256": digest(manifest_raw), "serverIndexSha256": digest(index_raw)}
    result = {"schemaVersion": 1, "status": "complete", "stateFips": state, "catalogSha256": catalog_sha,
              "baseBundle": base_identity,
              "baseManifestSha256": digest(manifest_raw), "baseIndexSha256": digest(index_raw),
              "landDisplays": {}, "geometryPlans": {}, "assets": {}, "audit": {"plans": {}, "runtimeHashes": hashes,
              "solverRuns": 0, "savedPlansModified": 0, "recordedConnectionsModified": 0}}
    pending = []
    for accepted in selected:
        plan = manifest["plans"][accepted["plan_id"]]
        identity = {"catalogSha256": catalog_sha, "baseBundle": base_identity, "acceptedPlanSha256": digest(encoded(accepted)), "appPlanSha256": digest(encoded(plan)), "runtimeHashes": hashes}
        path = safe_path(root, NAMESPACE / "plans" / (plan["id"] + ".json"))
        if path.exists():
            fragment = json.loads(path.read_bytes())
            verify_fragment(root, cache, fragment, identity)
            print(f"Reused land display {plan['id']}", flush=True)
            collect_fragment(result, fragment)
        else:
            pending.append((accepted, plan, identity, path))
    if pending:
        with source_reader(archive, source, state) as (reader, shp, shx):
            geoids, population, land = source_attributes(reader, state)
            if len(geoids) != selected[0]["block_count"] or int(population.sum()) != selected[0]["resident_population"]:
                raise ValueError("Source DBF totals differ from accepted state")
            frame = pending[0][1]["coordinateFrame"]
            @lru_cache(maxsize=16384)
            def geometry(node: int):
                return working_geometry(shape(reader.shape(node).__geo_interface__), frame)
            print(f"Preparing {state} source water geometry and pinned adjacency candidates", flush=True)
            candidate_plan = pending[0][0]
            candidate_report = json.loads(read_pinned(root, candidate_plan["report_path"], candidate_plan["report_sha256"], cache))
            candidates, candidate_audit, candidate_preserved = load_state_candidate_graph(
                root, cache, state, geoids, source["archive_sha256"], candidate_report)
            candidate_preserved[candidate_plan["report_path"]] = candidate_plan["report_sha256"]
            if candidates is None:
                bounds = source_bounds(shp, shx, len(geoids), geometry, frame)
                boxes = [box(*value) for value in bounds]
                tree = STRtree(boxes)
                def candidates(node: int):
                    return [int(value) for value in tree.query(boxes[node]) if int(value) != node]
            print(f"Candidate discovery for {state}: {candidate_audit['method']}", flush=True)
            water = {int(i): geometry(int(i)) for i in np.flatnonzero(land == 0)}
            for accepted, plan, identity, fragment_path in pending:
                plan_started = time.perf_counter()
                plan_id = plan["id"]
                print(f"Preparing land display {plan_id}", flush=True)
                preserved = {archive_relative.as_posix(): source["archive_sha256"], **candidate_preserved}
                run = Path(accepted.get("run_directory", accepted.get("candidate_dir", "")))
                checkpoint_path = run / "solver-result.json"
                checkpoint = json.loads(read_pinned(root, checkpoint_path, accepted["validation"]["checkpoint_sha256"], cache))
                preserved[checkpoint_path.as_posix()] = accepted["validation"]["checkpoint_sha256"]
                assignments = checked_assignments(accepted, checkpoint, geoids, population)
                full, proof = read_full_outlines(root, accepted, cache_root=cache)
                validate_collection(full, plan)
                preserved[proof["path"]] = proof["gzip_sha256"]
                preserved[accepted["report_path"]] = accepted["report_sha256"]
                read_pinned(root, accepted["report_path"], accepted["report_sha256"], cache)
                recorded = None
                if plan["assets"].get("connections"):
                    asset = plan["assets"]["connections"]
                    recorded = read_asset(root, cache, index, asset)
                    _, entry = checked_entry(root, cache, asset, index["assets"])
                    preserved[entry["path"]] = entry["gzipSha256"]
                print(f"Removing only zero-land source coverage for {plan_id}", flush=True)
                exact, parts = remove_water_only(full, water, assignments)
                print(f"Auditing physical part paths and original recorded links for {plan_id}", flush=True)
                features, path_audit = derive_state_water_paths(parts, water, geometry, geoids, land, assignments, candidates, recorded_connections=recorded, state_fips=state)
                if path_audit.get("all_components_explained") is not True:
                    failure_path = safe_path(root, NAMESPACE / "failures" / f"{plan_id}-{time.time_ns()}.json")
                    atomic_json(failure_path, {"status": "rejected-display", "planId": plan_id, "identity": identity,
                        "candidateGraph": candidate_audit, "waterPaths": path_audit,
                        "reason": "Physical and original recorded edges do not explain every exact display/source-water component.",
                        "preservedFiles": [{"path": path, "sha256": sha} for path, sha in sorted(preserved.items())]})
                    raise ValueError(f"Unexplained land components in {plan_id}; refusing publication; saved audit: {failure_path}")
                print(f"Simplifying the validated display partition for {plan_id}", flush=True)
                layers, geometry_audit = prepare_land_layers(exact, full, plan)
                builder = BundleBuilder(root, cache_root=cache)
                geometry_plan = {key: builder.generated(value, f"{plan_id}-land-{key}.geojson") for key, value in layers.items()}
                geometry_plan.update({"coverage": "land-focused", "coordinateFrame": frame})
                connections = {"type": "FeatureCollection", "features": features, "metadata": {
                    "schemaVersion": 2,
                    "planId": plan_id, "stateFips": state, "coordinateFrame": frame, "purpose": "display-only",
                    "kind": "derived-water-adjacency", "recordedConnectionCount": plan["recordedLinkCount"],
                    "method": "Schematic verified physical shared-edge water paths; recorded policy links remain separate and unchanged."}}
                summary = {"derivedConnectionCount": len(features), "zeroLandPopulation": int(population[land == 0].sum()),
                           "zeroLandBlockCount": len(water), "method": METHOD}
                land_display = {"planId": plan_id, "state": geometry_plan["detail"], "national": geometry_plan["overview"],
                                "connections": builder.generated(connections, f"{plan_id}-land-derived-connections.geojson"), "summary": summary}
                audit = {**geometry_audit, "waterPaths": path_audit, "candidateGraph": candidate_audit, "fullSource": proof, "summary": summary,
                         "residentPopulation": plan["residentPopulation"], "blockCount": len(geoids), "recordedLinkCount": plan["recordedLinkCount"],
                         "recordedConnectionsSha256": plan["assets"].get("connections", {}).get("sha256"),
                         "assignmentsSha256": accepted["validation"]["checkpoint_sha256"],
                         "sourceArchiveSha256": source["archive_sha256"], "runtimeSeconds": time.perf_counter() - plan_started,
                         "preservedFiles": [{"path": path, "sha256": sha} for path, sha in sorted(preserved.items())]}
                fragment = {"schemaVersion": 1, "status": "complete", "identity": identity, "landDisplay": land_display,
                            "geometryPlan": geometry_plan, "assets": builder.assets, "audit": audit}
                verify_fragment(root, cache, fragment, identity)
                atomic_json(fragment_path, fragment)
                collect_fragment(result, fragment)
                print(f"Prepared {plan_id}: {len(features)} physical display paths, {plan['recordedLinkCount']} preserved policy links, {audit['runtimeSeconds']:.2f}s", flush=True)
    if (safe_path(root, CATALOG).read_bytes() != catalog_raw or index_path.read_bytes() != index_raw or safe_path(root, OUTPUT / "manifest.json").read_bytes() != manifest_raw):
        raise ValueError("Authoritative app metadata changed during display preparation")
    if runtime_hashes() != hashes:
        raise ValueError("Display runtime changed during preparation")
    result["runtimeSeconds"] = time.perf_counter() - started
    result["audit"]["limitation"] = "ALAND20=0 exclusion is a display approximation; mixed land/water source blocks remain. Overview suppresses small enclosed water gaps without changing saved ownership. Derived lines are schematic, not travel routes or policy edges."
    suffix = state if district_count is None else f"{state}-districts-{district_count}"
    atomic_json(safe_path(root, NAMESPACE / "states" / f"{suffix}.json"), result)
    return result


def collect_fragment(result: dict, fragment: dict) -> None:
    plan_id = fragment["landDisplay"]["planId"]
    result["landDisplays"][plan_id] = fragment["landDisplay"]
    result["geometryPlans"][plan_id] = fragment["geometryPlan"]
    result["assets"].update(fragment["assets"])
    result["audit"]["plans"][plan_id] = fragment["audit"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--district-count", type=int, help="Optional accepted-plan pilot; writes a separate state report")
    args = parser.parse_args()
    result = build_state_land_display(args.bundle_root, args.cache_root, args.state, args.district_count)
    print(json.dumps({"status": result["status"], "plans": len(result["landDisplays"]), "assets": len(result["assets"]), "runtimeSeconds": result["runtimeSeconds"]}))


if __name__ == "__main__":
    main()
