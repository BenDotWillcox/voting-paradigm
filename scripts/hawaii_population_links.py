"""Population-aware, explicitly recorded connections for Hawaii's census parts.

The policy protects independently district-sized source components only when
their grouped populations admit an integer district allocation within the
configured budget. Smaller components can attach to a different root than the
nearest one; roots can merge when the population arithmetic requires it.

The population test is necessary, not sufficient: it treats people as divisible
and ignores internal geography and bridge endpoints. A solver and independent
polygon validation must still produce and verify each actual district plan.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from fractions import Fraction
import hashlib
from itertools import product
import math
from numbers import Integral, Real
from pathlib import Path
import time
from typing import Any

import numpy as np
import shapefile
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, shape
from shapely.ops import nearest_points

from districting.part_connectivity import PartGraph
from scripts import district_block_island_links as physical_helpers


POLICY = "population-aware-rooted-boundary-forest-v1"
EARTH_RADIUS_M = 6_371_000.0
HAWAII_EXTENT = (-179.0, 18.0, -154.0, 29.0)
MAX_POPULATED_COMPONENTS = 8


def _validate_numbers(populations: Sequence[int], districts: int, tolerance: float) -> tuple[int, ...]:
    if not populations or any(isinstance(p, bool) or not isinstance(p, Integral) or p < 0 for p in populations):
        raise ValueError("Populations must be nonnegative integers with a positive total.")
    pops = tuple(int(p) for p in populations)
    if sum(pops) <= 0:
        raise ValueError("Populations must have a positive total.")
    if isinstance(districts, bool) or not isinstance(districts, Integral) or districts < 1:
        raise ValueError("District count must be a positive integer.")
    if isinstance(tolerance, bool) or not isinstance(tolerance, Real) or not math.isfinite(tolerance) or not 0 <= tolerance < 1:
        raise ValueError("Population tolerance must be finite and between zero (inclusive) and one.")
    return pops


def population_allocation_bound(populations: Sequence[int], districts: int) -> dict[str, Any]:
    """Exact rational minimax necessary bound for positive integer group quotas."""
    pops = _validate_numbers(populations, districts, 0.0)
    if len(pops) > districts:
        return {"feasible_seat_allocation": False, "minimum_required_districts": len(pops),
                "reason": "More disconnected groups than districts.", "is_constructed_plan": False}
    total = sum(pops)
    dp: dict[int, tuple[Fraction, tuple[int, ...]]] = {0: (Fraction(0), ())}
    for population in pops:
        next_dp: dict[int, tuple[Fraction, tuple[int, ...]]] = {}
        for used, (prior, allocation) in dp.items():
            for seats in range(1, districts - used + 1):
                deviation = Fraction(abs(population * districts - seats * total), seats * total)
                entry = (max(prior, deviation), (*allocation, seats))
                if used + seats not in next_dp or entry < next_dp[used + seats]:
                    next_dp[used + seats] = entry
        dp = next_dp
    deviation, allocation = dp[districts]
    return {"feasible_seat_allocation": True, "best_max_deviation_pct": 100 * float(deviation),
            "deviation_fraction": [deviation.numerator, deviation.denominator],
            "seat_counts": list(allocation), "ideal_population": total / districts,
            "group_ideal_seats": [p * districts / total for p in pops],
            "is_constructed_plan": False,
            "interpretation": "Optimistic necessary bound: divisible people, ignoring whole blocks, internal geometry, and bridge endpoints."}


def _partitions(values: tuple[int, ...]) -> Iterator[tuple[tuple[int, ...], ...]]:
    if not values:
        yield ()
        return
    first, *remaining = values
    for partition in _partitions(tuple(remaining)):
        yield ((first,), *partition)
        for index in range(len(partition)):
            yield (*partition[:index], (first, *partition[index]), *partition[index + 1:])


def _forest(
    populations: tuple[int, ...], positive_groups: tuple[tuple[int, ...], ...],
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[list[int]]] | None:
    """Deterministic constrained Kruskal; not a global Steiner-forest optimum."""
    parents = list(range(len(populations)))
    labels: list[int | None] = [None] * len(parents)
    for label, members in enumerate(positive_groups):
        for member in members:
            labels[member] = label

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    selected = []
    for link in candidates:
        a, b = map(find, link["component_ids"])
        if a == b or (labels[a] is not None and labels[b] is not None and labels[a] != labels[b]):
            continue
        parents[b] = a
        labels[a] = labels[a] if labels[a] is not None else labels[b]
        selected.append(link)
    groups = [[] for _ in positive_groups]
    for index in range(len(populations)):
        label = labels[find(index)]
        if label is None:
            return None
        groups[label].append(index)
    if any(len({find(member) for member in group}) != 1 for group in groups):
        return None
    if len(selected) != len(populations) - len(groups):
        raise AssertionError("Population-aware forest contains a cycle or missing connection.")
    return selected, groups


def select_population_aware_forest(
    populations: Sequence[int], links: Sequence[dict[str, Any]], district_count: int,
    *, population_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Enumerate small-island attachments and root mergers, then choose distance.

Only an original component above (1-tolerance)*ideal is a protected root.
Aggregating smaller islands never creates another protected root. We maximize
the number of retained root groups that pass population feasibility, then pick
the shortest forest among the deterministic constrained-Kruskal candidates.
"""
    pops = _validate_numbers(populations, district_count, population_tolerance)
    positive = tuple(index for index, population in enumerate(pops) if population > 0)
    if len(positive) > MAX_POPULATED_COMPONENTS:
        raise ValueError(f"This bounded Hawaii policy supports at most {MAX_POPULATED_COMPONENTS} populated source components.")
    tolerance = Fraction(str(population_tolerance))
    ideal = Fraction(sum(pops), district_count)
    roots = tuple(index for index in positive if pops[index] >= (1 - tolerance) * ideal)
    # A one-district state, for example, can have no individually eligible root.
    # Joining all components is explicit, rather than silently dropping islands.
    root_partitions = tuple(_partitions(roots)) if roots else ((positive,),)
    small = tuple(index for index in positive if index not in roots) if roots else ()
    candidates = []
    pair_ids: set[tuple[int, int]] = set()
    link_ids: set[str] = set()
    for link in links:
        pair = link.get("component_ids")
        if not isinstance(pair, (tuple, list)) or len(pair) != 2 or any(
            isinstance(i, bool) or not isinstance(i, Integral) or not 0 <= i < len(pops) for i in pair
        ) or pair[0] == pair[1]:
            raise ValueError("Candidate connections must name two distinct existing components.")
        pair_key = tuple(sorted(map(int, pair)))
        distance = link.get("distance_m")
        if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance <= 0:
            raise ValueError("Candidate water gaps must have a positive finite distance.")
        if not isinstance(link.get("id"), str) or not link["id"] or link["id"] in link_ids or pair_key in pair_ids:
            raise ValueError("Candidate IDs and component pairs must be unique.")
        pair_ids.add(pair_key)
        link_ids.add(link["id"])
        candidates.append(link)
    candidates.sort(key=lambda row: (row["distance_m"], *sorted(row["component_ids"]), row["id"]))
    chosen = None
    counts = {"groupings_examined": 0, "population_feasible_groupings": 0, "geometrically_unconnectable_groupings": 0}
    for root_partition in root_partitions:
        if len(root_partition) > district_count:
            continue
        for targets in product(range(len(root_partition)), repeat=len(small)):
            groups = [list(group) for group in root_partition]
            for component, target in zip(small, targets, strict=True):
                groups[target].append(component)
            positive_groups = tuple(sorted(tuple(sorted(group)) for group in groups))
            counts["groupings_examined"] += 1
            bound = population_allocation_bound([sum(pops[i] for i in group) for group in positive_groups], district_count)
            if not bound["feasible_seat_allocation"] or Fraction(*bound["deviation_fraction"]) > tolerance:
                continue
            counts["population_feasible_groupings"] += 1
            forest = _forest(pops, positive_groups, candidates)
            if forest is None:
                counts["geometrically_unconnectable_groupings"] += 1
                continue
            selected, complete_groups = forest
            length = math.fsum(link["distance_m"] for link in selected)
            key = (-len(groups), length, tuple(link["id"] for link in selected), positive_groups)
            if chosen is None or key < chosen[0]:
                chosen = (key, selected, complete_groups, bound)
    if chosen is None:
        raise ValueError("No population-compatible forest can connect the source components using permitted positive-length water gaps.")
    _, selected, groups, bound = chosen
    return {
        "policy": POLICY, "district_count": district_count,
        "population_tolerance": population_tolerance, "ideal_population": float(ideal),
        "minimum_root_population": float((1 - tolerance) * ideal),
        "eligible_root_component_ids": list(roots),
        "no_individual_root_fallback": not bool(roots),
        "selected_link_ids": [link["id"] for link in selected],
        "selected_total_distance_m": math.fsum(link["distance_m"] for link in selected),
        "groups": [{"group_id": index, "component_ids": members, "population": sum(pops[i] for i in members),
                    "root_component_ids": [root for root in roots if root in members],
                    "district_count": bound["seat_counts"][index]}
                   for index, members in enumerate(groups)],
        "population_bound": bound,
        "selection_priority": ["Retain the most independently population-compatible original root groups.",
                               "Minimize total length among deterministic constrained-Kruskal forests for those feasible groupings.",
                               "Break ties by stable candidate IDs and component IDs."],
        "distance_optimality": "Best among enumerated constrained-Kruskal forests, not a globally optimal geometric or Steiner forest.",
        "population_guarantee": "Necessary group-allocation test only; actual whole-block balance and same-district connectivity require solving and independent validation.",
        **counts,
    }


