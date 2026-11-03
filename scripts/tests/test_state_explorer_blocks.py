"""Shared geography may save bytes, never change a saved plan's Features."""
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from scripts.build_block_plan_bundle import BundleBuilder, digest, encoded
from scripts.build_state_explorer_blocks import (
    assignment_document, base_records, build_state, county_summary, geometry_bounds,
    plan_summary, reconcile_geometry, shared_chunk, source_features, validate_reconstruction,
)


def feature(number, state="44", county="001", district=0, population=1, longitude=-71):
    return {"type": "Feature", "properties": {"geoid": f"{state}{county}{number:010d}",
        "population": population, "district_id": district, "unchanged": {"flag": True}},
        "geometry": {"type": "Polygon", "coordinates": [[[longitude, 42], [longitude + .001, 42],
            [longitude + .001, 42.001], [longitude, 42.001], [longitude, 42]]]}}


def plan(state="44", count=2, populations=(20, 80), block_count=3):
    return {"id": f"{state}-{count}", "stateFips": state, "coordinateFrame": "alaska-continuous" if state == "02" else "source",
        "districtCount": count, "residentPopulation": sum(populations), "districtPopulations": list(populations), "blockCount": block_count}


def fixture_records(state="44", longitude=-71):
    features = [feature(1, state=state, population=20, longitude=longitude),
        feature(2, state=state, population=80, district=1, longitude=longitude),
        feature(3, state=state, population=0, district=1, longitude=longitude)]
    p = plan(state)
    county = {"fips": "001", "population": 100, "blockCount": 3}
    source = source_features({"type": "FeatureCollection", "features": features}, county, p)
    return p, county, source, base_records(source, p["coordinateFrame"])


def test_shared_geometry_restores_whole_source_features_and_zero_population(tmp_path):
    p, county, source, records = fixture_records()
    before = deepcopy(source)
    builder = BundleBuilder(tmp_path)
    shared = shared_chunk("44", "source", "c001-test", records)
    assert all("district_id" not in f["properties"] for f in shared["features"])
    geometry_asset = builder.generated(shared, "geometry.geojson")
    assignments = reconcile_geometry(source, records)
    document = assignment_document(p, "c001-test", geometry_asset, records, assignments)
    assignment_asset = builder.generated(document, "assignments.json")
    def decode(asset):
        entry = builder.assets[asset["url"].removeprefix("/api/district-plans/")]
        return json.loads(gzip.decompress((tmp_path / entry["path"]).read_bytes()))
    descriptor = {"chunkId": "c001-test", "blockCount": 3, "population": 100, "asset": geometry_asset}
    seen = set()
    validate_reconstruction(decode(geometry_asset), decode(assignment_asset), descriptor, p, source, seen)
    assert seen == set(source)
    assert source == before
    summary = county_summary(records, assignments, county, "Bristol")
    assert summary["districtShares"] == [{"districtId": 0, "population": 20, "blockCount": 1, "percent": 20},
        {"districtId": 1, "population": 80, "blockCount": 2, "percent": 80}]
    assert plan_summary(p, [summary], [1, 2])["districts"][1]["blockCount"] == 2


def test_only_assignment_may_differ_between_anchors():
    _, _, source, records = fixture_records()
    alternate = deepcopy(source)
    alternate[next(iter(alternate))]["properties"]["district_id"] = 1
    assert set(reconcile_geometry(alternate, records).values()) == {1}
    for mutate in [lambda f: f["properties"].update(population=21),
                   lambda f: f["properties"]["unchanged"].update(flag=1),
                   lambda f: f["geometry"]["coordinates"][0][1].__setitem__(0, -70),
                   lambda f: f.update(added="not in base")]:
        bad = deepcopy(source)
        mutate(bad[next(iter(bad))])
        with pytest.raises(ValueError, match="beyond district_id"):
            reconcile_geometry(bad, records)
    with pytest.raises(ValueError, match="coverage"):
        reconcile_geometry({}, records)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(stateFips="26"), lambda p: p.update(planId="44-3"),
    lambda p: p.update(coordinateFrame="alaska-continuous"), lambda p: p.update(chunkId="wrong"),
    lambda p: p.update(geometrySha256="0" * 64), lambda p: p.update(districtIds=[0]),
    lambda p: p.update(districtIds=[0, 1, 2]), lambda p: p.update(districtIds=[False, 1, 1]),
])
def test_assignment_sidecar_rejects_wrong_identity_or_assignment(mutation):
    p, _, source, records = fixture_records()
    asset = {"sha256": "a" * 64}
    shared = shared_chunk("44", "source", "test", records)
    assignments = assignment_document(p, "test", asset, records, reconcile_geometry(source, records))
    mutation(assignments)
    with pytest.raises(ValueError):
        validate_reconstruction(shared, assignments, {"chunkId": "test", "asset": asset, "blockCount": 3, "population": 100}, p, source, set())


