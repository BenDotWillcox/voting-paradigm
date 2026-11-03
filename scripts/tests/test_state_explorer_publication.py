"""Publish only complete, pinned display derivatives of the accepted catalog.

The fixture has the real 181 state/count identities and 200 anchor/state pairs,
but just 1,000 synthetic blocks. It never reads the national benchmark cache.
"""
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import shutil
import threading

import pytest

from apportionment import apportion_us_2020
from scripts.build_block_plan_bundle import BundleBuilder, OUTPUT, digest, encoded
from scripts import publish_state_explorer as publisher


ANCHORS = [435, 574, 692, 1000]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_bytes(path, encoded(value))


def replace_bytes(path, raw):
    """Copy on write keeps shared immutable fixture payloads cheap and safe."""
    temp = path.with_suffix(path.suffix + ".fixture-tmp")
    temp.write_bytes(raw)
    temp.replace(path)


def read_json(path):
    return json.loads(path.read_bytes())


def make_fixture(root):
    cache = root / ".cache"
    cache.mkdir(parents=True)
    preserved_path = ".cache/original-saved-evidence.json"
    preserved_raw = encoded({"original": "immutable saved plans and proof"})
    (cache / "original-saved-evidence.json").write_bytes(preserved_raw)
    preserved = [{"path": preserved_path, "sha256": digest(preserved_raw)}]
    runtime_path = "scripts/fixture-state-builder.py"
    runtime_raw = b"# frozen synthetic fixture builder\n"
    (root / "scripts").mkdir()
    (root / runtime_path).write_bytes(runtime_raw)
    runtime = {runtime_path: digest(runtime_raw)}
    builder = BundleBuilder(root)
    cities = {"status": "complete", "states": {}, "assets": {}, "audit": {}}
    geometry = {"status": "complete", "plans": {}, "assets": {}, "audit": {
        "plans": {}, "runtimeHashes": {Path(runtime_path).name: digest(runtime_raw)},
        "limitation": "Synthetic census coverage; no clipping or new links."}}
    manifest = {"schemaVersion": 1, "houseSizes": ANCHORS, "plans": {}, "anchors": [],
                "michiganExplorer": {"plans": {}}, "landDisplays": {"26-13": {"preserve": True}}}
    old_assets = {}
    index = {"assets": old_assets, "proofs": {"fixture": {"reportPath": preserved_path, "reportSha256": digest(preserved_raw)}},
             "catalogPath": "prompts/catalog-fixture.json", "originalExtra": {"keep": [1, 2, 3]}}
    counts = {cap: apportion_us_2020(cap) for cap in ANCHORS}
    states = sorted(counts[435])
    blocks = {}

    def asset(fragment, value, name):
        reference = builder.generated(value, name)
        key = reference["url"].removeprefix(publisher.PREFIX)
        fragment["assets"][key] = deepcopy(builder.assets[key])
        return reference

    for state in states:
        frame = "alaska-continuous" if state == "02" else "source"
        block_count = counts[1000][state]
        population = block_count * 10
        west = -185 if state == "02" else -85
        features = [{"type": "Feature", "properties": {"geoid": f"{state}001{i:010d}", "population": 10},
                     "geometry": {"type": "Polygon", "coordinates": [[[west, 42], [west + .1, 42], [west + .1, 42.1], [west, 42]]]}}
                    for i in range(block_count)]
        city = {"type": "FeatureCollection", "metadata": {"stateFips": state, "coordinateFrame": frame},
                "features": [{"type": "Feature", "properties": {"geoid": f"{state}00001", "population": 10000},
                              "geometry": {"type": "Point", "coordinates": [west, 42]}}]}
        city_asset = asset(cities, city, f"{state}-places.geojson")
        cities["states"][state] = {"cities": city_asset, "cityMetadata": {
            "label": "Cities & places", "description": "Synthetic publication fixture", "featureCount": 1, "minimumPopulation": 10000, "sources": []}}
        if state == "26":
            manifest["michiganExplorer"]["cities"] = city_asset
            key = city_asset["url"].removeprefix(publisher.PREFIX)
            old_assets[key] = deepcopy(cities["assets"][key])
        fragment = {"status": "complete", "stateFips": state, "plans": {}, "assets": {}, "runtimeHashes": runtime,
                    "audit": {"preservedFiles": preserved}}
        blocks[state] = fragment
        chunk_id = f"{state}-c001"
        shared = {"type": "FeatureCollection", "features": features,
                  "metadata": {"schemaVersion": 2, "stateFips": state, "coordinateFrame": frame, "chunkId": chunk_id,
                               "sharedAcrossPlans": True, "wholeSavedBlocks": True, "assignmentField": "district_id"}}
        shared_ref = asset(fragment, shared, f"{state}-shared.geojson") if state != "26" else None
        for k in sorted({values[state] for values in counts.values()}):
            plan_id = f"{state}-{k}"
            ids = [i % k for i in range(block_count)]
            block_counts = [ids.count(d) for d in range(k)]
            populations = [n * 10 for n in block_counts]
            plan = {"id": plan_id, "stateFips": state, "coordinateFrame": frame, "districtCount": k,
                    "houseSizes": [cap for cap in ANCHORS if counts[cap][state] == k],
                    "residentPopulation": population, "blockCount": block_count, "districtPopulations": populations,
                    "recordedLinkCount": 0, "assets": {}, "originalMarker": {"unchanged": True}}
            manifest["plans"][plan_id] = plan
            summary = {"planId": plan_id, "stateFips": state, "coordinateFrame": frame,
                       "residentPopulation": population, "blockCount": block_count,
                       "counties": [{"fips": "001", "name": "Fixture", "bbox": [west, 42, west + .1, 42.1],
                                     "population": population, "blockCount": block_count,
                                     "districtShares": [{"districtId": d, "population": populations[d], "blockCount": block_counts[d],
                                                         "percent": populations[d] / population * 100} for d in range(k)]}],
                       "districts": [{"districtId": d, "population": populations[d], "blockCount": block_counts[d], "countyFips": ["001"]}
                                     for d in range(k)]}
            chunk = {"chunkId": chunk_id, "bbox": [west, 42, west + .1, 42.1], "population": population, "blockCount": block_count}
            if state == "26":
                whole = deepcopy(shared)
                whole["metadata"] = {"schemaVersion": 1, "planId": plan_id, "stateFips": state}
                for feature, district in zip(whole["features"], ids):
                    feature["properties"]["district_id"] = district
                chunk["asset"] = asset(fragment, whole, f"{plan_id}-whole.geojson")
            else:
                assignments = {"schemaVersion": 1, "planId": plan_id, "stateFips": state, "coordinateFrame": frame,
                               "chunkId": chunk_id, "geometrySha256": shared_ref["sha256"], "districtIds": ids}
                chunk.update({"asset": shared_ref, "assignments": asset(fragment, assignments, f"{plan_id}-assignments.json")})
            spatial = {"schemaVersion": 1 if state == "26" else 2, "planId": plan_id, "stateFips": state, "coordinateFrame": frame,
                       "totalPopulation": population, "totalBlockCount": block_count,
                       "counties": [{"fips": "001", "population": population, "blockCount": block_count}], "chunks": [chunk]}
            fragment["plans"][plan_id] = {"summary": asset(fragment, summary, f"{plan_id}-summary.json"),
                                         "spatialIndex": asset(fragment, spatial, f"{plan_id}-index.json")}
            overview = {"type": "FeatureCollection", "metadata": {"planId": plan_id, "coordinateFrame": frame},
                        "features": [{"type": "Feature", "properties": {"district_id": d, "population": populations[d]},
                                      "geometry": features[d]["geometry"]} for d in range(k)]}
            empty = {"type": "FeatureCollection", "metadata": overview["metadata"], "features": []}
            record = {"overview": asset(geometry, overview, f"{plan_id}-overview.geojson"),
                      "detail": asset(geometry, overview, f"{plan_id}-detail.geojson")}
            for kind in ("coast", "dividers", "detailDividers"):
                record[kind] = asset(geometry, empty, f"{plan_id}-{kind}.geojson")
            geometry["plans"][plan_id] = record
            geometry["audit"]["plans"][plan_id] = {"preservedFiles": preserved, "residentPopulation": population,
                                                   "blockCount": block_count, "savedDistrictPropertiesUnchanged": True}
            if state == "26":
                manifest["michiganExplorer"]["plans"][plan_id] = {**record, **fragment["plans"][plan_id]}
        if state == "26":
            old_assets.update(deepcopy(fragment["assets"]))
            for record in manifest["michiganExplorer"]["plans"].values():
                for reference in record.values():
                    key = reference["url"].removeprefix(publisher.PREFIX)
                    old_assets[key] = deepcopy(builder.assets[key])
    for cap in ANCHORS:
        manifest["anchors"].append({"houseSize": cap, "planIds": [f"{state}-{counts[cap][state]}" for state in states], "national": {"keep": cap}})
    assert len(manifest["plans"]) == 181
    catalog = {"status": "complete", "expected_unique_plans": 181, "house_sizes": ANCHORS,
               "plans": [{"plan_id": p["id"], "state_fips": p["stateFips"], "district_count": p["districtCount"],
                          "house_sizes": p["houseSizes"], "district_populations": p["districtPopulations"],
                          "resident_population": p["residentPopulation"], "status": "validated", "report_sha256": digest(preserved_raw),
                          "validation": {"status": "validated_saved_plan", "report_sha256": digest(preserved_raw),
                                         "policy_components": [1] * p["districtCount"]}}
                         for p in manifest["plans"].values()]}
    write_json(root / index["catalogPath"], catalog)
    index["catalogSha256"] = manifest["catalogSha256"] = digest(encoded(catalog))
    pins_path = OUTPUT / "state-explorer-city-source-pins.json"
    write_json(root / pins_path, {"schemaVersion": 1, "sources": []})
    cities["audit"].update({"preservedPlansSha256": digest(encoded(manifest["plans"])),
                           "preservedProofsSha256": digest(encoded(index["proofs"])),
                           "sourcePins": {"path": pins_path.as_posix(), "sha256": digest((root / pins_path).read_bytes())},
                           "savedAssignmentsModified": 0, "solverRuns": 0})
    for fragment in (cities, geometry, *blocks.values()):
        fragment["catalogSha256"] = index["catalogSha256"]
    for state, fragment in blocks.items():
        plans = sorted((p for p in manifest["plans"].values() if p["stateFips"] == state), key=lambda p: p["districtCount"])
        fragment["audit"]["preservedPlansSha256"] = digest(encoded(plans))
        if state != "26":
            write_json(root / publisher.BLOCKS / f"{state}.json", fragment)
    write_json(root / publisher.CITIES, cities)
    write_json(root / publisher.GEOMETRY, geometry)
    write_json(root / OUTPUT / "manifest.json", manifest)
    index["manifestSha256"] = digest(encoded(manifest))
    write_json(root / OUTPUT / "server-index.json", index)
    return root


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    return make_fixture(tmp_path_factory.mktemp("state-explorer-publication-template"))


