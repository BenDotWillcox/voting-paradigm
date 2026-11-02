"""Apply the audited Liberty water link and Ellis exclave link to New York.

These two policy edges never modify geography or add New Jersey territory.
The recorded diagnosis is pinned by SHA-256; source parts and every physical
edge are independently checked before adding either explicitly classified edge.
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
DEFAULT_NY_DIAGNOSTIC_DIR = ROOT / ".cache/state-block-benchmark/suite-through-1000/diagnostics/new-york"
POLICY = "new-york-harbor-recorded-mixed-v1"
SUPPORTED_DISTRICT_COUNTS = (26, 35, 42, 61)
# Immutable evidence for the two user-authorized exceptions, not runtime output.
PINNED_EVIDENCE_SHA256 = {
    "diagnosis.json": "c0c6328e9abecac3622fd2c439b5a016be35690778ee6978e815672c0bc59c63",
    "candidate-links.json": "960425feb448677b723481da6cb57f066744995b7bed8ae94b13a9aa2d7489de",
    "geography-context.json": "3ef1f218718f63348d7f73d6e910cc5cd6977649694f8e50b1d866ed66b7e92f",
}
_AUTHORIZED = {
    "ny-candidate-00-01": ("ny-water-liberty-001", "recorded-water-connection", True),
    "ny-candidate-00-02": ("ny-exclave-ellis-001", "recorded-exclave-connection", False),
}


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
                raise ValueError("Source must contain exactly the unique requested New York GEOIDs.")
            if int(record.record["POP20"]) != populations[indices[geoid]]:
                raise ValueError("Supplied whole-block population differs from the verified source record.")
            geometry = shape(record.shape.__geo_interface__)
            if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError("New York source parts must be unchanged valid polygons.")
            by_unit[indices[geoid]] = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    if any(parts is None for parts in by_unit):
        raise ValueError("Source is missing requested New York blocks.")
    parts, owners = [], []
    for unit, unit_parts in enumerate(by_unit):
        assert unit_parts is not None
        parts.extend(unit_parts)
        owners.extend([unit] * len(unit_parts))
    if tuple(owners) != graph.part_to_unit:
        raise ValueError("Part graph ownership/order differs from exact source geometry.")
    return parts


def _check_surface(candidate: dict[str, Any], surface: dict[str, Any], water_only: bool) -> None:
    """Reconcile the pinned full-source crossing audit, never infer water from gap."""
    if (surface["candidate_id"] != candidate["id"]
            or surface["candidate_endpoints"] != [e["coordinate"] for e in candidate["endpoints"]]
            or surface["component_ids"] != candidate["component_ids"]
            or surface["distance_m"] != candidate["distance_m"]
            or surface["new_jersey_interior_coverage_fraction"] != 1.0
            or surface["water_only_under_2020_census_area_water"] is not water_only):
        raise ValueError("Recorded connection water/land classification or endpoint evidence disagrees.")
    expected_classification = "mapped_water_only" if water_only else "crosses_mapped_water_and_new_jersey_land"
    if surface["classification"] != expected_classification:
        raise ValueError("Recorded connection classification must retain Liberty water and Ellis exclave semantics.")
    water, land, total = (surface[key] for key in
                         ("mapped_water_length_m", "outside_mapped_water_length_m", "candidate_planar_length_m"))
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in (water, land, total)):
        raise ValueError("Audited surface lengths must be finite and nonnegative.")
    if (water_only and land > 1e-6) or (not water_only and land <= 1e-6) or water <= 0:
        raise ValueError("Recorded classification disagrees with audited land/water lengths.")
    if not math.isclose(water + land, total, abs_tol=1e-6, rel_tol=1e-12):
        raise ValueError("Audited surface lengths do not cover the exact connection.")
    rows = surface["crossed_new_jersey_blocks"]
    if not rows or any(not row["geoid"].startswith("34") for row in rows):
        raise ValueError("Crossing evidence must identify the New Jersey context blocks.")
    land_rows = [row for row in rows if row["land_area_m2"] > 0 and row["water_area_m2"] == 0]
    if (water_only and land_rows) or (not water_only and not land_rows):
        raise ValueError("New Jersey block evidence disagrees with recorded connection classification.")


def build_new_york_connections(
    shapefile_path: Path, geoids: Sequence[str], populations: Sequence[int], part_graph: PartGraph,
    *, district_count: int, diagnostic_dir: Path = DEFAULT_NY_DIAGNOSTIC_DIR,
) -> tuple[PartGraph, tuple[dict[str, Any], ...], dict[str, Any]]:
    """Verify and add two recorded edges; retain physical and policy outcomes.

    The selector's 1% optimistic population-group budget is not a final district
    balance guarantee. Links only support a district when their endpoints share
    its assignment; independent full-polygon export checks enforce that rule.
    """
    started = time.perf_counter()
    if isinstance(district_count, bool) or not isinstance(district_count, Integral) or district_count not in SUPPORTED_DISTRICT_COUNTS:
        raise ValueError("New York recorded policy supports district counts 26, 35, 42, and 61 only.")
    ordered = tuple(geoids)
    if not ordered or len(set(ordered)) != len(ordered) or any(
        not isinstance(g, str) or len(g) != 15 or not g.isascii() or not g.isdigit() or not g.startswith("36") for g in ordered
    ):
        raise ValueError("GEOIDs must be unique 15-digit New York (36) blocks.")
    if len(ordered) != len(part_graph.unit_to_parts) or len(populations) != len(ordered):
        raise ValueError("GEOIDs, populations, and whole-block graph ownership must match.")
    if any(isinstance(p, bool) or not isinstance(p, Integral) or p < 0 for p in populations):
        raise ValueError("Populations must be nonnegative whole-block integers.")
    pops = tuple(int(p) for p in populations)
    if sum(pops) <= 0 or district_count > len(ordered):
        raise ValueError("A positive population and at least one block per district are required.")
    diagnostic_dir = Path(diagnostic_dir)
    hashes = {name: _sha256(diagnostic_dir / name) for name in PINNED_EVIDENCE_SHA256}
    if hashes != PINNED_EVIDENCE_SHA256:
        raise ValueError("Preserved New York diagnostic evidence hash changed; recorded exceptions must not be silently redefined.")
    evidence = {name: json.loads((diagnostic_dir / name).read_text(encoding="utf-8")) for name in hashes}
    diagnosis, candidates, context = (evidence[name] for name in ("diagnosis.json", "candidate-links.json", "geography-context.json"))
    if (diagnosis["state_fips"] != "36" or diagnosis["physical_component_count"] != 3
            or diagnosis["blocks_spanning_components"] or diagnosis["status"] != "diagnostic_complete_no_district_plans_generated"):
        raise ValueError("Expected the preserved three-component New York diagnosis.")
    if candidates != diagnosis["links"] or context["candidate_file_sha256"] != hashes["candidate-links.json"] or context["diagnosis_file_sha256"] != hashes["diagnosis.json"]:
        raise ValueError("Preserved candidate and geographic evidence disagrees.")
    if context["status"] != "complete" or context["source_geometry_modified"] is not False or context["source_year"] != 2020:
        raise ValueError("Expected unchanged full-resolution 2020 geographic evidence.")
    path = Path(shapefile_path)
    for suffix in (".shp", ".shx", ".dbf"):
        source_file = path.with_suffix(suffix)
        if diagnosis["source"]["extracted_file_sha256"].get(source_file.name) != _sha256(source_file):
            raise ValueError(f"Source {suffix} differs from the preserved New York diagnosis.")
    if _sha256(Path(diagnosis["source"]["archive_path"])) != diagnosis["source"]["archive_sha256"]:
        raise ValueError("New York source archive differs from the preserved diagnosis.")
    for archive, digest in context["source_archive_sha256"].items():
        if _sha256(ROOT / archive) != digest:
            raise ValueError("Geographic context source archive differs from the preserved diagnosis.")
    source_parts = _read_parts(path, ordered, part_graph, pops)
    physical_helpers._verify_physical_graph(source_parts, part_graph)
    components, membership = physical_helpers._components(part_graph)
    if len(components) != 3 or len(source_parts) != diagnosis["part_count"] or len(ordered) != diagnosis["block_count"]:
        raise ValueError("Exact source graph differs from the diagnosed New York components.")
    component_units: list[list[int]] = [[] for _ in components]
    for unit, nodes in enumerate(part_graph.unit_to_parts):
        owners = {membership[node] for node in nodes}
        if len(owners) != 1:
            raise ValueError("Common multipart ownership cannot connect physical components.")
        component_units[owners.pop()].append(unit)
    component_pops = [sum(pops[unit] for unit in units) for units in component_units]
    expected = diagnosis["components"]
    if (component_pops != [row["population"] for row in expected] or component_pops[1:] != [0, 0]
            or [len(nodes) for nodes in components] != [row["part_count"] for row in expected]
            or [len(units) for units in component_units] != [row["block_count"] for row in expected]
            or sum(pops) != diagnosis["total_population"]):
        raise ValueError("New York component populations/ownership differ from the preserved diagnosis.")
    tree = shapely.STRtree(source_parts)
    for candidate in candidates:
        if (candidate["classification"] != "positive_gap" or not candidate["eligible_positive_gap"]
                or candidate["source_boundaries_intersect"] or candidate["intervening_component_ids"]
                or candidate["endpoint_component_interior_crossings"]):
            raise ValueError("Recorded candidate is not an eligible positive gap.")
        for endpoint, component in zip(candidate["endpoints"], candidate["component_ids"], strict=True):
            node, part_index = endpoint["part_node"], endpoint["part_index"]
            if isinstance(node, bool) or not isinstance(node, Integral) or not 0 <= node < len(source_parts):
                raise ValueError("Invalid recorded endpoint node.")
            unit = part_graph.part_to_unit[node]
            if (endpoint["geoid"] != ordered[unit] or isinstance(part_index, bool) or not isinstance(part_index, Integral)
                    or not 0 <= part_index < len(part_graph.unit_to_parts[unit]) or part_graph.unit_to_parts[unit][part_index] != node
                    or membership[node] != component):
                raise ValueError("Recorded endpoint ownership/component differs from source.")
            coordinate = endpoint["coordinate"]
            if len(coordinate) != 2 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in coordinate):
                raise ValueError("Recorded endpoint coordinates must be finite.")
            if source_parts[node].boundary.distance(Point(coordinate)) > 1e-9:
                raise ValueError("Recorded endpoint is not on the unchanged source part boundary.")
        endpoints = [e["coordinate"] for e in candidate["endpoints"]]
        if not math.isclose(_great_circle_m(*endpoints), candidate["distance_m"], rel_tol=1e-12, abs_tol=1e-6):
            raise ValueError("Recorded candidate distance differs from its coordinates.")
        line = LineString(endpoints)
        for node in tree.query(line):
            part = source_parts[int(node)]
            if line.intersection(part).difference(part.boundary).length > 1e-10:
                raise ValueError("Recorded candidate crosses a New York source part interior.")
    selection = select_population_aware_forest(component_pops, candidates, district_count, population_tolerance=.01)
    if selection["selected_link_ids"] != list(_AUTHORIZED) or len(selection["groups"]) != 1:
        raise ValueError("Population-aware selector changed the two authorized New York attachments.")
    surfaces = {row["candidate_id"]: row for row in context["links"]}
    provenance = {
        "policy": POLICY, "builder_sha256": _sha256(Path(__file__)),
        "physical_validation_helpers_sha256": _sha256(Path(physical_helpers.__file__)),
        "source_archive_sha256": diagnosis["source"]["archive_sha256"],
        "source_files_sha256": {suffix: _sha256(path.with_suffix(suffix)) for suffix in (".shp", ".shx", ".dbf")},
        "diagnostic_evidence_sha256": hashes, "context_source_archive_sha256": context["source_archive_sha256"],
        "shapely_version": shapely.__version__, "geos_version": shapely.geos_version_string,
    }
    records = []
    for candidate in candidates:
        if candidate["id"] not in _AUTHORIZED:
            continue
        record_id, kind, water_only = _AUTHORIZED[candidate["id"]]
        surface = surfaces[candidate["id"]]
        _check_surface(candidate, surface, water_only)
        geographic_context = {
            "crossed_state": "New Jersey", "water_only": water_only,
            "mapped_water_length_m": surface["mapped_water_length_m"],
            "mapped_land_length_m": surface["outside_mapped_water_length_m"],
            "surface_length_measurement": context["measurement"], "source_year": 2020,
            "crossed_new_jersey_blocks": surface["crossed_new_jersey_blocks"],
            "classification": surface["classification"],
            "meaning": "Recorded connectivity exception only; no New Jersey territory, source polygons, bridge, or travel route is added.",
        }
        records.append({**copy.deepcopy(candidate), "id": record_id, "candidate_id": candidate["id"], "state_fips": "36",
                        "kind": kind, "policy": POLICY, "geographic_context": geographic_context, "provenance": provenance,
                        "distance_definition": "Spherical endpoint length of the preserved planar nearest-boundary candidate in census coverage."})
    if len({record["endpoints"][0]["part_node"] for record in records}) != 1:
        raise ValueError("Authorized New York links must retain their common main-coverage anchor.")
    rows = [set(neighbors) for neighbors in part_graph.adjacency]
    for record in records:
        a, b = [endpoint["part_node"] for endpoint in record["endpoints"]]
        rows[a].add(b)
        rows[b].add(a)
    augmented = PartGraph(tuple(tuple(sorted(row)) for row in rows), part_graph.part_to_unit)
    augmented_components, _ = physical_helpers._components(augmented)
    if len(augmented_components) != 1 or len(augmented_components[0]) != len(source_parts):
        raise ValueError("Recorded edges did not connect every New York source part.")
    audit = {"schema_version": 1, "policy": POLICY, "state_fips": "36", "district_count": district_count,
             "source_geometry_modified": False, "synthetic_ownership_edges": False, "source_population": sum(pops),
             "block_count": len(ordered), "part_count": len(source_parts), "physical_component_count": 3,
             "physical_edge_count": sum(map(len, part_graph.adjacency)) // 2, "synthetic_edge_count": 2,
             "augmented_edge_count": sum(map(len, augmented.adjacency)) // 2,
             "augmented_component_count": 1, "augmented_graph_connected": True,
             "eligible_root_count": len(selection["eligible_root_component_ids"]), "groups": selection["groups"],
             "population_selection": selection,
             "components": [{"component_id": i, "population": component_pops[i], "part_count": len(nodes),
                              "block_count": len(component_units[i])} for i, nodes in enumerate(components)],
             "candidate_count": len(candidates), "candidate_connections": candidates,
             "unselected_candidate_ids": [row["id"] for row in candidates if row["id"] not in _AUTHORIZED],
             "connection_kind_counts": {"recorded-water-connection": 1, "recorded-exclave-connection": 1},
             "provenance": provenance, "endpoint_tolerance_degrees": 1e-9, "elapsed_seconds": time.perf_counter() - started}
    return augmented, tuple(records), audit
