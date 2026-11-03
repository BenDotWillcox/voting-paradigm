"""Publish a Michigan-only display of the saved plans with water-only blocks hidden.

This is a rendering transformation, not a new districting policy. ALAND20 == 0
blocks are removed from the unsimplified display footprint; their assignments
and residents remain in every statistic. Mixed land/water blocks remain. Dashed
connections illustrate actual shared-edge paths through hidden water blocks.
No nearest-island bridges, coastline snapping, solver, or source writes occur.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from contextlib import contextmanager
from copy import deepcopy
import gzip
import hashlib
import inspect
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any
from zipfile import ZipFile

import numpy as np
import shapefile
from shapely import coverage_is_valid, coverage_simplify, union_all
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from scripts.build_block_plan_bundle import (
    BundleBuilder, CATALOG, OUTPUT, digest, encoded, read_pinned, resource_path,
    safe_path, validate_catalog,
)
from scripts.build_block_state_outlines import read_full_outlines

METHOD = "Hide source ALAND20=0 blocks; retain mixed land/water blocks and all saved populations."


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2 ** 20), b""):
            result.update(chunk)
    return result.hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read_graph(path: Path, identity: dict, geoids: list[str]) -> tuple[tuple[tuple[int, ...], ...], dict]:
    """Read the original immutable CSR cache and validate its exact payload.

    We intentionally do not import the old graph builder: a display build must
    never regenerate a graph or change a historical cache on a version mismatch.
    """
    if identity.get("ordered_geoids_sha256") != digest(canonical(geoids)):
        raise ValueError("Graph order differs from source DBF order")
    if identity.get("node_count") != len(geoids):
        raise ValueError("Graph node count differs from source DBF")
    with np.load(path, allow_pickle=False) as archive:
        if sorted(archive.files) != ["manifest", "neighbors", "offsets"]:
            raise ValueError("Unexpected graph archive members")
        offsets, neighbors, payload = archive["offsets"], archive["neighbors"], archive["manifest"]
    if payload.dtype != np.dtype("uint8") or payload.ndim != 1:
        raise ValueError("Invalid graph manifest encoding")
    manifest = json.loads(payload.tobytes())
    if manifest.get("identity") != identity:
        raise ValueError("Graph identity differs from pinned benchmark")
    meta = manifest["graph_metadata"]
    checksum = hashlib.sha256()
    for value in (offsets.tobytes(), neighbors.tobytes(), canonical(meta)):
        checksum.update(len(value).to_bytes(8, "little"))
        checksum.update(value)
    if checksum.hexdigest() != manifest["payload_sha256"]:
        raise ValueError("Graph payload hash mismatch")
    n = len(geoids)
    if offsets.dtype != np.dtype("<i8") or neighbors.dtype != np.dtype("<i8") or offsets.shape != (n + 1,) or neighbors.ndim != 1:
        raise ValueError("Invalid graph CSR shape or dtype")
    if offsets[0] != 0 or offsets[-1] != len(neighbors) or np.any(np.diff(offsets) < 0) or np.any(neighbors < 0) or np.any(neighbors >= n):
        raise ValueError("Invalid graph CSR offsets or indices")
    adjacency = tuple(tuple(int(v) for v in neighbors[offsets[i]:offsets[i + 1]]) for i in range(n))
    for node, row in enumerate(adjacency):
        if node in row or any(a >= b for a, b in zip(row, row[1:])):
            raise ValueError("Graph rows must be sorted, unique and omit self loops")
        for other in row:
            reverse = adjacency[other]
            index = bisect_left(reverse, node)
            if index == len(reverse) or reverse[index] != node:
                raise ValueError("Graph is not symmetric")
    if meta.get("node_count") != n or meta.get("edge_count") != len(neighbors) // 2 or len(neighbors) % 2 or meta.get("de9im_pattern") != "F***1****" or meta.get("all_source_geometries_valid") is not True or meta.get("source_coordinates_modified") is not False:
        raise ValueError("Graph metadata violates original shared-edge rule")
    return adjacency, {"identity": identity, "payload_sha256": checksum.hexdigest(), "file_sha256": file_digest(path)}


@contextmanager
def source_reader(archive_path: Path, source: dict):
    """Verify the archived source, then expose a seekable temporary SHP reader."""
    if archive_path.stat().st_size != source["archive_bytes"] or file_digest(archive_path) != source["archive_sha256"]:
        raise ValueError("Source archive identity mismatch")
    prefix = "tl_2020_26_tabblock20"
    pins = source["extracted_file_sha256"]
    with ZipFile(archive_path) as archive, tempfile.TemporaryFile() as shp:
        checksum = hashlib.sha256()
        with archive.open(prefix + ".shp") as original:
            for chunk in iter(lambda: original.read(2 ** 20), b""):
                checksum.update(chunk)
                shp.write(chunk)
        if checksum.hexdigest() != pins[prefix + ".shp"]:
            raise ValueError("Source SHP identity mismatch")
        pieces = {suffix: archive.read(prefix + suffix) for suffix in (".shx", ".dbf")}
        if any(digest(value) != pins[prefix + suffix] for suffix, value in pieces.items()):
            raise ValueError("Source DBF/SHX identity mismatch")
        shp.seek(0)
        reader = shapefile.Reader(shp=shp, shx=io.BytesIO(pieces[".shx"]), dbf=io.BytesIO(pieces[".dbf"]))
        try:
            yield reader
        finally:
            reader.close()


def source_attributes(reader) -> tuple[list[str], np.ndarray, np.ndarray]:
    geoids, population, land = [], [], []
    for row in reader.iterRecords(fields=["GEOID20", "POP20", "ALAND20"]):
        geoid = row["GEOID20"]
        if len(geoid) != 15 or not geoid.isdigit() or not geoid.startswith("26"):
            raise ValueError("Unexpected Michigan source GEOID")
        geoids.append(geoid)
        population.append(int(row["POP20"]))
        land.append(int(row["ALAND20"]))
    if len(set(geoids)) != len(geoids) or min(population, default=0) < 0 or min(land, default=0) < 0:
        raise ValueError("Duplicate source identity or negative attributes")
    return geoids, np.asarray(population, dtype=np.int64), np.asarray(land, dtype=np.int64)


def checked_assignments(plan: dict, checkpoint: dict, geoids: list[str], population: np.ndarray) -> np.ndarray:
    values = checkpoint["assignments"]
    if set(values) != set(geoids):
        raise ValueError("Saved assignment coverage differs from source")
    if any(type(value) is not int or not 0 <= value < plan["district_count"] for value in values.values()):
        raise ValueError("Invalid saved district assignment")
    assignments = np.asarray([values[geoid] for geoid in geoids], dtype=np.int64)
    counts = np.bincount(assignments, minlength=plan["district_count"]).tolist()
    totals = [int(population[assignments == d].sum()) for d in range(plan["district_count"])]
    if totals != plan["district_populations"] or counts != plan["validation"]["district_block_counts"]:
        raise ValueError("Saved assignments do not reproduce accepted populations/counts")
    return assignments


def polygon_parts(geometry) -> list:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [part for item in geometry.geoms for part in polygon_parts(item)]
    return []


def remove_water_only(collection: dict, water_geometries: dict[int, Any], assignments: np.ndarray) -> tuple[dict, dict[int, list]]:
    result = deepcopy(collection)
    parts = {}
    for feature in result["features"]:
        district = feature["properties"]["district_id"]
        full = shape(feature["geometry"])
        if not full.is_valid:
            raise ValueError("Pinned full district geometry is invalid")
        water = [geometry for index, geometry in water_geometries.items() if assignments[index] == district]
        display = full.difference(union_all(water)) if water else full
        # Overlay can include line-only remnants. They are not land areas and
        # are excluded without applying an area threshold to genuine islands.
        pieces = polygon_parts(display)
        display = union_all(pieces)
        if not display.is_valid:
            raise ValueError("Water removal produced invalid geometry")
        pieces = polygon_parts(display)
        pieces.sort(key=lambda p: (-p.area, p.bounds, p.wkb))
        parts[district] = pieces
        feature["geometry"] = mapping(display) if pieces else None
        # Population, block_count and every deviation remain from accepted plan.
    result["metadata"] = {"purpose": "display-only", "method": METHOD, "population_basis": "all saved assigned blocks, including hidden zero-land blocks"}
    return result, parts


def simplify_display(collection: dict, tolerance: float, *, full_collection: dict | None = None) -> dict:
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Display tolerance must be finite and nonnegative")
    result = deepcopy(collection)
    features = [f for f in result["features"] if f["geometry"] is not None]
    geometries = [shape(f["geometry"]) for f in features]
    ghosts = []
    land_only_valid = bool(coverage_is_valid(geometries)) if geometries else True
    if not land_only_valid:
        if full_collection is None:
            raise ValueError("Water-removed district coverage needs the complete original partition")
        originals = {f["properties"]["district_id"]: shape(f["geometry"]) for f in full_collection["features"]}
        # Removing water can expose a legitimate shell/hole point junction
        # where another district also touches. GEOS's land-only coverage check
        # rejects that representation. Restore omitted water as temporary faces,
        # verify the complete partition, and simplify all its shared edges once.
        # No coordinate snapping or movement repairs are used.
        for feature, land_geometry in zip(features, geometries):
            original = originals[feature["properties"]["district_id"]]
            if not original.covers(land_geometry):
                raise ValueError("Land display extends outside its original district")
            water_faces = polygon_parts(original.difference(land_geometry))
            if not original.equals(union_all([land_geometry, *water_faces])):
                raise ValueError("Land and omitted water do not reconstruct the original district")
            ghosts.extend(water_faces)
    complete = [*geometries, *ghosts]
    if any(geometry.is_empty or not geometry.is_valid for geometry in complete):
        raise ValueError("Complete display partition has an invalid face")
    if complete and not coverage_is_valid(complete):
        raise ValueError("Complete land/water display partition is invalid")
    simplified_complete = coverage_simplify(complete, tolerance) if complete else []
    if any(geometry.is_empty or not geometry.is_valid for geometry in simplified_complete):
        raise ValueError("Simplified complete display partition has an invalid face")
    simplified = simplified_complete[:len(geometries)]
    for feature, geometry, original in zip(features, simplified, geometries):
        if geometry.is_empty or not geometry.is_valid or len(polygon_parts(geometry)) != len(polygon_parts(original)):
            raise ValueError("Display simplification changed island presence or validity")
        if sum(len(p.interiors) for p in polygon_parts(geometry)) != sum(len(p.interiors) for p in polygon_parts(original)):
            raise ValueError("Display simplification changed inland water hole presence")
        feature["geometry"] = mapping(geometry)
    if len(simplified_complete) and not coverage_is_valid(simplified_complete):
        raise ValueError("Simplified complete display partition is invalid")
    result["metadata"]["simplification_tolerance_degrees"] = tolerance
    if ghosts:
        result["metadata"]["coverage_certificate"] = {
            "basis": "Matched complete partition of visible land and omitted zero-land water faces",
            "land_only_input_coverage_valid": land_only_valid,
            "joint_input_coverage_valid": True,
            "joint_simplified_coverage_valid": True,
            "land_only_simplified_coverage_valid": bool(coverage_is_valid(simplified)),
            "temporary_water_faces": len(ghosts),
            "exact_original_district_reconstruction": True,
            "land_components_and_water_holes_preserved": True,
            "coordinate_snapping_applied": False,
        }
    return result


def staged_plan(bundle_root: Path, identity: dict, create) -> tuple[dict, dict, list, dict, bool]:
    """Reuse only pinned exact display/proof work, never a partially built map.

    The stage is private build data, not an accepted plan or a browser asset.
    Changing the source, assignments, source full outlines, graph payload, path
    implementation or exact-removal implementation gives a new cache key.
    """
    directory = safe_path(bundle_root, Path(".cache/block-main-port/michigan-land-staging") / digest(canonical(identity)))
    manifest_path = directory / "manifest.json"
    hit = manifest_path.exists()
    if hit:
        manifest = json.loads(manifest_path.read_bytes())
        compressed = (directory / "prepared.json.gz").read_bytes()
        if manifest["identity"] != identity or digest(compressed) != manifest["gzip_sha256"]:
            raise ValueError("Prepared Michigan geometry cache identity changed")
        raw = gzip.decompress(compressed)
        if digest(raw) != manifest["raw_sha256"]:
            raise ValueError("Prepared Michigan geometry cache payload changed")
        prepared = json.loads(raw)
    else:
        display, parts, features, audit = create()
        prepared = {"display": display, "features": features, "path_audit": audit}
        raw = encoded(prepared)
        compressed = gzip.compress(raw, compresslevel=6, mtime=0)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "prepared.json.gz").write_bytes(compressed)
        manifest_path.write_bytes(encoded({"identity": identity, "raw_sha256": digest(raw), "gzip_sha256": digest(compressed)}))
    display, features, audit = prepared["display"], prepared["features"], prepared["path_audit"]
    parts = {}
    for feature in display["features"]:
        pieces = polygon_parts(shape(feature["geometry"])) if feature["geometry"] is not None else []
        pieces.sort(key=lambda p: (-p.area, p.bounds, p.wkb))
        parts[feature["properties"]["district_id"]] = pieces
    if not audit["all_components_explained"] or audit["derived_connection_count"] != len(features):
        raise ValueError("Prepared Michigan geometry has an incomplete path audit")
    return display, parts, features, audit, hit


def publish_land_assets(bundle_root: Path, manifest: dict, index: dict, builder: BundleBuilder, displays: dict, provenance: dict) -> None:
    """Extend the bundle without rewriting any accepted plan/catalog/proof."""
    manifest.setdefault("landDisplays", {}).update(displays)
    index["assets"].update(builder.assets)
    index["michiganLandDisplayProvenance"] = provenance
    manifest_bytes = encoded(manifest)
    index["manifestSha256"] = digest(manifest_bytes)
    for relative, data in [(OUTPUT / "manifest.json", manifest_bytes), (OUTPUT / "server-index.json", encoded(index))]:
        path = safe_path(bundle_root, relative)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)


def build_michigan_land_display(source_root: Path, bundle_root: Path, *, cache_root: Path | None = None, state_tolerance: float = 0.0001, national_tolerance: float = 0.002) -> dict:
    from scripts.michigan_water_paths import derive_water_paths
    started = time.perf_counter()
    source_root, bundle_root = source_root.resolve(), bundle_root.resolve()
    cache_root = (cache_root or source_root / ".cache").resolve()
    runtime_code = {path: file_digest(ROOT / path) for path in ("scripts/build_michigan_land_display.py", "scripts/michigan_water_paths.py")}
    history_path = safe_path(bundle_root, OUTPUT / "michigan-land-display-build-history.json")
    history = json.loads(history_path.read_bytes()) if history_path.exists() else None
    catalog_raw = safe_path(source_root, CATALOG).read_bytes()
    catalog = json.loads(catalog_raw)
    validate_catalog(catalog)
    read_pinned(bundle_root, CATALOG, digest(catalog_raw))
    plans = sorted((p for p in catalog["plans"] if p["state_fips"] == "26"), key=lambda p: p["district_count"])
    if [p["district_count"] for p in plans] != [13, 18, 21, 30] or any(p["connectivity_policy"] != "strict_shared_edge" or p["validation"]["recorded_links"] for p in plans):
        raise ValueError("Unexpected accepted Michigan plans or recorded connections")
    index_path = safe_path(bundle_root, OUTPUT / "server-index.json")
    initial_index_raw = index_path.read_bytes()
    index = json.loads(initial_index_raw)
    manifest = json.loads(read_pinned(bundle_root, OUTPUT / "manifest.json", index["manifestSha256"]))
    if manifest["catalogSha256"] != digest(catalog_raw) or index["catalogSha256"] != digest(catalog_raw):
        raise ValueError("Bundle/catalog identity mismatch")
    source = plans[0]["source"]
    archive_path = safe_path(cache_root, "state-block-benchmark/source/26/tl_2020_26_tabblock20.zip")
    preserved = {safe_path(source_root, CATALOG): digest(catalog_raw), archive_path: source["archive_sha256"]}
    reports, checkpoints, outlines = {}, {}, {}
    for plan in plans:
        for item in plan["evidence"]:
            path = resource_path(source_root, item["path"], cache_root)
            if file_digest(path) != item["sha256"]:
                raise ValueError(f"Historical evidence identity mismatch: {item['path']}")
            preserved[path] = item["sha256"]
        reports[plan["plan_id"]] = json.loads(read_pinned(source_root, plan["report_path"], plan["report_sha256"], cache_root))
        checkpoints[plan["plan_id"]] = json.loads(read_pinned(source_root, Path(plan["candidate_dir"]) / "solver-result.json", plan["validation"]["checkpoint_sha256"], cache_root))
        outlines[plan["plan_id"]], provenance = read_full_outlines(source_root, plan, cache_root=cache_root)
        preserved[resource_path(source_root, provenance["path"], cache_root)] = provenance["gzip_sha256"]
        if plan["source"]["archive_sha256"] != source["archive_sha256"]:
            raise ValueError("Michigan anchors use different source archives")
    graph_record = reports[plans[0]["plan_id"]]["graph_cache"]
    graph_path = safe_path(cache_root, f"state-block-benchmark/graph-cache/26/shared-edge-{graph_record['key']}.npz")
    builder, displays, audits = BundleBuilder(bundle_root), {}, {}
    with source_reader(archive_path, source) as reader:
        geoids, population, land = source_attributes(reader)
        adjacency, graph_audit = read_graph(graph_path, graph_record["identity"], geoids)
        preserved[graph_path] = graph_audit["file_sha256"]
        if len(geoids) != plans[0]["block_count"] or int(population.sum()) != plans[0]["resident_population"]:
            raise ValueError("Source attributes differ from accepted Michigan totals")
        geometry_cache = {}
        def block_geometry(index: int):
            if index not in geometry_cache:
                geometry = shape(reader.shape(index).__geo_interface__)
                if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                    raise ValueError(f"Invalid original source block {geoids[index]}")
                geometry_cache[index] = geometry
            return geometry_cache[index]
        water_geometries = {int(i): block_geometry(int(i)) for i in np.flatnonzero(land == 0)}
        if any(g.geom_type != "Polygon" for g in water_geometries.values()):
            raise ValueError("Michigan water-only path interior requires single source Polygon")
        shared_outline = None
        shared_union = None
        for plan in plans:
            plan_id = plan["plan_id"]
            print(f"Preparing Michigan {plan_id}: source water removal and path proof", flush=True)
            assignments = checked_assignments(plan, checkpoints[plan_id], geoids, population)
            def prepare_exact():
                display, parts = remove_water_only(outlines[plan_id], water_geometries, assignments)
                print(f"Removed zero-land footprint for {plan_id}; checking exact source paths", flush=True)
                features, path_audit = derive_water_paths(parts, water_geometries, block_geometry, geoids, land, assignments, adjacency)
                if not path_audit["all_components_explained"]:
                    raise ValueError(f"Display components lack verified source-water paths: {plan_id}: {path_audit}")
                return display, parts, features, path_audit
            stage_identity = {"version": "mi-zero-land-exact-v1", "source_sha256": source["archive_sha256"], "assignments_sha256": plan["validation"]["checkpoint_sha256"], "full_outline_sha256": digest(encoded(outlines[plan_id])), "graph_payload_sha256": graph_audit["payload_sha256"], "path_code_sha256": runtime_code["scripts/michigan_water_paths.py"], "removal_code_sha256": digest((inspect.getsource(remove_water_only) + inspect.getsource(polygon_parts)).encode())}
            display, parts, features, path_audit, stage_hit = staged_plan(bundle_root, stage_identity, prepare_exact)
            for feature in features:
                feature["properties"]["plan_id"] = plan_id
            union = union_all([piece for group in parts.values() for piece in group])
            if shared_union is not None and not union.equals(shared_union):
                if union.symmetric_difference(shared_union).area > 1e-12:
                    raise ValueError("Water-removed Michigan coverage differs across anchors")
            if shared_outline is None:
                shared_union = union
                state_outline = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"state_fips": "26", "state_name": "Michigan", "coordinate_frame": "source", "display_mode": "land-focused"}, "geometry": mapping(union.simplify(national_tolerance, preserve_topology=True))}], "metadata": {"method": METHOD, "catalog_sha256": digest(catalog_raw)}}
                shared_outline = builder.generated(state_outline, "michigan-land-state-outline.geojson")
            summary = {"derivedConnectionCount": len(features), "zeroLandPopulation": int(population[land == 0].sum()), "zeroLandBlockCount": int((land == 0).sum()), "method": METHOD}
            connections = {"type": "FeatureCollection", "features": features, "metadata": {"planId": plan_id, "kind": "derived-water-adjacency", "method": "Schematic indicators of verified same-district shared-edge source-block paths through hidden zero-land blocks; not added policy edges or travel routes.", "recordedConnectionCount": 0}}
            state_display = simplify_display(display, state_tolerance, full_collection=outlines[plan_id])
            national_display = simplify_display(display, national_tolerance, full_collection=outlines[plan_id])
            displays[plan_id] = {"planId": plan_id, "state": builder.generated(state_display, f"{plan_id}-land-state.geojson"), "national": builder.generated(national_display, f"{plan_id}-land-national.geojson"), "connections": builder.generated(connections, f"{plan_id}-derived-water-connections.geojson"), "stateOutline": shared_outline, "summary": summary}
            display_audit = {}
            for level, payload in (("state", state_display), ("national", national_display)):
                display_audit[level] = {"coverage": payload["metadata"].get("coverage_certificate", {"basis": "Matched land-only coverage", "passed": True}), "components_and_holes_preserved": True, "exact_input_area_source_degrees_squared": float(union.area), "simplified_area_source_degrees_squared": sum(shape(f["geometry"]).area for f in payload["features"] if f["geometry"] is not None)}
            audits[plan_id] = {"summary": summary, "path_audit": path_audit, "prepared_cache_hit": stage_hit, "prepared_cache_identity": stage_identity, "display_simplification": display_audit, "display_parts_by_district": {str(d): len(p) for d, p in parts.items()}, "district_populations": plan["district_populations"], "district_block_counts": plan["validation"]["district_block_counts"], "saved_report_sha256": plan["report_sha256"], "saved_assignments_sha256": plan["validation"]["checkpoint_sha256"], "display_assets": displays[plan_id]}
            print(f"Prepared {plan_id}: {len(features)} derived connections; saved population {sum(plan['district_populations']):,} retained", flush=True)
    for path, before in preserved.items():
        if file_digest(path) != before:
            raise ValueError(f"Original evidence changed during display build: {path}")
    for path, before in runtime_code.items():
        if file_digest(ROOT / path) != before:
            raise ValueError(f"Display runtime code changed during build: {path}")
    replay = None
    if history is not None:
        reference = history["reference_assets"]
        new_hashes = {entry["rawSha256"] for entry in builder.assets.values()}
        if not reference or any(item["raw_sha256"] not in new_hashes or file_digest(safe_path(bundle_root, item["path"])) != item["gzip_sha256"] for item in reference):
            raise ValueError("Optimized endpoint checks did not reproduce preserved display assets")
        replay = {"history_sha256": file_digest(history_path), "reference_plan": history["completed_reference_plan"], "identical_asset_count": len(reference), "stronger_endpoint_containment_check_passed": True}
    if index_path.read_bytes() != initial_index_raw:
        raise ValueError("Another process updated the bundle during this build")
    report = {"schema": 1, "status": "complete", "method": METHOD, "state_fips": "26", "catalog_sha256": digest(catalog_raw), "source_archive_sha256": source["archive_sha256"], "runtime_code_sha256": runtime_code, "optimized_replay": replay, "graph": graph_audit, "plans": audits, "historical_files_verified_unchanged": len(preserved), "preserved_files": [{"path": str(path), "sha256": value} for path, value in preserved.items()], "source_files_modified": 0, "saved_assignments_modified": 0, "display_state_tolerance_degrees": state_tolerance, "display_national_tolerance_degrees": national_tolerance, "runtime_seconds": time.perf_counter() - started}
    report_path = safe_path(bundle_root, OUTPUT / "michigan-land-display-report.json")
    report_path.write_bytes(encoded(report))
    publish_land_assets(bundle_root, manifest, index, builder, displays, {"reportPath": (OUTPUT / "michigan-land-display-report.json").as_posix(), "reportSha256": digest(encoded(report)), "catalogSha256": digest(catalog_raw), "sourceArchiveSha256": source["archive_sha256"]})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, default=os.environ.get("BLOCK_PLAN_CACHE_ROOT"))
    parser.add_argument("--state-tolerance", type=float, default=0.0001)
    parser.add_argument("--national-tolerance", type=float, default=0.002)
    args = parser.parse_args()
    report = build_michigan_land_display(args.source_root, args.bundle_root, cache_root=args.cache_root, state_tolerance=args.state_tolerance, national_tolerance=args.national_tolerance)
    print(json.dumps({"status": report["status"], "runtime_seconds": report["runtime_seconds"], "historical_files_verified_unchanged": report["historical_files_verified_unchanged"], "connections": {p: v["summary"]["derivedConnectionCount"] for p, v in report["plans"].items()}}, indent=2))


if __name__ == "__main__":
    main()
