"""Cached discovery is pinned and cannot substitute whole-block connectivity."""

import hashlib

import numpy as np
import pytest

from scripts.build_block_plan_bundle import digest
from scripts.build_michigan_land_display import canonical as encoded
from scripts.state_land_candidate_graph import LEGACY_BUILDER_SHA256, TOPOLOGY_RULE, load_state_candidate_graph


def fixture(tmp_path, state="44", *, overlap=0):
    root = tmp_path / "bundle"
    root.mkdir()
    cache = tmp_path / "history-cache"
    geoids = [state + "0000000000001", state + "0000000000002"]
    source = "a" * 64
    identity = {"schema": 1, "topology_rule": TOPOLOGY_RULE, "source_archive_sha256": source,
                "ordered_geoids_sha256": digest(encoded(geoids)), "node_count": 2,
                "adjacency_builder_sha256": LEGACY_BUILDER_SHA256,
                "shapely_version": "2.1.2", "geos_version": "3.13.1"}
    key = digest(encoded(identity))
    directory = cache / ("kansas-block-benchmark/graph-cache" if state == "20" else f"state-block-benchmark/graph-cache/{state}")
    directory.mkdir(parents=True)
    path = directory / f"shared-edge-{key}.npz"
    offsets, neighbors = np.array([0, 1, 2], dtype="<i8"), np.array([1, 0], dtype="<i8")
    metadata = {"node_count": 2, "edge_count": 1, "de9im_pattern": "F***1****",
                "all_source_geometries_valid": True, "source_coordinates_modified": False,
                "interior_overlap_pair_count": overlap}
    checksum = hashlib.sha256()
    for value in (offsets.tobytes(), neighbors.tobytes(), encoded(metadata)):
        checksum.update(len(value).to_bytes(8, "little"))
        checksum.update(value)
    manifest = {"identity": identity, "graph_metadata": metadata, "payload_sha256": checksum.hexdigest()}
    np.savez(path, offsets=offsets, neighbors=neighbors, manifest=np.frombuffer(encoded(manifest), dtype=np.uint8))
    report = {"graph_cache": {"identity": identity, "key": key, "bytes": path.stat().st_size}}
    return root, cache, geoids, source, path, report


def test_verified_candidates_are_read_only_and_preserved(tmp_path):
    root, cache, geoids, source, path, report = fixture(tmp_path)
    before = path.read_bytes()
    adjacency, audit, preserved = load_state_candidate_graph(root, cache, "44", geoids, source, report)
    assert adjacency == ((1,), (0,))
    assert audit["exactPartRecheckRequired"]
    assert not audit["syntheticOwnershipEdgesUsed"]
    assert audit["sourceInteriorOverlapPairCount"] == 0
    assert list(preserved.values()) == [digest(before)]
    assert path.read_bytes() == before


def test_part_cache_provenance_reconstructs_original_whole_block_identity(tmp_path):
    root, cache, geoids, source, _, report = fixture(tmp_path)
    identity = report["graph_cache"]["identity"]
    part_report = {"physical_part_graph_cache": {"identity": {
        "source_archive_sha256": source, "ordered_geoids_sha256": identity["ordered_geoids_sha256"],
        "block_count": 2, "shapely_version": identity["shapely_version"], "geos_version": identity["geos_version"],
    }}}
    adjacency, audit, _ = load_state_candidate_graph(root, cache, "44", geoids, source, part_report)
    assert adjacency == ((1,), (0,))
    assert audit["identity"] == identity
    assert "reconstructed" in audit["provenance"]


def test_kansas_uses_separate_immutable_cache_namespace(tmp_path):
    root, cache, geoids, source, _, report = fixture(tmp_path, "20")
    adjacency, audit, _ = load_state_candidate_graph(root, cache, "20", geoids, source, report)
    assert adjacency == ((1,), (0,))
    assert audit["path"].startswith(".cache/kansas-block-benchmark/graph-cache/")


def test_alaska_explicitly_falls_back_without_opening_a_legacy_cache(tmp_path):
    adjacency, audit, preserved = load_state_candidate_graph(tmp_path, tmp_path, "02", [], "unused", {})
    assert adjacency is None
    assert audit["method"] == "source-bbox-candidates"
    assert preserved == {}


@pytest.mark.parametrize("field,value", [
    ("ordered_geoids_sha256", "b" * 64), ("source_archive_sha256", "b" * 64),
    ("node_count", 3), ("adjacency_builder_sha256", "b" * 64),
    ("topology_rule", "touching"), ("schema", 2),
])
def test_legacy_identity_mismatch_rejected(tmp_path, field, value):
    root, cache, geoids, source, _, report = fixture(tmp_path)
    report["graph_cache"]["identity"][field] = value
    with pytest.raises(ValueError, match="Legacy candidate identity"):
        load_state_candidate_graph(root, cache, "44", geoids, source, report)


def test_geoid_order_mismatch_rejected(tmp_path):
    root, cache, geoids, source, _, report = fixture(tmp_path)
    with pytest.raises(ValueError, match="GEOID order"):
        load_state_candidate_graph(root, cache, "44", geoids[::-1], source, report)


def test_candidate_key_mismatch_rejected(tmp_path):
    root, cache, geoids, source, _, report = fixture(tmp_path)
    report["graph_cache"]["key"] = "b" * 64
    with pytest.raises(ValueError, match="cache key"):
        load_state_candidate_graph(root, cache, "44", geoids, source, report)


def test_interior_overlaps_disallow_claim_of_complete_part_candidates(tmp_path):
    root, cache, geoids, source, _, report = fixture(tmp_path, overlap=1)
    with pytest.raises(ValueError, match="zero source interior overlaps"):
        load_state_candidate_graph(root, cache, "44", geoids, source, report)


def test_corrupt_payload_is_rejected_without_rebuilding(tmp_path):
    root, cache, geoids, source, path, report = fixture(tmp_path)
    with np.load(path, allow_pickle=False) as archive:
        offsets, manifest = archive["offsets"], archive["manifest"]
    np.savez(path, offsets=offsets, neighbors=np.array([0, 1], dtype="<i8"), manifest=manifest)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="payload hash"):
        load_state_candidate_graph(root, cache, "44", geoids, source, report)
    assert path.read_bytes() == before


def test_wrong_part_identity_is_rejected(tmp_path):
    root, cache, geoids, source, _, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="part-cache source or GEOID identity"):
        load_state_candidate_graph(root, cache, "44", geoids, source, {"physical_part_graph_cache": {"identity": {}}})


def test_no_unpinned_provenance_fallback(tmp_path):
    root, cache, geoids, source, _, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="no pinned physical graph provenance"):
        load_state_candidate_graph(root, cache, "44", geoids, source, {})


def test_source_archive_selector_preserves_kansas_original_location():
    from scripts.build_state_land_display import source_archive_relative
    assert source_archive_relative("20").as_posix() == ".cache/kansas-block-benchmark/source/tl_2020_20_tabblock20.zip"
    assert source_archive_relative("02").as_posix() == ".cache/state-block-benchmark/source/02/tl_2020_02_tabblock20.zip"
    assert source_archive_relative("44").as_posix() == ".cache/state-block-benchmark/source/44/tl_2020_44_tabblock20.zip"
    with pytest.raises(ValueError, match="two-digit"):
        source_archive_relative("../20")
