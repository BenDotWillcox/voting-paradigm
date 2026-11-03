"""Build exact shared-edge adjacency from the original Census block polygons.

This offline geometry adapter retains every supplied block, including water and
zero-population blocks. It does not round coordinates, snap gaps, buffer shapes,
or treat corner contacts as shared edges.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import time
from typing import Any

import numpy as np
import shapefile
import shapely
from shapely.geometry import shape


_QUERY_BATCH_SIZE = 2_000


def _component_sizes(adjacency: Sequence[Sequence[int]]) -> list[int]:
    """Return component sizes, largest first, including isolated vertices."""
    visited = bytearray(len(adjacency))
    sizes: list[int] = []
    for start in range(len(adjacency)):
        if visited[start]:
            continue
        visited[start] = 1
        pending = [start]
        size = 0
        while pending:
            node = pending.pop()
            size += 1
            for neighbor in adjacency[node]:
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    pending.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def build_shared_edge_adjacency(
    shapefile_path: Path, geoids: Sequence[str]
) -> tuple[tuple[tuple[int, ...], ...], dict[str, Any]]:
    """Return symmetric neighbors indexed exactly by the supplied GEOID order.

    The input must enumerate the source's complete set of block GEOIDs once.
    Source polygons must be valid as supplied. The DE-9IM relation F***1****
    accepts a pair only when their interiors are disjoint and their boundaries
    intersect in a line (any positive length). Point contacts are excluded.

    Spatial-index candidates and topology results are bounded to query batches;
    geometry and index objects are released before graph statistics are computed.
    Connected graph vertices are whole blocks. If a source block is multipart,
    a final district-polygon validation is also necessary: this graph alone
    cannot certify that every polygon component of that block is connected.
    """
    started = time.perf_counter()
    ordered_geoids = tuple(geoids)
    if not ordered_geoids:
        raise ValueError("At least one block GEOID is required.")
    for geoid in ordered_geoids:
        if (
            not isinstance(geoid, str)
            or len(geoid) != 15
            or not geoid.isascii()
            or not geoid.isdigit()
        ):
            raise ValueError(f"Invalid block GEOID: {geoid!r}.")
    indices = {geoid: index for index, geoid in enumerate(ordered_geoids)}
    if len(indices) != len(ordered_geoids):
        raise ValueError("Duplicate input block GEOIDs.")

    geometries = np.empty(len(ordered_geoids), dtype=object)
    seen: set[str] = set()
    multipart_count = 0
    coordinate_count = 0
    with shapefile.Reader(str(shapefile_path)) as reader:
        fields = [field[0] for field in reader.fields[1:]]
        if "GEOID20" not in fields:
            raise ValueError("Source shapefile is missing GEOID20.")
        geoid_index = fields.index("GEOID20")
        for record in reader.iterShapeRecords():
            geoid = str(record.record[geoid_index])
            if geoid in seen:
                raise ValueError(f"Duplicate source block GEOID {geoid}.")
            if geoid not in indices:
                raise ValueError(f"Unexpected source block GEOID {geoid!r}.")
            seen.add(geoid)
            try:
                geometry = shape(record.shape.__geo_interface__)
            except (ValueError, TypeError, shapely.errors.GEOSException) as error:
                raise ValueError(f"Cannot read source block geometry {geoid}.") from error
            if geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError(f"Block {geoid} has empty or nonpolygonal geometry.")
            if not geometry.is_valid:
                reason = shapely.is_valid_reason(geometry)
                raise ValueError(f"Invalid source block geometry {geoid}: {reason}.")
            geometries[indices[geoid]] = geometry
            multipart_count += int(geometry.geom_type == "MultiPolygon")
            coordinate_count += len(record.shape.points)
    missing = set(indices) - seen
    if missing:
        raise ValueError(f"Missing source block GEOIDs: {sorted(missing)[:20]}.")
    # Do not retain the final streamed polygon while releasing the array later.
    del geometry, record, seen, indices
    loaded = time.perf_counter()

    tree = shapely.STRtree(geometries)
    neighbors: list[list[int]] = [[] for _ in ordered_geoids]
    candidate_count = 0
    corner_count = 0
    overlap_count = 0
    edge_count = 0
    batch_count = 0
    max_candidates = 0
    for start in range(0, len(ordered_geoids), _QUERY_BATCH_SIZE):
        batch_count += 1
        pairs = tree.query(geometries[start : start + _QUERY_BATCH_SIZE])
        left, right = pairs[0] + start, pairs[1]
        unique = left < right
        left, right = left[unique], right[unique]
        candidate_count += len(left)
        max_candidates = max(max_candidates, len(left))
        # Compute topology once per candidate, also recording point contacts and
        # overlaps. Testing relation[0] == F and relation[4] == 1 is precisely
        # the DE-9IM F***1**** predicate, without a second geometry operation.
        relations = shapely.relate(geometries[left], geometries[right])
        for first, second, relation in zip(left, right, relations, strict=True):
            if relation[0] != "F":
                overlap_count += 1
            elif relation[4] == "1":
                first_index, second_index = int(first), int(second)
                neighbors[first_index].append(second_index)
                neighbors[second_index].append(first_index)
                edge_count += 1
            elif relation[4] == "0":
                corner_count += 1
    del tree, geometries, pairs, left, right, unique, relations
    adjacency = tuple(tuple(sorted(adjacent)) for adjacent in neighbors)
    del neighbors
    built = time.perf_counter()

    component_sizes = _component_sizes(adjacency)
    isolated_indices = [index for index, adjacent in enumerate(adjacency) if not adjacent]
    metadata: dict[str, Any] = {
        "definition": "disjoint interiors and shared boundary of positive length",
        "de9im_pattern": "F***1****",
        "source_coordinates_modified": False,
        "all_source_geometries_valid": True,
        "node_count": len(ordered_geoids),
        "edge_count": edge_count,
        "candidate_pair_count": candidate_count,
        "excluded_corner_pair_count": corner_count,
        "interior_overlap_pair_count": overlap_count,
        "component_count": len(component_sizes),
        "component_sizes": component_sizes,
        "isolated_node_count": len(isolated_indices),
        "isolated_node_geoids": [ordered_geoids[index] for index in isolated_indices],
        "multipart_block_count": multipart_count,
        "source_coordinate_count": coordinate_count,
        "query_batch_size": _QUERY_BATCH_SIZE,
        "query_batch_count": batch_count,
        "max_batch_candidate_pair_count": max_candidates,
        "geometry_load_seconds": loaded - started,
        "topology_build_seconds": built - loaded,
        "graph_validation_seconds": time.perf_counter() - built,
        "elapsed_seconds": time.perf_counter() - started,
    }
    return adjacency, metadata
