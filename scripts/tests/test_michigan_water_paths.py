"""Regressions for honest display-only water-adjacency explanations."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, box

from scripts.michigan_water_paths import derive_water_paths


def derive(shapes, land, assignments, parts, edges):
    adjacency = [[] for _ in shapes]
    for a, b in edges:
        adjacency[a].append(b)
        adjacency[b].append(a)
    return derive_water_paths(parts, {i: shape for i, shape in enumerate(shapes) if land[i] == 0},
                              lambda i: shapes[i], [f"260000000{i:06d}" for i in range(len(shapes))],
                              np.array(land), np.array(assignments), adjacency)


def test_single_water_cell_connects_two_actual_land_components():
    left, water, right = box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)
    features, audit = derive([left, water, right], [1, 0, 1], [0, 0, 0], {0: [left, right]}, [(0, 1), (1, 2)])
    assert audit["all_components_explained"]
    assert len(features) == 1
    assert features[0]["properties"]["water_block_count"] == 1
    assert features[0]["properties"]["block_path"] == ["260000000000000", "260000000000001", "260000000000002"]
    assert features[0]["geometry"]["coordinates"] == [[1.0, 0.5], [2.0, 0.5]]
    assert features[0]["properties"]["schematic"] is True


def test_path_cannot_cross_another_saved_district():
    left, water, right = box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)
    # District1 also owns a real land endpoint beyond the water cell.
    top = box(1, 1, 2, 2)
    features, audit = derive([left, water, right, top], [1, 0, 1, 1], [0, 1, 0, 1],
                             {0: [left, right], 1: [top]}, [(0, 1), (1, 2), (1, 3)])
    assert features == []
    assert not audit["all_components_explained"]
    assert audit["districts"][0]["remaining_component_groups"] == 2


def test_multipart_land_block_does_not_teleport_between_its_parts():
    left, middle, right = box(0, 0, 1, 1), box(2, 0, 3, 1), box(4, 0, 5, 1)
    water1, water2 = box(1, 0, 2, 1), box(3, 0, 4, 1)
    features, audit = derive([MultiPolygon([left, right]), middle, water1, water2], [2, 1, 0, 0], [0] * 4,
                             {0: [left, middle, right]}, [(0, 2), (2, 1), (1, 3), (3, 0)])
    assert audit["all_components_explained"]
    assert len(features) == 2  # The shared census ID has not collapsed two islands.
    endpoint_parts = [endpoint["source_polygon_part"] for feature in features for endpoint in feature["properties"]["endpoints"]
                      if endpoint["geoid"] == "260000000000000"]
    assert sorted(endpoint_parts) == [0, 1]


def test_same_land_block_id_can_supply_two_distinct_physical_endpoints():
    left, water, right = box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)
    features, audit = derive([MultiPolygon([left, right]), water], [2, 0], [0, 0],
                             {0: [left, right]}, [(0, 1)])
    assert audit["all_components_explained"]
    assert features[0]["properties"]["block_path"] == ["260000000000000", "260000000000001", "260000000000000"]
    assert [value["source_polygon_part"] for value in features[0]["properties"]["endpoints"]] == [0, 1]


def test_corner_contact_in_cached_graph_is_rejected():
    land, water = box(0, 0, 1, 1), box(1, 1, 2, 2)
    with pytest.raises(ValueError, match="no actual shared-edge"):
        derive([land, water], [1, 0], [0, 0], {0: [land]}, [(0, 1)])


def test_multipart_water_cannot_teleport():
    land, water = box(0, 0, 1, 1), MultiPolygon([box(1, 0, 2, 1), box(10, 0, 11, 1)])
    with pytest.raises(ValueError, match="single Polygon"):
        derive([land, water], [1, 0], [0, 0], {0: [land]}, [(0, 1)])


def test_a_water_chain_has_no_land_interior_and_is_stable_under_graph_order():
    shapes = [box(i, 0, i + 1, 1) for i in range(5)]
    edges = [(0, 1), (1, 2), (2, 3), (3, 4)]
    first = derive(shapes, [1, 0, 0, 0, 1], [0] * 5, {0: [shapes[0], shapes[4]]}, edges)
    second = derive(shapes, [1, 0, 0, 0, 1], [0] * 5, {0: [shapes[0], shapes[4]]}, edges[::-1])
    assert first == second
    assert first[0][0]["properties"]["water_block_count"] == 3
    assert len(first[0][0]["properties"]["block_path"]) == 5


def test_three_components_share_water_without_redundant_cycle():
    left, right, top = box(0, 0, 1, 1), box(2, 0, 3, 1), box(1, 1, 2, 2)
    water = box(1, 0, 2, 1)
    features, audit = derive([left, right, top, water], [1, 1, 1, 0], [0] * 4,
                             {0: [left, right, top]}, [(0, 3), (1, 3), (2, 3)])
    assert len(features) == 2
    assert audit["all_components_explained"]


def test_endpoint_part_split_across_display_pieces_is_rejected():
    land, water = box(0, 0, 2, 1), box(2, 0, 3, 1)
    with pytest.raises(ValueError, match="exactly one display component"):
        derive([land, water], [1, 0], [0, 0], {0: [box(0, 0, 1, 1), box(1, 0, 2, 1)]}, [(0, 1)])
