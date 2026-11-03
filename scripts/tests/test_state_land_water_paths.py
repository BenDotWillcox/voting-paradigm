"""Part-level display connectivity must not manufacture physical connections."""

from __future__ import annotations

import copy

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, box

from scripts.state_land_water_paths import derive_state_water_paths


def run(shapes, land, *, assignments=None, parts=None, links=None, adjacency=None):
    assignments = np.array(assignments if assignments is not None else [0] * len(shapes), dtype=np.int64)
    if parts is None:
        parts = {0: [part for shape, area in zip(shapes, land) if area for part in
                     (list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape])]}
    return derive_state_water_paths(
        parts, {i: shape for i, shape in enumerate(shapes) if land[i] == 0},
        lambda node: shapes[node], [f"b{i}" for i in range(len(shapes))],
        np.array(land, dtype=np.int64), assignments,
        adjacency if adjacency is not None else lambda _: range(len(shapes)), links, "02",
    )


def link(identifier, left, left_point, right, right_point, *, parts=(0, 0), districts=None):
    props = {"id": identifier, "endpoints": [
        {"geoid": f"b{left}", "part_index": parts[0], "coordinate": list(left_point)},
        {"geoid": f"b{right}", "part_index": parts[1], "coordinate": list(right_point)},
    ]}
    if districts is not None:
        props["endpoint_districts"] = districts
    return {"type": "Feature", "properties": props, "geometry": {
        "type": "LineString", "coordinates": [list(left_point), list(right_point)],
    }}


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def test_physical_water_path_has_exact_part_trace_and_is_deterministic():
    shapes = [box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)]
    features, audit = run(shapes, [1, 0, 1])
    assert audit["all_components_explained"]
    assert audit["physical_shared_edge_only"]
    assert len(features) == 1
    props = features[0]["properties"]
    assert props["block_path"] == ["b0", "b1", "b2"]
    assert props["water_block_count"] == 1
    assert props["source_part_path"] == [
        {"geoid": "b0", "source_polygon_part": 0, "water_only": False},
        {"geoid": "b1", "source_polygon_part": 0, "water_only": True},
        {"geoid": "b2", "source_polygon_part": 0, "water_only": False},
    ]
    assert features[0]["geometry"]["coordinates"] == [[1.0, 0.5], [2.0, 0.5]]
    assert (features, audit) == run(shapes, [1, 0, 1], adjacency=lambda _: [2, 1, 0, 2])


def test_multipart_water_does_not_connect_distant_source_parts():
    shapes = [box(0, 0, 1, 1), MultiPolygon([box(1, 0, 2, 1), box(4, 0, 5, 1)]), box(5, 0, 6, 1)]
    features, audit = run(shapes, [1, 0, 1])
    assert features == []
    assert not audit["all_components_explained"]
    assert audit["districts"][0]["physical_source_component_groups"] == 2
    assert audit["districts"][0]["water_polygon_part_count"] == 2


def test_multipart_land_does_not_implicitly_connect_its_own_islands():
    shapes = [MultiPolygon([box(0, 0, 1, 1), box(4, 0, 5, 1)]), box(1, 0, 2, 1)]
    _, audit = run(shapes, [1, 0])
    assert not audit["all_components_explained"]
    assert audit["districts"][0]["land_component_count"] == 2


def test_same_block_multipart_water_can_connect_only_through_other_physical_parts():
    shapes = [box(0, 0, 1, 1), MultiPolygon([box(1, 0, 2, 1), box(3, 0, 4, 1)]),
              box(2, 0, 3, 1), box(4, 0, 5, 1)]
    features, audit = run(shapes, [1, 0, 0, 1])
    assert audit["all_components_explained"]
    assert features[0]["properties"]["block_path"] == ["b0", "b1", "b2", "b1", "b3"]
    assert [p["source_polygon_part"] for p in features[0]["properties"]["source_part_path"]] == [0, 0, 0, 1, 0]


def test_corner_contacts_and_bbox_false_positives_are_not_edges():
    shapes = [box(0, 0, 1, 1), box(1, 1, 2, 2), box(5, 5, 6, 6)]
    features, audit = run(shapes, [1, 0, 1])
    assert features == []
    assert not audit["all_components_explained"]
    assert audit["districts"][0]["combined_source_component_groups"] == 3


def test_recorded_link_on_retained_land_is_separate_from_physical_paths():
    shapes = [box(0, 0, 1, 1), box(4, 0, 5, 1)]
    links = collection(link("saved-water", 0, (1, .5), 1, (4, .5)))
    original = copy.deepcopy(links)
    features, audit = run(shapes, [1, 1], links=links)
    assert features == []
    assert audit["all_components_explained"]
    assert not audit["physical_shared_edge_only"]
    assert audit["districts"][0]["recorded_connection_ids_used"] == ["saved-water"]
    assert links == original


def test_recorded_link_on_removed_water_gets_physical_access_without_rewriting_link():
    shapes = [box(0, 0, 1, 1), box(1, 0, 2, 1), box(4, 0, 5, 1), box(5, 0, 6, 1)]
    links = collection(link("saved-exclave", 1, (2, .5), 2, (4, .5)))
    original = copy.deepcopy(links)
    features, audit = run(shapes, [1, 0, 0, 1], links=links)
    assert audit["all_components_explained"]
    assert len(features) == 2
    assert not audit["physical_shared_edge_only"]
    for feature in features:
        props = feature["properties"]
        assert props["derivation_schema_version"] == 2
        recorded = next(p for p in props["endpoints"] if p["kind"] == "recorded-connection-endpoint")
        assert recorded["recorded_link_id"] == "saved-exclave"
        side = recorded["recorded_endpoint_index"]
        assert recorded["coordinate"] == original["features"][0]["geometry"]["coordinates"][side]
        assert props["water_block_count"] == 1
        assert len(props["source_part_path"]) == 2
    assert links == original


