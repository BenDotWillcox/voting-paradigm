"""Rendering changes must preserve the accepted source-plan contract."""
from copy import deepcopy
import json

import numpy as np
import pytest
from shapely.geometry import box, mapping, shape

from scripts.build_block_plan_bundle import BundleBuilder, OUTPUT, digest, encoded
from scripts.build_michigan_land_display import (
    canonical, checked_assignments, publish_land_assets, read_graph,
    remove_water_only, simplify_display, source_reader, staged_plan,
)


def collection(*polygons):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"district_id": index, "population": 12 + index, "block_count": 3, "deviation": 0.2}, "geometry": mapping(polygon)}
        for index, polygon in enumerate(polygons)
    ]}


def test_remove_only_water_geometry_preserves_population_and_input():
    original = collection(box(0, 0, 3, 1))
    before = deepcopy(original)
    result, parts = remove_water_only(original, {1: box(1, 0, 2, 1)}, np.array([0, 0, 0]))
    assert original == before
    assert result["features"][0]["properties"] == original["features"][0]["properties"]
    assert len(parts[0]) == 2
    assert shape(result["features"][0]["geometry"]).area == 2
    assert result["features"][0]["properties"]["population"] == 12


def test_water_of_another_district_is_not_removed():
    original = collection(box(0, 0, 3, 1), box(3, 0, 4, 1))
    result, _ = remove_water_only(original, {0: box(1, 0, 2, 1)}, np.array([1]))
    assert shape(result["features"][0]["geometry"]).equals(box(0, 0, 3, 1))


def test_all_water_district_keeps_its_feature_and_people():
    original = collection(box(0, 0, 1, 1))
    result, parts = remove_water_only(original, {0: box(0, 0, 1, 1)}, np.array([0]))
    assert result["features"][0]["geometry"] is None
    assert result["features"][0]["properties"]["population"] == 12
    assert parts == {0: []}
    assert simplify_display(result, 0.1)["features"][0]["geometry"] is None


def test_simplification_retains_tiny_island_and_original_properties():
    from shapely.geometry import MultiPolygon
    original = collection(MultiPolygon([box(0, 0, 1, 1), box(2, 0, 2.00001, 0.00001)]))
    original["metadata"] = {}
    result = simplify_display(original, 0.002)
    assert len(shape(result["features"][0]["geometry"]).geoms) == 2
    assert result["features"][0]["properties"] == original["features"][0]["properties"]
    with pytest.raises(ValueError, match="tolerance"):
        simplify_display(original, float("nan"))


def test_source_population_audit_includes_water_residents():
    geoids = ["260000000000001", "260000000000002", "260000000000003"]
    plan = {"district_count": 2, "district_populations": [17, 8], "validation": {"district_block_counts": [2, 1]}}
    checkpoint = {"assignments": dict(zip(geoids, [0, 0, 1]))}
    result = checked_assignments(plan, checkpoint, geoids, np.array([12, 5, 8]))
    assert result.tolist() == [0, 0, 1]
    with pytest.raises(ValueError, match="populations"):
        checked_assignments(plan, checkpoint, geoids, np.array([12, 0, 8]))
    with pytest.raises(ValueError, match="coverage"):
        checked_assignments(plan, {"assignments": {geoids[0]: 0}}, geoids, np.array([12, 5, 8]))


def test_publication_adds_display_without_rewriting_saved_plans_or_proofs(tmp_path):
    bundle = tmp_path / OUTPUT
    bundle.mkdir(parents=True)
    source = tmp_path / "historical.json"
    source.write_bytes(b"saved original")
    manifest = {"catalogSha256": "catalog", "plans": {"26-13": {"recordedConnections": [], "state": {"sha256": "original"}}}, "anchors": {"435": "original"}, "comparisonLayers": {"26": "original"}}
    index = {"assets": {}, "proofs": {"original": {"hash": "unchanged"}}}
    original_manifest, original_index = deepcopy(manifest), deepcopy(index)
    builder = BundleBuilder(tmp_path)
    asset = builder.generated({"type": "FeatureCollection", "features": []}, "test.geojson")
    displays = {"26-13": {"state": asset}}
    publish_land_assets(tmp_path, manifest, index, builder, displays, {"test": True})
    after = json.loads((bundle / "manifest.json").read_bytes())
    for key in original_manifest:
        assert after[key] == original_manifest[key]
    saved_index = json.loads((bundle / "server-index.json").read_bytes())
    assert saved_index["proofs"] == original_index["proofs"]
    assert saved_index["manifestSha256"] == digest(encoded(after))
    assert source.read_bytes() == b"saved original"
    assert after["landDisplays"] == displays