@pytest.fixture
def bundle(tmp_path, template):
    root = tmp_path / "bundle"
    shutil.copytree(template, root, copy_function=os.link)
    return root


def snapshot_authority(root):
    return {name: (root / OUTPUT / name).read_bytes() for name in ("manifest.json", "server-index.json")}


def assert_authority_unchanged(root, before):
    assert snapshot_authority(root) == before


def test_dry_run_checks_every_plan_but_writes_no_publication_or_authority(bundle):
    before = snapshot_authority(bundle)
    report = publisher.publish(bundle, bundle / ".cache")
    assert report["status"] == "complete"
    assert (report["states"], report["plans"], report["anchorStatePairs"]) == (50, 181, 200)
    assert report["savedAssignmentsModified"] == report["solverRuns"] == 0
    assert report["checks"]["02-2"]["coordinateFrame"] == "alaska-continuous"
    assert report["checks"]["26-13"]["spatialSchema"] == 1
    assert report["checks"]["12-28"]["spatialSchema"] == 2
    assert not (bundle / publisher.REPORT).exists()
    assert not (bundle / OUTPUT / "publication-history").exists()
    assert_authority_unchanged(bundle, before)


def test_publication_adds_only_explorers_and_allowlisted_assets_and_saves_exact_backups(bundle):
    before = snapshot_authority(bundle)
    manifest, index = (json.loads(before[name]) for name in ("manifest.json", "server-index.json"))
    report = publisher.publish(bundle, bundle / ".cache", write=True)
    updated, updated_index = (read_json(bundle / OUTPUT / name) for name in ("manifest.json", "server-index.json"))
    assert {k: v for k, v in updated.items() if k != "stateExplorers"} == manifest
    assert len(updated["stateExplorers"]) == 50
    assert sum(len(state["plans"]) for state in updated["stateExplorers"].values()) == 181
    assert updated_index["proofs"] == index["proofs"]
    for key, value in index.items():
        if key not in {"assets", "manifestSha256"}:
            assert updated_index[key] == value
    for key, entry in index["assets"].items():
        assert updated_index["assets"][key] == entry
    assert updated_index["manifestSha256"] == digest(encoded(updated))
    assert updated_index["stateExplorerProvenance"] == {"reportPath": publisher.REPORT.as_posix(), "reportSha256": digest(encoded(report))}
    assert read_json(bundle / publisher.REPORT) == report
    for name, raw in before.items():
        assert (bundle / OUTPUT / "publication-history" / f"{Path(name).stem}-{digest(raw)}.json").read_bytes() == raw
    assert report["preservedPlanRecordsSha256"] == digest(encoded(manifest["plans"]))
    assert report["preservedProofsSha256"] == digest(encoded(index["proofs"]))


