from copy import deepcopy
import json
import math

import pytest
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box, mapping, shape
from shapely import coverage_is_valid

from scripts.build_block_plan_bundle import BundleBuilder, OUTPUT, digest, encoded
from scripts.publish_state_explorer import read_reference
import scripts.build_national_land_overview as national
import scripts.publish_state_land_display as land_publication
from scripts.national_land_arcs import shared_arc_partition
import scripts.national_land_arcs as arc_module
from scripts.tests.test_state_land_publication_integration import bundle as land_bundle


def plan(state="06", count=1, populations=None, bbox=None):
    populations = populations or [123] * count
    return {"id": f"{state}-{count}", "stateFips": state, "districtCount": count, "districtPopulations": populations,
            "residentPopulation": sum(populations), "coordinateFrame": "alaska-continuous" if state == "02" else "source", "bbox": bbox or [0, 0, 4, 4]}


def document(p, geometries):
    return {"type": "FeatureCollection", "metadata": {}, "features": [{"type": "Feature", "properties": {
        "district_id": i, "population": p["districtPopulations"][i], "saved_metric": "unchanged"}, "geometry": mapping(g)} for i, g in enumerate(geometries)]}


def test_boundary_error_is_a_conservative_continuous_bound():
    before, after = [box(0, 0, 1, 1)], [box(.02, 0, 1.02, 1)]
    bound = national.boundary_error_bound(before, after, .01)
    assert .02 <= bound <= .02500001


def test_opposite_ring_directions_use_one_shared_simplified_arc():
    divider = [(2 + .005 * math.sin(i / 3), i / 100) for i in range(201)]
    left = Polygon([[0, 0], *divider, [0, 2], [0, 0]])
    right = Polygon([divider[0], [4, 0], [4, 2], *divider[::-1]])
    original = [left, right]
    result, audit = shared_arc_partition(original, [box(4, 0, 5, 2)], .02, .05)
    assert coverage_is_valid(result)
    assert result[0].intersection(result[1]).area == 0
    assert result[0].union(result[1]).equals(left.union(right))
    assert audit["sharedArcsSimplifiedOnce"] and audit["protectedExteriorEdgesUnchanged"]
    assert audit["introducedCoordinates"] == 0
    assert national.point_count(result) < national.point_count(original) / 2


def test_local_rollback_preserves_hole_near_a_narrow_coastal_indent(monkeypatch):
    # Force a locally unsafe proposal to exercise rollback even when GEOS's
    # joint simplifier now anticipates and avoids this collision itself.
    class IndependentProposal:
        def __init__(self, coordinates):
            self.coordinates = coordinates
        def simplify(self, tolerance, preserve_topology):
            return MultiLineString([LineString(value).simplify(tolerance, preserve_topology=preserve_topology) for value in self.coordinates])
    monkeypatch.setattr(arc_module, "MultiLineString", IndependentProposal)
    coastline = [(-.015 * math.sin(math.pi * i / 100), i / 100) for i in range(101)]
    hole = box(-.0148, .49, -.0145, .51)
    mainland = Polygon([*coastline, [2, 1], [2, 0], coastline[0]], [list(hole.exterior.coords)])
    island = box(3, 0, 3.001, .001)
    original = [MultiPolygon([mainland, island])]
    assert original[0].is_valid
    result, audit = shared_arc_partition(original, [], .02, .05)
    assert audit["locallyRestoredArcSections"] > 0
    assert result[0].is_valid and coverage_is_valid(result)
    assert national.topology(result[0]) == national.topology(original[0]) == (2, 1)
    assert national.point_count(result) < national.point_count(original) * .8
    source_coordinates = set(map(tuple, national.get_coordinates(original[0])))
    assert set(map(tuple, national.get_coordinates(result[0]))).issubset(source_coordinates)


def test_shared_enclave_hole_boundary_keeps_matching_ownership():
    enclave = Polygon([(1 + .2 * math.cos(i * math.pi / 50), 1 + .2 * math.sin(i * math.pi / 50)) for i in range(101)])
    surrounding = Polygon(list(box(0, 0, 2, 2).exterior.coords), [list(enclave.exterior.coords)])
    result, audit = shared_arc_partition([surrounding, enclave], [], .02, .05)
    assert coverage_is_valid(result)
    assert result[0].intersection(result[1]).area == 0
    assert result[0].union(result[1]).equals(box(0, 0, 2, 2))
    assert national.topology(result[0]) == (1, 1)
    assert result[0].interiors[0].equals(result[1].exterior)
    assert audit["sharedArcsSimplifiedOnce"]


