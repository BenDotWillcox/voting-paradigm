"""Cache identity, corruption handling, and structural graph validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapefile

from scripts import district_block_graph_cache as cache


_GEOIDS = ("200010001000001", "200010001000002", "200010001000003")
_SOURCE_HASH = "a" * 64


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "blocks.shp"
    with shapefile.Writer(str(path)) as writer:
        writer.field("GEOID20", "C", size=15)
        for index, geoid in enumerate(_GEOIDS):
            writer.poly([[
                (index, 0), (index, 1), (index + 1, 1), (index + 1, 0), (index, 0)
            ]])
            writer.record(geoid)
    return path


def _run(source: Path, tmp_path: Path, **kwargs: Any) -> Any:
    return cache.load_or_build_shared_edge_graph(
        source, kwargs.pop("geoids", _GEOIDS),
        source_sha256=kwargs.pop("source_sha256", _SOURCE_HASH),
        cache_dir=tmp_path / "cache", **kwargs,
    )


def test_build_then_hit_reuses_verified_graph_without_reading_source(tmp_path: Path) -> None:
    source = _source(tmp_path)
    adjacency, graph, built = _run(source, tmp_path)
    assert adjacency == ((1,), (0, 2), (1,))
    assert built["status"] == "built"
    assert built["cache_hit"] is False
    assert built["bytes"] > 0
    assert built["build_seconds"] > 0
    assert not list((tmp_path / "cache").glob("*.tmp"))
    source.unlink()
    loaded, loaded_graph, hit = _run(source, tmp_path)
    assert loaded == adjacency
    assert loaded_graph == graph
    assert hit["key"] == built["key"]
    assert hit["status"] == "hit"
    assert hit["cache_hit"] is True
    assert hit["load_seconds"] > 0
    assert hit["build_seconds"] == 0
    assert hit["write_seconds"] == 0
    assert hit["original_build_timing_reused"] is True


def test_source_and_geoid_order_changes_invalidate_cache(tmp_path: Path) -> None:
    source = _source(tmp_path)
    _, _, original = _run(source, tmp_path)
    reordered, _, order_changed = _run(
        source, tmp_path, geoids=(_GEOIDS[1], _GEOIDS[0], _GEOIDS[2])
    )
    _, _, source_changed = _run(source, tmp_path, source_sha256="b" * 64)
    assert reordered == ((1, 2), (0,), (0,))
    assert len({original["key"], order_changed["key"], source_changed["key"]}) == 3
    assert not order_changed["cache_hit"]
    assert not source_changed["cache_hit"]


@pytest.mark.parametrize("setting", ["builder", "schema", "rule", "geos"])
def test_implementation_and_rule_changes_invalidate_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    source = _source(tmp_path)
    _, _, original = _run(source, tmp_path)
    if setting == "builder":
        monkeypatch.setattr(cache, "_builder_digest", lambda: "c" * 64)
    elif setting == "schema":
        monkeypatch.setattr(cache, "_CACHE_SCHEMA", 2)
    elif setting == "rule":
        monkeypatch.setattr(cache, "_TOPOLOGY_RULE", "different rule")
    else:
        monkeypatch.setattr(cache.shapely, "geos_version_string", "different GEOS")
    _, _, changed = _run(source, tmp_path)
    assert changed["status"] == "built"
    assert changed["key"] != original["key"]


def _rewrite_archive(path: Path, mutation: str) -> None:
    with np.load(path, allow_pickle=False) as archive:
        offsets, neighbors = archive["offsets"], archive["neighbors"]
        manifest = json.loads(archive["manifest"].tobytes().decode())
    if mutation == "checksum":
        manifest["payload_sha256"] = "0" * 64
    elif mutation == "identity":
        manifest["identity"]["ordered_geoids_sha256"] = "0" * 64
    elif mutation == "range":
        neighbors[0] = 999
    elif mutation == "asymmetric":
        offsets = np.array([0, 1, 2, 2], dtype="<i8")
        neighbors = np.array([1, 2], dtype="<i8")
        manifest["graph_metadata"]["edge_count"] = 1
    elif mutation == "self_loop":
        neighbors[0] = 0
    elif mutation == "offsets":
        offsets[0] = 1
    elif mutation == "dtype":
        neighbors = neighbors.astype(np.float64)
    elif mutation == "metadata":
        manifest["graph_metadata"]["source_coordinates_modified"] = True
    if mutation != "checksum":
        manifest["payload_sha256"] = cache._payload_digest(
            offsets, neighbors, manifest["graph_metadata"]
        )
    with path.open("wb") as stream:
        np.savez_compressed(
            stream, offsets=offsets, neighbors=neighbors,
            manifest=np.frombuffer(cache._json_bytes(manifest), dtype=np.uint8),
        )


@pytest.mark.parametrize("mutation", [
    "checksum", "identity", "range", "asymmetric", "self_loop", "offsets", "dtype", "metadata",
])
def test_malformed_or_stale_cache_is_rebuilt(tmp_path: Path, mutation: str) -> None:
    source = _source(tmp_path)
    adjacency, _, original = _run(source, tmp_path)
    path = Path(original["path"])
    _rewrite_archive(path, mutation)
    repaired, _, rebuilt = _run(source, tmp_path)
    assert repaired == adjacency
    assert rebuilt["status"] == "built"
    assert rebuilt["invalid_cache_reason"]
    assert _run(source, tmp_path)[2]["status"] == "hit"


def test_truncated_cache_is_rebuilt(tmp_path: Path) -> None:
    source = _source(tmp_path)
    _, _, original = _run(source, tmp_path)
    path = Path(original["path"])
    path.write_bytes(path.read_bytes()[:50])
    _, _, rebuilt = _run(source, tmp_path)
    assert rebuilt["status"] == "built"
    assert rebuilt["invalid_cache_reason"]


def test_pickle_array_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    _, _, original = _run(source, tmp_path)
    with Path(original["path"]).open("wb") as stream:
        np.savez_compressed(
            stream, offsets=np.array([object()], dtype=object),
            neighbors=np.array([], dtype="<i8"), manifest=np.array([], dtype=np.uint8),
        )
    _, _, rebuilt = _run(source, tmp_path)
    assert rebuilt["status"] == "built"
    assert "allow_pickle=False" in rebuilt["invalid_cache_reason"]


@pytest.mark.parametrize("kwargs", [
    {"source_sha256": "not-a-hash"},
    {"geoids": []},
    {"geoids": [_GEOIDS[0], _GEOIDS[0]]},
    {"geoids": ["not-a-block"]},
])
def test_invalid_cache_inputs_fail(tmp_path: Path, kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _run(tmp_path / "unused.shp", tmp_path, **kwargs)


def test_failed_atomic_write_retains_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    _, _, original = _run(source, tmp_path)
    path = Path(original["path"])
    path.write_bytes(b"existing invalid cache")

    def fail_replace(source: Any, destination: Any) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(cache.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated write failure"):
        _run(source, tmp_path)
    assert path.read_bytes() == b"existing invalid cache"
    assert not list((tmp_path / "cache").glob("*.tmp"))