@pytest.mark.parametrize("problem", ["missing-city", "missing-geometry", "incomplete-block", "wrong-catalog", "missing-block-plan"])
def test_publication_rejects_incomplete_or_mismatched_fragments_without_authority_writes(bundle, problem):
    before = snapshot_authority(bundle)
    relative = publisher.CITIES if problem == "missing-city" else publisher.GEOMETRY if problem == "missing-geometry" else publisher.BLOCKS / "12.json"
    fragment = read_json(bundle / relative)
    if problem == "missing-city":
        del fragment["states"]["12"]
    elif problem == "missing-geometry":
        del fragment["plans"]["12-28"]
    elif problem == "incomplete-block":
        fragment["status"] = "running"
    elif problem == "wrong-catalog":
        fragment["catalogSha256"] = "0" * 64
    else:
        del fragment["plans"]["12-28"]
    write_json(bundle / relative, fragment)
    with pytest.raises(ValueError):
        publisher.publish(bundle, bundle / ".cache", write=True)
    assert_authority_unchanged(bundle, before)


@pytest.mark.parametrize("problem", ["entry-conflict", "gzip-corrupt", "decoded-corrupt", "runtime-changed", "source-changed"])
def test_publication_rejects_conflicts_or_corruption_without_replacing_originals(bundle, problem):
    before = snapshot_authority(bundle)
    relative = publisher.BLOCKS / "12.json"
    fragment = read_json(bundle / relative)
    key, entry = next(iter(fragment["assets"].items()))
    if problem == "entry-conflict":
        index = read_json(bundle / OUTPUT / "server-index.json")
        index["assets"][key] = {**entry, "proof": "historical-proof-must-not-be-overwritten"}
        write_json(bundle / OUTPUT / "server-index.json", index)
        before = snapshot_authority(bundle)
    elif problem == "gzip-corrupt":
        replace_bytes(bundle / entry["path"], b"corrupt compressed map")
    elif problem == "decoded-corrupt":
        compressed = gzip.compress(b'{"tampered":true}', mtime=0)
        replace_bytes(bundle / entry["path"], compressed)
        entry["gzipSha256"], entry["gzipBytes"] = digest(compressed), len(compressed)
        write_json(bundle / relative, fragment)
    elif problem == "runtime-changed":
        replace_bytes(bundle / next(iter(fragment["runtimeHashes"])), b"changed source")
    else:
        replace_bytes(bundle / ".cache/original-saved-evidence.json", b"changed saved original")
    with pytest.raises(ValueError):
        publisher.publish(bundle, bundle / ".cache", write=True)
    assert_authority_unchanged(bundle, before)