def test_alaska_continuous_longitudes_and_missing_source_bbox_are_preserved():
    p, county, source, records = fixture_records("02", -187)
    original = deepcopy(source)
    assert records[0].bbox == (-187, 42, -186.999, 42.001)
    summary = county_summary(records, reconcile_geometry(source, records), county, "Aleutians West")
    assert summary["bbox"] == [-187, 42, -186.999, 42.001]
    assert summary["name"] == "Aleutians West"
    assert source == original
    with pytest.raises(ValueError, match="coordinate"):
        geometry_bounds(records[0].feature["geometry"], "source")


def test_vectorized_large_rings_match_scalar_full_bounds_and_reject_non_numbers():
    from scripts.build_michigan_spatial_blocks import geometry_bounds as scalar_bounds
    ring = [[-71 + i * .00001, 42 + (i % 9) * .00001] for i in range(100)]
    ring.append(ring[0])
    geometry = {"type": "Polygon", "coordinates": [ring]}
    assert geometry_bounds(geometry) == scalar_bounds(geometry)
    for invalid in [True, "-71", float("nan"), float("inf"), -400]:
        bad = deepcopy(geometry)
        bad["coordinates"][0][15][0] = invalid
        with pytest.raises(ValueError, match="coordinate"):
            geometry_bounds(bad)


def test_invalid_wrong_state_duplicate_and_noninteger_features_fail_closed():
    p, county, source, _ = fixture_records()
    for mutate in [lambda f: f["properties"].update(geoid="260010000000001"),
                   lambda f: f["properties"].update(population=True),
                   lambda f: f["properties"].update(district_id=-1),
                   lambda f: f["properties"].update(district_id=True)]:
        bad = deepcopy(list(source.values()))
        mutate(bad[0])
        with pytest.raises(ValueError):
            source_features({"type": "FeatureCollection", "features": bad}, county, p)
    bad = list(source.values()) + [next(iter(source.values()))]
    with pytest.raises(ValueError, match="duplicate"):
        source_features({"type": "FeatureCollection", "features": bad}, county, p)


def test_zero_population_county_shares_are_defined_and_totals_checked():
    p = plan(populations=(0, 0), block_count=1)
    f = feature(1, population=0, district=1)
    county = {"fips": "001", "population": 0, "blockCount": 1}
    records = base_records({f["properties"]["geoid"]: f}, "source")
    result = county_summary(records, reconcile_geometry({records[0].geoid: f}, records), county, "Empty")
    assert result["districtShares"][0]["percent"] == 0
    assert plan_summary(p, [result], [0, 1])["residentPopulation"] == 0
    with pytest.raises(ValueError, match="totals"):
        plan_summary(p, [result], [1, 0])


def test_end_to_end_fragment_is_additive_resumable_and_binds_inputs(tmp_path, monkeypatch):
    import scripts.build_state_explorer_blocks as module
    builder = BundleBuilder(tmp_path)
    p, county, source, _ = fixture_records()
    county_asset = builder.generated({"type": "FeatureCollection", "features": list(source.values())}, "saved-county.geojson")
    detail_asset = builder.generated({"planId": p["id"], "coordinateFrame": "source", "counties": [{**county, "asset": county_asset}]}, "detail.json")
    p["assets"] = {"detailIndex": detail_asset}
    counties_asset = builder.generated({"type": "FeatureCollection", "features": [{"properties": {"geoid": "44001", "name": "Bristol"}}]}, "counties.geojson")
    report_path = tmp_path / "saved-report.json"
    report_path.write_bytes(b'{"status":"complete"}')
    report_sha = digest(report_path.read_bytes())
    proof = {"reportPath": "saved-report.json", "reportSha256": report_sha, "manifestPath": "saved-report.json", "manifestSha256": report_sha}
    manifest = {"plans": {p["id"]: p}, "comparisonLayers": {"44": {"counties": {"asset": counties_asset}}}}
    index = {"catalogSha256": "a" * 64, "assets": deepcopy(builder.assets), "proofs": {p["id"]: proof}}
    catalog = {"plans": [{"plan_id": p["id"], "report_sha256": report_sha, "validation": {"district_block_counts": [1, 2]}}]}
    before = deepcopy((manifest, index, catalog))
    monkeypatch.setattr(module, "load_context", lambda root, cache: (manifest, index, catalog))
    monkeypatch.setattr(module, "runtime_hashes", lambda root: {"test": "pinned"})
    result = build_state(tmp_path, tmp_path / ".cache", "44")
    fragment = json.loads((tmp_path / result["path"]).read_bytes())
    assert fragment["status"] == "complete"
    assert fragment["audit"]["savedAssignmentsModified"] == 0
    assert fragment["audit"]["plans"]["44-2"]["districtPopulations"] == [20, 80]
    assert (manifest, index, catalog) == before
    assert build_state(tmp_path, tmp_path / ".cache", "44")["reused"] is True
    report_path.write_bytes(b'{"status":"changed"}')
    with pytest.raises(ValueError, match="Preserved input changed"):
        build_state(tmp_path, tmp_path / ".cache", "44")
