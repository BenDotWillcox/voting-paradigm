"""Population-aware island grouping never masquerades as a constructed plan."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import shapefile
from shapely.geometry import MultiPolygon, Point, box
from shapely.geometry.polygon import orient

from districting.part_connectivity import PartGraph, part_component_counts
from scripts.district_block_part_graph import build_shared_edge_part_graph
from scripts.hawaii_population_links import (
    build_hawaii_connections, population_allocation_bound, select_population_aware_forest,
)


def _links(count: int, special: dict[tuple[int, int], float] | None = None) -> list[dict[str, Any]]:
    special = special or {}
    return [{"id": f"candidate-{a}-{b}", "component_ids": [a, b], "distance_m": special.get((a, b), 100 + a * 10 + b)}
            for a in range(count) for b in range(a + 1, count)]


def _box(x: float, y: float = 0, width: float = 1) -> Any:
    return box(-158 + x * .01, 21 + y * .01, -158 + (x + width) * .01, 21 + (y + 1) * .01)


def _source(tmp_path: Path, geometries: list[Any]) -> tuple[Path, list[str], PartGraph]:
    path = tmp_path / "blocks.shp"
    geoids = [f"15001000100{index:04d}" for index in range(len(geometries))]
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


def _build(source: tuple[Path, list[str], PartGraph], populations: list[int], k: int = 2) -> Any:
    return build_hawaii_connections(*source[:2], populations, source[2], district_count=k)


def test_compatible_large_islands_keep_their_own_districts() -> None:
    selected = select_population_aware_forest([100, 100], _links(2), 2)
    assert selected["selected_link_ids"] == []
    assert [group["district_count"] for group in selected["groups"]] == [1, 1]
    assert selected["population_bound"]["best_max_deviation_pct"] == 0
    assert selected["population_bound"]["is_constructed_plan"] is False


def test_large_islands_can_require_merge_despite_both_exceeding_one_district() -> None:
    selected = select_population_aware_forest([150, 150], _links(2), 3)
    assert selected["eligible_root_component_ids"] == [0, 1]
    assert len(selected["groups"]) == 1
    assert selected["groups"][0]["district_count"] == 3
    assert selected["selected_link_ids"] == ["candidate-0-1"]
    assert population_allocation_bound([150, 150], 3)["best_max_deviation_pct"] == 50


def test_population_feasibility_changes_small_island_attachment_before_root_merger() -> None:
    # Nearest-only attaches the 10-person island to root 0, making 210/190.
    # Population-aware policy retains both roots by accepting the longer edge.
    links = _links(3, {(0, 2): 1, (1, 2): 10, (0, 1): 20})
    selected = select_population_aware_forest([200, 190, 10], links, 4)
    assert len(selected["groups"]) == 2
    assert selected["selected_link_ids"] == ["candidate-1-2"]
    assert selected["population_bound"]["best_max_deviation_pct"] == 0


def test_nearest_distance_is_secondary_among_population_compatible_attachments() -> None:
    selected = select_population_aware_forest([100, 100, 1], _links(3, {(0, 2): 10, (1, 2): 1}), 2)
    assert selected["selected_link_ids"] == ["candidate-1-2"]


@pytest.mark.parametrize("k", [2, 3, 4])
def test_actual_hawaii_anchors_have_one_original_root_and_one_network(k: int) -> None:
    populations = [1016508, 200629, 154100, 73214, 7369, 3367, 84, *([0] * 10)]
    selected = select_population_aware_forest(populations, _links(17), k)
    assert selected["eligible_root_component_ids"] == [0]
    assert len(selected["groups"]) == 1
    assert len(selected["selected_link_ids"]) == 16
    assert selected["groups"][0]["district_count"] == k
    assert selected["population_bound"]["best_max_deviation_pct"] == 0
    # In particular, K4 must not promote several small islands together into a
    # protected root and unnecessarily freeze their 0.453% arithmetic mismatch.


@pytest.mark.parametrize(("k", "roots", "groups"), [(8, 2, 2), (10, 3, 2)])
def test_actual_hawaii_larger_anchor_arithmetic_requires_reattachment_or_merger(k: int, roots: int, groups: int) -> None:
    populations = [1016508, 200629, 154100, 73214, 7369, 3367, 84, *([0] * 10)]
    selected = select_population_aware_forest(populations, _links(17), k)
    assert len(selected["eligible_root_component_ids"]) == roots
    assert len(selected["groups"]) == groups
    assert sum(group["district_count"] for group in selected["groups"]) == k
    assert selected["population_bound"]["best_max_deviation_pct"] <= 1
    assert len(selected["selected_link_ids"]) == 17 - groups


def test_zero_population_chain_is_retained_and_deterministic() -> None:
    links = _links(4, {(0, 1): 1, (1, 2): 1, (2, 3): 1})
    first = select_population_aware_forest([100, 0, 0, 1], links, 1)
    second = select_population_aware_forest([100, 0, 0, 1], list(reversed(links)), 1)
    assert first == second
    assert first["selected_link_ids"] == ["candidate-0-1", "candidate-1-2", "candidate-2-3"]
    assert first["groups"][0]["component_ids"] == [0, 1, 2, 3]


def test_no_single_eligible_root_joins_all_components_explicitly() -> None:
    selected = select_population_aware_forest([50, 50], _links(2), 1)
    assert selected["no_individual_root_fallback"] is True
    assert selected["selected_link_ids"] == ["candidate-0-1"]


def test_exact_allocation_bound_requires_positive_quota_per_group() -> None:
    assert population_allocation_bound([100, 0], 1)["feasible_seat_allocation"] is False
    bound = population_allocation_bound([200, 100], 3)
    assert bound["seat_counts"] == [2, 1]
    assert bound["deviation_fraction"] == [0, 1]


def test_missing_permitted_edges_rejects_unconnectable_grouping() -> None:
    with pytest.raises(ValueError, match="permitted positive-length"):
        select_population_aware_forest([100, 1], [], 1)


def test_candidate_schema_rejects_duplicates_and_zero_distance() -> None:
    with pytest.raises(ValueError, match="unique"):
        select_population_aware_forest([100, 1], _links(2) * 2, 1)
    with pytest.raises(ValueError, match="positive finite"):
        select_population_aware_forest([100, 1], [{**_links(2)[0], "distance_m": 0}], 1)


@pytest.mark.parametrize("tolerance", [-1, 1, float("nan"), float("inf"), True])
def test_invalid_population_budget_rejected(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerance"):
        select_population_aware_forest([100, 1], _links(2), 1, population_tolerance=tolerance)


def test_source_builder_records_true_part_endpoints_and_preserves_source(tmp_path: Path) -> None:
    geometries = [_box(0, width=10), _box(11)]
    source = _source(tmp_path, geometries)
    before = source[0].read_bytes()
    graph, records, audit = _build(source, [1000, 1])
    assert graph.adjacency == ((1,), (0,))
    assert audit["source_geometry_modified"] is False
    assert audit["physical_component_count"] == 2
    assert audit["augmented_graph_connected"] is True
    assert audit["groups"][0]["district_count"] == 2
    assert audit["source_population"] == 1001
    assert len(records) == 1
    assert records[0]["state_fips"] == "15"
    assert records[0]["distance_m"] < 1200
    for endpoint in records[0]["endpoints"]:
        assert geometries[endpoint["part_node"]].boundary.distance(Point(endpoint["coordinate"])) < 1e-9
        assert endpoint["geoid"] == source[1][endpoint["part_node"]]
    assert source[0].read_bytes() == before


def test_connection_cannot_cross_third_component_interiors(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0), _box(4), box(-157.98, 20.99, -157.97, 21.02)])
    graph, records, audit = _build(source, [1000, 1, 0])
    assert sorted(row["component_ids"] for row in records) == [[0, 2], [1, 2]]
    assert audit["excluded_candidates"] == [{"component_ids": [0, 1],
        "reason": "candidate line crosses unrelated source component interiors", "crossed_component_ids": [2]}]
    assert part_component_counts(graph, [0, 0, 0], n_districts=1) == (1,)
    assert part_component_counts(graph, [0, 0, 1], n_districts=2) == (2, 1)


def test_multipart_ownership_never_creates_a_water_connection(tmp_path: Path) -> None:
    source = _source(tmp_path, [MultiPolygon([_box(0), _box(5)]), _box(10)])
    with pytest.raises(ValueError, match="common ownership"):
        _build(source, [1000, 1])


def test_source_graph_is_independently_verified(tmp_path: Path) -> None:
    path, geoids, graph = _source(tmp_path, [_box(0), _box(5)])
    with pytest.raises(ValueError, match="exactly match"):
        _build((path, geoids, PartGraph(((1,), (0,)), graph.part_to_unit)), [1000, 1])
    path, geoids, graph = _source(tmp_path, [_box(0), _box(1)])
    with pytest.raises(ValueError, match="exactly match"):
        _build((path, geoids, PartGraph(((), ()), graph.part_to_unit)), [1000, 1])


def test_corner_contacts_are_not_water_connections(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="permitted positive-length"):
        _build(_source(tmp_path, [_box(0), _box(1, 1)]), [1000, 1])


def test_supported_hawaii_extent_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="supported Hawaii extent"):
        _build(_source(tmp_path, [box(0, 0, 1, 1)]), [1000], 1)


def test_repeated_geometry_build_is_reproducible(tmp_path: Path) -> None:
    source = _source(tmp_path, [_box(0), _box(5), _box(7)])
    first = _build(source, [1000, 1, 0])
    second = _build(source, [1000, 1, 0])
    assert first[:2] == second[:2]
    first[2].pop("elapsed_seconds")
    second[2].pop("elapsed_seconds")
    assert first[2] == second[2]
