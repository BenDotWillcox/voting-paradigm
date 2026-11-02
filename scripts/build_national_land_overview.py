"""Prepare a lighter national-only map without changing accepted state views.

Every state is simplified as shared arcs. Exterior source arcs approaching a
neighbor remain exact, so independently simplified historical borders cannot
acquire larger seams. Coast/divider meshes come from the same polygons.
Recorded and derived connection assets are reused exactly. No solver runs.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import gzip
import math
from pathlib import Path
import sys
import time

import numpy as np
from shapely import STRtree, coverage_is_valid, get_coordinates, points, linestrings, segmentize, union_all
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import BundleBuilder, OUTPUT, digest, encoded, read_pinned, resource_path, safe_path
from scripts.build_michigan_explorer_geometry import boundary_layers, line_parts
from scripts.build_michigan_land_display import file_digest, polygon_parts
from scripts.national_land_arcs import shared_arc_partition
from scripts.build_state_explorer_geometry import atomic_json, validate_collection
from scripts.publish_state_explorer import merge_assets, read_reference, validate_anchors, validate_assets
from scripts.publish_state_land_display import annotated_features, classify_coast

NAMESPACE = OUTPUT / "national-land-overview-v1"
DEFAULT_TOLERANCE = 0.02
DEFAULT_BORDER_BAND = 0.05
ERROR_SAMPLE_STEP = 0.01
MAX_BOUNDARY_ERROR = 0.05
RUNTIME_FILES = ("scripts/build_national_land_overview.py", "scripts/national_land_arcs.py", "scripts/build_michigan_explorer_geometry.py",
                 "scripts/build_michigan_land_display.py", "scripts/build_state_explorer_geometry.py",
                 "scripts/publish_state_land_display.py", "scripts/publish_state_explorer.py", "scripts/build_block_plan_bundle.py")


def topology(geometry) -> tuple[int, int]:
    parts = polygon_parts(geometry)
    return len(parts), sum(len(part.interiors) for part in parts)


def point_count(geometries) -> int:
    return sum(len(get_coordinates(value)) for value in geometries)


def boundary_error_bound(before, after, step: float = ERROR_SAMPLE_STEP) -> float:
    """Conservative continuous Hausdorff bound via samples and Lipschitz distance.

    Every boundary point is at most step/2 along its segment from a sample;
    nearest-boundary distance is 1-Lipschitz. Exact nearest-segment distances at
    all samples, in both directions, therefore bound the complete boundaries.
    A segment STRtree avoids the quadratic dense Hausdorff implementation.
    """
    def directed(source, target):
        segments = []
        for geometry in target:
            for coordinates in line_parts(geometry.boundary):
                array = np.asarray(coordinates, dtype=float)
                segments.extend(np.stack((array[:-1], array[1:]), axis=1))
        tree = STRtree(linestrings(np.asarray(segments)))
        maximum = 0.0
        for geometry in source:
            samples = get_coordinates(segmentize(geometry.boundary, step))
            for start in range(0, len(samples), 8192):
                _, distances = tree.query_nearest(points(samples[start:start + 8192]), return_distance=True, all_matches=False)
                if len(distances):
                    maximum = max(maximum, float(distances.max()))
        return maximum
    return max(directed(before, after), directed(after, before)) + step / 2


def simplify_state(collection: dict, plan: dict, neighboring_states: list, *, tolerance: float, border_band: float) -> tuple[dict, dict]:
    if not math.isfinite(tolerance) or tolerance <= 0 or not math.isfinite(border_band) or border_band < 2 * tolerance:
        raise ValueError("A positive national tolerance needs a border band at least twice as wide")
    validate_collection(collection, plan)
    original = [shape(feature["geometry"]) for feature in collection["features"]]
    input_valid = bool(coverage_is_valid(original))
    audit = {"requestedToleranceDegrees": tolerance, "borderBandDegrees": border_band,
             "inputCoverageValid": input_valid, "neighboringStates": len(neighboring_states),
             "inputPoints": point_count(original), "inputTopology": [topology(g) for g in original],
             "coordinateFrame": plan["coordinateFrame"], "coordinateWrappingApplied": False,
             "interstateMethod": "Keep every exterior source edge within the neighbor guard unchanged, including its original coordinates; simplify shared district arcs once.",
             "sourceStateOverviewChanged": False, "attempts": []}
    output = deepcopy(collection)
    chosen = original
    if input_valid:
        for candidate_tolerance in (tolerance, tolerance / 2, tolerance / 4):
            try:
                candidate, arc_audit = shared_arc_partition(original, neighboring_states, candidate_tolerance, border_band)
                if any(g.is_empty or not g.is_valid or g.geom_type not in ("Polygon", "MultiPolygon") for g in candidate):
                    raise ValueError("Shared-arc simplification produced invalid polygons")
                if any(topology(a) != topology(b) for a, b in zip(original, candidate)):
                    raise ValueError("Shared-arc simplification changed district islands or holes")
                if not coverage_is_valid(candidate):
                    raise ValueError("Shared-arc simplification is not a valid coverage")
                errors = [boundary_error_bound([before], [after]) for before, after in zip(original, candidate)]
                error = max(errors, default=0.0)
                if error > MAX_BOUNDARY_ERROR:
                    raise ValueError(f"Continuous boundary error bound {error:g} exceeds national display limit")
                chosen = candidate
                audit.update({"appliedToleranceDegrees": candidate_tolerance, "retainedOriginal": False,
                              "protectedExteriorEdgesUnchanged": True, "arcs": arc_audit, "boundaryErrorUpperBoundDegrees": error})
                audit["districtBoundaryErrorUpperBoundsDegrees"] = errors
                audit["attempts"].append({"tolerance": candidate_tolerance, "status": "accepted"})
                break
            except ValueError as error:
                audit["attempts"].append({"tolerance": candidate_tolerance, "status": "rejected", "reason": str(error)})
    if chosen is original:
        audit.update({"appliedToleranceDegrees": 0, "retainedOriginal": True, "protectedExteriorEdgesUnchanged": True,
                      "boundaryErrorUpperBoundDegrees": 0, "fallbackReason": "Input coverage invalid" if not input_valid else "No topology-preserving candidate passed"})
        audit["districtBoundaryErrorUpperBoundsDegrees"] = [0.0] * len(original)
    for feature, geometry in zip(output["features"], chosen):
        feature["geometry"] = mapping(geometry)
    output.setdefault("metadata", {}).update({"purpose": "national-only display", "planId": plan["id"], "stateFips": plan["stateFips"],
        "coordinateFrame": plan["coordinateFrame"], "coverage": "land-focused", "nationalSimplification": audit})
    validate_collection(output, plan)
    if [f["properties"] for f in output["features"]] != [f["properties"] for f in collection["features"]]:
        raise ValueError("National display changed district properties")
    audit.update({"outputPoints": point_count(chosen), "outputTopology": [topology(g) for g in chosen],
                  "outputCoverageValid": bool(coverage_is_valid(chosen)), "savedDistrictPropertiesUnchanged": True})
    return output, audit


def build_anchor(root: Path, cache: Path, manifest: dict, index: dict, house_size: int,
                 states: set[str] | None, tolerance: float, border_band: float) -> tuple[dict, dict, dict]:
    started = time.perf_counter()
    original = manifest["landAnchors"][str(house_size)]
    source = read_reference(root, cache, original["outlines"], index["assets"])
    by_state = {}
    for feature in source["features"]:
        by_state.setdefault(feature["properties"]["state_fips"], []).append(feature)
    plans = {manifest["plans"][p]["stateFips"]: manifest["plans"][p] for p in original["planIds"]}
    if set(by_state) != set(plans) or (states is not None and not states.issubset(plans)):
        raise ValueError("National source membership differs from the anchor")
    state_unions = {state: union_all([shape(feature["geometry"]) for feature in features]) for state, features in by_state.items()}
    state_ids = sorted(state_unions)
    tree = STRtree([state_unions[state] for state in state_ids])
    layers = {key: [] for key in ("outlines", "coast", "dividers")}
    checks = {}
    for state in state_ids:
        if states is not None and state not in states:
            continue
        plan = plans[state]
        near = [state_ids[int(value)] for value in tree.query(state_unions[state], predicate="dwithin", distance=border_band) if state_ids[int(value)] != state]
        document = {"type": "FeatureCollection", "features": by_state[state], "metadata": {"planId": plan["id"], "stateFips": state, "coordinateFrame": plan["coordinateFrame"]}}
        state_started = time.perf_counter()
        output, audit = simplify_state(document, plan, [state_unions[n] for n in near], tolerance=tolerance, border_band=border_band)
        coast, dividers, mesh = boundary_layers(output, plan["id"])
        coast, shoreline = classify_coast(coast)
        for key, value in (("outlines", output), ("coast", coast), ("dividers", dividers)):
            layers[key].extend(annotated_features(value, plan))
        audit.update({"neighborStateFips": near, "mesh": mesh, "shorelines": shoreline,
                      "runtimeSeconds": time.perf_counter() - state_started})
        checks[plan["id"]] = audit
        print(f"National {house_size}/{state}: {audit['inputPoints']} -> {audit['outputPoints']} points; retained={audit['retainedOriginal']}; {audit['runtimeSeconds']:.2f}s", flush=True)
    builder = BundleBuilder(root, cache_root=cache)
    plan_ids = [p for p in original["planIds"] if states is None or manifest["plans"][p]["stateFips"] in states]
    record = {"houseSize": house_size, "planIds": plan_ids}
    for key, features in layers.items():
        record[key] = builder.generated({"type": "FeatureCollection", "features": features, "metadata": {
            "houseSize": house_size, "planIds": plan_ids, "purpose": "national-only display", "sourceOutlinesSha256": original["outlines"]["sha256"],
            "coordinateFrames": {state: plans[state]["coordinateFrame"] for state in state_ids if states is None or state in states},
            **({"shorelineClassification": "top-level-containment-v1"} if key == "coast" else {})}}, f"national-land-{house_size}-{key}.geojson")
    # Exact old refs preserve every coordinate, block/part path and policy owner.
    for key in ("connections", "recordedConnections"):
        read_reference(root, cache, original[key], index["assets"])
        record[key] = deepcopy(original[key])
    input_bytes = sum(original[k]["gzipBytes"] for k in ("outlines", "coast", "dividers"))
    if states is not None:
        input_bytes = 0
        for key in ("outlines", "coast", "dividers"):
            document = read_reference(root, cache, original[key], index["assets"])
            subset = {**document, "features": [f for f in document["features"] if f["properties"]["state_fips"] in states]}
            input_bytes += len(gzip.compress(encoded(subset), compresslevel=6, mtime=0))
    metrics = {"inputGzipBytes": input_bytes,
               "gzipComparisonScope": "Selected state features re-encoded with original metadata" if states else "Complete anchor payloads",
               "outputGzipBytes": sum(record[k]["gzipBytes"] for k in ("outlines", "coast", "dividers")),
               "inputPoints": sum(c["inputPoints"] for c in checks.values()), "outputPoints": sum(c["outputPoints"] for c in checks.values()),
               "retainedStates": [p for p, c in checks.items() if c["retainedOriginal"]], "checks": checks,
               "runtimeSeconds": time.perf_counter() - started, "sourceRefs": deepcopy(original)}
    return record, builder.assets, metrics


def build(root: Path, cache: Path, *, house_sizes: list[int] | None = None, states: set[str] | None = None,
          tolerance: float = DEFAULT_TOLERANCE, border_band: float = DEFAULT_BORDER_BAND, publish: bool = False) -> dict:
    root, cache = root.resolve(), cache.resolve()
    started = time.perf_counter()
    index_path, manifest_path = safe_path(root, OUTPUT / "server-index.json"), safe_path(root, OUTPUT / "manifest.json")
    index_raw = index_path.read_bytes()
    index = json.loads(index_raw)
    manifest_raw = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(manifest_raw)
    validate_anchors(manifest)
    houses = house_sizes or manifest["houseSizes"]
    if not houses or len(set(houses)) != len(houses) or any(size not in manifest["houseSizes"] for size in houses):
        raise ValueError("Select approved House anchors only")
    complete = states is None and set(houses) == set(manifest["houseSizes"])
    if publish and not complete:
        raise ValueError("Only the complete four-anchor national display may be published")
    hashes = {name: file_digest(ROOT / name) for name in RUNTIME_FILES}
    anchors, additions, metrics = {}, {}, {}
    for house in houses:
        record, assets, audit = build_anchor(root, cache, manifest, index, house, states, tolerance, border_band)
        anchors[str(house)], metrics[str(house)] = record, audit
        merge_assets(additions, assets)
    validate_assets(root, cache, additions)
    if file_digest(index_path) != digest(index_raw) or file_digest(manifest_path) != digest(manifest_raw):
        raise ValueError("Live metadata changed during national preparation")
    if {name: file_digest(ROOT / name) for name in RUNTIME_FILES} != hashes:
        raise ValueError("National runtime changed during preparation")
    report = {"schemaVersion": 1, "status": "complete" if complete else "pilot", "published": publish,
              "baseManifestSha256": digest(manifest_raw), "baseIndexSha256": digest(index_raw),
              "catalogSha256": index["catalogSha256"], "runtimeHashes": hashes, "houseSizes": houses,
              "states": sorted(states) if states is not None else None, "toleranceDegrees": tolerance,
              "borderBandDegrees": border_band, "anchors": anchors, "assets": additions, "metrics": metrics,
              "savedPlansModified": 0, "solverRuns": 0, "stateViewsModified": 0,
              "connectionsReusedExactly": True, "runtimeSeconds": time.perf_counter() - started}
    report_name = "publication.json" if publish else "prepared-" + "-".join(map(str, houses)) + ("-" + "-".join(sorted(states)) if states else "") + ".json"
    report_path = NAMESPACE / report_name
    if not publish:
        old_report = safe_path(root, report_path)
        if old_report.exists():
            previous = old_report.read_bytes()
            archived = safe_path(root, NAMESPACE / "pilot-history" / f"{digest(previous)}.json")
            archived.parent.mkdir(parents=True, exist_ok=True)
            if not archived.exists():
                archived.write_bytes(previous)
        atomic_json(safe_path(root, report_path), report)
        return report
    return publish_prepared(root, cache, report)


def publish_prepared(root: Path, cache: Path, prepared: dict) -> dict:
    """Publish a validated complete prepared result without repeating geometry."""
    root, cache = root.resolve(), cache.resolve()
    started = time.perf_counter()
    report = deepcopy(prepared)
    index_path, manifest_path = safe_path(root, OUTPUT / "server-index.json"), safe_path(root, OUTPUT / "manifest.json")
    index_raw = index_path.read_bytes()
    index = json.loads(index_raw)
    manifest_raw = read_pinned(root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(manifest_raw)
    validate_anchors(manifest)
    if (report.get("status") != "complete" or report.get("states") is not None
            or set(report.get("houseSizes", [])) != set(manifest["houseSizes"])):
        raise ValueError("Prepared publication requires all four complete anchors")
    if (report.get("baseManifestSha256") != digest(manifest_raw) or report.get("baseIndexSha256") != digest(index_raw)
            or report.get("catalogSha256") != index["catalogSha256"]):
        raise ValueError("Prepared national display has stale base metadata")
    hashes = {name: file_digest(ROOT / name) for name in RUNTIME_FILES}
    if report.get("runtimeHashes") != hashes:
        raise ValueError("Prepared national runtime differs")
    anchors, additions = report["anchors"], report["assets"]
    if set(anchors) != {str(size) for size in manifest["houseSizes"]}:
        raise ValueError("Prepared national anchors differ")
    expected_assets = set()
    combined = dict(index["assets"])
    merge_assets(combined, additions)
    for size, anchor in anchors.items():
        source = manifest["landAnchors"][size]
        if (anchor["planIds"] != source["planIds"] or anchor["houseSize"] != source["houseSize"]
                or report["metrics"][size]["sourceRefs"] != source):
            raise ValueError("Prepared national membership or source identity differs")
        for key in ("connections", "recordedConnections"):
            if anchor[key] != source[key]:
                raise ValueError("Prepared national connections changed")
            read_reference(root, cache, source[key], index["assets"])
        for key in ("outlines", "coast", "dividers"):
            expected_assets.add(anchor[key]["url"].removeprefix("/api/district-plans/"))
            document = read_reference(root, cache, anchor[key], combined)
            if document["metadata"].get("planIds") != source["planIds"]:
                raise ValueError("Prepared national asset membership differs")
        before = read_reference(root, cache, source["outlines"], index["assets"])
        after = read_reference(root, cache, anchor["outlines"], combined)
        if [f["properties"] for f in before["features"]] != [f["properties"] for f in after["features"]]:
            raise ValueError("Prepared national district properties changed")
        for plan_id in source["planIds"]:
            plan = manifest["plans"][plan_id]
            original_features = [f for f in before["features"] if f["properties"]["state_fips"] == plan["stateFips"]]
            original_geometries = [shape(f["geometry"]) for f in original_features]
            features = [f for f in after["features"] if f["properties"]["state_fips"] == plan["stateFips"]]
            validate_collection({"type": "FeatureCollection", "features": features}, plan)
            geometries = [shape(f["geometry"]) for f in features]
            check = report["metrics"][size]["checks"][plan_id]
            observed = [list(topology(g)) for g in geometries]
            source_topology = [list(topology(g)) for g in original_geometries]
            source_valid = bool(coverage_is_valid(original_geometries))
            output_valid = bool(coverage_is_valid(geometries))
            if (source_topology != [list(v) for v in check["inputTopology"]]
                    or observed != source_topology
                    or observed != [list(v) for v in check["outputTopology"]]
                    or not check["protectedExteriorEdgesUnchanged"]
                    or check["boundaryErrorUpperBoundDegrees"] > MAX_BOUNDARY_ERROR
                    or check["inputCoverageValid"] != source_valid or check["outputCoverageValid"] != output_valid
                    or (source_valid and not output_valid)
                    or (not source_valid and any(not a.equals_exact(b, 0) for a, b in zip(original_geometries, geometries)))):
                raise ValueError("Prepared national topology or error audit differs")
    if set(additions) != expected_assets:
        raise ValueError("Prepared national asset index contains unexpected additions")
    validate_assets(root, cache, additions)
    if file_digest(index_path) != digest(index_raw) or file_digest(manifest_path) != digest(manifest_raw):
        raise ValueError("Live metadata changed during prepared verification")
    updated = deepcopy(manifest)
    updated["nationalLandAnchors"] = anchors
    if {k: v for k, v in updated.items() if k != "nationalLandAnchors"} != {k: v for k, v in manifest.items() if k != "nationalLandAnchors"}:
        raise ValueError("National publication changed existing manifest fields")
    backup = safe_path(root, NAMESPACE / "publication-history")
    backup.mkdir(parents=True, exist_ok=True)
    for name, raw in (("manifest", manifest_raw), ("server-index", index_raw)):
        path = backup / f"{name}-{digest(raw)}.json"
        if path.exists() and file_digest(path) != digest(raw):
            raise ValueError("National publication backup conflicts")
        if not path.exists():
            path.write_bytes(raw)
    report["published"] = True
    report["publicationSeconds"] = time.perf_counter() - started
    report_path = NAMESPACE / "publication.json"
    assets = dict(index["assets"])
    merge_assets(assets, additions)
    updated_index = {**index, "assets": assets, "manifestSha256": digest(encoded(updated)),
                     "nationalLandOverviewProvenance": {"reportPath": report_path.as_posix(), "reportSha256": digest(encoded(report))}}
    atomic_json(safe_path(root, report_path), report)
    atomic_json(manifest_path, updated)
    atomic_json(index_path, updated_index)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--house-sizes", nargs="+", type=int)
    parser.add_argument("--states", nargs="+", help="Read-only publication pilot subset; all neighbors still supply protected borders")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--border-band", type=float, default=DEFAULT_BORDER_BAND)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--publish-prepared", type=Path, help="Verify and publish an existing complete prepared report without rebuilding geometry")
    args = parser.parse_args()
    if args.publish_prepared:
        if args.publish or args.house_sizes or args.states:
            parser.error("--publish-prepared cannot be combined with generation options")
        result = publish_prepared(args.bundle_root, args.cache_root, json.loads(args.publish_prepared.read_bytes()))
    else:
        result = build(args.bundle_root, args.cache_root, house_sizes=args.house_sizes, states=set(args.states) if args.states else None,
                       tolerance=args.tolerance, border_band=args.border_band, publish=args.publish)
    print(json.dumps({"status": result["status"], "runtimeSeconds": result["runtimeSeconds"],
        "metrics": {size: {k: v for k, v in data.items() if k not in ("checks", "sourceRefs")} for size, data in result["metrics"].items()}}))


if __name__ == "__main__":
    main()
