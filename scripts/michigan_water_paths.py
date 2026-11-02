"""Explain saved Michigan water-block adjacency without changing a plan.

The nodes being connected are *physical Polygon components* of the exact display
geometry, not whole census-block IDs. A multipart land block does not connect its
parts. Paths contain only same-district, zero-land Polygon blocks between their
two land-bearing endpoints. The returned lines are schematic illustrations of
those verified paths, not bridges, travel routes, or additional policy edges.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep
from shapely.strtree import STRtree


@dataclass(frozen=True)
class _Seed:
    component: int
    land_node: int
    land_part: int
    coordinate: tuple[float, float]


def _polygon_parts(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    raise ValueError("A source block must contain Polygon parts only.")


def _edge_point(left: BaseGeometry, right: BaseGeometry) -> tuple[float, float]:
    if not left.relate_pattern(right, "F***1****"):
        raise ValueError("A cached edge is not an exact shared-edge connection.")
    edge = left.boundary.intersection(right.boundary)
    # Some adjacent blocks also touch at isolated corners elsewhere, yielding a
    # GeometryCollection of lines and points. Pick a deterministic real edge.
    def lines(geometry: BaseGeometry) -> list[BaseGeometry]:
        if geometry.geom_type in ("LineString", "LinearRing"):
            return [geometry]
        return [line for part in getattr(geometry, "geoms", ()) for line in lines(part)]
    shared_lines = lines(edge)
    if not shared_lines:
        raise ValueError("A shared edge has no linear geometry.")
    segment = sorted(shared_lines, key=lambda line: (-line.length, line.bounds, line.wkb))[0]
    point = segment.interpolate(0.5, normalized=True)
    return float(point.x), float(point.y)


def derive_water_paths(
    land_parts_by_district: Mapping[int, Sequence[Polygon]],
    water_geometries: Mapping[int, Polygon],
    block_geometry: Callable[[int], BaseGeometry],
    geoids: Sequence[str],
    land_area: np.ndarray,
    assignments: np.ndarray,
    adjacency: Sequence[Sequence[int]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return a deterministic connecting forest and its independent audit.

    ``land_parts_by_district`` must be the exact, unsimplified components after
    removing zero-land block geometry. Its list order supplies stable component
    IDs. ``adjacency`` uses source DBF order, already pinned by the caller. Every
    edge this helper actually uses is checked again against source coordinates.

    A multi-source BFS through water blocks supplies candidate paths. Kruskal
    selects a minimum-edge-count connecting forest, preferring fewer water
    blocks and then stable source IDs. This is not a geographic-distance optimum.
    Unexplained components are explicitly reported; callers must not publish
    such a forest as a certificate that all display components are explained.
    """
    size = len(geoids)
    if len(land_area) != size or len(assignments) != size or len(adjacency) != size:
        raise ValueError("Source geometry, assignment and graph sizes disagree.")
    if len(set(geoids)) != size:
        raise ValueError("Source block IDs must be unique.")
    water_nodes = set(map(int, np.flatnonzero(np.asarray(land_area) == 0)))
    if set(water_geometries) != water_nodes:
        raise ValueError("Every zero-land source block needs its exact geometry.")
    for node, geometry in water_geometries.items():
        if not isinstance(geometry, Polygon) or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Water block {geoids[node]} must be a valid single Polygon.")
    if not set(map(int, assignments)).issubset(land_parts_by_district):
        raise ValueError("An assigned district has no land-display component list.")

    features: list[dict[str, Any]] = []
    district_audits: list[dict[str, Any]] = []
    exact_edges: set[tuple[int, int]] = set()
    geometry_cache: dict[int, BaseGeometry] = {}

    def source_geometry(node: int) -> BaseGeometry:
        if node in water_geometries:
            return water_geometries[node]
        if node not in geometry_cache:
            geometry_cache[node] = block_geometry(node)
        return geometry_cache[node]

    def verify_water_edge(left: int, right: int) -> None:
        key = min(left, right), max(left, right)
        if key not in exact_edges:
            _edge_point(source_geometry(left), source_geometry(right))
            exact_edges.add(key)

    for district, supplied_parts in sorted(land_parts_by_district.items()):
        parts = list(supplied_parts)
        if not parts or any(not isinstance(part, Polygon) or part.is_empty or not part.is_valid for part in parts):
            raise ValueError(f"District {district} needs valid exact display Polygon components.")
        tree = STRtree(parts)
        prepared_parts = [prep(part) for part in parts]
        part_labels: dict[tuple[int, int], int] = {}
        district_water = sorted((node for node in water_nodes if int(assignments[node]) == district), key=lambda node: geoids[node])
        seeds: dict[int, list[_Seed]] = {}
        water_neighbors: dict[int, list[int]] = {}

        def label_land_part(node: int, part_index: int, part: Polygon) -> int:
            key = node, part_index
            if key in part_labels:
                return part_labels[key]
            # Locate by an interior point, then prove the *entire* source part
            # belongs to that component. Prepared predicates avoid repeatedly
            # overlaying a tiny shoreline block with a million-vertex mainland.
            point = part.representative_point()
            matches = [int(index) for index in tree.query(point)
                       if prepared_parts[int(index)].covers(point)]
            if len(matches) != 1:
                raise ValueError(f"Endpoint part of {geoids[node]} does not belong to exactly one display component.")
            label = matches[0]
            if not prepared_parts[label].covers(part):
                raise ValueError(f"Endpoint part of {geoids[node]} is not wholly within its display component.")
            part_labels[key] = label
            return label

        for water in district_water:
            water_shape = water_geometries[water]
            endpoints: dict[int, _Seed] = {}
            neighbors: list[int] = []
            for neighbor_value in adjacency[water]:
                neighbor = int(neighbor_value)
                if neighbor < 0 or neighbor >= size or neighbor == water:
                    raise ValueError("The cached graph contains an invalid node index.")
                if int(assignments[neighbor]) != district:
                    continue
                if neighbor in water_nodes:
                    verify_water_edge(water, neighbor)
                    neighbors.append(neighbor)
                    continue
                touched = False
                for part_index, part in enumerate(_polygon_parts(source_geometry(neighbor))):
                    if not part.relate_pattern(water_shape, "F***1****"):
                        continue
                    touched = True
                    label = label_land_part(neighbor, part_index, part)
                    seed = _Seed(label, neighbor, part_index, _edge_point(part, water_shape))
                    previous = endpoints.get(label)
                    if previous is None or (geoids[neighbor], part_index, seed.coordinate) < (geoids[previous.land_node], previous.land_part, previous.coordinate):
                        endpoints[label] = seed
                if not touched:
                    raise ValueError(f"Cached land/water edge at {geoids[neighbor]} has no actual shared-edge part.")
            seeds[water] = sorted(endpoints.values(), key=lambda seed: (seed.component, geoids[seed.land_node], seed.land_part))
            water_neighbors[water] = sorted(set(neighbors), key=lambda node: geoids[node])

        owners: dict[int, _Seed] = {}
        parents: dict[int, int | None] = {}
        queue: deque[int] = deque()
        # A candidate is (start seed, path of water nodes, end seed).
        candidates: dict[tuple[int, int, tuple[str, ...]], tuple[_Seed, list[int], _Seed]] = {}

        def chain(node: int) -> list[int]:
            result = [node]
            while parents[result[-1]] is not None:
                result.append(int(parents[result[-1]]))
            return result[::-1]

        def add_candidate(left: _Seed, path: list[int], right: _Seed) -> None:
            if left.component == right.component:
                return
            if left.component > right.component:
                left, right = right, left
                path = path[::-1]
            if len(set(path)) != len(path):
                raise ValueError("A derived water path revisits a water block.")
            block_ids = (geoids[left.land_node], *(geoids[node] for node in path), geoids[right.land_node])
            candidates[left.component, right.component, block_ids] = left, path, right

        for water in district_water:
            if not seeds[water]:
                continue
            owner = seeds[water][0]
            owners[water] = owner
            parents[water] = None
            queue.append(water)
            for other in seeds[water][1:]:
                add_candidate(owner, [water], other)
        while queue:
            water = queue.popleft()
            for neighbor in water_neighbors[water]:
                if neighbor not in owners:
                    owners[neighbor] = owners[water]
                    parents[neighbor] = water
                    queue.append(neighbor)
                elif owners[neighbor].component != owners[water].component:
                    add_candidate(owners[water], chain(water) + chain(neighbor)[::-1], owners[neighbor])

        roots = list(range(len(parts)))

        def find(label: int) -> int:
            while roots[label] != label:
                roots[label] = roots[roots[label]]
                label = roots[label]
            return label

        selected: list[tuple[_Seed, list[int], _Seed]] = []
        ordered = sorted(candidates.values(), key=lambda value: (len(value[1]), value[0].component, value[2].component,
                         geoids[value[0].land_node], tuple(geoids[node] for node in value[1]), geoids[value[2].land_node]))
        for left, path, right in ordered:
            left_root, right_root = find(left.component), find(right.component)
            if left_root == right_root:
                continue
            roots[max(left_root, right_root)] = min(left_root, right_root)
            selected.append((left, path, right))
        group_count = len({find(label) for label in range(len(parts))})
        for index, (left, path, right) in enumerate(selected):
            block_path = [left.land_node, *path, right.land_node]
            if any(int(assignments[node]) != district for node in block_path):
                raise ValueError("A derived path crosses a saved district assignment.")
            coordinates = [list(left.coordinate)]
            # Shared-boundary points explain source adjacency; straight segments
            # through concave water cells remain schematic, not contained routes.
            for a, b in zip(path, path[1:]):
                coordinates.append(list(_edge_point(water_geometries[a], water_geometries[b])))
            coordinates.append(list(right.coordinate))
            features.append({
                "type": "Feature",
                "properties": {
                    "id": f"mi-derived-d{district + 1:03d}-{index + 1:03d}",
                    "kind": "derived-water-adjacency",
                    "district_id": district,
                    "block_path": [geoids[node] for node in block_path],
                    "water_block_count": len(path),
                    "land_component_ids": [left.component, right.component],
                    "endpoints": [{"geoid": geoids[seed.land_node], "coordinate": list(seed.coordinate),
                                   "source_polygon_part": seed.land_part, "land_component_id": seed.component}
                                  for seed in (left, right)],
                    "proof": "Same-district path; every consecutive source Polygon part shares a positive-length edge; all interior blocks have ALAND20=0.",
                    "schematic": True,
                    "interpretation": "Display illustration of saved census water adjacency, not a new policy connection or travel route.",
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            })
        district_audits.append({
            "district_id": district,
            "land_component_count": len(parts),
            "water_block_count": len(district_water),
            "water_blocks_reached_from_land": len(owners),
            "candidate_path_count": len(candidates),
            "derived_connection_count": len(selected),
            "remaining_component_groups": group_count,
            "all_components_explained": group_count == 1,
        })
    return features, {
        "method": "Exact display Polygon components; same-district zero-land-block multi-source BFS and deterministic connecting forest.",
        "line_interpretation": "Schematic saved-adjacency illustrations, not bridges, travel routes or policy edges.",
        "derived_connection_count": len(features),
        "all_components_explained": all(value["all_components_explained"] for value in district_audits),
        "districts": district_audits,
    }