@pytest.mark.parametrize("target", ["authority", "fragment"])
def test_publication_rejects_stale_authority_and_fragment_changes_before_commit(bundle, monkeypatch, target):
    original = publisher.validate_assets
    before = snapshot_authority(bundle)
    path = bundle / OUTPUT / "server-index.json" if target == "authority" else bundle / publisher.CITIES
    changed = path.read_bytes() + b"\n"

    def concurrent_change(root, cache, assets):
        original(root, cache, assets)
        replace_bytes(path, changed)

    monkeypatch.setattr(publisher, "validate_assets", concurrent_change)
    with pytest.raises(ValueError, match="changed during publication"):
        publisher.publish(bundle, bundle / ".cache", write=True)
    assert (bundle / OUTPUT / "manifest.json").read_bytes() == before["manifest.json"]
    assert (bundle / OUTPUT / "server-index.json").read_bytes() == (changed if target == "authority" else before["server-index.json"])
    assert not (bundle / publisher.REPORT).exists()


def test_publication_rejects_valid_readdressed_assignments_that_change_district_counts(bundle):
    before = snapshot_authority(bundle)
    relative = publisher.BLOCKS / "12.json"
    fragment = read_json(bundle / relative)
    record = fragment["plans"]["12-28"]
    spatial = publisher.read_reference(bundle, bundle / ".cache", record["spatialIndex"], fragment["assets"])
    chunk = spatial["chunks"][0]
    sidecar = publisher.read_reference(bundle, bundle / ".cache", chunk["assignments"], fragment["assets"])
    sidecar["districtIds"][0] = 1
    builder = BundleBuilder(bundle)
    chunk["assignments"] = builder.generated(sidecar, "changed-sidecar.json")
    record["spatialIndex"] = builder.generated(spatial, "changed-spatial-index.json")
    fragment["assets"].update(builder.assets)
    write_json(bundle / relative, fragment)
    with pytest.raises(ValueError, match="district block counts"):
        publisher.publish(bundle, bundle / ".cache", write=True)
    assert_authority_unchanged(bundle, before)