def test_recorded_chain_through_all_water_component_has_endpoint_to_endpoint_access():
    shapes = [box(0, 0, 1, 1), box(3, 0, 4, 1), box(6, 0, 7, 1)]
    links = collection(link("left", 0, (1, .5), 1, (3, .5)), link("right", 1, (4, .5), 2, (6, .5)))
    features, audit = run(shapes, [1, 0, 1], links=links)
    assert audit["all_components_explained"]
    assert len(features) == 1
    props = features[0]["properties"]
    assert props["block_path"] == ["b1"]
    assert props["land_component_ids"] == [None, None]
    assert {e["recorded_link_id"] for e in props["endpoints"]} == {"left", "right"}
    assert features[0]["geometry"]["coordinates"] == [[3., .5], [4., .5]]


def test_recorded_link_cannot_join_the_wrong_part_of_a_multipart_water_block():
    shapes = [box(0, 0, 1, 1), MultiPolygon([box(1, 0, 2, 1), box(4, 0, 5, 1)]), box(8, 0, 9, 1)]
    links = collection(link("saved", 1, (5, .5), 2, (8, .5), parts=(1, 0)))
    _, audit = run(shapes, [1, 0, 1], links=links)
    assert not audit["all_components_explained"]
    assert audit["districts"][0]["combined_source_component_groups"] == 2


def test_unseen_all_water_orphan_is_not_silently_discarded():
    shapes = [box(0, 0, 1, 1), box(4, 0, 5, 1)]
    features, audit = run(shapes, [1, 0])
    assert not features
    assert audit["districts"][0]["remaining_component_groups"] == 1
    assert audit["districts"][0]["combined_source_component_groups"] == 2
    assert not audit["all_components_explained"]


def test_cross_district_recorded_link_remains_unused():
    shapes = [box(0, 0, 1, 1), box(3, 0, 4, 1)]
    links = collection(link("unused", 0, (1, .5), 1, (3, .5), districts=[0, 1]))
    features, audit = run(shapes, [1, 1], assignments=[0, 1], parts={0: [shapes[0]], 1: [shapes[1]]}, links=links)
    assert not features
    assert audit["all_components_explained"]
    assert not audit["recorded_connections"][0]["used_in_combined_audit"]
    assert all(not district["recorded_connection_ids_used"] for district in audit["districts"])


def test_physical_paths_never_cross_saved_district_assignments():
    shapes = [box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1), box(1, 1, 2, 2)]
    features, audit = run(shapes, [1, 0, 1, 1], assignments=[0, 1, 0, 1],
                          parts={0: [shapes[0], shapes[2]], 1: [shapes[3]]})
    assert not features
    assert not audit["all_components_explained"]


def test_alaska_continuous_longitude_is_preserved():
    shapes = [box(-182, 50, -181, 51), box(-181, 50, -180, 51), box(-180, 50, -179, 51)]
    features, audit = run(shapes, [1, 0, 1])
    assert audit["all_components_explained"]
    assert features[0]["geometry"]["coordinates"] == [[-181., 50.5], [-180., 50.5]]


@pytest.mark.parametrize("mutate,match", [
    (lambda f: f["properties"]["endpoints"][0].update(part_index=99), "source Polygon part"),
    (lambda f: f["properties"]["endpoints"][0].update(coordinate=[1., .4]), "preserved line"),
    (lambda f: f["properties"].update(endpoint_districts=[0, 1]), "saved assignments"),
    (lambda f: f["properties"].update(used_by_district=1), "same-district ownership"),
])
def test_stale_recorded_evidence_is_rejected(mutate, match):
    shapes = [box(0, 0, 1, 1), box(3, 0, 4, 1)]
    item = link("stale", 0, (1, .5), 1, (3, .5))
    mutate(item)
    with pytest.raises(ValueError, match=match):
        run(shapes, [1, 1], links=collection(item))


def test_endpoint_outside_its_original_source_geometry_is_rejected():
    shapes = [box(0, 0, 1, 1), box(3, 0, 4, 1)]
    with pytest.raises(ValueError, match="off its source boundary"):
        run(shapes, [1, 1], links=collection(link("bad", 0, (1.01, .5), 1, (3, .5))))


def test_source_part_must_wholly_belong_to_exact_land_component():
    shapes = [box(0, 0, 2, 1), box(2, 0, 3, 1)]
    with pytest.raises(ValueError, match="wholly within one"):
        run(shapes, [1, 0], parts={0: [box(0, 0, 1.5, 1)]})


def test_all_water_district_requires_explicit_fallback():
    with pytest.raises(ValueError, match="explicit display fallback"):
        run([box(0, 0, 1, 1)], [0], parts={0: []})


def test_all_source_zero_land_parts_are_required():
    with pytest.raises(ValueError, match="Every zero-land"):
        derive_state_water_paths({0: [box(0, 0, 1, 1)]}, {}, lambda _: box(1, 0, 2, 1),
                                 ["b0", "b1"], np.array([1, 0]), np.array([0, 0]), [[], []])
