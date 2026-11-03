"""Explicit, auditable island exceptions to exact polygon-part connectivity.

This first adapter is scoped to Rhode Island. It never changes source geometry:
the returned graph contains the physical shared edges plus separately recorded
connections across gaps in the census coverage. These are policy connections,
not claims of a bridge, ferry route, land continuity, or a jurisdiction boundary.

Eligible components can each support at least the requested minimum district
population. A rooted minimum spanning forest joins every smaller component to
one eligible component, possibly through other small components. It does not
create shortcuts between two eligible roots. A future national policy needs
separate handling for states without an eligible root and nonlocal projections.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import math
from numbers import Integral
from pathlib import Path
import time
from typing import Any

import numpy as np
import shapefile
import shapely
from shapely.affinity import affine_transform
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

from districting.part_connectivity import PartGraph


_POLICY = "undersized-component-rooted-nearest-boundary-forest-v1"
_EARTH_RADIUS_M = 6_371_000.0
_ENDPOINT_TOLERANCE_DEGREES = 1e-9
_RI_EXTENT = (-72.1, 40.9, -70.5, 42.1)


def _components(graph: PartGraph) -> tuple[tuple[tuple[int, ...], ...], tuple[int, ...]]:
    """Stable IDs: largest part count first, then lowest source part index."""
    seen: set[int] = set()
    groups = []
    for start in range(len(graph.adjacency)):
        if start in seen:
            continue
        seen.add(start)
        pending, members = [start], []
        while pending:
            part = pending.pop()
            members.append(part)
            for neighbor in graph.adjacency[part]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        groups.append(tuple(sorted(members)))
    groups.sort(key=lambda members: (-len(members), members[0]))
    membership = [-1] * len(graph.adjacency)
    for component, members in enumerate(groups):
        for part in members:
            membership[part] = component
    return tuple(groups), tuple(membership)


def _read_parts(path: Path, geoids: tuple[str, ...], graph: PartGraph) -> list[Any]:
    indices = {geoid: index for index, geoid in enumerate(geoids)}
    by_unit: list[list[Any] | None] = [None] * len(geoids)
    with shapefile.Reader(str(path)) as reader:
        fields = [field[0] for field in reader.fields[1:]]
        if "GEOID20" not in fields:
            raise ValueError("Source shapefile is missing GEOID20.")
        geoid_index = fields.index("GEOID20")
        for record in reader.iterShapeRecords():
            geoid = str(record.record[geoid_index])
            if geoid not in indices:
                raise ValueError(f"Unexpected source GEOID {geoid!r}.")
            unit = indices[geoid]
            if by_unit[unit] is not None:
                raise ValueError(f"Duplicate source GEOID {geoid}.")
            geometry = shape(record.shape.__geo_interface__)
            if geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError(f"Empty or nonpolygonal source geometry {geoid}.")
            if not geometry.is_valid:
                raise ValueError(f"Invalid source geometry {geoid}.")
            by_unit[unit] = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    if any(parts is None for parts in by_unit):
        raise ValueError("Source is missing one or more requested GEOIDs.")
    parts, owners = [], []
    for unit, unit_parts in enumerate(by_unit):
        assert unit_parts is not None
        parts.extend(unit_parts)
        owners.extend([unit] * len(unit_parts))
    if tuple(owners) != graph.part_to_unit:
        raise ValueError("Part graph ownership/order differs from the exact source geometry.")
    bounds = shapely.total_bounds(parts)
    if not np.all(np.isfinite(bounds)) or not (
        bounds[0] >= _RI_EXTENT[0] and bounds[1] >= _RI_EXTENT[1]
        and bounds[2] <= _RI_EXTENT[2] and bounds[3] <= _RI_EXTENT[3]
    ):
        raise ValueError("Source geometry is outside this adapter's supported Rhode Island extent.")
    return parts


def _verify_physical_graph(parts: list[Any], graph: PartGraph) -> None:
    """Reject overlap, invented ownership edges, and omitted physical edges."""
    geometries = np.asarray(parts, dtype=object)
    tree = shapely.STRtree(geometries)
    actual = [set() for _ in parts]
    for start in range(0, len(parts), 2_000):
        pairs = tree.query(geometries[start : start + 2_000])
        left, right = pairs[0] + start, pairs[1]
        unique = left < right
        left, right = left[unique], right[unique]
        for first, second, relation in zip(
            left, right, shapely.relate(geometries[left], geometries[right]), strict=True,
        ):
            if relation[0] != "F":
                raise ValueError("Source polygon parts have overlapping interiors.")
            if relation[4] == "1":
                actual[int(first)].add(int(second))
                actual[int(second)].add(int(first))
    if any(neighbors != set(graph.adjacency[index]) for index, neighbors in enumerate(actual)):
        raise ValueError("Input part graph must exactly match source shared-edge geometry.")


def _endpoint(
    source_point: Point, members: tuple[int, ...], source_parts: list[Any],
    graph: PartGraph, geoids: tuple[str, ...],
) -> dict[str, Any]:
    candidates = [
        node for node in members
        if source_parts[node].boundary.distance(source_point) <= _ENDPOINT_TOLERANCE_DEGREES
    ]
    if not candidates:
        raise ValueError("Computed connection endpoint does not lie on a source part boundary.")
    # Boundary vertices can belong to several blocks; resolve their equal
    # physical endpoints by GEOID and original part order, independent of trees.
    node = min(candidates, key=lambda n: (geoids[graph.part_to_unit[n]], n))
    unit = graph.part_to_unit[node]
    return {
        "geoid": geoids[unit],
        "part_index": graph.unit_to_parts[unit].index(node),
        "part_node": node,
        "coordinate": [float(source_point.x), float(source_point.y)],
        "source_boundary_error_degrees": float(source_parts[node].boundary.distance(source_point)),
    }


def build_island_connections(
    shapefile_path: Path, geoids: Sequence[str], populations: Sequence[int], part_graph: PartGraph,
    *, state_fips: str, minimum_district_population: float,
) -> tuple[PartGraph, tuple[dict[str, Any], ...], dict[str, Any]]:
    """Return augmented graph, explicit connection records, and policy audit.

    Population remains at whole-block granularity. Any block whose parts span
    global physical components is rejected rather than guessed or double-counted.
    Distances use a bbox-centered local equirectangular metric (meters), followed
    by inverse affine projection to the unmodified source boundary coordinates.
    The forest is deterministic for fixed ordered source parts and library
    versions. Equal candidate distances use component IDs as a secondary key.
    """
    started = time.perf_counter()
    if state_fips != "44":
        raise ValueError("This island-connection adapter currently supports Rhode Island (44) only.")
    ordered = tuple(geoids)
    if not ordered or len(set(ordered)) != len(ordered) or any(
        not isinstance(g, str) or len(g) != 15 or not g.isascii() or not g.isdigit()
        or not g.startswith(state_fips) for g in ordered
    ):
        raise ValueError("GEOIDs must be unique 15-digit blocks in the requested state.")
    if len(ordered) != len(part_graph.unit_to_parts):
        raise ValueError("GEOID count differs from the graph's block ownership.")
    if len(populations) != len(ordered) or any(
        isinstance(p, bool) or not isinstance(p, Integral) or p < 0 for p in populations
    ):
        raise ValueError("Populations must be nonnegative integers, one per whole block.")
    minimum = float(minimum_district_population)
    if not math.isfinite(minimum) or minimum <= 0:
        raise ValueError("Minimum district population must be finite and positive.")
    pops = tuple(int(p) for p in populations)
    source_parts = _read_parts(Path(shapefile_path), ordered, part_graph)
    _verify_physical_graph(source_parts, part_graph)
    components, membership = _components(part_graph)
    component_units: list[list[int]] = [[] for _ in components]
    for unit, nodes in enumerate(part_graph.unit_to_parts):
        owners = {membership[node] for node in nodes}
        if len(owners) != 1:
            raise ValueError(
                f"Block {ordered[unit]} spans physical source components; common ownership "
                "cannot supply a geometric or island-policy connection."
            )
        component_units[owners.pop()].append(unit)
    component_pops = [sum(pops[unit] for unit in units) for units in component_units]
    roots = {index for index, population in enumerate(component_pops) if population >= minimum}
    if not roots:
        raise ValueError("No source component meets the minimum district population; policy needs an explicit root rule.")

    bounds = shapely.total_bounds(source_parts)
    lon0, lat0 = (float(bounds[0] + bounds[2]) / 2, float(bounds[1] + bounds[3]) / 2)
    y_scale = _EARTH_RADIUS_M * math.pi / 180
    x_scale = y_scale * math.cos(math.radians(lat0))
    component_geometries = [shapely.union_all([source_parts[n] for n in nodes]) for nodes in components]
    projected = [affine_transform(g, [x_scale, 0, 0, y_scale, -lon0*x_scale, -lat0*y_scale]) for g in component_geometries]
    if any(g.is_empty or not g.is_valid or g.geom_type != "Polygon" for g in component_geometries):
        raise ValueError("A physical part component did not independently dissolve to one valid polygon.")
    provenance = {
        "policy": _POLICY,
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_files_sha256": {
            suffix: hashlib.sha256(Path(shapefile_path).with_suffix(suffix).read_bytes()).hexdigest()
            for suffix in (".shp", ".shx", ".dbf")
        },
        "shapely_version": shapely.__version__,
        "geos_version": shapely.geos_version_string,
    }
    projection = {"kind": "bbox-centered-equirectangular", "lon0": lon0, "lat0": lat0,
                  "earth_radius_m": _EARTH_RADIUS_M, "x_scale": x_scale, "y_scale": y_scale}
    candidates = []
    zero_distance_pairs = []
    for first in range(len(components)):
        for second in range(first + 1, len(components)):
            if first in roots and second in roots:
                continue
            p, q = nearest_points(projected[first].boundary, projected[second].boundary)
            distance = float(p.distance(q))
            if distance <= 0:
                zero_distance_pairs.append([first, second])
                continue  # A corner contact is not an island water gap.
            candidates.append((distance, first, second, p, q))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))

    parents = list(range(len(components)))
    group_roots: list[int | None] = [i if i in roots else None for i in parents]

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    rows = [set(neighbors) for neighbors in part_graph.adjacency]
    records = []
    for distance, first, second, p, q in candidates:
        first_group, second_group = find(first), find(second)
        if first_group == second_group:
            continue
        if group_roots[first_group] is not None and group_roots[second_group] is not None:
            continue
        endpoints = [
            _endpoint(Point(point.x/x_scale+lon0, point.y/y_scale+lat0), components[component],
                      source_parts, part_graph, ordered)
            for point, component in ((p, first), (q, second))
        ]
        a, b = (endpoint["part_node"] for endpoint in endpoints)
        rows[a].add(b)
        rows[b].add(a)
        records.append({
            "id": f"ri-water-{len(records)+1:03d}", "state_fips": state_fips,
            "component_ids": [first, second], "distance_m": distance, "endpoints": endpoints,
            "kind": "recorded-water-connection", "distance_definition": "shortest boundary gap in included census coverage",
            "projection": projection, "provenance": provenance,
        })
        parents[second_group] = first_group
        group_roots[first_group] = group_roots[first_group] if group_roots[first_group] is not None else group_roots[second_group]
    if any(group_roots[find(index)] is None for index in range(len(components))):
        raise ValueError("Some undersized components cannot attach to a root with positive-length gap connections.")
    augmented = PartGraph(tuple(tuple(sorted(row)) for row in rows), part_graph.part_to_unit)
    resulting, _ = _components(augmented)
    if len(resulting) != len(roots) or len(records) != len(components) - len(roots):
        raise AssertionError("Rooted forest invariants failed.")
    audit: dict[str, Any] = {
        "schema_version": 1, "policy": _POLICY, "state_fips": state_fips,
        "minimum_district_population": minimum, "source_geometry_modified": False,
        "synthetic_ownership_edges": False, "source_population": sum(pops), "block_count": len(ordered),
        "part_count": len(source_parts), "physical_component_count": len(components),
        "physical_edge_count": sum(map(len, part_graph.adjacency)) // 2,
        "synthetic_edge_count": len(records), "augmented_edge_count": sum(map(len, augmented.adjacency)) // 2,
        "augmented_component_count": len(resulting), "augmented_graph_connected": len(resulting) == 1,
        "all_undersized_components_attached": True, "eligible_root_count": len(roots),
        "components": [{"component_id": i, "part_count": len(parts), "block_count": len(component_units[i]),
                        "population": component_pops[i], "eligible_root": i in roots,
                        "attached_root_component": group_roots[find(i)]} for i, parts in enumerate(components)],
        "zero_distance_component_pairs_excluded": zero_distance_pairs,
        "distance_candidate_count": len(candidates), "projection": projection, "provenance": provenance,
        "endpoint_tolerance_degrees": _ENDPOINT_TOLERANCE_DEGREES,
        "elapsed_seconds": time.perf_counter() - started,
    }
    return augmented, tuple(records), audit
