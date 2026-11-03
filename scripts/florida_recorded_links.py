"""Apply Florida's explicitly authorized, source-pinned water connections.

These are policy edges across offshore census-coverage gaps. Official regional
geography supports the water attribution; no independent global shoreline or
land-mask certificate is claimed. Exact source parts and all physical edges are
checked separately from the added connection, without modifying polygons.
"""
from __future__ import annotations

from collections.abc import Sequence
import copy
import hashlib
import json
import math
from numbers import Integral
from pathlib import Path
import time
from typing import Any

import shapefile
import shapely
from shapely.geometry import LineString, Point, shape

from districting.part_connectivity import PartGraph
from scripts import district_block_island_links as physical_helpers
from scripts.hawaii_population_links import _great_circle_m, select_population_aware_forest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FL_DIAGNOSTIC_DIR = ROOT / ".cache/state-block-benchmark/suite-through-1000/diagnostics/florida"
POLICY = "florida-recorded-water-v1"
SUPPORTED_DISTRICT_COUNTS = (28, 37, 45, 65)
SOURCE_ARCHIVE_SHA256 = "ce5d7a02e47df17dadfa9c889edb6d35a89dfb520b8669bc4d302c2c0e100418"
EXPECTED_COMPONENT_COUNT = 2
PINNED_EVIDENCE_SHA256 = {
    "diagnosis.json": "194944247f3faea9f6fefd02fe90b576bb83a8a0edfc9d50232ac434ddc32e3a",
    "candidate-links.json": "d08f371408f62e756d573b28a11ff1bce8a1c7ecd72fa8498de2268c6b2b736f",
    "geography-context.json": "50b003eb8f380bed1daac314ded547242cdddb000b19a2a8535fdacd598b0e4e",
}
AUTHORIZED_CANDIDATE_IDS = ("fl-candidate-00-01",)
_ENDPOINT_TOLERANCE_DEGREES = 1e-9
_INTERIOR_ROUNDOFF_TOLERANCE_DEGREES = 1e-10


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _read_parts(path: Path, geoids: tuple[str, ...], graph: PartGraph, populations: tuple[int, ...]) -> list[Any]:
    indices = {geoid: index for index, geoid in enumerate(geoids)}
    by_unit: list[list[Any] | None] = [None] * len(geoids)
    with shapefile.Reader(str(path)) as reader:
        for record in reader.iterShapeRecords():
            geoid = str(record.record["GEOID20"])
            if geoid not in indices or by_unit[indices[geoid]] is not None:
                raise ValueError("Source must contain exactly the unique requested Florida GEOIDs.")
            if int(record.record["POP20"]) != populations[indices[geoid]]:
                raise ValueError("Supplied whole-block population differs from the verified source record.")
            geometry = shape(record.shape.__geo_interface__)
            if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError("Florida source parts must be unchanged valid polygons.")
            by_unit[indices[geoid]] = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    if any(parts is None for parts in by_unit):
        raise ValueError("Source is missing requested Florida blocks.")
    parts, owners = [], []
    for unit, unit_parts in enumerate(by_unit):
        assert unit_parts is not None
        parts.extend(unit_parts)
        owners.extend([unit] * len(unit_parts))
    if tuple(owners) != graph.part_to_unit:
        raise ValueError("Part graph ownership/order differs from exact source geometry.")
    return parts


def _validate_endpoint(candidate: dict[str, Any], source_parts: list[Any], graph: PartGraph,
                       geoids: tuple[str, ...], membership: tuple[int, ...]) -> None:
    pair, endpoints = candidate.get("component_ids"), candidate.get("endpoints")
    if (not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]
            or any(isinstance(i, bool) or not isinstance(i, Integral) or not 0 <= i < EXPECTED_COMPONENT_COUNT for i in pair)
            or not isinstance(endpoints, list) or len(endpoints) != 2):
        raise ValueError("Recorded candidate must identify two distinct source components and endpoints.")
    for endpoint, component in zip(endpoints, pair, strict=True):
        node, part_index = endpoint.get("part_node"), endpoint.get("part_index")
        if isinstance(node, bool) or not isinstance(node, Integral) or not 0 <= node < len(source_parts):
            raise ValueError("Invalid recorded endpoint node.")
        unit = graph.part_to_unit[node]
        if (endpoint.get("geoid") != geoids[unit] or isinstance(part_index, bool) or not isinstance(part_index, Integral)
                or not 0 <= part_index < len(graph.unit_to_parts[unit]) or graph.unit_to_parts[unit][part_index] != node
                or membership[node] != component):
            raise ValueError("Recorded endpoint ownership/component differs from source.")
        coordinate = endpoint.get("coordinate")
        if (not isinstance(coordinate, list) or len(coordinate) != 2
                or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in coordinate)):
            raise ValueError("Recorded endpoint coordinates must be finite.")
        if source_parts[node].boundary.distance(Point(coordinate)) > _ENDPOINT_TOLERANCE_DEGREES:
            raise ValueError("Recorded endpoint is not on the unchanged source part boundary.")
    distance = candidate.get("distance_m")
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance <= 0:
        raise ValueError("Recorded candidate requires a positive finite gap distance.")
    if not math.isclose(_great_circle_m(*(e["coordinate"] for e in endpoints)), distance, rel_tol=1e-12, abs_tol=1e-6):
        raise ValueError("Recorded candidate distance differs from its coordinates.")


