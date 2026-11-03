"""Exercise publication against real tiny gzip assets and preserved app metadata."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, Polygon, box, mapping

from scripts.build_block_plan_bundle import BundleBuilder, OUTPUT, digest, encoded
from scripts.build_michigan_explorer_geometry import boundary_layers
from scripts.publish_state_explorer import read_reference
import scripts.publish_state_land_display as publication


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))


def collection(plan, geometry, *, schema=None):
    metadata = {"planId": plan["id"], "stateFips": plan["stateFips"], "coordinateFrame": plan["coordinateFrame"], "coverage": "land-focused"}
    if schema is not None:
        metadata["schemaVersion"] = schema
    return {"type": "FeatureCollection", "metadata": metadata, "features": [{"type": "Feature",
        "properties": {"district_id": 0, "population": plan["residentPopulation"]}, "geometry": mapping(geometry)}]}


def geometry_assets(builder, plan, geometry, label):
    document = collection(plan, geometry)
    coast, dividers, _ = boundary_layers(document, plan["id"])
    coast["features"][0]["properties"]["state_fips"] = plan["stateFips"]
    result = {"overview": builder.generated(document, f"{label}-overview.geojson"),
              "detail": builder.generated(document, f"{label}-detail.geojson"),
              "coast": builder.generated(coast, f"{label}-coast.geojson"),
              "dividers": builder.generated(dividers, f"{label}-dividers.geojson"),
              "detailDividers": builder.generated(dividers, f"{label}-detail-dividers.geojson"),
              "coordinateFrame": plan["coordinateFrame"], "coverage": "land-focused"}
    return result


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """Only national membership size is mocked; IO, hashes and validation run."""
    root, cache = tmp_path, tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(publication, "validate_anchors", lambda manifest: ["02", "26"])
    runtime_path = root / "scripts" / "frozen-display.py"
    runtime_path.parent.mkdir()
    runtime_path.write_bytes(b"# frozen display dependency\n")
    (cache / "source.zip").write_bytes(b"preserved source evidence")
    (cache / "assignments.json").write_bytes(b'{"original_assignments":[0,0]}')
    source_sha = digest((cache / "source.zip").read_bytes())
    assignment_sha = digest((cache / "assignments.json").read_bytes())
    plans = {
        "26-1": {"id": "26-1", "stateFips": "26", "coordinateFrame": "source", "districtCount": 1,
                 "residentPopulation": 13, "districtPopulations": [13], "blockCount": 3, "recordedLinkCount": 0,
                 "bbox": [-88, 41, -82, 48], "assets": {}, "houseSizes": [435, 574, 692, 1000]},
        "02-1": {"id": "02-1", "stateFips": "02", "coordinateFrame": "alaska-continuous", "districtCount": 1,
                 "residentPopulation": 21, "districtPopulations": [21], "blockCount": 4, "recordedLinkCount": 1,
                 "bbox": [-190, 50, -180, 60], "assets": {}, "houseSizes": [435, 574, 692, 1000]},
    }
    catalog = {"plans": [{"plan_id": p["id"], "validation": {"checkpoint_sha256": assignment_sha},
                           "source": {"archive_sha256": source_sha}} for p in plans.values()]}
    catalog_path = "prompts/catalog.json"
    write_json(root / catalog_path, catalog)
    catalog_sha = digest(encoded(catalog))
    original = BundleBuilder(root, cache_root=cache)
    recorded_document = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {
        "id": "accepted-ak-water-001", "kind": "recorded-water-link", "endpoint_districts": [0, 0], "used_by_district": 0},
        "geometry": {"type": "LineString", "coordinates": [[-188, 52], [-183, 52]]}}]}
    recorded = original.generated(recorded_document, "preserved-recorded.geojson")
    plans["02-1"]["assets"]["connections"] = recorded
    explorers, land_displays = {}, {}
    for state in ("26", "02"):
        p = plans[f"{state}-1"]
        full = box(-87, 42, -83, 47) if state == "26" else box(-190, 50, -180, 60)
        geometries = geometry_assets(original, p, full, state + "-original")
        geometries["coverage"] = "land-focused" if state == "26" else "census"
        plans[p["id"]]["assets"].update({"full": geometries["detail"], "state": geometries["detail"], "national": geometries["overview"]})
        geometries["summary"] = original.generated({"original-populations": [p["residentPopulation"]]}, f"{state}-summary.json")
        geometries["spatialIndex"] = original.generated({"original-block-chunks": ["unchanged"]}, f"{state}-spatial.json")
        cities = original.generated({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "Preserved city"},
            "geometry": {"type": "Point", "coordinates": [full.centroid.x, full.centroid.y]}}]}, f"{state}-cities.geojson")
        explorers[state] = {"cities": cities, "cityCount": 1, "plans": {p["id"]: geometries}}
        if state == "26":
            connections = original.generated({"type": "FeatureCollection", "features": []}, "mi-original-derived.geojson")
            land_displays[p["id"]] = {"planId": p["id"], "state": geometries["detail"], "national": geometries["overview"],
                "connections": connections, "summary": {"derivedConnectionCount": 0, "method": "Original Michigan method"}}
    manifest = {"schemaVersion": 1, "catalogSha256": catalog_sha, "houseSizes": [435, 574, 692, 1000],
                "plans": plans, "stateExplorers": explorers, "landDisplays": land_displays,
                "anchors": [{"houseSize": size, "planIds": ["02-1", "26-1"], "outlines": plans["02-1"]["assets"]["national"]}
                            for size in (435, 574, 692, 1000)], "comparisonLayers": {"unchanged": True}}
    index = {"schemaVersion": 1, "catalogPath": catalog_path, "catalogSha256": catalog_sha,
             "manifestSha256": digest(encoded(manifest)), "assets": deepcopy(original.assets), "proofs": {"02-1": {"pinned": "original-proof"}}}
    write_json(root / OUTPUT / "manifest.json", manifest)
    write_json(root / OUTPUT / "server-index.json", index)
    before_manifest, before_index = encoded(manifest), encoded(index)

    # New land geometry is continuous in Alaska and retains both land islands.
    land = MultiPolygon([Polygon([[-189, 51], [-188, 51], [-188, 54], [-189, 54], [-189, 51]],
                                [[[-188.8, 52], [-188.2, 52], [-188.2, 53], [-188.8, 53], [-188.8, 52]]]),
                         box(-183, 51, -182, 54)])
    generated = BundleBuilder(root, cache_root=cache)
    geometry = geometry_assets(generated, plans["02-1"], land, "02-land")
    derived_document = {"type": "FeatureCollection", "metadata": {"planId": "02-1", "stateFips": "02",
        "coordinateFrame": "alaska-continuous", "schemaVersion": 2}, "features": [{"type": "Feature",
        "properties": {"id": "ak-derived-001", "kind": "derived-water-adjacency", "district_id": 0},
        "geometry": {"type": "LineString", "coordinates": [[-188.8, 52], [-188.2, 52]]}}]}
    derived = generated.generated(derived_document, "02-derived.geojson")
    display = {"planId": "02-1", "state": geometry["detail"], "national": geometry["overview"], "connections": derived,
               "summary": {"derivedConnectionCount": 1, "zeroLandBlockCount": 1, "zeroLandPopulation": 0, "method": "display-only"}}
    audit = {"residentPopulation": 21, "blockCount": 4, "recordedLinkCount": 1, "recordedConnectionsSha256": recorded["sha256"],
             "assignmentsSha256": assignment_sha, "sourceArchiveSha256": source_sha,
             "waterPaths": {"all_components_explained": True, "derived_connection_count": 1},
             "preservedFiles": [{"path": ".cache/source.zip", "sha256": source_sha}, {"path": ".cache/assignments.json", "sha256": assignment_sha}]}
    fragment = {"status": "complete", "catalogSha256": catalog_sha, "baseManifestSha256": digest(before_manifest),
                "baseIndexSha256": digest(before_index), "landDisplays": {"02-1": display}, "geometryPlans": {"02-1": geometry},
                "assets": generated.assets, "audit": {"runtimeHashes": {"scripts/frozen-display.py": digest(runtime_path.read_bytes())}, "plans": {"02-1": audit}}}
    fragment_path = root / publication.NAMESPACE / "states/02.json"
    write_json(fragment_path, fragment)
    return {"root": root, "cache": cache, "beforeManifest": before_manifest, "beforeIndex": before_index,
            "manifest": manifest, "index": index, "fragment": fragment, "fragmentPath": fragment_path,
            "runtimePath": runtime_path, "recordedDocument": recorded_document, "derivedDocument": derived_document}


def assert_live_unchanged(bundle):
    assert (bundle["root"] / OUTPUT / "manifest.json").read_bytes() == bundle["beforeManifest"]
    assert (bundle["root"] / OUTPUT / "server-index.json").read_bytes() == bundle["beforeIndex"]


def test_dryrun_then_publish_preserves_originals_and_emits_all_anchor_layers(bundle):
    root, cache = bundle["root"], bundle["cache"]
    original_source = (cache / "source.zip").read_bytes()
    original_assignments = (cache / "assignments.json").read_bytes()
    dry = publication.publish(root, cache)
    assert dry["status"] == "complete" and dry["states"] == 2 and dry["plans"] == 2
    assert_live_unchanged(bundle)
    assert not (root / publication.REPORT).exists()
    report = publication.publish(root, cache, write=True)
    current = json.loads((root / OUTPUT / "manifest.json").read_bytes())
    index = json.loads((root / OUTPUT / "server-index.json").read_bytes())
    assert index["manifestSha256"] == digest(encoded(current))
    assert index["stateLandDisplayProvenance"]["reportSha256"] == digest((root / publication.REPORT).read_bytes())
    assert current["plans"] == bundle["manifest"]["plans"]
    assert current["anchors"] == bundle["manifest"]["anchors"]
    assert current["comparisonLayers"] == bundle["manifest"]["comparisonLayers"]
    assert current["stateExplorers"]["26"] == bundle["manifest"]["stateExplorers"]["26"]
    assert current["landDisplays"]["26-1"] == bundle["manifest"]["landDisplays"]["26-1"]
    assert index["proofs"] == bundle["index"]["proofs"]
    assert all(index["assets"][key] == value for key, value in bundle["index"]["assets"].items())
    old = bundle["manifest"]["stateExplorers"]["02"]
    new = current["stateExplorers"]["02"]
    assert new["cities"] == old["cities"]
    assert new["plans"]["02-1"]["spatialIndex"] == old["plans"]["02-1"]["spatialIndex"]
    assert new["plans"]["02-1"]["summary"] == old["plans"]["02-1"]["summary"]
    assert new["plans"]["02-1"]["censusOverview"] == old["plans"]["02-1"]["overview"]
    assert set(current["landAnchors"]) == {"435", "574", "692", "1000"}
    for anchor in current["landAnchors"].values():
        for key in ("outlines", "coast", "dividers", "connections", "recordedConnections"):
            document = read_reference(root, cache, anchor[key], index["assets"])
            assert document["type"] == "FeatureCollection"
            assert document["metadata"]["coordinateFrames"]["02"] == "alaska-continuous"
        outlines = read_reference(root, cache, anchor["outlines"], index["assets"])
        assert sum(feature["properties"]["population"] for feature in outlines["features"]) == 34
        alaska = next(f for f in outlines["features"] if f["properties"]["state_fips"] == "02")
        assert alaska["geometry"]["type"] == "MultiPolygon" and alaska["geometry"]["coordinates"][0][0][0][0] < -180
        recorded = read_reference(root, cache, anchor["recordedConnections"], index["assets"])["features"][0]
        assert recorded["geometry"] == bundle["recordedDocument"]["features"][0]["geometry"]
        assert recorded["properties"]["id"] == "accepted-ak-water-001"
        derived = read_reference(root, cache, anchor["connections"], index["assets"])["features"][0]
        assert derived["properties"]["id"] == "ak-derived-001"
        assert derived["geometry"] == bundle["derivedDocument"]["features"][0]["geometry"]
    assert report["shorelines"]["02-1"] == {"outer": 2, "inland": 1}
    history = root / publication.NAMESPACE / "publication-history"
    assert (history / f"manifest-{digest(bundle['beforeManifest'])}.json").read_bytes() == bundle["beforeManifest"]
    assert (history / f"server-index-{digest(bundle['beforeIndex'])}.json").read_bytes() == bundle["beforeIndex"]
    assert (cache / "source.zip").read_bytes() == original_source
    assert (cache / "assignments.json").read_bytes() == original_assignments


@pytest.mark.parametrize("failure,expected", [
    ("partial", "Incomplete"), ("base", "different app metadata"), ("runtime", "runtime changed"),
    ("missing-runtime", "Mixed or missing"), ("assignment", "source/assignment identity"),
    ("mismatched-display", "matched explorer geometry"), ("unexplained", "does not reconcile"),
    ("derived-count", "Derived connections"), ("source-evidence", "Preserved evidence changed"),
])
def test_bad_fragment_never_replaces_live_metadata(bundle, failure, expected):
    fragment = deepcopy(bundle["fragment"])
    if failure == "partial":
        fragment["geometryPlans"].clear()
    elif failure == "base":
        fragment["baseManifestSha256"] = "0" * 64
    elif failure == "runtime":
        bundle["runtimePath"].write_bytes(b"changed runtime")
    elif failure == "missing-runtime":
        fragment["audit"]["runtimeHashes"] = {}
    elif failure == "assignment":
        fragment["audit"]["plans"]["02-1"]["assignmentsSha256"] = "0" * 64
    elif failure == "mismatched-display":
        fragment["landDisplays"]["02-1"]["state"] = bundle["manifest"]["plans"]["02-1"]["assets"]["full"]
    elif failure == "unexplained":
        fragment["audit"]["plans"]["02-1"]["waterPaths"]["all_components_explained"] = False
    elif failure == "derived-count":
        fragment["landDisplays"]["02-1"]["summary"]["derivedConnectionCount"] = 2
    elif failure == "source-evidence":
        (bundle["cache"] / "source.zip").write_bytes(b"changed source")
    write_json(bundle["fragmentPath"], fragment)
    with pytest.raises(ValueError, match=expected):
        publication.publish(bundle["root"], bundle["cache"], write=True)
    assert_live_unchanged(bundle)
    assert not (bundle["root"] / publication.REPORT).exists()
