"""Read-only Alaska longitude normalization and exact polygon-part topology.

The 2020 Alaska source uses two longitude representations of neighboring
regions. This adapter translates each entirely eastern-hemisphere block by
-360 degrees. It does not snap, buffer, repair, split, or join polygon parts.
It deliberately rejects a block spanning the longitude seam rather than
guessing its ring semantics. Source files and ordinary state adapters remain
untouched. A translated working frame is not ordinary RFC 7946 longitude.
"""
from __future__ import annotations

from collections.abc import Sequence
import hashlib
import io
import math
from numbers import Integral
from pathlib import Path
import time
from typing import Any
import zipfile

import numpy as np
import shapefile
import shapely
from shapely.affinity import translate
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from districting.part_connectivity import PartGraph


NORMALIZATION = "alaska-whole-block-positive-longitude-minus-360-v1"
_SOURCE_STEM = "tl_2020_02_tabblock20"
_QUERY_BATCH_SIZE = 2_000


def normalize_alaska_geometry(geometry: BaseGeometry) -> tuple[BaseGeometry, float]:
    """Return a valid whole-geometry longitude translation or reject ambiguity."""
    if geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Alaska normalization requires nonempty polygonal geometry.")
    if geometry.has_z:
        raise ValueError("Alaska source geometry must be two-dimensional.")
    coordinates = shapely.get_coordinates(geometry)
    if not np.all(np.isfinite(coordinates)):
        raise ValueError("Source coordinates must be finite.")
    if np.any(np.abs(coordinates[:, 0]) > 180) or np.any(np.abs(coordinates[:, 1]) > 90):
        raise ValueError("Source coordinates must be original longitude/latitude, not an already normalized frame.")
    if not geometry.is_valid:
        raise ValueError(f"Invalid source geometry: {shapely.is_valid_reason(geometry)}.")
    positive = coordinates[:, 0] > 0
    if np.any(positive) and not np.all(positive):
        raise ValueError("A whole block mixes longitude sides; seam-crossing geometry is unsupported.")
    parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    for part in parts:
        for ring in (part.exterior, *part.interiors):
            ring_coordinates = np.asarray(ring.coords)
            if np.any(np.abs(np.diff(ring_coordinates[:, 0])) > 180):
                raise ValueError("Source ring crosses the longitude seam; splitting is not authorized.")
    offset = -360.0 if np.all(positive) else 0.0
    normalized = translate(geometry, xoff=offset) if offset else geometry
    if normalized.is_empty or not normalized.is_valid or normalized.geom_type != geometry.geom_type:
        raise ValueError("Longitude translation failed geometry validation.")
    if normalized.bounds[2] - normalized.bounds[0] > 180:
        raise ValueError("Normalized block still spans more than 180 degrees.")
    return normalized, offset


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a nonnegative integer.")
    try:
        numeric = float(value)
        integer = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a nonnegative integer.") from error
    if not math.isfinite(numeric) or numeric != integer or integer < 0:
        raise ValueError(f"{name} must be a nonnegative integer.")
    return integer