def _validate_context(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    validation = context.get("water_context_validation", {})
    if (validation.get("source_component_clearance_verified") is not True
            or validation.get("official_regional_geography_reviewed") is not True
            or validation.get("independent_global_land_mask_tested") is not False
            or validation.get("foreign_land_exclave_identified") is not False
            or validation.get("connection_kind") != "proposed recorded-water-connection"):
        raise ValueError("Water attribution must retain its regional-geography basis and untested global land-mask limitation.")
    rows = context.get("links", [])
    surfaces = {row["candidate_id"]: row for row in rows}
    if len(surfaces) != len(rows) or set(surfaces) != set(AUTHORIZED_CANDIDATE_IDS):
        raise ValueError("Geographic attribution must cover exactly the authorized Florida connection.")
    if not context.get("sources") or any(not row.get("summary") for row in rows):
        raise ValueError("The recorded water attribution needs source references and per-link explanation.")
    return surfaces


def build_florida_connections(
    shapefile_path: Path, geoids: Sequence[str], populations: Sequence[int], part_graph: PartGraph,
    *, district_count: int, diagnostic_dir: Path = DEFAULT_FL_DIAGNOSTIC_DIR,
) -> tuple[PartGraph, tuple[dict[str, Any], ...], dict[str, Any]]:
    """Verify unchanged source geometry and add only the authorized edge.

    The 1% population-group budget selects the same one-root forest diagnosed
    earlier. It does not certify a balanced partition. The exporter must still
    validate full district polygons and same-district ownership of link ends.
    """
    started = time.perf_counter()
    if isinstance(district_count, bool) or not isinstance(district_count, Integral) or district_count not in SUPPORTED_DISTRICT_COUNTS:
        raise ValueError("Florida recorded policy is currently authorized for district counts 28, 37, 45, and 65 only.")
    ordered = tuple(geoids)
    if not ordered or len(set(ordered)) != len(ordered) or any(
        not isinstance(g, str) or len(g) != 15 or not g.isascii() or not g.isdigit() or not g.startswith("12") for g in ordered
    ):
        raise ValueError("GEOIDs must be unique 15-digit Florida (12) blocks.")
    if len(ordered) != len(part_graph.unit_to_parts) or len(populations) != len(ordered):
        raise ValueError("GEOIDs, populations, and whole-block graph ownership must match.")
    if any(isinstance(p, bool) or not isinstance(p, Integral) or p < 0 for p in populations):
        raise ValueError("Populations must be nonnegative whole-block integers.")
    pops = tuple(int(p) for p in populations)
    if sum(pops) <= 0 or district_count > len(ordered):
        raise ValueError("A positive population and at least one block per district are required.")
    diagnostic_dir = Path(diagnostic_dir)
    payloads = {name: (diagnostic_dir / name).read_bytes() for name in PINNED_EVIDENCE_SHA256}
    hashes = {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}
    if hashes != PINNED_EVIDENCE_SHA256:
        raise ValueError("Preserved Florida diagnostic evidence hash changed; authorized links must not be silently redefined.")
    evidence = {name: json.loads(payload) for name, payload in payloads.items()}
    diagnosis, candidates, context = (evidence[name] for name in ("diagnosis.json", "candidate-links.json", "geography-context.json"))
    if (diagnosis.get("state_fips") != "12" or diagnosis.get("physical_component_count") != EXPECTED_COMPONENT_COUNT
            or diagnosis.get("blocks_spanning_components") or diagnosis.get("status") != "diagnostic_complete_no_district_plans_generated"):
        raise ValueError("Expected the preserved two-component Florida diagnosis with unambiguous population ownership.")
    if candidates != diagnosis.get("links"):
        raise ValueError("Preserved Florida candidates disagree with the diagnosis.")
    surfaces = _validate_context(context)
    by_id = {candidate["id"]: candidate for candidate in candidates}
    if len(by_id) != len(candidates) or not set(AUTHORIZED_CANDIDATE_IDS).issubset(by_id):
        raise ValueError("Candidate IDs must be unique and include the authorized connection.")
    saved_plans = [plan for plan in diagnosis.get("plans", []) if plan["district_count"] == district_count]
    if len(saved_plans) != 1:
        raise ValueError("The pinned diagnosis must contain exactly one source-policy plan for the target count.")
    saved_plan = saved_plans[0]
    if (saved_plan.get("selected_link_ids") != list(AUTHORIZED_CANDIDATE_IDS)
            or saved_plan.get("actual_district_plan_generated") is not False):
        raise ValueError("The preserved target-count source-policy plan must select exactly the authorized connection.")
    if diagnosis["source"]["archive_sha256"] != SOURCE_ARCHIVE_SHA256:
        raise ValueError("The Florida diagnosis does not use the authorized source archive.")
    path = Path(shapefile_path)
    for suffix in (".shp", ".shx", ".dbf"):
        source_file = path.with_suffix(suffix)
        if diagnosis["source"]["extracted_file_sha256"].get(source_file.name) != _sha256(source_file):
            raise ValueError(f"Source {suffix} differs from the preserved Florida diagnosis.")
    if _sha256(Path(diagnosis["source"]["archive_path"])) != diagnosis["source"]["archive_sha256"]:
        raise ValueError("Florida source archive differs from the preserved diagnosis.")
    source_parts = _read_parts(path, ordered, part_graph, pops)
    physical_helpers._verify_physical_graph(source_parts, part_graph)
    components, membership = physical_helpers._components(part_graph)
    if len(components) != EXPECTED_COMPONENT_COUNT or len(source_parts) != diagnosis["part_count"] or len(ordered) != diagnosis["block_count"]:
        raise ValueError("Exact source graph differs from the diagnosed Florida components.")
    component_units: list[list[int]] = [[] for _ in components]
    for unit, nodes in enumerate(part_graph.unit_to_parts):
        owners = {membership[node] for node in nodes}
        if len(owners) != 1:
            raise ValueError("Common multipart ownership cannot connect physical components or distribute block population.")
        component_units[owners.pop()].append(unit)
    component_pops = [sum(pops[unit] for unit in units) for units in component_units]
    expected = diagnosis["components"]
    if (component_pops != [row["population"] for row in expected]
            or [len(nodes) for nodes in components] != [row["part_count"] for row in expected]
            or [len(units) for units in component_units] != [row["block_count"] for row in expected]
            or sum(pops) != diagnosis["total_population"]):
        raise ValueError("Florida component populations/ownership differ from the preserved diagnosis.")
    tree = shapely.STRtree(source_parts)
    eligible = []
    for candidate in candidates:
        _validate_endpoint(candidate, source_parts, part_graph, ordered, membership)
        if not candidate.get("eligible_positive_gap"):
            continue  # Preserved excluded candidates remain evidence, never policy edges.
        if (candidate.get("classification") != "positive_gap" or candidate.get("source_boundaries_intersect") is not False
                or candidate.get("intervening_component_ids") or candidate.get("endpoint_component_interior_crossings")):
            raise ValueError("Recorded candidate is not an eligible positive gap.")
        line = LineString([e["coordinate"] for e in candidate["endpoints"]])
        for node in tree.query(line):
            part = source_parts[int(node)]
            if line.intersection(part).difference(part.boundary).length > _INTERIOR_ROUNDOFF_TOLERANCE_DEGREES:
                raise ValueError("Recorded candidate crosses a Florida source part interior.")
        eligible.append(candidate)
    selection = select_population_aware_forest(component_pops, eligible, district_count, population_tolerance=.01)
    if (selection["selected_link_ids"] != list(AUTHORIZED_CANDIDATE_IDS) or len(selection["groups"]) != 1
            or selection["eligible_root_component_ids"] != [0]
            or selection["groups"][0]["district_count"] != district_count
            or selection["groups"][0]["population"] != sum(pops)):
        raise ValueError("Population-aware selector changed the authorized Florida attachment or target-count allocation.")
    if (saved_plan.get("policy") != selection
            or saved_plan.get("policy_population_bound") != selection["population_bound"]
            or saved_plan.get("augmented_component_count") != 1):
        raise ValueError("Recomputed target-count population policy differs from the pinned diagnosis.")
    verified_source_hashes = {suffix: _sha256(path.with_suffix(suffix)) for suffix in (".shp", ".shx", ".dbf")}
    if any(diagnosis["source"]["extracted_file_sha256"].get(path.with_suffix(suffix).name) != digest
           for suffix, digest in verified_source_hashes.items()):
        raise ValueError("Florida source changed while its physical geometry and policy were being verified.")
    provenance = {
        "policy": POLICY, "builder_sha256": _sha256(Path(__file__)),
        "physical_validation_helpers_sha256": _sha256(Path(physical_helpers.__file__)),
        "population_selector_sha256": _sha256(ROOT / "scripts/hawaii_population_links.py"),
        "source_archive_sha256": diagnosis["source"]["archive_sha256"],
        "source_files_sha256": verified_source_hashes,
        "diagnostic_evidence_sha256": hashes,
        "shapely_version": shapely.__version__, "geos_version": shapely.geos_version_string,
    }
    records = []
    for index, candidate_id in enumerate(AUTHORIZED_CANDIDATE_IDS, 1):
        records.append({**copy.deepcopy(by_id[candidate_id]), "id": f"fl-water-{index:03d}", "candidate_id": candidate_id,
                        "state_fips": "12", "kind": "recorded-water-connection", "policy": POLICY,
                        "geographic_context": {"evidence_basis": "Official regional geographic attribution, not a global shoreline-intersection certificate.",
                                               "summary": surfaces[candidate_id]["summary"], "sources": copy.deepcopy(context["sources"]),
                                               "source_component_clearance_verified": True, "independent_global_land_mask_tested": False,
                                               "foreign_land_exclave_identified": False, "source_geometry_modified": False},
                        "provenance": provenance,
                        "distance_definition": "Spherical endpoint length of the preserved planar nearest-boundary candidate in water-inclusive census coverage."})
    rows = [set(neighbors) for neighbors in part_graph.adjacency]
    for record in records:
        a, b = [endpoint["part_node"] for endpoint in record["endpoints"]]
        rows[a].add(b)
        rows[b].add(a)
    augmented = PartGraph(tuple(tuple(sorted(row)) for row in rows), part_graph.part_to_unit)
    augmented_components, _ = physical_helpers._components(augmented)
    if len(augmented_components) != 1 or len(augmented_components[0]) != len(source_parts):
        raise ValueError("Recorded edges did not connect every Florida source part.")
    physical_edges = sum(map(len, part_graph.adjacency)) // 2
    augmented_edges = sum(map(len, augmented.adjacency)) // 2
    if augmented_edges - physical_edges != len(AUTHORIZED_CANDIDATE_IDS):
        raise ValueError("Augmented graph must add exactly the authorized new source-part edge.")
    audit = {"schema_version": 1, "policy": POLICY, "state_fips": "12", "district_count": district_count,
             "source_geometry_modified": False, "synthetic_ownership_edges": False, "source_population": sum(pops),
             "block_count": len(ordered), "part_count": len(source_parts), "physical_component_count": EXPECTED_COMPONENT_COUNT,
             "physical_edge_count": physical_edges, "synthetic_edge_count": len(AUTHORIZED_CANDIDATE_IDS), "augmented_edge_count": augmented_edges,
             "augmented_component_count": 1, "augmented_graph_connected": True, "all_source_parts_reached": True,
             "target_selection_verified_against_diagnosis": True,
             "eligible_root_count": 1, "groups": selection["groups"], "population_selection": selection,
             "components": [{"component_id": i, "population": component_pops[i], "part_count": len(nodes),
                              "block_count": len(component_units[i])} for i, nodes in enumerate(components)],
             "candidate_count": len(candidates), "candidate_connections": candidates,
             "unselected_candidate_ids": [row["id"] for row in candidates if row["id"] not in AUTHORIZED_CANDIDATE_IDS],
             "connection_kind_counts": {"recorded-water-connection": len(records)},
             "water_context_validation": copy.deepcopy(context["water_context_validation"]),
             "provenance": provenance, "endpoint_tolerance_degrees": _ENDPOINT_TOLERANCE_DEGREES,
             "interior_roundoff_tolerance_degrees": _INTERIOR_ROUNDOFF_TOLERANCE_DEGREES,
             "elapsed_seconds": time.perf_counter() - started}
    return augmented, tuple(records), audit
