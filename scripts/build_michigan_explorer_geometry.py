"""Build display-only Michigan overview fills and actual district-divider meshes.

The accepted full census partition remains authoritative. Small enclosed water
gaps are hidden in the overview only, using that partition's existing ownership.
Open channels, holes containing land islands, and larger lakes are not filled.
No solver, source writes, buffering, snapping or new connectivity edges are used.
This module does not publish the shared app manifest or server index.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path
import sys
import time

from shapely import STRtree, line_merge, union_all
from shapely.geometry import Polygon, mapping, shape
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.build_block_plan_bundle import (
    BundleBuilder, CATALOG, OUTPUT, digest, encoded, read_pinned, resource_path,
    safe_path, validate_catalog,
)
from scripts.build_block_state_outlines import read_full_outlines
from scripts.build_michigan_land_display import canonical, file_digest, polygon_parts, simplify_display

REPORT = OUTPUT / "michigan-explorer-geometry-report.json"
MAX_OVERVIEW_HOLE_AREA_M2 = 4_000_000.0
OVERVIEW_TOLERANCE = 0.002
# A fixed local equal-area approximation is sufficient for a display threshold.
# It is not a geodesic measurement or an administrative land-area statistic.
AREA_SCALE_M2 = 111_320.0 ** 2 * math.cos(math.radians(45.0))


def geometries_by_district(collection: dict) -> dict:
    result = {}
    for feature in collection["features"]:
        district = feature["properties"]["district_id"]
        if district in result:
            raise ValueError("Duplicate district in display collection")
        geometry = shape(feature["geometry"]) if feature["geometry"] is not None else Polygon()
        if not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Invalid display district geometry")
        result[district] = geometry
    return result


def clean_overview_partition(
    exact_land: dict,
    full_census: dict,
    max_hole_area_m2: float = MAX_OVERVIEW_HOLE_AREA_M2,
    *,
    area_scale_m2: float = AREA_SCALE_M2,
) -> tuple[dict, dict]:
    """Fill selected *state* water holes, preserving ownership and land islands.

    Filling individual district holes would paint over another district's land
    enclave. Instead select holes in the dissolved state mask, reject every hole
    with land inside it, and assign only the selected water through the saved
    full census partition. Only enclosed holes qualify; coastal inlets never do.
    """
    if not math.isfinite(max_hole_area_m2) or max_hole_area_m2 < 0:
        raise ValueError("Invalid overview water-hole threshold")
    if not math.isfinite(area_scale_m2) or area_scale_m2 <= 0:
        raise ValueError("Invalid overview area scale")
    land = geometries_by_district(exact_land)
    full = geometries_by_district(full_census)
    if set(land) != set(full):
        raise ValueError("Land and census district identities differ")
    state_land = union_all(list(land.values()))
    full_state = union_all(list(full.values()))
    if not state_land.is_valid or not full_state.is_valid:
        raise ValueError("Invalid input state partition")
    for district, geometry in land.items():
        if not full[district].covers(geometry):
            raise ValueError("Exact land extends beyond the accepted district")
    selected = []
    larger = islands = uncovered = 0
    state_parts = polygon_parts(state_land)
    state_parts_tree = STRtree(state_parts)
    state_part_points = [part.representative_point() for part in state_parts]
    full_state_prepared = prep(full_state)
    for part_index, part in enumerate(state_parts):
        for ring in part.interiors:
            hole = Polygon(ring)
            if hole.area * area_scale_m2 > max_hole_area_m2:
                larger += 1
            # In a valid dissolved MultiPolygon, land inside one part's hole
            # can only be another component. Checking its interior point avoids
            # overlaying every hole against the whole 900k-vertex state again.
            elif any(int(other) != part_index and hole.contains(state_part_points[int(other)])
                     for other in state_parts_tree.query(hole)):
                islands += 1
            elif not full_state_prepared.covers(hole):
                uncovered += 1
            else:
                selected.append(hole)
    additions = union_all(selected) if selected else Polygon()
    mask = union_all([state_land, additions])
    if not mask.is_valid or not mask.covers(state_land):
        raise ValueError("Clean overview mask removed original land")
    if len(polygon_parts(mask)) != len(polygon_parts(state_land)):
        raise ValueError("Clean overview mask joined or removed a land island")

    result = deepcopy(exact_land)
    output = []
    for feature in result["features"]:
        district = feature["properties"]["district_id"]
        # Work only on the selected enclosed gaps; original exact land is copied.
        restored = full[district].intersection(additions) if selected else Polygon()
        rendered = union_all([land[district], *polygon_parts(restored)])
        if not rendered.is_valid or not rendered.covers(land[district]) or not full[district].covers(rendered):
            raise ValueError("Clean display changed land or accepted district ownership")
        feature["geometry"] = mapping(rendered) if not rendered.is_empty else None
        output.append(rendered)
    output_union = union_all(output)
    if not output_union.equals(mask):
        raise ValueError("Clean overview has uncovered or unexpected areas")
    if abs(sum(value.area for value in output) - output_union.area) > 1e-10:
        raise ValueError("Clean overview districts overlap")
    for i, first in enumerate(output):
        for second in output[i + 1:]:
            if first.intersection(second).area > 0:
                raise ValueError("Clean overview districts overlap")
    audit = {
        "max_enclosed_water_hole_area_m2": max_hole_area_m2,
        "area_method": "Source longitude/latitude area scaled by 111320^2*cos(45 degrees); approximate display threshold only",
        "suppressed_water_holes": len(selected),
        "suppressed_water_area_m2_approx": additions.area * area_scale_m2,
        "larger_holes_retained": larger,
        "holes_with_land_islands_retained": islands,
        "holes_outside_full_census_coverage_retained": uncovered,
        "state_land_components_before": len(polygon_parts(state_land)),
        "state_land_components_after": len(polygon_parts(mask)),
        "open_channels_unchanged": True,
        "all_original_land_retained": True,
        "restored_water_uses_saved_district_ownership": True,
        "overlapping_district_interiors": False,
        "buffering_or_snapping_applied": False,
    }
    result.setdefault("metadata", {}).update({
        "purpose": "display-only", "overview_water_detail": audit,
        "method": "Suppress only small enclosed water holes without land islands; restore display fill using the saved full census district ownership.",
    })
    return result, audit


def line_parts(geometry) -> list:
    if geometry.is_empty:
        return []
    if geometry.geom_type in ("LineString", "LinearRing"):
        return [list(geometry.coords)] if geometry.length > 0 else []
    if geometry.geom_type in ("MultiLineString", "GeometryCollection"):
        return [coords for part in geometry.geoms for coords in line_parts(part)]
    return []


def boundary_layers(collection: dict, plan_id: str) -> tuple[dict, dict, dict]:
    """Shared dividers are bright; every state/water shoreline belongs to coast."""
    districts = geometries_by_district(collection)
    ids = sorted(districts)
    shapes = [districts[d] for d in ids]
    tree = STRtree(shapes)
    features = []
    for index, first in enumerate(shapes):
        for other_index in sorted(int(value) for value in tree.query(first, predicate="intersects")):
            if other_index <= index:
                continue
            second = shapes[other_index]
            if first.intersection(second).area > 0:
                raise ValueError("Cannot derive district dividers from overlapping districts")
            shared = first.boundary.intersection(second.boundary)
            lines = line_parts(line_merge(shared))
            if lines:
                features.append({"type": "Feature", "properties": {
                    "plan_id": plan_id, "district_ids": [ids[index], ids[other_index]], "kind": "shared-district-divider",
                }, "geometry": {"type": "MultiLineString", "coordinates": lines}})
    united = union_all(shapes)
    coast = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {
        "state_fips": "26", "plan_id": plan_id, "kind": "state-and-water-shoreline",
    }, "geometry": {"type": "MultiLineString", "coordinates": line_parts(united.boundary)}}],
        "metadata": {"purpose": "display-only", "planId": plan_id}}
    dividers = {"type": "FeatureCollection", "features": features,
                "metadata": {"purpose": "display-only", "planId": plan_id, "kind": "shared-district-dividers"}}
    return coast, dividers, {"shared_district_pairs": len(features), "coastline_not_in_divider_layer": True}


def read_asset(bundle_root: Path, cache_root: Path, index: dict, asset: dict) -> dict:
    prefix = "/api/district-plans/"
    if not asset["url"].startswith(prefix):
        raise ValueError("Unexpected asset URL")
    entry = index["assets"][asset["url"][len(prefix):]]
    compressed = read_pinned(bundle_root, entry["path"], entry["gzipSha256"], cache_root)
    raw = gzip.decompress(compressed)
    if digest(raw) != asset["sha256"] or digest(raw) != entry["rawSha256"] or len(raw) != asset["bytes"]:
        raise ValueError("Display asset identity mismatch")
    return json.loads(raw)


def read_exact_stage(bundle_root: Path, land_plan_report: dict, fine: dict, full: dict) -> tuple[dict, dict]:
    identity = land_plan_report["prepared_cache_identity"]
    directory = safe_path(bundle_root, Path(".cache/block-main-port/michigan-land-staging") / digest(canonical(identity)))
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest["identity"] != identity:
        raise ValueError("Exact Michigan stage identity differs from saved display proof")
    compressed = (directory / "prepared.json.gz").read_bytes()
    if digest(compressed) != manifest["gzip_sha256"]:
        raise ValueError("Exact Michigan stage compressed identity changed")
    raw = gzip.decompress(compressed)
    if digest(raw) != manifest["raw_sha256"]:
        raise ValueError("Exact Michigan stage payload changed")
    exact = json.loads(raw)["display"]
    # The private cache alone is not the authority. It must reproduce the pinned
    # accepted fine display exactly under the documented original simplifier.
    replay = simplify_display(exact, 0.0001, full_collection=full)
    if canonical(replay) != canonical(fine):
        raise ValueError("Exact stage did not reproduce the pinned fine display")
    return exact, {"identity": identity, "raw_sha256": manifest["raw_sha256"], "fine_asset_replayed_exactly": True}


def build_geometry(bundle_root: Path, cache_root: Path) -> dict:
    started = time.perf_counter()
    bundle_root, cache_root = bundle_root.resolve(), cache_root.resolve()
    catalog_raw = safe_path(bundle_root, CATALOG).read_bytes()
    catalog = json.loads(catalog_raw)
    validate_catalog(catalog)
    index_path = safe_path(bundle_root, OUTPUT / "server-index.json")
    manifest_path = safe_path(bundle_root, OUTPUT / "manifest.json")
    index_raw = index_path.read_bytes()
    index = json.loads(index_raw)
    manifest_raw = read_pinned(bundle_root, OUTPUT / "manifest.json", index["manifestSha256"])
    manifest = json.loads(manifest_raw)
    if manifest["catalogSha256"] != digest(catalog_raw) or index["catalogSha256"] != digest(catalog_raw):
        raise ValueError("Geometry build must use the accepted catalog")
    land_provenance = index["michiganLandDisplayProvenance"]
    land_report_path = safe_path(bundle_root, land_provenance["reportPath"])
    land_report_raw = read_pinned(bundle_root, land_provenance["reportPath"], land_provenance["reportSha256"])
    land_report = json.loads(land_report_raw)
    preserved = {safe_path(bundle_root, CATALOG): digest(catalog_raw), index_path: digest(index_raw),
                 manifest_path: digest(manifest_raw), land_report_path: digest(land_report_raw)}
    builder = BundleBuilder(bundle_root, cache_root=cache_root)
    plans = {}
    audits = {}
    selected = sorted((p for p in catalog["plans"] if p["state_fips"] == "26"), key=lambda p: p["district_count"])
    if [p["district_count"] for p in selected] != [13, 18, 21, 30]:
        raise ValueError("Unexpected Michigan district anchors")
    for plan in selected:
        plan_id = plan["plan_id"]
        print(f"Building clean Michigan overview {plan_id}", flush=True)
        full, full_proof = read_full_outlines(bundle_root, plan, cache_root=cache_root)
        preserved[resource_path(bundle_root, full_proof["path"], cache_root)] = full_proof["gzip_sha256"]
        fine_asset = manifest["landDisplays"][plan_id]["state"]
        fine = read_asset(bundle_root, cache_root, index, fine_asset)
        fine_entry = index["assets"][fine_asset["url"].removeprefix("/api/district-plans/")]
        preserved[resource_path(bundle_root, fine_entry["path"], cache_root)] = fine_entry["gzipSha256"]
        exact, stage_proof = read_exact_stage(bundle_root, land_report["plans"][plan_id], fine, full)
        identity = stage_proof["identity"]
        if (identity["assignments_sha256"] != plan["validation"]["checkpoint_sha256"]
                or identity["source_sha256"] != plan["source"]["archive_sha256"]
                or identity["full_outline_sha256"] != digest(encoded(full))):
            raise ValueError("Exact stage provenance differs from accepted plan/source")
        print(f"Replayed {plan_id} fine display; constructing overview mask", flush=True)
        clean, overview_audit = clean_overview_partition(exact, full)
        print(f"Constructed {plan_id} mask; simplifying and extracting divider meshes", flush=True)
        simplified = simplify_display(clean, OVERVIEW_TOLERANCE, full_collection=full)
        simplified["metadata"]["planId"] = plan_id
        coast, dividers, divider_audit = boundary_layers(simplified, plan_id)
        _, detail_dividers, detail_audit = boundary_layers(fine, plan_id)
        if [f["properties"] for f in simplified["features"]] != [f["properties"] for f in exact["features"]]:
            raise ValueError("Overview display changed authoritative district properties")
        if sum(f["properties"]["population"] for f in simplified["features"]) != plan["resident_population"]:
            raise ValueError("Overview display population differs from accepted plan")
        plans[plan_id] = {
            "overview": builder.generated(simplified, f"{plan_id}-explorer-overview.geojson"),
            "coast": builder.generated(coast, f"{plan_id}-explorer-coast.geojson"),
            "dividers": builder.generated(dividers, f"{plan_id}-explorer-dividers.geojson"),
            "detailDividers": builder.generated(detail_dividers, f"{plan_id}-explorer-detail-dividers.geojson"),
        }
        audits[plan_id] = {"overview": overview_audit, "overview_dividers": divider_audit,
                          "detail_dividers": detail_audit, "exact_stage_proof": stage_proof,
                          "joint_simplification": simplified["metadata"].get("coverage_certificate", {"matched_land_coverage_valid": True}),
                          "population": plan["resident_population"], "saved_district_properties_unchanged": True,
                          "full_source": full_proof, "fine_source": fine_asset}
        print(f"Prepared {plan_id}: {overview_audit['suppressed_water_holes']} tiny water holes suppressed", flush=True)
    for path, expected in preserved.items():
        if file_digest(path) != expected:
            raise ValueError(f"Existing evidence changed during geometry preparation: {path}")
    result = {"schemaVersion": 1, "status": "complete", "plans": plans, "assets": builder.assets,
              "audit": {"catalog_sha256": digest(catalog_raw), "plans": audits,
                        "max_overview_hole_area_m2": MAX_OVERVIEW_HOLE_AREA_M2,
                        "simplification_tolerance_degrees": OVERVIEW_TOLERANCE,
                        "preserved_file_count": len(preserved), "saved_plans_modified": 0,
                        "preserved_files": [{"path": str(path), "sha256": value} for path, value in preserved.items()]},
              "runtime_seconds": time.perf_counter() - started}
    safe_path(bundle_root, REPORT).write_bytes(encoded(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", type=Path, default=ROOT)
    parser.add_argument("--cache-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_geometry(args.bundle_root, args.cache_root)
    print(json.dumps({"status": result["status"], "plans": list(result["plans"]), "runtime_seconds": result["runtime_seconds"]}))


if __name__ == "__main__":
    main()