def load_normalized_parts(
    archive_path: Path, *, normalize: bool = True,
) -> tuple[list[BaseGeometry], list[dict[str, Any]], tuple[int, ...], tuple[int, ...], dict[str, Any]]:
    """Read Alaska ZIP without extraction; retain source block and part order.

    Each record owns one population irrespective of its part count. Passing
    ``normalize=False`` returns original geometries for an independent raw-edge
    audit, while applying exactly the same source checks. Official state total
    reconciliation belongs to the calling diagnosis/benchmark.
    """
    if not isinstance(normalize, bool):
        raise ValueError("normalize must be a boolean.")
    started = time.perf_counter()
    parts: list[BaseGeometry] = []
    records: list[dict[str, Any]] = []
    owners: list[int] = []
    part_indices: list[int] = []
    seen: set[str] = set()
    source_bounds = [math.inf, math.inf, -math.inf, -math.inf]
    coordinate_count = ring_count = shifted_blocks = shifted_population = 0
    maximum_roundtrip_error = 0.0
    archive_path = Path(archive_path)
    with archive_path.open("rb") as source:
        archive_digest = hashlib.file_digest(source, "sha256").hexdigest()
    with zipfile.ZipFile(archive_path) as archive:
        required_files = [_SOURCE_STEM + suffix for suffix in (".shp", ".shx", ".dbf")]
        names = archive.namelist()
        if any(names.count(name) != 1 for name in required_files):
            raise ValueError("Alaska archive must contain one exact SHP/SHX/DBF member each.")
        streams = [io.BytesIO(archive.read(name)) for name in required_files]
        with shapefile.Reader(shp=streams[0], shx=streams[1], dbf=streams[2]) as reader:
            required_fields = {"GEOID20", "POP20", "ALAND20", "AWATER20", "INTPTLON20", "INTPTLAT20"}
            fields = [field[0] for field in reader.fields[1:]]
            if len(fields) != len(set(fields)) or not required_fields.issubset(fields):
                raise ValueError("Alaska source has missing or duplicate required fields.")
            for item in reader.iterShapeRecords():
                geoid = str(item.record["GEOID20"])
                if (len(geoid) != 15 or not geoid.isascii() or not geoid.isdigit()
                        or not geoid.startswith("02") or geoid in seen):
                    raise ValueError("Alaska block GEOIDs must be unique 15-digit state-02 identifiers.")
                seen.add(geoid)
                population = _nonnegative_integer(item.record["POP20"], f"POP20 for {geoid}")
                land = _nonnegative_integer(item.record["ALAND20"], f"ALAND20 for {geoid}")
                water = _nonnegative_integer(item.record["AWATER20"], f"AWATER20 for {geoid}")
                internal_point = [float(item.record["INTPTLON20"]), float(item.record["INTPTLAT20"])]
                if not all(map(math.isfinite, internal_point)) or not (-180 <= internal_point[0] <= 180 and -90 <= internal_point[1] <= 90):
                    raise ValueError(f"Invalid original internal point for {geoid}.")
                original = shape(item.shape.__geo_interface__)
                normalized, offset = normalize_alaska_geometry(original)
                if (internal_point[0] > 0) != (offset == -360):
                    raise ValueError(f"Internal point and geometry use different longitude sides for {geoid}.")
                geometry = normalized if normalize else original
                block_parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
                raw_coordinates = shapely.get_coordinates(original)
                normalized_coordinates = shapely.get_coordinates(normalized)
                restored = normalized_coordinates.copy()
                restored[:, 0] -= offset
                maximum_roundtrip_error = max(maximum_roundtrip_error, float(np.max(np.abs(restored - raw_coordinates))))
                source_bounds = [min(source_bounds[0], original.bounds[0]), min(source_bounds[1], original.bounds[1]),
                                 max(source_bounds[2], original.bounds[2]), max(source_bounds[3], original.bounds[3])]
                unit = len(records)
                parts.extend(block_parts)
                owners.extend([unit] * len(block_parts))
                part_indices.extend(range(len(block_parts)))
                coordinate_count += len(raw_coordinates)
                ring_count += sum(1 + len(part.interiors) for part in block_parts)
                shifted_blocks += int(bool(offset))
                shifted_population += population if offset else 0
                records.append({"geoid": geoid, "population": population, "land_area_m2": land,
                                "water_area_m2": water, "internal_point": internal_point,
                                "working_internal_point": [internal_point[0] + (offset if normalize else 0), internal_point[1]],
                                "source_part_count": len(block_parts), "longitude_offset_degrees": offset if normalize else 0.0})
    if not records:
        raise ValueError("Alaska source contains no blocks.")
    working_bounds = list(map(float, shapely.total_bounds(parts)))
    if normalize and working_bounds[2] - working_bounds[0] > 180:
        raise ValueError("Normalized state extent still spans more than 180 degrees.")
    metadata = {
        "normalization": NORMALIZATION if normalize else "none-original-source-frame",
        "source_archive_sha256": archive_digest,
        "source_bbox": source_bounds, "working_bbox": working_bounds,
        "source_longitude_span_degrees": source_bounds[2] - source_bounds[0],
        "working_longitude_span_degrees": working_bounds[2] - working_bounds[0],
        "block_count": len(records), "part_count": len(parts), "source_ring_count": ring_count,
        "source_coordinate_count": coordinate_count, "total_population": sum(row["population"] for row in records),
        "positive_longitude_block_count": shifted_blocks, "positive_longitude_population": shifted_population,
        "longitude_translated_block_count": shifted_blocks if normalize else 0,
        "multipart_block_count": sum(row["source_part_count"] > 1 for row in records),
        "zero_population_block_count": sum(row["population"] == 0 for row in records),
        "water_only_block_count": sum(row["land_area_m2"] == 0 and row["water_area_m2"] > 0 for row in records),
        "maximum_inverse_translation_error_degrees": maximum_roundtrip_error,
        "all_source_and_working_geometries_valid": True,
        "part_order": "source block record order, then original MultiPolygon part order",
        "source_files_modified": False, "polygon_repair_applied": False, "ring_split_applied": False,
        "synthetic_ownership_edges": False,
        "working_coordinates_are_geographic_representation": True,
        "ordinary_rfc7946_longitude_domain": not normalize or shifted_blocks == 0,
        "elapsed_seconds": time.perf_counter() - started,
    }
    return parts, records, tuple(owners), tuple(part_indices), metadata


