import gzip
import json
from pathlib import Path
from copy import deepcopy

import pytest
from shapely.geometry import LineString, box, mapping, shape

from scripts.build_block_plan_bundle import digest, encoded
from scripts.build_block_state_outlines import dissolve_state, read_full_outlines, read_source_pinned


def collection(*polygons):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"district_id": i, "population": i + 5}, "geometry": mapping(p)}
        for i, p in enumerate(polygons)
    ]}


def test_dissolve_removes_shared_district_edge_before_simplification():
    output = dissolve_state(collection(box(0, 0, 1, 1), box(1, 0, 2, 1)), "20", "Kansas")
    geometry = shape(output["geometry"])
    assert geometry.equals(box(0, 0, 2, 1))
    assert geometry.boundary.intersection(LineString([(1, .1), (1, .9)])).is_empty


def test_preserves_separate_island_and_hole():
    mainland = box(0, 0, 10, 10).difference(box(2, 2, 3, 3))
    output = dissolve_state(collection(mainland, box(20, 0, 21, 1)), "44", "Rhode Island")
    geometry = shape(output["geometry"])
    assert geometry.geom_type == "MultiPolygon"
    assert len(geometry.geoms) == 2
    assert sum(len(p.interiors) for p in geometry.geoms) == 1


def test_alaska_preserves_continuous_longitudes_beyond_minus_180():
    output = dissolve_state(collection(box(-190, 51, -189, 52), box(-160, 60, -159, 61)), "02", "Alaska")
    assert output["properties"]["coordinate_frame"] == "alaska-continuous"
    assert shape(output["geometry"]).bounds == (-190.0, 51.0, -159.0, 61.0)


@pytest.mark.parametrize("tolerance", [-1, float("nan"), float("inf")])
def test_rejects_invalid_simplification_tolerance(tolerance):
    with pytest.raises(ValueError, match="tolerance"):
        dissolve_state(collection(box(0, 0, 1, 1)), "20", "Kansas", tolerance)


@pytest.fixture
def full_source(tmp_path):
    directory = tmp_path / ".cache/test/maps"
    directory.mkdir(parents=True)
    data = collection(box(0, 0, 1, 1), box(1, 0, 2, 1))
    raw = encoded(data)
    compressed = gzip.compress(raw, mtime=0)
    filename = "districts-full.geojson.gz"
    (directory / filename).write_bytes(compressed)
    maps = {"district_outlines": {"full": {"gzip_path": filename}}}
    map_bytes = encoded(maps)
    (directory / "map-manifest.json").write_bytes(map_bytes)
    plan = {"plan_id": "20-2", "state_fips": "20", "map_directory": ".cache/test/maps",
            "district_count": 2, "district_populations": [5, 6], "validation": {
                "map_manifest_sha256": digest(map_bytes), "payloads": {filename: {
                    "gzip_sha256": digest(compressed), "raw_sha256": digest(raw),
                    "gzip_bytes": len(compressed), "raw_bytes": len(raw)}}}}
    return tmp_path, plan, directory, filename


def test_full_input_is_pinned_and_preservation_is_read_only(full_source):
    root, plan, directory, filename = full_source
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    data, provenance = read_full_outlines(root, plan)
    assert len(data["features"]) == 2
    assert provenance["raw_sha256"] == plan["validation"]["payloads"][filename]["raw_sha256"]
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}


def test_rejects_mutated_source_full_payload(full_source):
    root, plan, directory, filename = full_source
    (directory / filename).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Hash mismatch"):
        read_full_outlines(root, plan)


def test_rejects_wrong_saved_district_population(full_source):
    root, plan, _, _ = full_source
    plan = deepcopy(plan)
    plan["district_populations"] = [6, 5]
    with pytest.raises(ValueError, match="populations differ"):
        read_full_outlines(root, plan)


def test_external_cache_mount_does_not_need_cache_inside_new_worktree(full_source, tmp_path):
    root, plan, directory, filename = full_source
    new_worktree = tmp_path / "new-worktree"
    new_worktree.mkdir()
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    data, _ = read_full_outlines(new_worktree, plan, cache_root=root / ".cache")
    assert len(data["features"]) == 2
    assert not (new_worktree / ".cache").exists()
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}


def test_external_cache_source_cannot_escape_mount(tmp_path):
    mount = tmp_path / "mount"
    mount.mkdir()
    secret = tmp_path / "outside.json"
    secret.write_bytes(b"outside")
    with pytest.raises(ValueError, match="Unsafe relative path"):
        read_source_pinned(tmp_path, Path(".cache/../outside.json"), digest(b"outside"), mount)