def test_neighbor_band_preserves_interstate_area_and_shared_district_coverage():
    left = [(0.008 * math.sin(i * .5), i / 100) for i in range(201)]
    first = Polygon([*left, [2, 2], [2, 0], left[0]])
    second = box(2, 0, 4, 2)
    p = plan(count=2)
    source = document(p, [first, second])
    before = deepcopy(source)
    neighbor = box(4, 0, 5, 2)
    result, audit = national.simplify_state(source, p, [neighbor], tolerance=.02, border_band=.05)
    assert source == before
    assert not audit["retainedOriginal"]
    assert audit["outputPoints"] < audit["inputPoints"] / 2
    assert audit["protectedExteriorEdgesUnchanged"]
    assert audit["outputCoverageValid"]
    guard = neighbor.buffer(.05, quad_segs=4)
    for original, output in zip(source["features"], result["features"]):
        assert original["properties"] == output["properties"]
        assert shape(original["geometry"]).intersection(guard).equals(shape(output["geometry"]).intersection(guard))
    assert coverage_is_valid([shape(f["geometry"]) for f in result["features"]])


def test_islands_holes_and_alaska_frame_are_preserved():
    geometry = MultiPolygon([Polygon([[-189, 51], [-188, 51], [-188, 54], [-189, 54], [-189, 51]],
        [[[-188.8, 52], [-188.2, 52], [-188.2, 53], [-188.8, 53], [-188.8, 52]]]), box(-183, 51, -182.999, 51.001)])
    p = plan("02", bbox=[-190, 50, -180, 60])
    result, audit = national.simplify_state(document(p, [geometry]), p, [], tolerance=.02, border_band=.05)
    assert audit["inputTopology"] == audit["outputTopology"] == [(2, 1)]
    assert shape(result["features"][0]["geometry"]).bounds[0] < -180
    assert audit["coordinateWrappingApplied"] is False


def test_unacceptable_simplification_is_retained_explicitly(monkeypatch):
    p = plan()
    source = document(p, [box(0, 0, 1, 1)])
    monkeypatch.setattr(national, "boundary_error_bound", lambda *args: .1)
    output, audit = national.simplify_state(source, p, [], tolerance=.02, border_band=.05)
    assert output["features"] == source["features"]
    assert audit["retainedOriginal"] and len(audit["attempts"]) == 3
    assert all(attempt["status"] == "rejected" for attempt in audit["attempts"])


@pytest.fixture
def national_bundle(land_bundle, monkeypatch):
    root, cache = land_bundle["root"], land_bundle["cache"]
    land_publication.publish(root, cache, write=True)
    monkeypatch.setattr(national, "validate_anchors", lambda manifest: ["02", "26"])
    land_bundle["beforeManifest"] = (root / OUTPUT / "manifest.json").read_bytes()
    land_bundle["beforeIndex"] = (root / OUTPUT / "server-index.json").read_bytes()
    return land_bundle


def test_national_dryrun_and_publication_are_additive_and_reuse_connections(national_bundle):
    root, cache = national_bundle["root"], national_bundle["cache"]
    old = json.loads(national_bundle["beforeManifest"])
    old_index = json.loads(national_bundle["beforeIndex"])
    dry = national.build(root, cache)
    assert dry["status"] == "complete" and not dry["published"]
    assert (root / OUTPUT / "manifest.json").read_bytes() == national_bundle["beforeManifest"]
    assert (root / OUTPUT / "server-index.json").read_bytes() == national_bundle["beforeIndex"]
    report = national.build(root, cache, publish=True)
    current = json.loads((root / OUTPUT / "manifest.json").read_bytes())
    index = json.loads((root / OUTPUT / "server-index.json").read_bytes())
    assert {k: v for k, v in current.items() if k != "nationalLandAnchors"} == old
    assert index["proofs"] == old_index["proofs"]
    assert all(index["assets"][k] == v for k, v in old_index["assets"].items())
    assert index["manifestSha256"] == digest(encoded(current))
    assert set(report["assets"]) == set(index["assets"]) - set(old_index["assets"])
    for size, anchor in current["nationalLandAnchors"].items():
        assert anchor["planIds"] == old["landAnchors"][size]["planIds"]
        for key in ("connections", "recordedConnections"):
            assert anchor[key] == old["landAnchors"][size][key]
        output = read_reference(root, cache, anchor["outlines"], index["assets"])
        assert sum(f["properties"]["population"] for f in output["features"]) == 34
        alaska = next(f for f in output["features"] if f["properties"]["state_fips"] == "02")
        assert shape(alaska["geometry"]).bounds[0] < -180
        assert all(c["savedDistrictPropertiesUnchanged"] for c in report["metrics"][size]["checks"].values())
    history = root / national.NAMESPACE / "publication-history"
    assert (history / f"manifest-{digest(national_bundle['beforeManifest'])}.json").read_bytes() == national_bundle["beforeManifest"]
    assert (history / f"server-index-{digest(national_bundle['beforeIndex'])}.json").read_bytes() == national_bundle["beforeIndex"]


