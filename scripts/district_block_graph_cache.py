"""Reusable, validated offline cache for exact Census block adjacency.

The caller verifies the source archive SHA-256 before calling this adapter.
Cache files contain compressed integer CSR arrays and UTF-8 JSON only; loading
never permits pickle. Their identity includes the source, exact GEOID order,
adjacency implementation, topology rule, schema, and geometry-library versions.
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
import shapely

from scripts import district_block_adjacency


_CACHE_SCHEMA = 1
_TOPOLOGY_RULE = "F***1****; original source coordinates; no snapping or buffering"
_INTEGER_DTYPE = np.dtype("<i8")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _builder_digest() -> str:
    return hashlib.sha256(Path(district_block_adjacency.__file__).read_bytes()).hexdigest()


def _identity(geoids: Sequence[str], source_sha256: str) -> dict[str, Any]:
    if (
        len(source_sha256) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in source_sha256)
    ):
        raise ValueError("source_sha256 must be the verified source archive SHA-256.")
    if not geoids:
        raise ValueError("At least one block GEOID is required.")
    if any(
        not isinstance(geoid, str)
        or len(geoid) != 15
        or not geoid.isascii()
        or not geoid.isdigit()
        for geoid in geoids
    ):
        raise ValueError("Block GEOIDs must be 15-digit ASCII strings.")
    if len(set(geoids)) != len(geoids):
        raise ValueError("Duplicate input block GEOIDs.")
    return {
        "schema": _CACHE_SCHEMA,
        "topology_rule": _TOPOLOGY_RULE,
        "source_archive_sha256": source_sha256.lower(),
        "ordered_geoids_sha256": hashlib.sha256(_json_bytes(list(geoids))).hexdigest(),
        "node_count": len(geoids),
        "adjacency_builder_sha256": _builder_digest(),
        "shapely_version": shapely.__version__,
        "geos_version": shapely.geos_version_string,
    }


def _payload_digest(
    offsets: np.ndarray[Any, Any],
    neighbors: np.ndarray[Any, Any],
    graph_metadata: dict[str, Any],
) -> str:
    digest = hashlib.sha256()
    for value in (offsets.tobytes(), neighbors.tobytes(), _json_bytes(graph_metadata)):
        digest.update(len(value).to_bytes(8, "little"))
        digest.update(value)
    return digest.hexdigest()


def _validate_csr(
    offsets: np.ndarray[Any, Any],
    neighbors: np.ndarray[Any, Any],
    node_count: int,
    graph_metadata: dict[str, Any],
) -> tuple[tuple[int, ...], ...]:
    if offsets.dtype != _INTEGER_DTYPE or offsets.shape != (node_count + 1,):
        raise ValueError("Invalid cached CSR offsets dtype or shape.")
    if neighbors.dtype != _INTEGER_DTYPE or neighbors.ndim != 1:
        raise ValueError("Invalid cached CSR neighbors dtype or shape.")
    if (
        offsets[0] != 0
        or offsets[-1] != len(neighbors)
        or np.any(offsets < 0)
        or np.any(offsets > len(neighbors))
        or np.any(offsets[1:] < offsets[:-1])
    ):
        raise ValueError("Invalid cached CSR offsets.")
    if np.any(neighbors < 0) or np.any(neighbors >= node_count):
        raise ValueError("Cached neighbor index is outside the GEOID range.")
    adjacency = tuple(
        tuple(int(neighbor) for neighbor in neighbors[offsets[node] : offsets[node + 1]])
        for node in range(node_count)
    )
    for node, row in enumerate(adjacency):
        if node in row or any(first >= second for first, second in zip(row, row[1:])):
            raise ValueError("Cached neighbors must be sorted, unique, and exclude self-loops.")
        for neighbor in row:
            reverse = adjacency[neighbor]
            insertion = bisect_left(reverse, node)
            if insertion == len(reverse) or reverse[insertion] != node:
                raise ValueError("Cached adjacency is not symmetric.")
    if (
        graph_metadata.get("node_count") != node_count
        or graph_metadata.get("edge_count") != len(neighbors) // 2
        or len(neighbors) % 2
        or graph_metadata.get("de9im_pattern") != "F***1****"
        or graph_metadata.get("all_source_geometries_valid") is not True
        or graph_metadata.get("source_coordinates_modified") is not False
    ):
        raise ValueError("Cached graph metadata disagrees with the graph or topology rule.")
    return adjacency


def _read_cache(
    path: Path, identity: dict[str, Any]
) -> tuple[tuple[tuple[int, ...], ...], dict[str, Any]]:
    with np.load(path, allow_pickle=False) as archive:
        if sorted(archive.files) != ["manifest", "neighbors", "offsets"]:
            raise ValueError("Unexpected cache archive members.")
        offsets, neighbors, encoded = archive["offsets"], archive["neighbors"], archive["manifest"]
    if encoded.dtype != np.dtype("uint8") or encoded.ndim != 1:
        raise ValueError("Invalid cache manifest encoding.")
    manifest = json.loads(encoded.tobytes().decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("identity") != identity:
        raise ValueError("Stale or mismatched cache identity.")
    graph_metadata = manifest.get("graph_metadata")
    if not isinstance(graph_metadata, dict):
        raise ValueError("Invalid cached graph metadata.")
    if manifest.get("payload_sha256") != _payload_digest(offsets, neighbors, graph_metadata):
        raise ValueError("Cache payload checksum mismatch.")
    adjacency = _validate_csr(offsets, neighbors, int(identity["node_count"]), graph_metadata)
    return adjacency, graph_metadata


def _write_cache(
    path: Path,
    identity: dict[str, Any],
    adjacency: Sequence[Sequence[int]],
    graph_metadata: dict[str, Any],
) -> None:
    counts = np.fromiter((len(row) for row in adjacency), dtype=_INTEGER_DTYPE)
    offsets = np.empty(len(adjacency) + 1, dtype=_INTEGER_DTYPE)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])
    neighbors = np.fromiter(
        (neighbor for row in adjacency for neighbor in row), dtype=_INTEGER_DTYPE,
        count=int(offsets[-1]),
    )
    _validate_csr(offsets, neighbors, int(identity["node_count"]), graph_metadata)
    manifest = {
        "identity": identity,
        "graph_metadata": graph_metadata,
        "payload_sha256": _payload_digest(offsets, neighbors, graph_metadata),
    }
    encoded = np.frombuffer(_json_bytes(manifest), dtype=np.uint8)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent, delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            np.savez_compressed(stream, offsets=offsets, neighbors=neighbors, manifest=encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_or_build_shared_edge_graph(
    shapefile_path: Path,
    geoids: Sequence[str],
    *,
    source_sha256: str,
    cache_dir: Path,
) -> tuple[tuple[tuple[int, ...], ...], dict[str, Any], dict[str, Any]]:
    """Load a verified reusable graph, or build and atomically cache one.

    The source archive hash must already have been checked by the caller. A hit
    does not reread source geometry. A changed source, GEOID ordering, builder,
    rule, schema, or geometry library gets a different cache key. Invalid files
    at the expected key are rebuilt, with the rejection reason reported.

    Graph metadata preserves the original build's measurements. Only the
    returned cache metadata describes this invocation's measured work.
    """
    started = time.perf_counter()
    ordered_geoids = tuple(geoids)
    identity = _identity(ordered_geoids, source_sha256)
    key = hashlib.sha256(_json_bytes(identity)).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"shared-edge-{key}.npz"
    load_started = time.perf_counter()
    rejection_reason: str | None = None
    if path.exists():
        try:
            adjacency, graph_metadata = _read_cache(path, identity)
        except (
            ValueError, TypeError, KeyError, OSError, EOFError,
            OverflowError, zipfile.BadZipFile, zlib.error,
        ) as error:
            rejection_reason = f"{type(error).__name__}: {error}"
        else:
            return adjacency, graph_metadata, {
                "status": "hit", "cache_hit": True, "key": key, "path": str(path.resolve()),
                "identity": identity,
                "bytes": path.stat().st_size, "load_seconds": time.perf_counter() - load_started,
                "build_seconds": 0.0, "write_seconds": 0.0,
                "total_seconds": time.perf_counter() - started,
                "source_hash_verified_by_caller": True,
                "original_build_timing_reused": True,
                "invalid_cache_reason": None,
            }
    load_seconds = time.perf_counter() - load_started
    build_started = time.perf_counter()
    adjacency, graph_metadata = district_block_adjacency.build_shared_edge_adjacency(
        shapefile_path, ordered_geoids
    )
    build_seconds = time.perf_counter() - build_started
    write_started = time.perf_counter()
    _write_cache(path, identity, adjacency, graph_metadata)
    write_seconds = time.perf_counter() - write_started
    return adjacency, graph_metadata, {
        "status": "built", "cache_hit": False, "key": key, "path": str(path.resolve()),
        "identity": identity,
        "bytes": path.stat().st_size, "load_seconds": load_seconds,
        "build_seconds": build_seconds, "write_seconds": write_seconds,
        "total_seconds": time.perf_counter() - started,
        "source_hash_verified_by_caller": True,
        "original_build_timing_reused": False,
        "invalid_cache_reason": rejection_reason,
    }
