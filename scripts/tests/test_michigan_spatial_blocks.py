from copy import deepcopy
import gzip
import json
import math

import pytest

from scripts.build_block_plan_bundle import BundleBuilder, encoded
from scripts.build_michigan_spatial_blocks import (
    PLAN_IDS, canonical_feature, chunk_document, combine_spatial, geometry_bounds,
    saved_blocks, spatial_groups, union_bounds, validate_chunk,
)


def feature(number, x=-85.0, population=1, district=0, size=0.001):
    return {"type": "Feature", "properties": {"geoid": f"26081{number:010d}", "population": population,
            "district_id": district, "custom": {"unchanged": [None, True, "source"]}},
            "geometry": {"type": "Polygon", "coordinates": [[[x, 43], [x + size, 43],
                [x + size, 43 + size], [x, 43 + size], [x, 43]]]}}


def records(features):
    return saved_blocks({"type": "FeatureCollection", "features": features},
        {"fips": "081", "blockCount": len(features), "population": sum(f["properties"]["population"] for f in features)}, 2, set())


def test_grid_split_preserves_every_whole_feature_and_zero_population_once():
    features = [feature(i, x=-85 + i * 0.00001, population=i % 3, district=i % 2) for i in range(700)]
    before = [canonical_feature(f) for f in features]
    groups = list(spatial_groups(records(features), "081"))
    assert all(len(values) <= 256 for _, values in groups)
    exported = [block for _, values in groups for block in values]
    assert len(exported) == len({b.geoid for b in exported}) == 700
    assert sorted(canonical_feature(b.feature) for b in exported) == sorted(before)
    assert [canonical_feature(f) for f in features] == before
    assert any(b.population == 0 for b in exported)


def test_partition_is_deterministic_under_reordered_county_input():
    features = [feature(i, x=-85 + (i % 17) * 0.0001) for i in range(600)]
    a = [(name, [b.geoid for b in values]) for name, values in spatial_groups(records(features), "081")]
    b = [(name, [b.geoid for b in values]) for name, values in spatial_groups(records(features[::-1]), "081")]
    assert a == b


def test_recursive_byte_limit_and_identical_centers_terminate_without_dropping_blocks():
    values = records([feature(i) for i in range(40)])
    groups = list(spatial_groups(values, "081", max_blocks=256, max_raw_bytes=1800))
    assert sum(len(v) for _, v in groups) == 40
    for name, group in groups:
        assert len(encoded(chunk_document("26-13", name, group))) <= 1800


def test_large_multipart_extent_is_isolated_and_full_bounds_cover_distant_piece():
    broad = feature(0, population=0)
    broad["geometry"] = {"type": "MultiPolygon", "coordinates": [broad["geometry"]["coordinates"], feature(99, x=-88)["geometry"]["coordinates"]]}
    values = records([broad, feature(1)])
    groups = list(spatial_groups(values, "081"))
    outlier = next((name, group) for name, group in groups if name.startswith("o"))
    assert len(outlier[1]) == 1
    assert union_bounds(outlier[1]) == [-88, 43, -84.999, 43.001]
    assert geometry_bounds(broad["geometry"])[0] == -88


def test_oversized_individual_block_is_retained_whole():
    large = feature(0)
    large["properties"]["sourceText"] = "x" * 2000
    groups = list(spatial_groups(records([large, feature(1)]), "081", max_raw_bytes=1000))
    outlier = next(v for name, v in groups if name.startswith("o"))
    assert len(outlier) == 1
    assert canonical_feature(outlier[0].feature) == canonical_feature(large)


@pytest.mark.parametrize("mutation", [
    lambda f: f["properties"].update(population=-1),
    lambda f: f["properties"].update(district_id=2),
    lambda f: f["properties"].update(geoid="261630000000001"),
    lambda f: f["geometry"]["coordinates"][0][1].__setitem__(0, math.nan),
    lambda f: f.update(geometry=None),
])
def test_invalid_source_features_fail_closed(mutation):
    bad = feature(1)
    mutation(bad)
    with pytest.raises((ValueError, TypeError)):
        records([bad])