def test_partial_national_pilot_cannot_publish(national_bundle):
    with pytest.raises(ValueError, match="complete four-anchor"):
        national.build(national_bundle["root"], national_bundle["cache"], house_sizes=[1000], states={"02"}, publish=True)


def test_prepared_report_publishes_without_rebuilding_geometry(national_bundle, monkeypatch):
    root, cache = national_bundle["root"], national_bundle["cache"]
    prepared = national.build(root, cache)
    monkeypatch.setattr(national, "build_anchor", lambda *args, **kwargs: pytest.fail("Publication must reuse prepared assets"))
    report = national.publish_prepared(root, cache, prepared)
    assert report["published"] and report["publicationSeconds"] >= 0
    assert json.loads((root / OUTPUT / "manifest.json").read_bytes())["nationalLandAnchors"] == prepared["anchors"]


@pytest.mark.parametrize("key", ["baseManifestSha256", "runtimeHashes", "connections"])
def test_prepared_report_rejects_stale_or_changed_pins(national_bundle, key):
    root, cache = national_bundle["root"], national_bundle["cache"]
    prepared = national.build(root, cache)
    if key == "baseManifestSha256":
        prepared[key] = "0" * 64
    elif key == "runtimeHashes":
        prepared[key] = {}
    else:
        prepared["anchors"]["1000"]["connections"] = prepared["anchors"]["1000"]["outlines"]
    with pytest.raises(ValueError):
        national.publish_prepared(root, cache, prepared)
    assert (root / OUTPUT / "manifest.json").read_bytes() == national_bundle["beforeManifest"]


def test_prepared_topology_is_compared_with_actual_source_not_only_report(national_bundle):
    root, cache = national_bundle["root"], national_bundle["cache"]
    prepared = national.build(root, cache)
    old_index = json.loads(national_bundle["beforeIndex"])
    assets = {**old_index["assets"], **prepared["assets"]}
    old_ref = prepared["anchors"]["1000"]["outlines"]
    output = read_reference(root, cache, old_ref, assets)
    feature = next(f for f in output["features"] if f["properties"]["state_fips"] == "02")
    geometry = shape(feature["geometry"])
    feature["geometry"] = mapping(MultiPolygon([*geometry.geoms, box(-186, 55, -185.99, 55.01)]))
    builder = BundleBuilder(root, cache_root=cache)
    new_ref = builder.generated(output, "tampered-national-1000.geojson")
    prepared["anchors"]["1000"]["outlines"] = new_ref
    del prepared["assets"][old_ref["url"].removeprefix("/api/district-plans/")]
    prepared["assets"].update(builder.assets)
    check = prepared["metrics"]["1000"]["checks"]["02-1"]
    check["inputTopology"] = check["outputTopology"] = [(3, 1)]
    with pytest.raises(ValueError, match="topology or error audit"):
        national.publish_prepared(root, cache, prepared)
    assert (root / OUTPUT / "manifest.json").read_bytes() == national_bundle["beforeManifest"]


def test_prepared_false_coverage_flag_cannot_disable_geometry_validation(national_bundle):
    root, cache = national_bundle["root"], national_bundle["cache"]
    prepared = national.build(root, cache)
    prepared["metrics"]["1000"]["checks"]["02-1"]["outputCoverageValid"] = False
    with pytest.raises(ValueError, match="topology or error audit"):
        national.publish_prepared(root, cache, prepared)


def test_stale_base_prevents_national_publication(national_bundle, monkeypatch):
    real = national.build_anchor
    def intervening_change(root, *args, **kwargs):
        result = real(root, *args, **kwargs)
        path = root / OUTPUT / "manifest.json"
        value = json.loads(path.read_bytes())
        value["intervening_change"] = True
        path.write_bytes(encoded(value))
        return result
    monkeypatch.setattr(national, "build_anchor", intervening_change)
    with pytest.raises(ValueError, match="Live metadata changed"):
        national.build(national_bundle["root"], national_bundle["cache"], house_sizes=[1000])
    assert (national_bundle["root"] / OUTPUT / "server-index.json").read_bytes() == national_bundle["beforeIndex"]