def test_source_hash_mismatch_fails_before_reading_or_modifying_archive(tmp_path):
    source = tmp_path / "source.zip"
    source.write_bytes(b"source unchanged")
    with pytest.raises(ValueError, match="archive identity"):
        with source_reader(source, {"archive_bytes": source.stat().st_size, "archive_sha256": "0" * 64}):
            pytest.fail("Unpinned source must not be opened")
    assert source.read_bytes() == b"source unchanged"


def test_graph_order_and_payload_pins_are_enforced(tmp_path):
    import hashlib
    geoids = ["260000000000001", "260000000000002"]
    identity = {"node_count": 2, "ordered_geoids_sha256": digest(canonical(geoids))}
    offsets = np.array([0, 1, 2], dtype="<i8")
    neighbors = np.array([1, 0], dtype="<i8")
    metadata = {"node_count": 2, "edge_count": 1, "de9im_pattern": "F***1****", "all_source_geometries_valid": True, "source_coordinates_modified": False}
    checksum = hashlib.sha256()
    for value in (offsets.tobytes(), neighbors.tobytes(), canonical(metadata)):
        checksum.update(len(value).to_bytes(8, "little"))
        checksum.update(value)
    manifest = {"identity": identity, "graph_metadata": metadata, "payload_sha256": checksum.hexdigest()}
    graph = tmp_path / "graph.npz"
    np.savez(graph, offsets=offsets, neighbors=neighbors, manifest=np.frombuffer(canonical(manifest), dtype=np.uint8))
    assert read_graph(graph, identity, geoids)[0] == ((1,), (0,))
    with pytest.raises(ValueError, match="order"):
        read_graph(graph, identity, geoids[::-1])
    np.savez(graph, offsets=offsets, neighbors=np.array([0, 1], dtype="<i8"), manifest=np.frombuffer(canonical(manifest), dtype=np.uint8))
    with pytest.raises(ValueError, match="payload hash"):
        read_graph(graph, identity, geoids)


def test_staging_reuses_only_identical_pinned_proof_and_detects_tampering(tmp_path):
    calls = []
    def create():
        calls.append(True)
        display = collection(box(0, 0, 1, 1))
        return display, {0: [box(0, 0, 1, 1)]}, [], {"all_components_explained": True, "derived_connection_count": 0}
    identity = {"source": "same", "assignments": "same", "code": "same"}
    assert staged_plan(tmp_path, identity, create)[-1] is False
    assert staged_plan(tmp_path, identity, create)[-1] is True
    assert len(calls) == 1
    assert staged_plan(tmp_path, {**identity, "assignments": "different"}, create)[-1] is False
    directory = tmp_path / ".cache/block-main-port/michigan-land-staging" / digest(canonical(identity))
    (directory / "prepared.json.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="cache identity"):
        staged_plan(tmp_path, identity, create)


def test_pinched_water_hole_uses_valid_complete_partition_without_snapping():
    from shapely import coverage_is_valid
    from shapely.geometry import Polygon
    full = collection(box(0, 0, 3, 3), box(-3, 0, 0, 3))
    water_a = Polygon([(0, 1), (1, 0.5), (1, 1.5)])
    land_b = Polygon([(-1, 0), (0, 1), (-1, 2)])
    land = collection(box(0, 0, 3, 3).difference(water_a), land_b)
    land["metadata"] = {}
    assert not coverage_is_valid([shape(f["geometry"]) for f in land["features"]])
    before = deepcopy(land)
    result = simplify_display(land, 0.0001, full_collection=full)
    proof = result["metadata"]["coverage_certificate"]
    assert proof["joint_input_coverage_valid"]
    assert proof["joint_simplified_coverage_valid"]
    assert proof["exact_original_district_reconstruction"]
    assert not proof["coordinate_snapping_applied"]
    assert proof["temporary_water_faces"] == 3
    assert land == before
    assert all(a["properties"] == b["properties"] for a, b in zip(result["features"], land["features"]))
    for original, rendered in zip(land["features"], result["features"]):
        assert shape(original["geometry"]).equals(shape(rendered["geometry"]))


def test_invalid_partition_is_not_excused_by_hidden_water_fallback():
    full = collection(box(0, 0, 2, 2), box(1, 0, 3, 2))
    full["metadata"] = {}
    with pytest.raises(ValueError, match="Complete land/water"):
        simplify_display(full, 0.001, full_collection=full)