def test_duplicate_source_geoid_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        records([feature(1), feature(1)])


def test_written_chunk_roundtrip_detects_geometry_property_bounds_and_duplicate_mutations(tmp_path):
    values = records([feature(1, population=0), feature(2, district=1)])
    document = chunk_document("26-13", "test", values)
    builder = BundleBuilder(tmp_path)
    reference = builder.generated(document, "test.geojson")
    entry = builder.assets[reference["url"].split("/api/district-plans/")[1]]
    decoded = json.loads(gzip.decompress((tmp_path / entry["path"]).read_bytes()))
    descriptor = {"chunkId": "test", "blockCount": 2, "population": 1, "bbox": union_bounds(values)}
    expected = {b.geoid: b for b in values}
    seen = set()
    validate_chunk(decoded, descriptor, "26-13", expected, seen)
    assert seen == set(expected)
    for mutate in [lambda d: d["features"][0]["properties"].update(population=1),
                   lambda d: d["features"][0]["geometry"]["coordinates"][0][1].__setitem__(0, -84),
                   lambda d: d["features"].append(d["features"][0])]:
        wrong = deepcopy(decoded)
        mutate(wrong)
        with pytest.raises(ValueError):
            validate_chunk(wrong, descriptor, "26-13", expected, set())
    with pytest.raises(ValueError, match="bounds"):
        validate_chunk(decoded, {**descriptor, "bbox": [-85, 43, -84.9999, 43.001]}, "26-13", expected, set())


def publication_fixture(tmp_path):
    builder = BundleBuilder(tmp_path)
    manifest = {"plans": {}, "michiganExplorer": {"plans": {}}, "anchors": [435, 574], "landDisplays": {"unchanged": True}}
    plans = {}
    for plan_id in PLAN_IDS:
        manifest["plans"][plan_id] = {"blockCount": 1, "residentPopulation": 1}
        manifest["michiganExplorer"]["plans"][plan_id] = {"overview": {"old": True}}
        values = records([feature(1)])
        chunk = builder.generated(chunk_document(plan_id, "test", values), f"{plan_id}.geojson")
        document = {"schemaVersion": 1, "planId": plan_id, "stateFips": "26", "totalBlockCount": 1, "totalPopulation": 1,
                    "counties": [{"fips": "081", "blockCount": 1, "population": 1}],
                    "chunks": [{"chunkId": "test", "blockCount": 1, "population": 1, "bbox": union_bounds(values), "asset": chunk}]}
        plans[plan_id] = {"spatialIndex": builder.generated(document, f"{plan_id}-index.json")}
    index = {"assets": {"old": {"unchanged": True}}, "proofs": {"old": True}}
    return manifest, index, plans, builder.assets


def test_publication_adds_only_spatial_references_and_preserves_all_original_records(tmp_path):
    manifest, index, plans, assets = publication_fixture(tmp_path)
    before = deepcopy((manifest, index))
    updated, updated_index = combine_spatial(tmp_path, manifest, index, plans, assets)
    assert (manifest, index) == before
    assert updated["plans"] == manifest["plans"]
    for plan_id in PLAN_IDS:
        assert updated["michiganExplorer"]["plans"][plan_id] == {**manifest["michiganExplorer"]["plans"][plan_id], **plans[plan_id]}
    assert updated_index["proofs"] == index["proofs"]
    assert updated_index["assets"]["old"] == index["assets"]["old"]


def test_publication_rejects_swapped_plan_index_or_conflicting_old_asset(tmp_path):
    manifest, index, plans, assets = publication_fixture(tmp_path)
    wrong = deepcopy(plans)
    wrong["26-13"] = wrong["26-18"]
    with pytest.raises(ValueError, match="accepted plan"):
        combine_spatial(tmp_path, manifest, index, wrong, assets)
    index["assets"][next(iter(assets))] = {"historical": "must remain"}
    with pytest.raises(ValueError, match="preserved resource"):
        combine_spatial(tmp_path, manifest, index, plans, assets)