def _read_parts(path: Path, geoids: tuple[str, ...], graph: PartGraph) -> list[Any]:
    indices = {geoid: index for index, geoid in enumerate(geoids)}
    by_unit: list[list[Any] | None] = [None] * len(geoids)
    with shapefile.Reader(str(path)) as reader:
        if "GEOID20" not in [field[0] for field in reader.fields[1:]]:
            raise ValueError("Source shapefile is missing GEOID20.")
        for record in reader.iterShapeRecords():
            geoid = str(record.record["GEOID20"])
            if geoid not in indices or by_unit[indices[geoid]] is not None:
                raise ValueError("Source GEOIDs must match the unique requested blocks.")
            geometry = shape(record.shape.__geo_interface__)
            if geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon") or not geometry.is_valid:
                raise ValueError(f"Invalid or nonpolygonal source geometry {geoid}.")
            by_unit[indices[geoid]] = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    if any(parts is None for parts in by_unit):
        raise ValueError("Source is missing requested GEOIDs.")
    parts, owners = [], []
    for unit, unit_parts in enumerate(by_unit):
        assert unit_parts is not None
        parts.extend(unit_parts)
        owners.extend([unit] * len(unit_parts))
    if tuple(owners) != graph.part_to_unit:
        raise ValueError("Part graph ownership/order differs from exact source geometry.")
    bounds = shapely.total_bounds(parts)
    if not np.all(np.isfinite(bounds)) or not (
        bounds[0] >= HAWAII_EXTENT[0] and bounds[1] >= HAWAII_EXTENT[1]
        and bounds[2] <= HAWAII_EXTENT[2] and bounds[3] <= HAWAII_EXTENT[3]
    ):
        raise ValueError("Source geometry is outside the supported Hawaii extent; antimeridian geometry is unsupported.")
    return parts