def test_reference_validation_rejects_escape_missing_and_metadata_mismatch(template):
    bundle = template
    fragment = read_json(bundle / publisher.CITIES)
    reference = fragment["states"]["12"]["cities"]
    assets = fragment["assets"]
    for changed in ({**reference, "url": "/api/district-plans/not-allowed"}, {**reference, "url": "https://example.test/map.json"},
                    {**reference, "bytes": reference["bytes"] + 1}, {**reference, "sha256": "0" * 64}):
        with pytest.raises(ValueError):
            publisher.reference_entry(changed, assets)
    key = reference["url"].removeprefix(publisher.PREFIX)
    malicious = {key: {**assets[key], "path": "../outside.gz"}}
    with pytest.raises(ValueError, match="Unsafe"):
        publisher.read_reference(bundle, bundle / ".cache", reference, malicious)


@pytest.mark.parametrize("problem", ["missing-anchor", "wrong-state-plan", "wrong-seat-total", "plan-anchor-mismatch"])
def test_anchor_coverage_rejects_incomplete_ambiguous_or_wrong_house_totals(template, problem):
    bundle = template
    manifest = read_json(bundle / OUTPUT / "manifest.json")
    if problem == "missing-anchor":
        manifest["anchors"].pop()
    elif problem == "wrong-state-plan":
        manifest["anchors"][0]["planIds"][0] = manifest["anchors"][0]["planIds"][1]
    elif problem == "wrong-seat-total":
        manifest["plans"]["12-28"]["districtCount"] += 1
    else:
        manifest["plans"]["12-28"]["houseSizes"] = []
    with pytest.raises(ValueError):
        publisher.validate_anchors(manifest)


