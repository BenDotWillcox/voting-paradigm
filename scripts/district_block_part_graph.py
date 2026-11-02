"""Exact polygon-part adjacency with whole-block ownership and a separate cache.

One vertex represents one source Polygon, never an entire multipart block.
Ownership couples parts for assignment/population without inventing geometric
edges. Coordinates are not repaired, rounded, snapped, or buffered. The caller
must verify the source archive before supplying its SHA-256 to the cache API.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
import zipfile
import zlib

import numpy as np
import shapefile
import shapely
from shapely.geometry import shape

from districting import part_connectivity
from districting.part_connectivity import PartGraph


_QUERY_BATCH_SIZE = 2_000
_CACHE_SCHEMA = 1
_TOPOLOGY_RULE = "polygon parts; F***1****; original coordinates; no synthetic ownership edges"
_INTEGER_DTYPE = np.dtype("<i8")


def _validate_geoids(geoids: Sequence[str]) -> tuple[str, ...]:
    ordered = tuple(geoids)
    if not ordered:
        raise ValueError("At least one block GEOID is required.")
    if any(
        not isinstance(geoid, str) or len(geoid) != 15
        or not geoid.isascii() or not geoid.isdigit()
        for geoid in ordered
    ):
        raise ValueError("Block GEOIDs must be 15-digit ASCII strings.")
    if len(set(ordered)) != len(ordered):
        raise ValueError("Duplicate input block GEOIDs.")
    return ordered


def _component_sizes(adjacency: Sequence[Sequence[int]]) -> list[int]:
    seen = bytearray(len(adjacency))
    sizes: list[int] = []
    for start in range(len(adjacency)):
        if seen[start]:
            continue
        seen[start] = 1
        pending, size = [start], 0
        while pending:
            node = pending.pop()
            size += 1
            for neighbor in adjacency[node]:
                if not seen[neighbor]:
                    seen[neighbor] = 1
                    pending.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def build_shared_edge_part_graph(
    shapefile_path: Path, geoids: Sequence[str],
) -> tuple[PartGraph, dict[str, Any]]:
    """Read every source block and build exact shared-edge Polygon adjacency.

    Vertex order is input GEOID order followed by source MultiPolygon part
    order. Every block must occur exactly once and own at least one part. All
    blocks are retained, including zero-population/water blocks. Overlapping
    interiors are reported and excluded from adjacency; callers must reject a
    nonzero overlap count before claiming a valid source partition.
    """
    started = time.perf_counter()
    ordered = _validate_geoids(geoids)
    indices = {geoid: index for index, geoid in enumerate(ordered)}
    by_unit: list[list[Any] | None] = [None] * len(ordered)
    seen: set[str] = set()
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
                raise ValueError(
                    f"Invalid source block geometry {geoid}: {shapely.is_valid_reason(geometry)}."
                )
            by_unit[indices[geoid]] = (
                list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
            )
            coordinate_count += len(record.shape.points)
    missing = set(indices) - seen
    if missing:
        raise ValueError(f"Missing source block GEOIDs: {sorted(missing)[:20]}.")
    parts: list[Any] = []
    owners: list[int] = []
    multipart_count = 0
    for unit, unit_parts in enumerate(by_unit):
        assert unit_parts is not None
        multipart_count += int(len(unit_parts) > 1)
        parts.extend(unit_parts)
        owners.extend([unit] * len(unit_parts))
    geometries = np.asarray(parts, dtype=object)
    del by_unit, parts, geometry, record, unit_parts, seen, indices
    loaded = time.perf_counter()

    tree = shapely.STRtree(geometries)
    neighbors: list[list[int]] = [[] for _ in owners]
    candidate_count = corner_count = overlap_count = edge_count = batch_count = 0
    max_candidates = 0
    for start in range(0, len(owners), _QUERY_BATCH_SIZE):
        batch_count += 1
        pairs = tree.query(geometries[start : start + _QUERY_BATCH_SIZE])
        left, right = pairs[0] + start, pairs[1]
        unique = left < right
        left, right = left[unique], right[unique]
        candidate_count += len(left)
        max_candidates = max(max_candidates, len(left))
        relations = shapely.relate(geometries[left], geometries[right])
        for first, second, relation in zip(left, right, relations, strict=True):
            if relation[0] != "F":
                overlap_count += 1
            elif relation[4] == "1":
                a, b = int(first), int(second)
                neighbors[a].append(b)
                neighbors[b].append(a)
                edge_count += 1
            elif relation[4] == "0":
                corner_count += 1
    del tree, geometries, pairs, left, right, unique, relations
    adjacency = tuple(tuple(sorted(row)) for row in neighbors)
    del neighbors
    built = time.perf_counter()
    component_sizes = _component_sizes(adjacency)
    isolated = [index for index, row in enumerate(adjacency) if not row]
    graph = PartGraph(adjacency=adjacency, part_to_unit=tuple(owners))
    metadata: dict[str, Any] = {
        "definition": "source Polygon parts with disjoint interiors and shared boundary of positive length",
        "de9im_pattern": "F***1****",
        "source_coordinates_modified": False,
        "all_source_geometries_valid": True,
        "synthetic_ownership_edges": False,
        "part_order": "ordered GEOIDs, then source MultiPolygon parts",
        "block_count": len(ordered),
        "node_count": len(owners),
        "part_count": len(owners),
        "edge_count": edge_count,
        "multipart_block_count": multipart_count,
        "candidate_pair_count": candidate_count,
        "excluded_corner_pair_count": corner_count,
        "interior_overlap_pair_count": overlap_count,
        "component_count": len(component_sizes),
        "component_sizes": component_sizes,
        "isolated_part_count": len(isolated),
        "isolated_part_indices": isolated,
        "isolated_part_geoids": [ordered[owners[index]] for index in isolated],
        "source_coordinate_count": coordinate_count,
        "query_batch_size": _QUERY_BATCH_SIZE,
        "query_batch_count": batch_count,
        "max_batch_candidate_pair_count": max_candidates,
        "geometry_load_seconds": loaded - started,
        "topology_build_seconds": built - loaded,
        "graph_validation_seconds": time.perf_counter() - built,
        "elapsed_seconds": time.perf_counter() - started,
    }
    return graph, metadata


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _builder_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _domain_digest() -> str:
    return hashlib.sha256(Path(part_connectivity.__file__).read_bytes()).hexdigest()


def _identity(geoids: Sequence[str], source_sha256: str) -> dict[str, Any]:
    ordered = _validate_geoids(geoids)
    if not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in source_sha256
    ):
        raise ValueError("source_sha256 must be the verified source archive SHA-256.")
    return {
        "schema": _CACHE_SCHEMA,
        "topology_rule": _TOPOLOGY_RULE,
        "source_archive_sha256": source_sha256.lower(),
        "ordered_geoids_sha256": hashlib.sha256(_json_bytes(list(ordered))).hexdigest(),
        "block_count": len(ordered),
        "part_builder_sha256": _builder_digest(),
        "part_domain_sha256": _domain_digest(),
        "shapely_version": shapely.__version__,
        "geos_version": shapely.geos_version_string,
        "pyshp_version": shapefile.__version__,
    }


def _payload_digest(
    offsets: np.ndarray[Any, Any], neighbors: np.ndarray[Any, Any],
    owners: np.ndarray[Any, Any], metadata: dict[str, Any],
) -> str:
    digest = hashlib.sha256()
    for value in (offsets.tobytes(), neighbors.tobytes(), owners.tobytes(), _json_bytes(metadata)):
        digest.update(len(value).to_bytes(8, "little"))
        digest.update(value)
    return digest.hexdigest()


def _validate_arrays(
    offsets: np.ndarray[Any, Any], neighbors: np.ndarray[Any, Any],
    owners: np.ndarray[Any, Any], block_count: int, metadata: dict[str, Any],
) -> PartGraph:
    if owners.dtype != _INTEGER_DTYPE or owners.ndim != 1 or len(owners) < block_count:
        raise ValueError("Invalid cached ownership dtype, shape, or coverage.")
    if np.any(owners < 0) or np.any(owners >= block_count):
        raise ValueError("Cached part ownership is outside the block range.")
    if np.any(owners[1:] < owners[:-1]) or not np.array_equal(np.unique(owners), np.arange(block_count)):
        raise ValueError("Cached ownership must cover every block in GEOID order.")
    part_count = len(owners)
    if offsets.dtype != _INTEGER_DTYPE or offsets.shape != (part_count + 1,):
        raise ValueError("Invalid cached CSR offsets dtype or shape.")
    if neighbors.dtype != _INTEGER_DTYPE or neighbors.ndim != 1:
        raise ValueError("Invalid cached CSR neighbors dtype or shape.")
    if (
        offsets[0] != 0 or offsets[-1] != len(neighbors)
        or np.any(offsets < 0) or np.any(offsets > len(neighbors))
        or np.any(offsets[1:] < offsets[:-1])
    ):
        raise ValueError("Invalid cached CSR offsets.")
    if np.any(neighbors < 0) or np.any(neighbors >= part_count):
        raise ValueError("Cached neighbor index is outside the part range.")
    adjacency = tuple(
        tuple(int(neighbor) for neighbor in neighbors[offsets[node] : offsets[node + 1]])
        for node in range(part_count)
    )
    for node, row in enumerate(adjacency):
        if node in row or any(a >= b for a, b in zip(row, row[1:])):
            raise ValueError("Cached neighbors must be sorted, unique, and exclude self-loops.")
        for neighbor in row:
            reverse = adjacency[neighbor]
            insertion = bisect_left(reverse, node)
            if insertion == len(reverse) or reverse[insertion] != node:
                raise ValueError("Cached adjacency is not symmetric.")
    component_sizes = _component_sizes(adjacency)
    isolated = [node for node, row in enumerate(adjacency) if not row]
    multipart_count = int(np.count_nonzero(np.bincount(owners, minlength=block_count) > 1))
    if (
        metadata.get("block_count") != block_count
        or metadata.get("node_count") != part_count or metadata.get("part_count") != part_count
        or metadata.get("edge_count") != len(neighbors) // 2 or len(neighbors) % 2
        or metadata.get("multipart_block_count") != multipart_count
        or metadata.get("component_sizes") != component_sizes
        or metadata.get("component_count") != len(component_sizes)
        or metadata.get("isolated_part_indices") != isolated
        or metadata.get("isolated_part_count") != len(isolated)
        or metadata.get("de9im_pattern") != "F***1****"
        or metadata.get("all_source_geometries_valid") is not True
        or metadata.get("source_coordinates_modified") is not False
        or metadata.get("synthetic_ownership_edges") is not False
    ):
        raise ValueError("Cached graph metadata disagrees with topology or ownership.")
    return PartGraph(adjacency=adjacency, part_to_unit=tuple(int(owner) for owner in owners))


def _read_cache(path: Path, identity: dict[str, Any]) -> tuple[PartGraph, dict[str, Any]]:
    with np.load(path, allow_pickle=False) as archive:
        if sorted(archive.files) != ["manifest", "neighbors", "offsets", "part_to_unit"]:
            raise ValueError("Unexpected cache archive members.")
        offsets, neighbors = archive["offsets"], archive["neighbors"]
        owners, encoded = archive["part_to_unit"], archive["manifest"]
    if encoded.dtype != np.dtype("uint8") or encoded.ndim != 1:
        raise ValueError("Invalid cache manifest encoding.")
    manifest = json.loads(encoded.tobytes().decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("identity") != identity:
        raise ValueError("Stale or mismatched cache identity.")
    metadata = manifest.get("graph_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Invalid cached graph metadata.")
    if manifest.get("payload_sha256") != _payload_digest(offsets, neighbors, owners, metadata):
        raise ValueError("Cache payload checksum mismatch.")
    graph = _validate_arrays(offsets, neighbors, owners, int(identity["block_count"]), metadata)
    return graph, metadata


def _write_cache(path: Path, identity: dict[str, Any], graph: PartGraph, metadata: dict[str, Any]) -> None:
    counts = np.fromiter((len(row) for row in graph.adjacency), dtype=_INTEGER_DTYPE)
    offsets = np.empty(len(graph.adjacency) + 1, dtype=_INTEGER_DTYPE)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])
    neighbors = np.fromiter(
        (neighbor for row in graph.adjacency for neighbor in row),
        dtype=_INTEGER_DTYPE, count=int(offsets[-1]),
    )
    owners = np.asarray(graph.part_to_unit, dtype=_INTEGER_DTYPE)
    _validate_arrays(offsets, neighbors, owners, int(identity["block_count"]), metadata)
    manifest = {
        "identity": identity, "graph_metadata": metadata,
        "payload_sha256": _payload_digest(offsets, neighbors, owners, metadata),
    }
    encoded = np.frombuffer(_json_bytes(manifest), dtype=np.uint8)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent, delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            np.savez_compressed(
                stream, offsets=offsets, neighbors=neighbors, part_to_unit=owners, manifest=encoded,
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_or_build_shared_edge_part_graph(
    shapefile_path: Path, geoids: Sequence[str], *, source_sha256: str, cache_dir: Path,
) -> tuple[PartGraph, dict[str, Any], dict[str, Any]]:
    """Reuse a checksummed, structurally validated, pickle-free part graph.

    The separate namespace leaves legacy whole-block caches intact. Identity
    includes source/archive order, builder/domain code, topology and libraries.
    Invalid entries are rebuilt atomically with their rejection reason retained.
    Build timings in graph metadata refer to the first build; cache timings
    always describe this invocation. Hits do not read source geometry again.
    """
    started = time.perf_counter()
    ordered = _validate_geoids(geoids)
    identity = _identity(ordered, source_sha256)
    key = hashlib.sha256(_json_bytes(identity)).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"shared-edge-parts-{key}.npz"
    load_started = time.perf_counter()
    rejection: str | None = None
    if path.exists():
        try:
            graph, metadata = _read_cache(path, identity)
        except (
            ValueError, TypeError, KeyError, OSError, EOFError, OverflowError,
            zipfile.BadZipFile, zlib.error,
        ) as error:
            rejection = f"{type(error).__name__}: {error}"
        else:
            return graph, metadata, {
                "status": "hit", "cache_hit": True, "key": key, "path": str(path.resolve()),
                "identity": identity, "bytes": path.stat().st_size,
                "load_seconds": time.perf_counter() - load_started,
                "build_seconds": 0.0, "write_seconds": 0.0,
                "total_seconds": time.perf_counter() - started,
                "source_hash_verified_by_caller": True, "original_build_timing_reused": True,
                "invalid_cache_reason": None,
            }
    load_seconds = time.perf_counter() - load_started
    build_started = time.perf_counter()
    graph, metadata = build_shared_edge_part_graph(shapefile_path, ordered)
    build_seconds = time.perf_counter() - build_started
    write_started = time.perf_counter()
    _write_cache(path, identity, graph, metadata)
    write_seconds = time.perf_counter() - write_started
    return graph, metadata, {
        "status": "built", "cache_hit": False, "key": key, "path": str(path.resolve()),
        "identity": identity, "bytes": path.stat().st_size, "load_seconds": load_seconds,
        "build_seconds": build_seconds, "write_seconds": write_seconds,
        "total_seconds": time.perf_counter() - started,
        "source_hash_verified_by_caller": True, "original_build_timing_reused": False,
        "invalid_cache_reason": rejection,
    }
