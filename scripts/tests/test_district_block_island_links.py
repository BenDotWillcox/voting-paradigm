"""Recorded water links join physical components without altering geography."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import shapefile
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient

from districting.part_connectivity import PartGraph, part_component_counts
from scripts.district_block_island_links import build_island_connections
from scripts.district_block_part_graph import build_shared_edge_part_graph


def _geoid(index: int) -> str:
    return f"44001000100{index:04d}"


def _box(x: float, y: float, width: float = 1, height: float = 1) -> Polygon:
    return box(-71.9+x*.01, 41.2+y*.01, -71.9+(x+width)*.01, 41.2+(y+height)*.01)


def _source(tmp_path: Path, geometries: list[Any]) -> tuple[Path, list[str], PartGraph]:
    path = tmp_path / "blocks.shp"
    geoids = [_geoid(index) for index in range(len(geometries))]
    with shapefile.Writer(str(path)) as writer:
        writer.field("GEOID20", "C", size=15)
        for geoid, geometry in zip(geoids, geometries, strict=True):
            parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
            rings = []
            for part in parts:
                clockwise = orient(part, sign=-1)
                rings.extend([list(clockwise.exterior.coords), *[list(ring.coords) for ring in clockwise.interiors]])
            writer.poly(rings)
            writer.record(geoid)
    graph, _ = build_shared_edge_part_graph(path, geoids)
    return path, geoids, graph


def _build(source: tuple[Path, list[str], PartGraph], pops: list[int], minimum: float = 100) -> Any:
    return build_island_connections(*source[:2], pops, source[2], state_fips="44", minimum_district_population=minimum)


def test_connection_uses_nearest_boundaries_not_centers(tmp_path: Path) -> None:
    geometries = [_box(0, 0, 10, 1), _box(11, 0, 1, 1)]
    source = _source(tmp_path, geometries)
    before = source[0].read_bytes()
    augmented, records, audit = _build(source, [1000, 1])
    assert len(records) == 1
    record = records[0]
    # Gap is one longitude increment; centroid separation would be 6.5 increments.
    assert record["distance_m"] == pytest.approx(audit["projection"]["x_scale"] * .01)
    assert record["distance_m"] < geometries[0].centroid.distance(geometries[1].centroid) * audit["projection"]["x_scale"]
    assert record["state_fips"] == "44"
    assert record["component_ids"] == [0, 1]
    assert augmented.adjacency == ((1,), (0,))
    assert audit["physical_edge_count"] == 0
    assert audit["synthetic_edge_count"] == 1
    assert audit["augmented_graph_connected"] is True
    assert audit["source_geometry_modified"] is False
    for endpoint in record["endpoints"]:
        assert endpoint["geoid"] == source[1][endpoint["part_node"]]
        assert endpoint["part_index"] == 0
        assert geometries[endpoint["part_node"]].boundary.distance(Point(endpoint["coordinate"])) < 1e-9
    assert source[0].read_bytes() == before


def test_close_island_chain_eventually_reaches_root(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0, 0), _box(5, 0), _box(7, 0)])
    graph, records, audit = _build(source, [1000, 2, 3])
    # The nearest islands join first, then the group attaches to the root.
    assert [r["component_ids"] for r in records] == [[1, 2], [0, 1]]
    assert graph.adjacency == ((1,), (0, 2), (1,))
    assert audit["augmented_component_count"] == 1
    assert all(component["attached_root_component"] == 0 for component in audit["components"])
    assert part_component_counts(graph, [0, 0, 0], n_districts=1) == (1,)
    # Putting the intermediate island in another district cannot let district 0
    # silently jump over it to the distal island.
    assert part_component_counts(graph, [0, 1, 0], n_districts=2) == (2, 1)


def test_forest_never_merges_two_eligible_roots(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0, 0), _box(5, 0), _box(2, 0)])
    graph, records, audit = _build(source, [1000, 1000, 3])
    assert len(records) == 1
    assert records[0]["component_ids"] == [0, 2]
    assert graph.adjacency == ((2,), (), (0,))
    assert audit["eligible_root_count"] == audit["augmented_component_count"] == 2
    assert audit["augmented_graph_connected"] is False
    assert audit["all_undersized_components_attached"] is True


def test_root_population_is_inclusive_and_counted_per_block(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0, 0), _box(1, 0), _box(5, 0)])
    _, records, audit = _build(source, [40, 60, 1])
    assert len(records) == 1
    assert audit["components"][0]["population"] == 100
    assert audit["components"][0]["eligible_root"] is True
    assert audit["source_population"] == 101
    assert audit["physical_edge_count"] == 1


def test_no_eligible_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No source component"):
        _build(_source(tmp_path, [_box(0, 0), _box(5, 0)]), [40, 40])


def test_disconnected_multipart_common_ownership_cannot_connect(tmp_path: Path) -> None:
    source = _source(tmp_path, [MultiPolygon([_box(0, 0), _box(5, 0)]), _box(10, 0)])
    assert source[2].part_to_unit == (0, 0, 1)
    with pytest.raises(ValueError, match="common ownership"):
        _build(source, [1000, 1])


def test_connected_multipart_owns_exact_endpoint_part(tmp_path: Path) -> None:
    # First block's pieces connect through the second block, not by ownership.
    source = _source(tmp_path, [MultiPolygon([_box(0, 0), _box(2, 0)]), _box(1, 0), _box(4, 0)])
    graph, records, audit = _build(source, [1000, 0, 1])
    assert source[2].adjacency == ((2,), (2,), (0, 1), ())
    endpoint = records[0]["endpoints"][0]
    assert endpoint["geoid"] == _geoid(0)
    assert endpoint["part_index"] == 1
    assert endpoint["part_node"] == 1
    assert 3 in graph.adjacency[1]
    assert 3 not in graph.adjacency[0]
    assert audit["source_population"] == 1001


def test_repeated_call_records_are_deterministic(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0, 0), _box(4, 0), _box(2, 2)])
    first = _build(source, [1000, 1, 1])
    second = _build(source, [1000, 1, 1])
    assert first[:2] == second[:2]
    for audit in (first[2], second[2]):
        audit.pop("elapsed_seconds")
    assert first[2] == second[2]


def test_false_or_missing_physical_graph_edges_rejected(tmp_path: Path) -> None:
    path, geoids, graph = _source(tmp_path, [_box(0, 0), _box(5, 0)])
    forged = PartGraph(((1,), (0,)), graph.part_to_unit)
    with pytest.raises(ValueError, match="exactly match source"):
        _build((path, geoids, forged), [1000, 1])
    path, geoids, graph = _source(tmp_path, [_box(0, 0), _box(1, 0)])
    missing = PartGraph(((), ()), graph.part_to_unit)
    with pytest.raises(ValueError, match="exactly match source"):
        _build((path, geoids, missing), [1000, 1])


def test_corner_contact_cannot_be_reclassified_as_water_gap(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0, 0), _box(1, 1)])
    with pytest.raises(ValueError, match="positive-length gap"):
        _build(source, [1000, 1])


def test_overlap_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0, 0, 2), _box(1, 0)])
    with pytest.raises(ValueError, match="overlapping interiors"):
        _build(source, [1000, 1])


def test_supported_state_and_extent_are_explicit(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0, 0), _box(5, 0)])
    with pytest.raises(ValueError, match="Rhode Island"):
        build_island_connections(*source[:2], [1000, 1], source[2], state_fips="06", minimum_district_population=100)
    with pytest.raises(ValueError, match="requested state"):
        _build((source[0], ["06"+g[2:] for g in source[1]], source[2]), [1000, 1])
    with pytest.raises(ValueError, match="supported Rhode Island extent"):
        _build(_source(tmp_path, [box(0, 0, 1, 1)]), [1000])


@pytest.mark.parametrize("minimum", [0, -1, float("nan"), float("inf")])
def test_invalid_minimum_rejected(tmp_path: Path, minimum: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        _build(_source(tmp_path, [_box(0, 0)]), [1000], minimum)


@pytest.mark.parametrize("pops", [[-1], [True], [1.2], []])
def test_invalid_populations_rejected(tmp_path: Path, pops: list[int]) -> None:
    with pytest.raises(ValueError, match="nonnegative integers"):
        _build(_source(tmp_path, [_box(0, 0)]), pops)
