"""Overview cartography may hide tiny water, never reassign land or fake dividers."""
from copy import deepcopy
import gzip
import json

import pytest
from shapely.geometry import box, mapping, shape
from shapely import union_all

from scripts.build_michigan_explorer_geometry import boundary_layers, clean_overview_partition, read_exact_stage
from scripts.build_michigan_land_display import canonical, simplify_display
from scripts.build_block_plan_bundle import digest, encoded


def collection(*polygons):
    return {"type": "FeatureCollection", "metadata": {}, "features": [
        {"type": "Feature", "properties": {"district_id": index, "population": 100 + index, "block_count": 10}, "geometry": mapping(polygon)}
        for index, polygon in enumerate(polygons)]}


def test_small_enclosed_water_is_filled_by_saved_ownership_not_nearest_land():
    water = box(4, 4, 6, 6)
    full = collection(box(0, 0, 5, 10), box(5, 0, 10, 10))
    land = collection(box(0, 0, 5, 10).difference(water), box(5, 0, 10, 10).difference(water))
    before = deepcopy(land)
    clean, audit = clean_overview_partition(land, full, 5, area_scale_m2=1)
    assert audit["suppressed_water_holes"] == 1
    assert audit["suppressed_water_area_m2_approx"] == 4
    assert land == before
    for original, rendered in zip(full["features"], clean["features"]):
        assert shape(rendered["geometry"]).equals(shape(original["geometry"]))
        assert rendered["properties"] == original["properties"]
    assert shape(clean["features"][0]["geometry"]).intersection(shape(clean["features"][1]["geometry"])).area == 0


def test_large_lake_and_open_coastal_inlet_remain_visible():
    large_lake = box(2, 2, 5, 5)
    inlet = box(8, 4, 11, 6)
    full = collection(box(0, 0, 10, 10))
    land = collection(box(0, 0, 10, 10).difference(union_all([large_lake, inlet])))
    clean, audit = clean_overview_partition(land, full, 4, area_scale_m2=1)
    assert audit["suppressed_water_holes"] == 0
    assert audit["larger_holes_retained"] == 1
    assert shape(clean["features"][0]["geometry"]).equals(shape(land["features"][0]["geometry"]))


def test_tiny_water_surrounding_another_district_island_is_never_filled():
    lake = box(4, 4, 6, 6)
    island = box(4.9, 4.9, 5.1, 5.1)
    full = collection(box(0, 0, 10, 10).difference(island), island)
    land = collection(box(0, 0, 10, 10).difference(lake), island)
    clean, audit = clean_overview_partition(land, full, 5, area_scale_m2=1)
    assert audit["suppressed_water_holes"] == 0
    assert audit["holes_with_land_islands_retained"] == 1
    assert audit["state_land_components_before"] == audit["state_land_components_after"] == 2
    assert shape(clean["features"][1]["geometry"]).equals(island)
    assert not shape(clean["features"][0]["geometry"]).intersects(island)


def test_only_shared_district_edges_enter_bright_divider_mesh():
    first = box(0, 0, 5, 10).difference(box(0, 3, 2, 5))
    second = box(5, 0, 10, 10)
    coast, dividers, audit = boundary_layers(collection(first, second), "26-test")
    assert audit["shared_district_pairs"] == 1
    divider = shape(dividers["features"][0]["geometry"])
    assert divider.equals(first.boundary.intersection(second.boundary))
    assert list(dividers["features"][0]["properties"]["district_ids"]) == [0, 1]
    assert divider.intersection(shape(coast["features"][0]["geometry"])).length == 0
    assert divider.bounds == (5.0, 0.0, 5.0, 10.0)


def test_corner_only_neighbors_do_not_create_a_divider():
    _, dividers, _ = boundary_layers(collection(box(0, 0, 1, 1), box(1, 1, 2, 2)), "26-test")
    assert dividers["features"] == []


def test_invalid_land_ownership_and_overlap_are_rejected():
    with pytest.raises(ValueError, match="accepted district"):
        clean_overview_partition(collection(box(0, 0, 2, 2)), collection(box(0, 0, 1, 1)), 1, area_scale_m2=1)
    with pytest.raises(ValueError, match="overlapping"):
        boundary_layers(collection(box(0, 0, 2, 2), box(1, 0, 3, 2)), "26-test")
    with pytest.raises(ValueError, match="threshold"):
        clean_overview_partition(collection(box(0, 0, 1, 1)), collection(box(0, 0, 1, 1)), float("nan"))


def test_exact_stage_replay_matches_json_coordinate_roundtrip_and_rejects_changes(tmp_path):
    full = collection(box(0, 0, 2, 2))
    exact = collection(box(0, 0, 2, 2).difference(box(0.9, 0.9, 1.1, 1.1)))
    fine = json.loads(encoded(simplify_display(exact, 0.0001, full_collection=full)))
    identity = {"source": "pinned", "assignment": "pinned"}
    directory = tmp_path / ".cache/block-main-port/michigan-land-staging" / digest(canonical(identity))
    directory.mkdir(parents=True)
    raw = encoded({"display": exact})
    compressed = gzip.compress(raw, mtime=0)
    (directory / "prepared.json.gz").write_bytes(compressed)
    (directory / "manifest.json").write_bytes(encoded({"identity": identity, "gzip_sha256": digest(compressed), "raw_sha256": digest(raw)}))
    replay, proof = read_exact_stage(tmp_path, {"prepared_cache_identity": identity}, fine, full)
    assert canonical(replay) == canonical(exact)
    assert proof["fine_asset_replayed_exactly"]
    fine["features"][0]["properties"]["population"] += 1
    with pytest.raises(ValueError, match="pinned fine display"):
        read_exact_stage(tmp_path, {"prepared_cache_identity": identity}, fine, full)
    (directory / "prepared.json.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="compressed identity"):
        read_exact_stage(tmp_path, {"prepared_cache_identity": identity}, fine, full)