@pytest.mark.parametrize("problem", ["plan", "state", "frame", "geometry", "chunk", "length", "range", "float", "boolean"])
def test_assignment_binding_rejects_valid_json_with_wrong_saved_plan_identity(template, problem):
    bundle = template
    fragment = read_json(bundle / publisher.BLOCKS / "12.json")
    manifest = read_json(bundle / OUTPUT / "manifest.json")
    plan = manifest["plans"]["12-28"]
    spatial = publisher.read_reference(bundle, bundle / ".cache", fragment["plans"][plan["id"]]["spatialIndex"], fragment["assets"])
    chunk = spatial["chunks"][0]
    assignments = publisher.read_reference(bundle, bundle / ".cache", chunk["assignments"], fragment["assets"])
    if problem == "length":
        assignments["districtIds"].pop()
    elif problem in ("range", "float", "boolean"):
        assignments["districtIds"][0] = {"range": 28, "float": 0.5, "boolean": True}[problem]
    else:
        field, value = {"plan": ("planId", "12-37"), "state": ("stateFips", "26"), "frame": ("coordinateFrame", "alaska-continuous"),
                        "geometry": ("geometrySha256", "0" * 64), "chunk": ("chunkId", "other")}[problem]
        assignments[field] = value
    with pytest.raises(ValueError):
        publisher.validate_assignments(assignments, plan, chunk)


def test_parallel_asset_validation_limits_submission_and_checks_each_entry_once(tmp_path, monkeypatch):
    batches, visits, workers = [], [], []

    class ObservedExecutor:
        def __init__(self, *, max_workers):
            workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def map(self, function, iterable):
            batch = tuple(iterable)
            batches.append(len(batch))
            return map(function, batch)

    def validate(root, cache, key, entry):
        assert root == tmp_path and cache == tmp_path / "cache"
        visits.append((key, entry))

    monkeypatch.setattr(publisher, "ThreadPoolExecutor", ObservedExecutor)
    monkeypatch.setattr(publisher, "_validate_asset", validate)
    assets = {str(i): {"fixture": i} for i in range(513)}
    publisher.validate_assets(tmp_path, tmp_path / "cache", assets)
    assert workers == [8]
    assert batches == [256, 256, 1]
    assert visits == list(assets.items())


def test_parallel_asset_validation_actually_uses_eight_bounded_readers(tmp_path, monkeypatch):
    barrier, lock = threading.Barrier(8), threading.Lock()
    active, peak, visited = 0, 0, []

    def validate(root, cache, key, entry):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)
            visited.append(key)
        barrier.wait(timeout=5)
        with lock:
            active -= 1

    monkeypatch.setattr(publisher, "_validate_asset", validate)
    publisher.validate_assets(tmp_path, tmp_path, {str(i): {} for i in range(8)})
    assert active == 0 and peak == 8
    assert sorted(visited) == [str(i) for i in range(8)]


