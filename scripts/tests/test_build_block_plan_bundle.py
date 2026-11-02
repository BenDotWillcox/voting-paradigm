import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.build_block_plan_bundle import BundleBuilder, digest, encoded, read_pinned, safe_path, validate_catalog


def write_json(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(data))
    return digest(path.read_bytes())


def put_payload(root, directory, name, value):
    raw = encoded(value)
    data = gzip.compress(raw, mtime=0)
    path = root / directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"raw_sha256": digest(raw), "gzip_sha256": digest(data), "raw_bytes": len(raw), "gzip_bytes": len(data)}


@pytest.fixture
def plan_fixture(tmp_path):
    directory = Path(".cache/accepted/44-2/maps")
    collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"district_id": i, "population": p, "block_count": 1}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 1], [0, 0]]]}}
        for i, p in enumerate([5, 6])
    ]}
    payloads = {f"districts-{level}.geojson.gz": put_payload(tmp_path, directory, f"districts-{level}.geojson.gz", collection) for level in ["national", "state", "full"]}
    payloads["blocks/county-001.geojson.gz"] = put_payload(tmp_path, directory, "blocks/county-001.geojson.gz", {"type": "FeatureCollection", "features": []})
    maps = {"source_bbox": [0, 0, 1, 1], "district_outlines": {level: {"gzip_path": f"districts-{level}.geojson.gz"} for level in ["national", "state", "full"]}, "county_blocks": [{"county_fips": "001", "block_count": 2, "population": 11, "bbox": [0, 0, 1, 1], "gzip_path": "blocks/county-001.geojson.gz"}]}
    report_path = ".cache/accepted/44-2/benchmark.json"
    report_hash = write_json(tmp_path, report_path, {"status": "complete", "input": {}})
    map_hash = write_json(tmp_path, directory / "map-manifest.json", maps)
    plan = {
        "plan_id": "44-2", "state_fips": "44", "state": "Rhode Island", "district_count": 2, "house_sizes": [435],
        "report_path": report_path, "report_sha256": report_hash, "map_directory": directory.as_posix(),
        "resident_population": 11, "block_count": 2, "district_populations": [5, 6], "max_deviation_people": .5, "max_deviation_percent": 100 / 11, "population_range_people": 1,
        "connectivity_policy": "strict_shared_edge", "optimizer": {"inner_pass_count": 1, "unsuccessful_inner_pass_count": 0, "inner_iteration_caps": 0, "centers_converged": True},
        "runtime_scope": "full_plan_pipeline", "pipeline_seconds": 12, "peak_process_working_set_bytes": 1024, "caveats": ["Explicit historical caveat."],
        "validation": {"payloads": payloads, "map_manifest_sha256": map_hash, "all_districts_physically_connected": True, "policy_components": [1, 1], "recorded_link_count": 0},
    }
    return tmp_path, plan, maps


@pytest.mark.parametrize("value", ["../outside", "a/../../outside", "C:/secret", "/secret", "a\\..\\secret", "a//b", "a/./b"])
def test_rejects_path_escape(tmp_path, value):
    with pytest.raises(ValueError):
        safe_path(tmp_path, value)


def test_pinned_file_rejects_mutation(tmp_path):
    (tmp_path / "data.json").write_bytes(b"original")
    pin = digest(b"original")
    assert read_pinned(tmp_path, "data.json", pin) == b"original"
    (tmp_path / "data.json").write_bytes(b"modified")
    with pytest.raises(ValueError, match="Hash mismatch"):
        read_pinned(tmp_path, "data.json", pin)


@pytest.mark.parametrize("change", [{"status": "running"}, {"errors": ["failure"]}, {"house_sizes": [435, 11037]}, {"plans": []}])
def test_catalog_rejects_nonterminal_or_wrong_scope(change):
    catalog = {"status": "complete", "errors": [], "house_sizes": [435, 574, 692, 1000], "plans": [], "expected_unique_plans": 181}
    catalog.update(change)
    with pytest.raises(ValueError):
        validate_catalog(catalog)


def test_catalog_rejects_duplicate_selection():
    p = {"state_fips": "44", "district_count": 2}
    with pytest.raises(ValueError, match="Duplicate"):
        validate_catalog({"status": "complete", "errors": [], "house_sizes": [435, 574, 692, 1000], "expected_unique_plans": 181, "plans": [p] * 181})


def test_plan_builds_small_index_without_copying_county_payloads(plan_fixture):
    root, plan, _ = plan_fixture
    builder = BundleBuilder(root)
    output = builder.plan(plan)
    assert output["id"] == "44-2"
    assert output["caveats"] == plan["caveats"]
    assert output["coordinateFrame"] == "source"
    assert output["assets"]["state"]["url"].startswith("/api/district-plans/")
    generated = list((root / "data/districting-block-plans/assets").glob("*.gz"))
    assert len(generated) == 1  # only the small rewritten detail index
    detail = json.loads(gzip.decompress(generated[0].read_bytes()))
    county_url = detail["counties"][0]["asset"]["url"]
    key = county_url.removeprefix("/api/district-plans/")
    assert builder.assets[key]["path"].startswith(".cache/")
    assert ".cache" not in json.dumps(output)
    assert str(root) not in json.dumps(detail)
    assert "path" not in detail["counties"][0]
    props = builder.national_features["44-2"][0]["properties"]
    assert (props["state_fips"], props["plan_id"], props["district_id"]) == ("44", "44-2", 0)