def build_exact_part_graph(
    parts: Sequence[BaseGeometry], owners: Sequence[int],
) -> tuple[PartGraph, dict[str, Any]]:
    """Build uncached F***1**** adjacency in the caller's explicit common frame."""
    started = time.perf_counter()
    if not parts or len(parts) != len(owners):
        raise ValueError("Parts and ownership must have matching nonzero lengths.")
    if any(isinstance(owner, bool) or not isinstance(owner, Integral) or owner < 0 for owner in owners):
        raise ValueError("Part owners must be nonnegative integers.")
    if tuple(owners) != tuple(sorted(owners)) or set(owners) != set(range(max(owners) + 1)):
        raise ValueError("Part owners must cover all blocks in source order.")
    if any(part.is_empty or part.geom_type != "Polygon" or not part.is_valid for part in parts):
        raise ValueError("Every graph vertex must be one valid nonempty polygon part.")
    geometries = np.asarray(parts, dtype=object)
    if not np.all(np.isfinite(shapely.get_coordinates(geometries))):
        raise ValueError("Part graph coordinates must be finite.")
    tree = shapely.STRtree(geometries)
    rows: list[list[int]] = [[] for _ in parts]
    edges = corners = candidates = overlaps = 0
    for start in range(0, len(parts), _QUERY_BATCH_SIZE):
        pairs = tree.query(geometries[start:start + _QUERY_BATCH_SIZE])
        left, right = pairs[0] + start, pairs[1]
        unique = left < right
        left, right = left[unique], right[unique]
        candidates += len(left)
        for a, b, relation in zip(left, right, shapely.relate(geometries[left], geometries[right]), strict=True):
            if relation[0] != "F":
                overlaps += 1
            elif relation[4] == "1":
                rows[int(a)].append(int(b))
                rows[int(b)].append(int(a))
                edges += 1
            elif relation[4] == "0":
                corners += 1
    if overlaps:
        raise ValueError(f"Source parts have {overlaps} overlapping-interior pairs in this coordinate frame.")
    graph = PartGraph(tuple(tuple(sorted(row)) for row in rows), tuple(map(int, owners)))
    seen: set[int] = set()
    component_sizes = []
    for start in range(len(parts)):
        if start in seen:
            continue
        pending, count = [start], 0
        seen.add(start)
        while pending:
            node = pending.pop()
            count += 1
            for neighbor in graph.adjacency[node]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        component_sizes.append(count)
    return graph, {"de9im_pattern": "F***1****", "part_count": len(parts),
                   "block_count": len(graph.unit_to_parts), "edge_count": edges,
                   "candidate_pair_count": candidates, "excluded_corner_pair_count": corners,
                   "interior_overlap_pair_count": 0, "component_count": len(component_sizes),
                   "component_sizes": sorted(component_sizes, reverse=True),
                   "synthetic_ownership_edges": False, "geometry_modified_by_graph_builder": False,
                   "cache_reused": False, "elapsed_seconds": time.perf_counter() - started}