def test_parallel_asset_validation_propagates_worker_failure_before_next_batch(tmp_path, monkeypatch):
    lock, visited = threading.Lock(), []

    def validate(root, cache, key, entry):
        with lock:
            visited.append(int(key))
        if key == "0":
            raise ValueError("Fixture decoded payload mismatch")

    monkeypatch.setattr(publisher, "_validate_asset", validate)
    with pytest.raises(ValueError, match="Fixture decoded payload mismatch"):
        publisher.validate_assets(tmp_path, tmp_path, {str(i): {} for i in range(513)})
    assert 0 in visited
    assert max(visited) < 256


def sidecar_fixture(count):
    plan = {"id": "02-2", "stateFips": "02", "coordinateFrame": "alaska-continuous", "districtCount": 2}
    chunks = [{"chunkId": str(i), "blockCount": 1, "asset": {"sha256": "a" * 64}, "assignments": {"url": str(i)}} for i in range(count)]
    documents = {str(i): {"schemaVersion": 1, "planId": plan["id"], "stateFips": plan["stateFips"],
                         "coordinateFrame": plan["coordinateFrame"], "chunkId": str(i), "geometrySha256": "a" * 64,
                         "districtIds": [i % 2]} for i in range(count)}
    summary = {"districts": [{"districtId": 1, "blockCount": count // 2}, {"districtId": 0, "blockCount": (count + 1) // 2}]}
    return plan, {"chunks": chunks}, summary, documents


def test_parallel_sidecars_use_bounded_batches_and_reconcile_every_saved_id(tmp_path, monkeypatch):
    batches, visits, workers = [], [], []

    class ObservedExecutor:
        def __init__(self, *, max_workers):
            workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def map(self, function, iterable):
            batch = tuple(iterable)
            batches.append(len(batch))
            return map(function, batch)

    plan, spatial, summary, documents = sidecar_fixture(513)

    def read(root, cache, reference, assets):
        assert root == tmp_path and cache == tmp_path / "cache"
        visits.append(reference["url"])
        return documents[reference["url"]]

    monkeypatch.setattr(publisher, "ThreadPoolExecutor", ObservedExecutor)
    monkeypatch.setattr(publisher, "read_reference", read)
    publisher.validate_plan_assignments(tmp_path, tmp_path / "cache", spatial, plan, summary, {})
    assert workers == [8] and batches == [256, 256, 1]
    assert visits == list(documents)
    summary["districts"][0]["blockCount"] += 1
    with pytest.raises(ValueError, match="district block counts"):
        publisher.validate_plan_assignments(tmp_path, tmp_path / "cache", spatial, plan, summary, {})


def test_parallel_sidecars_use_eight_readers_and_preserve_binding_failures(tmp_path, monkeypatch):
    plan, spatial, summary, documents = sidecar_fixture(8)
    barrier, lock = threading.Barrier(8), threading.Lock()
    active, peak = 0, 0

    def read(root, cache, reference, assets):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(active, peak)
        barrier.wait(timeout=5)
        with lock:
            active -= 1
        return documents[reference["url"]]

    monkeypatch.setattr(publisher, "read_reference", read)
    publisher.validate_plan_assignments(tmp_path, tmp_path, spatial, plan, summary, {})
    assert active == 0 and peak == 8
    documents["4"]["geometrySha256"] = "b" * 64
    with pytest.raises(ValueError, match="geometry binding"):
        publisher.validate_plan_assignments(tmp_path, tmp_path, spatial, plan, summary, {})


def test_parallel_sidecar_error_does_not_read_another_batch(tmp_path, monkeypatch):
    plan, spatial, summary, documents = sidecar_fixture(513)
    visits, lock = [], threading.Lock()

    def read(root, cache, reference, assets):
        with lock:
            visits.append(int(reference["url"]))
        if reference["url"] == "0":
            raise ValueError("Pinned sidecar checksum mismatch")
        return documents[reference["url"]]

    monkeypatch.setattr(publisher, "read_reference", read)
    with pytest.raises(ValueError, match="checksum mismatch"):
        publisher.validate_plan_assignments(tmp_path, tmp_path, spatial, plan, summary, {})
    assert 0 in visits and max(visits) < 256
