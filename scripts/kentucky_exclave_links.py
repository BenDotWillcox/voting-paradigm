"""Explicit Kentucky Bend connection using the preserved exact-source diagnosis.

This is an exclave exception across Missouri water and land. It is not a
water-only route, a bridge, a boundary change, or a grant of Missouri territory.
Source polygons and whole-block populations remain unchanged.
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
DEFAULT_KY_DIAGNOSTIC_DIR = ROOT / ".cache/state-block-benchmark/suite-through-1000/diagnostics/kentucky"
POLICY = "kentucky-bend-recorded-exclave-v1"
SUPPORTED_DISTRICT_COUNTS = (6, 8, 9, 14)


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
                raise ValueError("Source must contain exactly the unique requested Kentucky GEOIDs.")
            if int(record.record["POP20"]) != populations[indices[geoid]]:
                raise ValueError("Supplied whole-block population differs from the verified source record.")
            geometry = shape(record.shape.__geo_interface__)
            if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError("Kentucky source parts must be unchanged valid polygons.")
            by_unit[indices[geoid]] = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    if any(parts is None for parts in by_unit):
        raise ValueError("Source is missing requested Kentucky blocks.")
    parts, owners = [], []
    for unit, unit_parts in enumerate(by_unit):
        assert unit_parts is not None
        parts.extend(unit_parts)
        owners.extend([unit] * len(unit_parts))
    if tuple(owners) != graph.part_to_unit:
        raise ValueError("Part graph ownership/order differs from exact source geometry.")
    return parts


def build_kentucky_connections(
    shapefile_path: Path, geoids: Sequence[str], populations: Sequence[int], part_graph: PartGraph,
    *, district_count: int, diagnostic_dir: Path = DEFAULT_KY_DIAGNOSTIC_DIR,
) -> tuple[PartGraph, tuple[dict[str, Any], ...], dict[str, Any]]:
    """Verify and apply the recorded Kentucky Bend edge; never modify geography.

    The population selector's 1% budget is an optimistic group-allocation check,
    not a guarantee about the final whole-block district populations. Actual
    plans still require independent same-district endpoint/polygon validation.
    """
    started = time.perf_counter()
    if isinstance(district_count, bool) or not isinstance(district_count, Integral) or district_count not in SUPPORTED_DISTRICT_COUNTS:
        raise ValueError("Kentucky exclave policy supports district counts 6, 8, 9, and 14 only.")
    ordered = tuple(geoids)
    if not ordered or len(set(ordered)) != len(ordered) or any(
        not isinstance(g, str) or len(g) != 15 or not g.isascii() or not g.isdigit() or not g.startswith("21")
        for g in ordered
    ):
        raise ValueError("GEOIDs must be unique 15-digit Kentucky (21) blocks.")
    if len(ordered) != len(part_graph.unit_to_parts) or len(populations) != len(ordered):
        raise ValueError("GEOIDs, populations, and whole-block graph ownership must match.")
    if any(isinstance(p, bool) or not isinstance(p, Integral) or p < 0 for p in populations):
        raise ValueError("Populations must be nonnegative whole-block integers.")
    pops = tuple(int(p) for p in populations)
    if sum(pops) <= 0 or district_count > len(ordered):
        raise ValueError("A positive population and at least one block per district are required.")
    diagnostic_dir = Path(diagnostic_dir)
    evidence_names = ("diagnosis.json", "candidate-links.json", "area-water-audit.json", "missouri-connection-context.json")
    evidence = {name: json.loads((diagnostic_dir / name).read_text(encoding="utf-8")) for name in evidence_names}
    evidence_hashes = {name: _sha256(diagnostic_dir / name) for name in evidence_names}
    diagnosis = evidence["diagnosis.json"]
    area = evidence["area-water-audit.json"]
    context = evidence["missouri-connection-context.json"]
    if (diagnosis["state_fips"] != "21" or diagnosis["physical_component_count"] != 2
            or diagnosis["blocks_spanning_components"] or diagnosis["status"] != "diagnostic_complete_no_district_plans_generated"):
        raise ValueError("Expected the preserved two-component Kentucky diagnosis.")
    source_files = diagnosis["source"]["extracted_file_sha256"]
    path = Path(shapefile_path)
    for suffix in (".shp", ".shx", ".dbf"):
        source_file = path.with_suffix(suffix)
        if source_files.get(source_file.name) != _sha256(source_file):
            raise ValueError(f"Source {suffix} differs from the preserved Kentucky diagnosis.")
    archive = Path(diagnosis["source"]["archive_path"])
    if _sha256(archive) != diagnosis["source"]["archive_sha256"]:
        raise ValueError("Kentucky source archive differs from the preserved diagnosis.")
    if len(diagnosis["links"]) != 1:
        raise ValueError("Kentucky exclave policy expects one explicitly diagnosed candidate.")
    candidate = copy.deepcopy(diagnosis["links"][0])
    raw_candidates = evidence["candidate-links.json"]
    if len(raw_candidates) != 1 or any(candidate[field] != raw_candidates[0][field] for field in ("id", "endpoints", "component_ids", "distance_m")):
        raise ValueError("Preserved Kentucky candidate evidence disagrees.")
    if area["candidate_file_sha256"] != evidence_hashes["candidate-links.json"]:
        raise ValueError("Area-water evidence does not describe the preserved candidate file.")
    endpoints = [endpoint["coordinate"] for endpoint in candidate["endpoints"]]
    if (area["candidate_endpoints"] != endpoints or context["candidate_endpoints"] != endpoints
            or area["candidate_id"] != candidate["id"] or context["coverage_fraction"] != 1.0
            or area["water_only_under_2020_census_area_water"] is not False
            or area["outside_mapped_water_length_m"] <= 0):
        raise ValueError("The recorded Kentucky exception must retain its cross-Missouri land/water classification.")
    area_archive = ROOT / area["source_archive"]
    if _sha256(area_archive) != area["source_archive_sha256"]:
        raise ValueError("Recorded area-water source archive changed.")
    if _sha256(Path(context["source_archive"])) != context["source_archive_sha256"]:
        raise ValueError("Recorded Missouri context source archive changed.")
    if (candidate["classification"] != "positive_gap" or not candidate["eligible_positive_gap"]
            or candidate["source_boundaries_intersect"] or candidate["intervening_component_ids"]
            or candidate["endpoint_component_interior_crossings"]):
        raise ValueError("Recorded exclave candidate is not an eligible positive gap.")
    source_parts = _read_parts(path, ordered, part_graph, pops)
    physical_helpers._verify_physical_graph(source_parts, part_graph)
    components, membership = physical_helpers._components(part_graph)
    if len(components) != 2 or len(source_parts) != diagnosis["part_count"] or len(ordered) != diagnosis["block_count"]:
        raise ValueError("Exact source graph differs from the diagnosed Kentucky components.")
    component_units: list[list[int]] = [[] for _ in components]
    for unit, nodes in enumerate(part_graph.unit_to_parts):
        owners = {membership[node] for node in nodes}
        if len(owners) != 1:
            raise ValueError("Common multipart ownership cannot connect different physical components.")
        component_units[owners.pop()].append(unit)
    component_pops = [sum(pops[unit] for unit in units) for units in component_units]
    expected = diagnosis["components"]
    if (component_pops != [row["population"] for row in expected]
            or [len(nodes) for nodes in components] != [row["part_count"] for row in expected]
            or [len(units) for units in component_units] != [row["block_count"] for row in expected]
            or sum(pops) != diagnosis["total_population"]):
        raise ValueError("Kentucky component populations/ownership differ from the preserved diagnosis.")
    for endpoint, component in zip(candidate["endpoints"], candidate["component_ids"], strict=True):
        node, part_index = endpoint["part_node"], endpoint["part_index"]
        if isinstance(node, bool) or not isinstance(node, Integral) or not 0 <= node < len(source_parts):
            raise ValueError("Invalid recorded exclave endpoint node.")
        unit = part_graph.part_to_unit[node]
        if (endpoint["geoid"] != ordered[unit] or isinstance(part_index, bool) or not isinstance(part_index, Integral)
                or not 0 <= part_index < len(part_graph.unit_to_parts[unit]) or part_graph.unit_to_parts[unit][part_index] != node
                or membership[node] != component):
            raise ValueError("Recorded exclave endpoint ownership/component differs from source.")
        coordinate = endpoint["coordinate"]
        if len(coordinate) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in coordinate):
            raise ValueError("Recorded endpoint coordinates must be finite.")
        if source_parts[node].boundary.distance(Point(coordinate)) > 1e-9:
            raise ValueError("Recorded endpoint is not on the unchanged source part boundary.")
    measured = _great_circle_m(*endpoints)
    if not math.isclose(measured, candidate["distance_m"], rel_tol=1e-12, abs_tol=1e-6):
        raise ValueError("Recorded candidate distance differs from its endpoint coordinates.")
    line = LineString(endpoints)
    tree = shapely.STRtree(source_parts)
    for node in tree.query(line):
        source_part = source_parts[int(node)]
        if line.intersection(source_part).difference(source_part.boundary).length > 1e-10:
            raise ValueError("Recorded candidate crosses a Kentucky source part interior.")
    selection = select_population_aware_forest(component_pops, [candidate], district_count, population_tolerance=.01)
    if selection["selected_link_ids"] != [candidate["id"]] or len(selection["groups"]) != 1:
        raise ValueError("Population-aware selector did not retain the diagnosed single exclave attachment.")
    provenance = {
        "policy": POLICY, "builder_sha256": _sha256(Path(__file__)),
        "physical_validation_helpers_sha256": _sha256(Path(physical_helpers.__file__)),
        "source_archive_sha256": diagnosis["source"]["archive_sha256"],
        "source_files_sha256": {suffix: _sha256(path.with_suffix(suffix)) for suffix in (".shp", ".shx", ".dbf")},
        "diagnostic_evidence_sha256": evidence_hashes,
        "shapely_version": shapely.__version__, "geos_version": shapely.geos_version_string,
    }
    record = {**candidate, "id": "ky-exclave-001", "candidate_id": candidate["id"], "state_fips": "21",
              "kind": "recorded-exclave-connection", "policy": POLICY,
              "distance_definition": "Spherical endpoint length of the preserved planar nearest-boundary candidate in census coverage.",
              "geographic_context": {"crossed_state": "Missouri", "water_only": False,
                 "mapped_water_length_m": area["mapped_water_length_m"],
                 "mapped_land_length_m": area["outside_mapped_water_length_m"],
                 "surface_length_measurement": area["measurement"],
                 "source_year": 2020, "area_water_source_url": area["source_url"],
                 "area_water_archive_sha256": area["source_archive_sha256"],
                 "meaning": "Explicit cross-jurisdiction connectivity exception; no Missouri territory, source polygon, bridge, or travel route is added."},
              "provenance": provenance}
    a, b = [endpoint["part_node"] for endpoint in record["endpoints"]]
    rows = [set(neighbors) for neighbors in part_graph.adjacency]
    rows[a].add(b)
    rows[b].add(a)
    augmented = PartGraph(tuple(tuple(sorted(row)) for row in rows), part_graph.part_to_unit)
    augmented_components, _ = physical_helpers._components(augmented)
    if len(augmented_components) != 1 or len(augmented_components[0]) != len(source_parts):
        raise ValueError("Recorded exclave edge did not connect every source polygon part.")
    audit = {"schema_version": 1, "policy": POLICY, "state_fips": "21", "district_count": district_count,
             "source_geometry_modified": False, "synthetic_ownership_edges": False, "source_population": sum(pops),
             "block_count": len(ordered), "part_count": len(source_parts), "physical_component_count": len(components),
             "physical_edge_count": sum(map(len, part_graph.adjacency)) // 2, "synthetic_edge_count": 1,
             "augmented_edge_count": sum(map(len, augmented.adjacency)) // 2,
             "augmented_component_count": 1, "augmented_graph_connected": True,
             "eligible_root_count": len(selection["eligible_root_component_ids"]),
             "groups": selection["groups"], "population_selection": selection,
             "components": [{"component_id": index, "population": component_pops[index], "part_count": len(nodes),
                              "block_count": len(component_units[index])} for index, nodes in enumerate(components)],
             "candidate_count": 1, "candidate_connections": [candidate], "excluded_candidates": [],
             "geographic_context": record["geographic_context"], "provenance": provenance,
             "endpoint_tolerance_degrees": 1e-9, "elapsed_seconds": time.perf_counter() - started}
    return augmented, (record,), audit
