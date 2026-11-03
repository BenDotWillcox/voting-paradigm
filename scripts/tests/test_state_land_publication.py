from copy import deepcopy

import pytest
from shapely.geometry import Polygon, mapping

from scripts.publish_state_land_display import annotated_features, assert_preserved, classify_coast


def ring(west, south, east, north):
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def coast(lines):
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"plan_id": "26-13"},
        "geometry": {"type": "MultiLineString", "coordinates": lines}}]}


def test_nested_lake_islands_stay_subdued_and_coordinates_unchanged():
    lines = [ring(0, 0, 10, 10), ring(2, 2, 8, 8), ring(3, 3, 4, 4), ring(11, 0, 12, 1)]
    source = coast(lines)
    before = deepcopy(source)
    result, counts = classify_coast(source)
    assert counts == {"outer": 2, "inland": 2}
    assert [f["properties"]["shoreline_scope"] for f in result["features"]] == ["outer", "inland", "inland", "outer"]
    assert [f["geometry"]["coordinates"] for f in result["features"]] == lines
    assert source == before


def test_concave_coast_does_not_treat_bbox_containment_as_inland():
    outer = [[0, 0], [10, 0], [10, 10], [8, 10], [8, 2], [2, 2], [2, 10], [0, 10], [0, 0]]
    _, counts = classify_coast(coast([outer, ring(3, 3, 4, 4)]))
    assert counts == {"outer": 2, "inland": 0}


def test_touching_components_and_alaska_continuous_frame_are_retained():
    lines = [ring(-190, 50, -189, 51), ring(-189, 51, -188, 52)]
    result, counts = classify_coast(coast(lines))
    assert counts == {"outer": 2, "inland": 0}
    assert [f["geometry"]["coordinates"] for f in result["features"]] == lines


@pytest.mark.parametrize("lines", [[ring(0, 0, 1, 1)] * 2, [[[0, 0], [1, 1], [2, 2], [0, 0]]], [[[0, 0], [1, 0], [1, 1], [0, 1]]]])
def test_ambiguous_coast_is_rejected(lines):
    with pytest.raises(ValueError):
        classify_coast(coast(lines))


def test_recorded_link_annotation_preserves_original_identity_and_coordinates():
    document = {"features": [{"type": "Feature", "properties": {"kind": "recorded-water-link", "link_id": "original-1"},
        "geometry": {"type": "LineString", "coordinates": [[-184, 54], [-179, 55]]}}]}
    before = deepcopy(document)
    result = annotated_features(document, {"stateFips": "02", "id": "02-2", "coordinateFrame": "alaska-continuous"})
    assert document == before
    assert result[0]["geometry"] == before["features"][0]["geometry"]
    assert result[0]["properties"]["link_id"] == "original-1"
    assert result[0]["properties"]["coordinate_frame"] == "alaska-continuous"


def manifest_pair():
    before = {"plans": {"02-2": {"population": [1, 2]}}, "anchors": [435], "landDisplays": {"26-13": {"original": True}},
        "stateExplorers": {"02": {"cities": "old-cities", "plans": {"02-2": {"overview": "continuous-census", "detail": "old-detail", "summary": "original-populations", "spatialIndex": "original-blocks"}}},
                           "26": {"cities": "mi-cities", "plans": {"26-13": {"overview": "clean-mi"}}}}}
    after = deepcopy(before)
    after["stateExplorers"]["02"]["plans"]["02-2"].update({"overview": "land", "detail": "land-fine", "censusOverview": "continuous-census"})
    after["landDisplays"]["02-2"] = {"new": True}
    return before, after


def test_publication_allows_only_display_changes():
    assert_preserved(*manifest_pair())


@pytest.mark.parametrize("target", ["population", "blocks", "census", "cities", "michigan"])
def test_publication_rejects_preservation_regressions(target):
    before, after = manifest_pair()
    record = after["stateExplorers"]["02"]["plans"]["02-2"]
    if target == "population":
        after["plans"]["02-2"]["population"] = [2, 1]
    elif target == "blocks":
        record["spatialIndex"] = "changed"
    elif target == "census":
        record["censusOverview"] = "wrapped-alaska"
    elif target == "cities":
        after["stateExplorers"]["02"]["cities"] = "changed"
    else:
        after["landDisplays"]["26-13"]["original"] = False
    with pytest.raises(ValueError):
        assert_preserved(before, after)
