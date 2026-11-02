"""Topology and source-alignment checks for the offline block graph adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
import shapefile
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

from scripts import district_block_adjacency
from scripts.district_block_adjacency import build_shared_edge_adjacency


def _geoid(index: int) -> str:
    return f"20001000100{index:04d}"


def _write_source(tmp_path: Path, rows: list[tuple[str, Polygon]]) -> Path:
    path = tmp_path / "blocks.shp"
    with shapefile.Writer(str(path)) as writer:
        writer.field("GEOID20", "C", size=15)
        for geoid, polygon in rows:
            # Shapefile exterior rings use clockwise orientation.
            polygon = orient(polygon, sign=-1)
            writer.poly([
                list(polygon.exterior.coords),
                *[list(interior.coords) for interior in polygon.interiors],
            ])
            writer.record(geoid)
    return path


def test_shared_edges_exclude_corners_and_preserve_input_order(tmp_path: Path) -> None:
    source = _write_source(tmp_path, [
        (_geoid(1), box(0, 0, 1, 1)),
        (_geoid(2), box(1, 0, 2, 1)),
        (_geoid(3), box(2, 1, 3, 2)),
    ])
    adjacency, stats = build_shared_edge_adjacency(
        source, [_geoid(3), _geoid(1), _geoid(2)]
    )
    assert adjacency == ((), (2,), (1,))
    assert stats["edge_count"] == 1
    assert stats["excluded_corner_pair_count"] == 1
    assert stats["component_sizes"] == [2, 1]
    assert stats["isolated_node_geoids"] == [_geoid(3)]
    assert stats["all_source_geometries_valid"] is True
    assert stats["source_coordinates_modified"] is False
    assert build_shared_edge_adjacency(source, [_geoid(3), _geoid(1), _geoid(2)])[0] == adjacency


def test_tiny_positive_edge_is_accepted_without_a_length_threshold(tmp_path: Path) -> None:
    source = _write_source(tmp_path, [
        (_geoid(1), box(0, 0, 1, 1)),
        (_geoid(2), box(1, 1 - 1e-10, 2, 2)),
    ])
    adjacency, stats = build_shared_edge_adjacency(source, [_geoid(1), _geoid(2)])
    assert adjacency == ((1,), (0,))
    assert stats["component_count"] == 1


def test_gap_is_not_snapped_and_overlap_is_not_an_edge(tmp_path: Path) -> None:
    source = _write_source(tmp_path, [
        (_geoid(1), box(0, 0, 1, 1)),
        (_geoid(2), box(1 + 1e-10, 0, 2, 1)),
        (_geoid(3), box(0.5, 0.5, 0.75, 0.75)),
    ])
    adjacency, stats = build_shared_edge_adjacency(
        source, [_geoid(1), _geoid(2), _geoid(3)]
    )
    assert adjacency == ((), (), ())
    assert stats["interior_overlap_pair_count"] == 1
    assert stats["component_sizes"] == [1, 1, 1]


def test_hole_boundary_and_multiple_query_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(district_block_adjacency, "_QUERY_BATCH_SIZE", 1)
    enclosing_block = Polygon(
        [(0, 0), (3, 0), (3, 3), (0, 3)],
        holes=[[(1, 1), (2, 1), (2, 2), (1, 2)]],
    )
    source = _write_source(tmp_path, [
        (_geoid(1), enclosing_block),
        (_geoid(2), box(1, 1, 2, 2)),
        (_geoid(3), box(3, 0, 4, 3)),
    ])
    adjacency, stats = build_shared_edge_adjacency(
        source, [_geoid(3), _geoid(1), _geoid(2)]
    )
    assert adjacency == ((1,), (0, 2), (1,))
    assert stats["edge_count"] == 2
    assert stats["query_batch_count"] == 3
    assert stats["component_sizes"] == [3]


@pytest.mark.parametrize("geoids, message", [
    ([_geoid(1), _geoid(1)], "Duplicate input"),
    ([_geoid(1), _geoid(2)], "Missing source"),
    ([_geoid(2)], "Unexpected source"),
    (["invalid"], "Invalid block GEOID"),
    ([], "At least one"),
])
def test_input_identifiers_must_match_source(
    tmp_path: Path, geoids: list[str], message: str
) -> None:
    source = _write_source(tmp_path, [(_geoid(1), box(0, 0, 1, 1))])
    with pytest.raises(ValueError, match=message):
        build_shared_edge_adjacency(source, geoids)


def test_duplicate_source_identifiers_fail(tmp_path: Path) -> None:
    source = _write_source(tmp_path, [
        (_geoid(1), box(0, 0, 1, 1)),
        (_geoid(1), box(1, 0, 2, 1)),
    ])
    with pytest.raises(ValueError, match="Duplicate source"):
        build_shared_edge_adjacency(source, [_geoid(1)])


def test_invalid_source_geometry_fails_without_repair(tmp_path: Path) -> None:
    source = _write_source(tmp_path, [
        (_geoid(1), Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])),
    ])
    with pytest.raises(ValueError, match="Invalid source block geometry"):
        build_shared_edge_adjacency(source, [_geoid(1)])