def _great_circle_m(a: Sequence[float], b: Sequence[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def build_hawaii_connections(
    shapefile_path: Path, geoids: Sequence[str], populations: Sequence[int], part_graph: PartGraph,
    *, district_count: int, population_tolerance: float = 0.01,
) -> tuple[PartGraph, tuple[dict[str, Any], ...], dict[str, Any]]:
    """Validate source geometry and return augmented part graph, links, and audit.

Candidate endpoints minimize a per-pair equirectangular boundary gap. Their
reported length is spherical great-circle distance, not a certified shortest
geodesic, a shoreline distance, or an actual bridge/ferry route. Connections
crossing an unrelated source component's interior are excluded.
"""
    started = time.perf_counter()
    ordered = tuple(geoids)
    if not ordered or len(set(ordered)) != len(ordered) or any(
        not isinstance(g, str) or len(g) != 15 or not g.isascii() or not g.isdigit() or not g.startswith("15")
        for g in ordered
    ):
        raise ValueError("GEOIDs must be unique 15-digit Hawaii (15) blocks.")
    if len(ordered) != len(part_graph.unit_to_parts) or len(populations) != len(ordered):
        raise ValueError("GEOIDs, populations, and whole-block ownership counts must match.")
    pops = _validate_numbers(populations, district_count, population_tolerance)
    if district_count > len(ordered):
        raise ValueError("District count cannot exceed the number of whole blocks.")
    path = Path(shapefile_path)
    source_parts = _read_parts(path, ordered, part_graph)
    physical_helpers._verify_physical_graph(source_parts, part_graph)
    components, membership = physical_helpers._components(part_graph)
    component_units: list[list[int]] = [[] for _ in components]
    for unit, nodes in enumerate(part_graph.unit_to_parts):
        owners = {membership[node] for node in nodes}
        if len(owners) != 1:
            raise ValueError(f"Block {ordered[unit]} spans physical components; common ownership cannot supply a connection.")
        component_units[owners.pop()].append(unit)
    component_pops = [sum(pops[unit] for unit in units) for units in component_units]
    geometries = [shapely.union_all([source_parts[node] for node in nodes]) for nodes in components]
    if any(g.is_empty or not g.is_valid or g.geom_type != "Polygon" for g in geometries):
        raise ValueError("A source component did not independently dissolve to one valid polygon.")
    provenance = {
        "policy": POLICY, "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "physical_validation_helpers_sha256": hashlib.sha256(Path(physical_helpers.__file__).read_bytes()).hexdigest(),
        "source_files_sha256": {suffix: hashlib.sha256(path.with_suffix(suffix).read_bytes()).hexdigest()
                                for suffix in (".shp", ".shx", ".dbf")},
        "shapely_version": shapely.__version__, "geos_version": shapely.geos_version_string,
    }
    links, excluded = [], []
    for first in range(len(components)):
        for second in range(first + 1, len(components)):
            bounds = shapely.total_bounds([geometries[first], geometries[second]])
            lon0, lat0 = float(bounds[0] + bounds[2]) / 2, float(bounds[1] + bounds[3]) / 2
            ys = EARTH_RADIUS_M * math.pi / 180
            xs = ys * math.cos(math.radians(lat0))
            projected = [affine_transform(geometries[i], [xs, 0, 0, ys, -lon0 * xs, -lat0 * ys]) for i in (first, second)]
            a, b = nearest_points(projected[0].boundary, projected[1].boundary)
            planar = float(a.distance(b))
            if planar <= 0:
                excluded.append({"component_ids": [first, second], "reason": "zero-distance corner contact is not a water gap"})
                continue
            endpoints = [physical_helpers._endpoint(Point(point.x / xs + lon0, point.y / ys + lat0), components[component],
                                                   source_parts, part_graph, ordered)
                         for point, component in ((a, first), (b, second))]
            line = LineString([endpoint["coordinate"] for endpoint in endpoints])
            crossed = [i for i, geometry in enumerate(geometries) if i not in (first, second) and line.relate(geometry)[0] != "F"]
            if crossed:
                excluded.append({"component_ids": [first, second], "reason": "candidate line crosses unrelated source component interiors",
                                 "crossed_component_ids": crossed})
                continue
            links.append({"id": f"hi-candidate-{first:02d}-{second:02d}", "component_ids": [first, second],
                          "distance_m": _great_circle_m(endpoints[0]["coordinate"], endpoints[1]["coordinate"]),
                          "planar_candidate_distance_m": planar, "endpoints": endpoints,
                          "projection": {"kind": "per-pair-bbox-centered-equirectangular", "lon0": lon0, "lat0": lat0,
                                         "earth_radius_m": EARTH_RADIUS_M}})
    selection = select_population_aware_forest(component_pops, links, district_count, population_tolerance=population_tolerance)
    by_id = {link["id"]: link for link in links}
    rows = [set(neighbors) for neighbors in part_graph.adjacency]
    records = []
    for candidate_id in selection["selected_link_ids"]:
        candidate = by_id[candidate_id]
        a, b = (endpoint["part_node"] for endpoint in candidate["endpoints"])
        rows[a].add(b)
        rows[b].add(a)
        records.append({**candidate, "id": f"hi-water-{len(records) + 1:03d}", "candidate_id": candidate_id,
                        "state_fips": "15", "kind": "recorded-water-connection",
                        "distance_definition": "Spherical endpoint length of a per-pair planar nearest-boundary candidate in water-inclusive census coverage.",
                        "provenance": provenance})
    augmented = PartGraph(tuple(tuple(sorted(row)) for row in rows), part_graph.part_to_unit)
    resulting, result_membership = physical_helpers._components(augmented)
    if len(resulting) != len(selection["groups"]) or len(records) != len(components) - len(resulting):
        raise AssertionError("Augmented source-part forest does not match its audited grouping.")
    for group in selection["groups"]:
        labels = {result_membership[node] for component in group["component_ids"] for node in components[component]}
        if len(labels) != 1:
            raise AssertionError("Population group is disconnected in the constructed part graph.")
        group["augmented_component_id"] = labels.pop()
    audit = {
        "schema_version": 1, "policy": POLICY, "state_fips": "15", "district_count": district_count,
        "source_geometry_modified": False, "synthetic_ownership_edges": False, "source_population": sum(pops),
        "block_count": len(ordered), "part_count": len(source_parts), "physical_component_count": len(components),
        "physical_edge_count": sum(map(len, part_graph.adjacency)) // 2,
        "synthetic_edge_count": len(records), "augmented_edge_count": sum(map(len, augmented.adjacency)) // 2,
        "augmented_component_count": len(resulting), "augmented_graph_connected": len(resulting) == 1,
        "eligible_root_count": len(selection["eligible_root_component_ids"]),
        "groups": selection["groups"], "population_selection": selection,
        "components": [{"component_id": index, "population": component_pops[index], "part_count": len(nodes),
                        "block_count": len(component_units[index]), "eligible_root": index in selection["eligible_root_component_ids"]}
                       for index, nodes in enumerate(components)],
        "candidate_count": len(links), "candidate_connections": links,
        "excluded_candidates": excluded, "provenance": provenance,
        "endpoint_tolerance_degrees": 1e-9, "elapsed_seconds": time.perf_counter() - started,
    }
    return augmented, tuple(records), audit
