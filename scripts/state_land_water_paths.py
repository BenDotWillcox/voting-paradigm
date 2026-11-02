"""Display-only explanations of accepted census-water and recorded connectivity.

Each zero-land Polygon part is a separate physical node. Recorded edges are
never inserted into a path described as shared-edge adjacency: their unchanged
endpoint coordinates become terminals, and the original edges participate only
in the separate combined-connectivity audit. Lines are schematic, not routes.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep
from shapely.strtree import STRtree

from scripts.michigan_water_paths import _edge_point, _polygon_parts

PartKey = tuple[int, int]


class _Union:
    def __init__(self, values: Sequence[Any]) -> None:
        self.roots = {value: value for value in values}

    def find(self, value: Any) -> Any:
        while self.roots[value] != value:
            self.roots[value] = self.roots[self.roots[value]]
            value = self.roots[value]
        return value

    def join(self, left: Any, right: Any) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.roots[b] = a

    def groups(self, values: Sequence[Any] | None = None) -> int:
        return len({self.find(value) for value in (self.roots if values is None else values)})


@dataclass(frozen=True)
class _Seed:
    terminal: int
    source: PartKey
    coordinate: tuple[float, float]
    recorded_link_id: str | None = None
    recorded_endpoint_index: int | None = None


def derive_state_water_paths(
    land_parts_by_district: Mapping[int, Sequence[Polygon]],
    water_geometries: Mapping[int, BaseGeometry],
    block_geometry: Callable[[int], BaseGeometry],
    geoids: Sequence[str],
    land_area: np.ndarray,
    assignments: np.ndarray,
    adjacency: Sequence[Sequence[int]] | Callable[[int], Sequence[int]],
    recorded_connections: dict[str, Any] | None = None,
    state_fips: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return physical derived paths and an independent source/component audit.

    ``adjacency`` may be broad source-bounding-box candidates, not certified
    edges. All candidate Polygon parts are tested with exact ``F***1****``;
    corner contacts and bbox false positives are skipped. Candidate coverage is
    the caller's responsibility. Geometry, records and endpoints must already
    share the accepted working coordinate frame (continuous longitude in AK).

    A physical connecting forest joins visible land components and any recorded
    endpoints in hidden water. The original recorded lines are neither emitted
    nor altered. Cross-district recorded links remain unused for connectivity.
    An isolated all-water component is audited even though it has no visible
    land, so removing it cannot conceal a disconnected or populated source part.
    """
    size = len(geoids)
    if len(land_area) != size or len(assignments) != size or (not callable(adjacency) and len(adjacency) != size):
        raise ValueError("Source geometry, assignments and candidate graph sizes disagree.")
    if len(set(geoids)) != size:
        raise ValueError("Source block IDs must be unique.")
    if any(not isinstance(v, (int, np.integer)) or int(v) < 0 for v in assignments):
        raise ValueError("Assignments must be nonnegative integer district IDs.")
    if not set(map(int, assignments)).issubset(land_parts_by_district):
        raise ValueError("An assigned district has no land-display component list.")
    water_nodes = set(map(int, np.flatnonzero(np.asarray(land_area) == 0)))
    if set(water_geometries) != water_nodes:
        raise ValueError("Every zero-land source block needs its exact geometry.")
    geoid_index = {geoid: index for index, geoid in enumerate(geoids)}

    @lru_cache(maxsize=2048)
    def source_parts(node: int) -> tuple[Polygon, ...]:
        geometry = water_geometries[node] if node in water_nodes else block_geometry(node)
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Source block {geoids[node]} must be nonempty and valid.")
        return tuple(_polygon_parts(geometry))

    water_parts = {(node, part): shape for node in sorted(water_nodes)
                   for part, shape in enumerate(source_parts(node))}

    def shape_of(key: PartKey) -> Polygon:
        return water_parts[key] if key in water_parts else source_parts(key[0])[key[1]]

    def order(key: PartKey) -> tuple[str, int]:
        return geoids[key[0]], key[1]

    def physical_node(key: PartKey) -> tuple[str, int, int]:
        return "water", key[0], key[1]

    # Parse all saved endpoints independently of any display path selection.
    parsed_links: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    collection = recorded_connections or {"type": "FeatureCollection", "features": []}
    if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
        raise ValueError("Recorded connections must be their accepted FeatureCollection.")
    for feature in collection["features"]:
        props = feature.get("properties", {})
        identifier = props.get("id", feature.get("id"))
        geometry = feature.get("geometry", {})
        endpoints = props.get("endpoints")
        coordinates = geometry.get("coordinates")
        if not isinstance(identifier, str) or not identifier or identifier in seen_ids:
            raise ValueError("Recorded connection IDs must be unique nonempty strings.")
        seen_ids.add(identifier)
        if geometry.get("type") != "LineString" or not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError(f"Recorded connection {identifier} needs its unchanged working LineString.")
        if not isinstance(endpoints, list) or len(endpoints) != 2:
            raise ValueError(f"Recorded connection {identifier} needs two exact source endpoints.")
        parsed = []
        for side, endpoint in enumerate(endpoints):
            node = geoid_index.get(endpoint.get("geoid"))
            part = endpoint.get("part_index", endpoint.get("source_polygon_part"))
            coordinate = endpoint.get("coordinate")
            if node is None or not isinstance(part, int) or isinstance(part, bool) or not 0 <= part < len(source_parts(node)):
                raise ValueError(f"Recorded endpoint {identifier}/{side} has no valid source Polygon part.")
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2 or not all(np.isfinite(v) for v in coordinate):
                raise ValueError(f"Recorded endpoint {identifier}/{side} has invalid coordinates.")
            point = tuple(map(float, coordinate))
            line_point = tuple(map(float, coordinates[0 if side == 0 else -1]))
            if point != line_point:
                raise ValueError(f"Recorded endpoint {identifier}/{side} differs from its preserved line.")
            # Accepted inverse-projection endpoints can be roundoff off-boundary.
            # This tolerance only validates evidence; coordinates are never moved.
            error = source_parts(node)[part].boundary.distance(Point(point))
            if error > 1e-9:
                raise ValueError(f"Recorded endpoint {identifier}/{side} is off its source boundary ({error:g} degrees).")
            parsed.append({"key": (node, part), "coordinate": point,
                           "district": int(assignments[node]), "boundary_error_degrees": float(error)})
        actual_districts = [p["district"] for p in parsed]
        if "endpoint_districts" in props and props["endpoint_districts"] != actual_districts:
            raise ValueError(f"Recorded connection {identifier} contradicts saved assignments.")
        if "used_by_district" in props:
            expected = actual_districts[0] if actual_districts[0] == actual_districts[1] else None
            if props["used_by_district"] != expected:
                raise ValueError(f"Recorded connection {identifier} has stale same-district ownership.")
        parsed_links.append({"id": identifier, "endpoints": parsed})
    parsed_links.sort(key=lambda value: value["id"])

    features: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    recorded_audits: dict[str, dict[str, Any]] = {}
    for link in parsed_links:
        recorded_audits[link["id"]] = {
            "id": link["id"], "endpoint_districts": [p["district"] for p in link["endpoints"]],
            "used_in_combined_audit": link["endpoints"][0]["district"] == link["endpoints"][1]["district"],
            "endpoints": [],
        }

    for district, supplied in sorted(land_parts_by_district.items()):
        parts = list(supplied)
        if not parts or any(not isinstance(part, Polygon) or part.is_empty or not part.is_valid for part in parts):
            raise ValueError(f"District {district} has no valid retained land components; an explicit display fallback is required.")
        tree = STRtree(parts)
        prepared = [prep(part) for part in parts]
        labels: dict[PartKey, int] = {}

        def land_label(key: PartKey) -> int:
            if key in labels:
                return labels[key]
            part = shape_of(key)
            point = part.representative_point()
            matches = [int(i) for i in tree.query(point) if prepared[int(i)].covers(point)]
            if len(matches) != 1 or not prepared[matches[0]].covers(part):
                raise ValueError(f"Source part {geoids[key[0]]}/{key[1]} is not wholly within one exact display component.")
            labels[key] = matches[0]
            return matches[0]

        waters = sorted((key for key in water_parts if int(assignments[key[0]]) == district), key=order)
        seeds: dict[PartKey, dict[int, _Seed]] = {key: {} for key in waters}
        neighbors: dict[PartKey, set[PartKey]] = {key: set() for key in waters}
        physical_edges: dict[tuple[PartKey, PartKey], tuple[float, float]] = {}
        physical = _Union([*(('land', i) for i in range(len(parts))), *(physical_node(key) for key in waters)])

        def seed_order(seed: _Seed) -> tuple[Any, ...]:
            return (*order(seed.source), seed.coordinate, seed.recorded_link_id or "", seed.recorded_endpoint_index or 0)

        def add_seed(water: PartKey, seed: _Seed) -> None:
            previous = seeds[water].get(seed.terminal)
            if previous is None or seed_order(seed) < seed_order(previous):
                seeds[water][seed.terminal] = seed

        candidates_by_block: dict[int, list[int]] = {}
        for water in waters:
            node = water[0]
            if node not in candidates_by_block:
                values = adjacency(node) if callable(adjacency) else adjacency[node]
                candidates = sorted(set(map(int, values)))
                if any(value < 0 or value >= size for value in candidates):
                    raise ValueError("Source candidate graph has an invalid block index.")
                candidates_by_block[node] = candidates
            water_shape = water_parts[water]
            for other_node in candidates_by_block[node]:
                if other_node == node or int(assignments[other_node]) != district:
                    continue
                for part_index, part in enumerate(source_parts(other_node)):
                    other = other_node, part_index
                    if other_node in water_nodes and order(other) < order(water):
                        continue
                    if not water_shape.relate_pattern(part, "F***1****"):
                        continue
                    coordinate = _edge_point(water_shape, part)
                    if other_node in water_nodes:
                        neighbors[water].add(other)
                        neighbors[other].add(water)
                        physical_edges[tuple(sorted((water, other)))] = coordinate
                        physical.join(physical_node(water), physical_node(other))
                    else:
                        label = land_label(other)
                        add_seed(water, _Seed(label, other, coordinate))
                        physical.join(physical_node(water), ('land', label))

        # Source endpoint nodes are mapped before adding policy edges. Their
        # labels remain distinct until exact physical connectivity proves them.
        terminal_count = len(parts)
        policy_terminals: dict[tuple[str, int], int] = {}
        policy_source_nodes: dict[tuple[str, int], Any] = {}
        for link in parsed_links:
            for side, endpoint in enumerate(link["endpoints"]):
                if endpoint["district"] != district:
                    continue
                key = endpoint["key"]
                if key in water_parts:
                    terminal = terminal_count
                    terminal_count += 1
                    add_seed(key, _Seed(terminal, key, endpoint["coordinate"], link["id"], side))
                    policy_source_nodes[link["id"], side] = physical_node(key)
                    component = None
                else:
                    terminal = land_label(key)
                    component = terminal
                    policy_source_nodes[link["id"], side] = ('land', terminal)
                policy_terminals[link["id"], side] = terminal
                recorded_audits[link["id"]]["endpoints"].append({
                    "index": side, "district_id": district, "geoid": geoids[key[0]],
                    "source_polygon_part": key[1], "coordinate": list(endpoint["coordinate"]),
                    "water_only": key in water_parts, "land_component_id": component,
                    "source_boundary_error_degrees": endpoint["boundary_error_degrees"],
                })

        owners: dict[PartKey, _Seed] = {}
        parents: dict[PartKey, PartKey | None] = {}
        queue: deque[PartKey] = deque()
        paths: dict[tuple[Any, ...], tuple[_Seed, list[PartKey], _Seed]] = {}

        def chain(key: PartKey) -> list[PartKey]:
            result = [key]
            while parents[result[-1]] is not None:
                result.append(parents[result[-1]])  # type: ignore[arg-type]
            return result[::-1]

        def candidate(left: _Seed, path: list[PartKey], right: _Seed) -> None:
            if left.terminal == right.terminal:
                return
            if left.terminal > right.terminal:
                left, right, path = right, left, path[::-1]
            if len(path) != len(set(path)):
                raise ValueError("A physical water path revisits a Polygon part.")
            paths[left.terminal, right.terminal, tuple(path), left.source, right.source] = left, path, right

        for water in waters:
            available = sorted(seeds[water].values(), key=lambda seed: (seed.terminal, seed_order(seed)))
            if available:
                owners[water], parents[water] = available[0], None
                queue.append(water)
                for seed in available[1:]:
                    candidate(available[0], [water], seed)
        while queue:
            water = queue.popleft()
            for other in sorted(neighbors[water], key=order):
                if other not in owners:
                    owners[other], parents[other] = owners[water], water
                    queue.append(other)
                elif owners[water].terminal != owners[other].terminal:
                    candidate(owners[water], chain(water) + chain(other)[::-1], owners[other])

        selected = []
        forest = _Union(list(range(terminal_count)))
        for left, path, right in sorted(paths.values(), key=lambda value: (
            len(value[1]), value[0].terminal, value[2].terminal,
            seed_order(value[0]), tuple(map(order, value[1])), seed_order(value[2]),
        )):
            if forest.find(left.terminal) != forest.find(right.terminal):
                forest.join(left.terminal, right.terminal)
                selected.append((left, path, right))

        rendered = _Union(list(range(terminal_count)))
        feature_start = len(features)
        for index, (left, path, right) in enumerate(selected):
            source_path = ([] if left.recorded_link_id else [left.source]) + path + ([] if right.recorded_link_id else [right.source])
            # Recheck the selected proof without relying on BFS or source graph
            # labels. Never infer edges from a common whole-block identifier.
            if any(int(assignments[key[0]]) != district for key in source_path):
                raise ValueError("A derived path crosses accepted district assignments.")
            for a, b in zip(source_path, source_path[1:]):
                _edge_point(shape_of(a), shape_of(b))
            coordinates = [list(left.coordinate)]
            for a, b in zip(path, path[1:]):
                coordinates.append(list(physical_edges[tuple(sorted((a, b)))]))
            coordinates.append(list(right.coordinate))

            def endpoint(seed: _Seed) -> dict[str, Any]:
                value = {"kind": "land-component", "geoid": geoids[seed.source[0]],
                         "source_polygon_part": seed.source[1], "coordinate": list(seed.coordinate)}
                if seed.recorded_link_id is None:
                    value["land_component_id"] = seed.terminal
                else:
                    value.update(kind="recorded-connection-endpoint", recorded_link_id=seed.recorded_link_id,
                                 recorded_endpoint_index=seed.recorded_endpoint_index)
                return value

            features.append({
                "type": "Feature", "properties": {
                    "id": f"{state_fips or 'state'}-derived-d{district + 1:03d}-{index + 1:04d}",
                    "kind": "derived-water-adjacency", "derivation_schema_version": 2,
                    "district_id": district, "block_path": [geoids[key[0]] for key in source_path],
                    "source_part_path": [{"geoid": geoids[key[0]], "source_polygon_part": key[1],
                                          "water_only": key in water_parts} for key in source_path],
                    "water_block_count": sum(key in water_parts for key in source_path),
                    "land_component_ids": [seed.terminal if seed.recorded_link_id is None else None for seed in (left, right)],
                    "endpoints": [endpoint(left), endpoint(right)], "schematic": True,
                    "proof": "Same-district source Polygon-part path; each consecutive part shares a positive-length edge; every non-land endpoint/interior part has ALAND20=0. Recorded endpoint coordinates are unchanged; no recorded edge occurs inside this path.",
                    "interpretation": "Display illustration of saved physical census-water adjacency, not a new policy edge, land bridge, or travel route.",
                }, "geometry": {"type": "LineString", "coordinates": coordinates},
            })
            rendered.join(left.terminal, right.terminal)

        physical_source_groups = physical.groups()
        physical_land_groups = physical.groups([('land', index) for index in range(len(parts))])
        combined = _Union(list(physical.roots))
        for node in physical.roots:
            combined.join(node, physical.find(node))
        used_ids = []
        for link in parsed_links:
            if all(endpoint["district"] == district for endpoint in link["endpoints"]):
                used_ids.append(link["id"])
                combined.join(policy_source_nodes[link["id"], 0], policy_source_nodes[link["id"], 1])
                rendered.join(policy_terminals[link["id"], 0], policy_terminals[link["id"], 1])
        combined_groups = combined.groups()
        rendered_groups = rendered.groups()
        audits.append({
            "district_id": district, "land_component_count": len(parts),
            "water_block_count": len({key[0] for key in waters}), "water_polygon_part_count": len(waters),
            "water_parts_reached_from_land_or_recorded_endpoints": len(owners),
            "candidate_path_count": len(paths), "derived_connection_count": len(features) - feature_start,
            "physical_source_component_groups": physical_source_groups,
            "physical_land_component_groups": physical_land_groups,
            "recorded_connection_ids_used": used_ids,
            "combined_source_component_groups": combined_groups,
            "remaining_component_groups": rendered_groups,
            "all_components_explained": combined_groups == 1 and rendered_groups == 1,
        })

    for value in recorded_audits.values():
        value["endpoints"].sort(key=lambda endpoint: endpoint["index"])
    return features, {
        "method": "Exact Polygon-part physical graph; deterministic terminal connecting forest; separate original recorded-edge combined audit.",
        "derivation_schema_version": 2,
        "line_interpretation": "Schematic physical census-water adjacency and access to unchanged recorded endpoints; no new connectivity policy.",
        "derived_connection_count": len(features), "recorded_connection_count": len(parsed_links),
        "all_components_explained": all(value["all_components_explained"] for value in audits),
        "physical_shared_edge_only": all(value["physical_source_component_groups"] == 1 for value in audits),
        "recorded_connections": list(recorded_audits.values()), "districts": audits,
    }