def test_changed_report_fails_before_any_new_asset(plan_fixture):
    root, plan, _ = plan_fixture
    (root / plan["report_path"]).write_text('{"status":"complete","changed":true}')
    with pytest.raises(ValueError, match="Hash mismatch"):
        BundleBuilder(root).plan(plan)
    assert not (root / "data/districting-block-plans/assets").exists()


def test_changed_map_manifest_fails(plan_fixture):
    root, plan, _ = plan_fixture
    (root / plan["map_directory"] / "map-manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="Hash mismatch"):
        BundleBuilder(root).plan(plan)


def test_unlisted_payload_cannot_be_registered(plan_fixture):
    root, plan, _ = plan_fixture
    with pytest.raises(ValueError, match="Unvalidated map resource"):
        BundleBuilder(root).cached(plan, "secret.geojson.gz")


def test_outline_hash_checked_even_when_size_unchanged(plan_fixture):
    root, plan, _ = plan_fixture
    path = root / plan["map_directory"] / "districts-national.geojson.gz"
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(ValueError, match="Hash mismatch"):
        BundleBuilder(root).decoded_cached(plan, path.name)


def test_generated_urls_deterministic_and_content_addressed(tmp_path):
    builder = BundleBuilder(tmp_path)
    first = builder.generated({"hello": "world"}, "detail.json")
    second = builder.generated({"hello": "world"}, "detail.json")
    third = builder.generated({"hello": "changed"}, "detail.json")
    assert first == second
    assert first["url"] != third["url"]
    assert len(list((tmp_path / "data/districting-block-plans/assets").glob("*.gz"))) == 2


def test_county_population_mismatch_rejected(plan_fixture):
    root, plan, maps = plan_fixture
    maps["county_blocks"][0]["population"] = 12
    plan["validation"]["map_manifest_sha256"] = write_json(root, Path(plan["map_directory"]) / "map-manifest.json", maps)
    with pytest.raises(ValueError, match="County index"):
        BundleBuilder(root).plan(plan)


def test_outline_population_mismatch_rejected(plan_fixture):
    root, plan, _ = plan_fixture
    plan["district_populations"] = [6, 5]
    with pytest.raises(ValueError, match="district identity/population"):
        BundleBuilder(root).plan(plan)


def test_alaska_uses_working_detail_and_wrapped_national(plan_fixture):
    root, plan, maps = plan_fixture
    old_directory = Path(plan["map_directory"])
    directory = Path(".cache/accepted/02-2/maps")
    plan.update(plan_id="02-2", state_fips="02", state="Alaska", map_directory=directory.as_posix())
    plan["report_sha256"] = write_json(root, plan["report_path"], {"status": "complete", "input": {"working_bbox": [-188, 51, -130, 72]}})
    working = json.loads(gzip.decompress((root / old_directory / "districts-national.geojson.gz").read_bytes()))
    working["features"][0]["geometry"]["coordinates"][0][0][0] = -187
    wrapped = deepcopy(working)
    wrapped["features"][0]["geometry"]["coordinates"][0][0][0] = 173
    files = ["districts-national.working.geojson.gz", "districts-national.wrapped.geojson.gz", "districts-state.working.geojson.gz", "districts-full.working.geojson.gz", "connections.working.geojson.gz", "counties/001.working.geojson.gz"]
    plan["validation"]["payloads"] = {name: put_payload(root, directory, name, wrapped if ".wrapped." in name else working) for name in files}
    maps = {"state_file": files[2], "full_file": files[3], "connections_file": files[4], "counties": [{"county_fips": "001", "block_count": 2, "population": 11, "working_file": files[5]}]}
    plan["validation"]["map_manifest_sha256"] = write_json(root, directory / "manifest.json", maps)
    builder = BundleBuilder(root)
    result = builder.plan(plan)
    assert result["coordinateFrame"] == "alaska-continuous"
    assert "wrapped" in result["assets"]["national"]["url"]
    assert "working" in result["assets"]["state"]["url"]
    feature = builder.national_features["02-2"][0]
    assert feature["geometry"]["coordinates"][0][0][0] == -187
    assert feature["properties"]["coordinate_frame"] == "alaska-continuous"


def test_builder_reads_preserved_external_cache_but_writes_only_local_bundle(plan_fixture, tmp_path):
    import shutil
    root, plan, maps = plan_fixture
    external = tmp_path / "external-cache"
    shutil.move(str(root / ".cache"), external)
    before = {p.relative_to(external): digest(p.read_bytes()) for p in external.rglob("*") if p.is_file()}
    builder = BundleBuilder(root, cache_root=external)
    result = builder.plan(plan)
    assert result["residentPopulation"] == 11
    assert (root / "data/districting-block-plans/assets").is_dir()
    assert not (root / ".cache").exists()
    assert before == {p.relative_to(external): digest(p.read_bytes()) for p in external.rglob("*") if p.is_file()}
