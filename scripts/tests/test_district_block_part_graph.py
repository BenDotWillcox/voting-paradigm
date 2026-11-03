"""Polygon-part geometry regressions and independent cache integrity checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import shapefile
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from districting.part_connectivity import part_component_counts
from scripts import district_block_part_graph as adapter


def _geoid(index: int) -> str:
    return f"20001000100{index:04d}"


def _source(tmp_path: Path, rows: list[tuple[str, Polygon | MultiPolygon]]) -> Path:
    path = tmp_path / "blocks.shp"
    with shapefile.Writer(str(path)) as writer:
        writer.field("GEOID20", "C", size=15)
        for geoid, geometry in rows:
            parts = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
            rings = []
            for part in parts:
                part = orient(part, sign=-1)
                rings.extend([list(part.exterior.coords), *[list(ring.coords) for ring in part.interiors]])
            writer.poly(rings)
            writer.record(geoid)
    return path


def _multipart_source(tmp_path: Path) -> Path:
    return _source(tmp_path, [
        (_geoid(1), MultiPolygon([box(0, 0, 1, 1), box(3, 0, 4, 1)])),
        (_geoid(2), box(0, -1, 4, 0)),
        (_geoid(3), box(-1, 0, 0, 1)),
    ])


def _cached(source: Path, tmp_path: Path, **kwargs: Any) -> Any:
    return adapter.load_or_build_shared_edge_part_graph(
        source, kwargs.pop("geoids", [_geoid(1), _geoid(2), _geoid(3)]),
        source_sha256=kwargs.pop("source_sha256", "a" * 64),
        cache_dir=tmp_path / "cache", **kwargs,
    )


def test_multipart_ownership_never_supplies_connectivity(tmp_path: Path) -> None:
    graph, metadata = adapter.build_shared_edge_part_graph(
        _multipart_source(tmp_path), [_geoid(1), _geoid(2), _geoid(3)],
    )
    assert graph.part_to_unit == (0, 0, 1, 2)
    assert graph.adjacency == ((2, 3), (2,), (0, 1), (0,))
    assert metadata["part_count"] == 4
    assert metadata["block_count"] == 3
    assert metadata["multipart_block_count"] == 1
    assert metadata["component_count"] == 1
    assert metadata["synthetic_ownership_edges"] is False
    # Unit 0's two parts do not connect district 0 through common ownership.
    assert part_component_counts(graph, [0, 1, 0], n_districts=2) == (2, 1)
    # Moving the entire zero-population unit to the common recipient repairs it.
    assert part_component_counts(graph, [1, 1, 0], n_districts=2) == (1, 1)


def test_source_order_and_hole_ring_are_preserved(tmp_path: Path) -> None:
    ring = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)], holes=[[(1, 1), (3, 1), (3, 3), (1, 3)]])
    source = _source(tmp_path, [
        (_geoid(1), ring),
        (_geoid(2), MultiPolygon([box(10, 0, 11, 1), box(1, 1, 3, 3)])),
    ])
    graph, metadata = adapter.build_shared_edge_part_graph(source, [_geoid(2), _geoid(1)])
    assert graph.part_to_unit == (0, 0, 1)
    assert graph.adjacency == ((), (2,), (1,))
    assert metadata["component_sizes"] == [2, 1]
    assert metadata["isolated_part_geoids"] == [_geoid(2)]


def test_corner_gap_and_overlap_are_not_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_QUERY_BATCH_SIZE", 1)
    source = _source(tmp_path, [
        (_geoid(1), box(0, 0, 1, 1)),
        (_geoid(2), box(1, 1, 2, 2)),
        (_geoid(3), box(1 + 1e-10, 0, 2, 0.5)),
        (_geoid(4), box(0.1, 0.1, 0.2, 0.2)),
    ])
    graph, metadata = adapter.build_shared_edge_part_graph(source, [_geoid(i) for i in range(1, 5)])
    assert graph.adjacency == ((), (), (), ())
    assert metadata["interior_overlap_pair_count"] == 1
    assert metadata["excluded_corner_pair_count"] == 1
    assert metadata["query_batch_count"] == 4
    assert metadata["source_coordinates_modified"] is False


def test_tiny_shared_edge_is_retained(tmp_path: Path) -> None:
    source = _source(tmp_path, [
        (_geoid(1), box(0, 0, 1, 1)),
        (_geoid(2), box(1, 1 - 1e-10, 2, 2)),
    ])
    graph, _ = adapter.build_shared_edge_part_graph(source, [_geoid(1), _geoid(2)])
    assert graph.adjacency == ((1,), (0,))


@pytest.mark.parametrize("state,culprit,source_district,target_district,parts", [
    ("maryland", "240419608001043", 16, 15, 3),
    ("virginia", "510010906001010", 18, 14, 2),
])
def test_actual_census_parts_expose_hidden_district_fragments(
    tmp_path: Path, state: str, culprit: str, source_district: int, target_district: int, parts: int,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / f"{state}-multipart-blocks.geojson"
    features = json.loads(fixture.read_text())["features"]
    geoids = [feature["properties"]["geoid"] for feature in features]
    geometries = [shape(feature["geometry"]) for feature in features]
    source = _source(tmp_path, list(zip(geoids, geometries)))
    graph, metadata = adapter.build_shared_edge_part_graph(source, geoids)
    unit = geoids.index(culprit)
    assert len(graph.unit_to_parts[unit]) == parts
    assert features[unit]["properties"]["population"] == 0
    assert metadata["interior_overlap_pair_count"] == 0
    labels = [int(feature["properties"]["district_id"] == target_district) for feature in features]
    assert features[unit]["properties"]["district_id"] == source_district
    before = part_component_counts(graph, labels, n_districts=2)
    assert before[0] >= parts
    # The fixture is a local neighborhood, not an entire state: other pieces
    # can connect outside it. Compare physical counts to exact local unions,
    # and require that moving all culprit parts removes its detached pieces.
    for district in range(2):
        union = unary_union([geometry for geometry, label in zip(geometries, labels) if label == district])
        count = len(union.geoms) if isinstance(union, MultiPolygon) else 1
        assert before[district] == count
    labels[unit] = 1
    after = part_component_counts(graph, labels, n_districts=2)
    assert after[0] == before[0] - (parts - 1)
    assert after[1] <= before[1]
    for part in graph.unit_to_parts[unit]:
        assert any(labels[graph.part_to_unit[neighbor]] == 1 for neighbor in graph.adjacency[part])


def test_build_and_hit_preserve_graph_without_source_read(tmp_path: Path) -> None:
    source = _multipart_source(tmp_path)
    graph, metadata, built = _cached(source, tmp_path)
    assert built["status"] == "built"
    assert built["bytes"] > 0
    assert "shared-edge-parts-" in built["path"]
    source.unlink()
    loaded, cached_metadata, hit = _cached(source, tmp_path)
    assert loaded == graph
    assert cached_metadata == metadata
    assert hit["status"] == "hit"
    assert hit["original_build_timing_reused"] is True
    assert hit["build_seconds"] == hit["write_seconds"] == 0
    assert not list((tmp_path / "cache").glob("*.tmp"))


@pytest.mark.parametrize("setting", ["source", "order", "builder", "domain", "schema", "rule", "geos"])
def test_identity_changes_never_reuse_stale_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str,
) -> None:
    source = _multipart_source(tmp_path)
    _, _, original = _cached(source, tmp_path)
    kwargs: dict[str, Any] = {}
    if setting == "source":
        kwargs["source_sha256"] = "b" * 64
    elif setting == "order":
        kwargs["geoids"] = [_geoid(2), _geoid(1), _geoid(3)]
    elif setting in ("builder", "domain"):
        monkeypatch.setattr(adapter, f"_{setting}_digest", lambda: "c" * 64)
    elif setting == "schema":
        monkeypatch.setattr(adapter, "_CACHE_SCHEMA", 2)
    elif setting == "rule":
        monkeypatch.setattr(adapter, "_TOPOLOGY_RULE", "new topology")
    else:
        monkeypatch.setattr(adapter.shapely, "geos_version_string", "new version")
    _, _, changed = _cached(source, tmp_path, **kwargs)
    assert changed["status"] == "built"
    assert original["key"] != changed["key"]


def _corrupt(path: Path, mutation: str) -> None:
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    manifest = json.loads(arrays.pop("manifest").tobytes().decode())
    if mutation == "checksum":
        manifest["payload_sha256"] = "0" * 64
    elif mutation == "identity":
        manifest["identity"]["ordered_geoids_sha256"] = "0" * 64
    elif mutation == "owner_missing":
        arrays["part_to_unit"][:] = 0
    elif mutation == "owner_range":
        arrays["part_to_unit"][0] = 9
    elif mutation == "owner_order":
        arrays["part_to_unit"][:] = [1, 0, 0, 2]
    elif mutation == "owner_dtype":
        arrays["part_to_unit"] = arrays["part_to_unit"].astype(float)
    elif mutation == "neighbor_range":
        arrays["neighbors"][0] = 99
    elif mutation == "self_loop":
        arrays["neighbors"][0] = 0
    elif mutation == "asymmetric":
        arrays["neighbors"][0] = 1
    elif mutation == "offsets":
        arrays["offsets"][0] = 1
    elif mutation == "metadata":
        manifest["graph_metadata"]["component_count"] = 999
    if mutation != "checksum":
        manifest["payload_sha256"] = adapter._payload_digest(
            arrays["offsets"], arrays["neighbors"], arrays["part_to_unit"], manifest["graph_metadata"],
        )
    arrays["manifest"] = np.frombuffer(adapter._json_bytes(manifest), dtype=np.uint8)
    with path.open("wb") as stream:
        np.savez_compressed(stream, **arrays)


@pytest.mark.parametrize("mutation", [
    "checksum", "identity", "owner_missing", "owner_range", "owner_order", "owner_dtype",
    "neighbor_range", "self_loop", "asymmetric", "offsets", "metadata",
])
def test_corrupt_cache_is_rebuilt_even_with_recomputed_checksum(tmp_path: Path, mutation: str) -> None:
    source = _multipart_source(tmp_path)
    original, _, built = _cached(source, tmp_path)
    _corrupt(Path(built["path"]), mutation)
    graph, _, rebuilt = _cached(source, tmp_path)
    assert graph == original
    assert rebuilt["status"] == "built"
    assert rebuilt["invalid_cache_reason"]
    assert _cached(source, tmp_path)[2]["status"] == "hit"


def test_truncated_and_pickle_caches_rebuild_safely(tmp_path: Path) -> None:
    source = _multipart_source(tmp_path)
    _, _, built = _cached(source, tmp_path)
    path = Path(built["path"])
    path.write_bytes(path.read_bytes()[:50])
    assert _cached(source, tmp_path)[2]["invalid_cache_reason"]
    with path.open("wb") as stream:
        np.savez_compressed(
            stream, offsets=np.array([object()], dtype=object), neighbors=np.array([], dtype="<i8"),
            part_to_unit=np.array([], dtype="<i8"), manifest=np.array([], dtype=np.uint8),
        )
    _, _, rebuilt = _cached(source, tmp_path)
    assert "allow_pickle=False" in rebuilt["invalid_cache_reason"]


@pytest.mark.parametrize("geoids,message", [
    ([], "At least one"), ([_geoid(1), _geoid(1)], "Duplicate input"),
    (["invalid"], "15-digit"), ([_geoid(1), _geoid(2)], "Missing source"),
    ([_geoid(2)], "Unexpected source"),
])
def test_input_alignment_is_required(tmp_path: Path, geoids: list[str], message: str) -> None:
    source = _source(tmp_path, [(_geoid(1), box(0, 0, 1, 1))])
    with pytest.raises(ValueError, match=message):
        adapter.build_shared_edge_part_graph(source, geoids)


def test_invalid_geometry_is_not_repaired(tmp_path: Path) -> None:
    source = _source(tmp_path, [(_geoid(1), Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)]))])
    with pytest.raises(ValueError, match="Invalid source block geometry"):
        adapter.build_shared_edge_part_graph(source, [_geoid(1)])


def test_atomic_failure_keeps_existing_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _multipart_source(tmp_path)
    _, _, built = _cached(source, tmp_path)
    path = Path(built["path"])
    path.write_bytes(b"old invalid cache")

    def fail_replace(source: Any, destination: Any) -> None:
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(adapter.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replacement failure"):
        _cached(source, tmp_path)
    assert path.read_bytes() == b"old invalid cache"
    assert not list((tmp_path / "cache").glob("*.tmp"))
