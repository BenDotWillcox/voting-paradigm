"""Fail-closed publication and independent evidence checks for the WV cache run."""
from copy import deepcopy
import gzip
import hashlib
import json

import pytest
from shapely.geometry import box, mapping

from scripts import summarize_west_virginia_cached_balance as summary


def test_exact_fractional_population_metrics():
    result = summary.metrics([597905, 597905, 597906])
    assert result["max_absolute_deviation_people"] == pytest.approx(2 / 3)
    assert result["deviation_numerators"] == [-1, -1, 2]
    assert result["squared_deviation_numerator"] == 6
    assert result["integer_population_lower_bound_people"] == pytest.approx(2 / 3)
    assert result["integer_population_lower_bound_attained"] is True
    assert result["total_range_people"] == 1
    assert result["ideal_floor_population"] == 597905
    assert result["ideal_ceil_population"] == 597906


@pytest.mark.parametrize("populations,bound,reached,span", [
    ([1, 1, 1], 0, True, 0), ([1, 2], .5, True, 1),
    ([2, 2, 1], 2 / 3, True, 1), ([3, 1, 1], 2 / 3, False, 2),
])
def test_integer_bound_is_arithmetic_and_does_not_imply_all_plans_reach_it(populations, bound, reached, span):
    result = summary.metrics(populations)
    assert result["integer_population_lower_bound_people"] == pytest.approx(bound)
    assert result["integer_population_lower_bound_attained"] is reached
    assert result["total_range_people"] == span


@pytest.mark.parametrize("bad", [[-1, 2, 3], [True, 2, 3], [1.5, 2, 3], [0, 0, 0]])
def test_invalid_population_values_rejected(bad):
    with pytest.raises(ValueError):
        summary.metrics(bad)


def test_missing_blocks_and_boolean_district_labels_rejected():
    with pytest.raises(ValueError, match="every source block"):
        summary.population_audit({"a": 0}, {"a": 1, "b": 1})
    with pytest.raises(ValueError, match="district assignment"):
        summary.population_audit({"a": 0, "b": True, "c": 2}, {"a": 1, "b": 1, "c": 1})


@pytest.fixture
def replay_case():
    source = {"a": 100, "b": 50, "c": 140, "d": 10}
    start = {"a": 0, "b": 1, "c": 2, "d": 2}
    move = {"units": [3], "geoids": ["d"], "source_district": 2, "target_district": 1, "population": 10}
    return source, start, move


def test_replay_recomputes_population_and_primary_objective(replay_case):
    source, start, move = replay_case
    labels, trace = summary.replay_moves(start, [move], source, offset=1000)
    assert labels["d"] == 1 and start["d"] == 2
    assert trace[0]["moves"] == 1000 and trace[1]["moves"] == 1001
    assert trace[1]["district_populations"] == [100, 60, 140]
    assert trace[1]["max_absolute_deviation_people"] == 40


def test_replay_accepts_exact_secondary_improvement_at_equal_primary():
    source = {"a": 90, "b": 10, "c": 40, "d": 160}
    start = {"a": 0, "b": 0, "c": 1, "d": 2}
    move = {"units": [1], "geoids": ["b"], "source_district": 0, "target_district": 1, "population": 10}
    _, trace = summary.replay_moves(start, [move], source)
    assert trace[0]["max_absolute_deviation_people"] == trace[1]["max_absolute_deviation_people"] == 60
    assert trace[1]["squared_deviation_numerator"] < trace[0]["squared_deviation_numerator"]


@pytest.mark.parametrize("change", [
    {"geoids": ["c"]}, {"population": 11}, {"units": [3, 3]},
    {"source_district": 1}, {"units": [-1]}, {"target_district": True},
])
def test_replay_rejects_corrupted_move_identity_or_population(replay_case, change):
    source, start, move = replay_case
    move.update(change)
    with pytest.raises(ValueError):
        summary.replay_moves(start, [move], source)


def test_worsening_move_cannot_be_relabelled_as_progress(replay_case):
    source, start, _ = replay_case
    move = {"units": [1], "geoids": ["b"], "source_district": 1, "target_district": 2, "population": 50}
    with pytest.raises(ValueError, match="lexicographic objective"):
        summary.replay_moves(start, [move], source)


def test_equal_endpoint_does_not_replace_ordered_move_equivalence():
    a = {"moves": [{"ordinal": n} for n in range(100)], "assignments": {"a": 0}, "stop_reason": "max_moves"}
    b, old = deepcopy(a), deepcopy(a)
    assert summary.exact_equivalence(a, b, old)["compared_move_count"] == 100
    b["moves"][0], b["moves"][1] = b["moves"][1], b["moves"][0]
    with pytest.raises(ValueError, match="modes differ: moves"):
        summary.exact_equivalence(a, b, old)


def test_saved_trace_cannot_invent_a_smaller_deviation(replay_case):
    source, start, move = replay_case
    _, derived = summary.replay_moves(start, [move], source)
    saved = [{"moves": row["moves"], "populations": row["district_populations"],
              "max_deviation_people": row["max_absolute_deviation_people"],
              "max_deviation_percent": row["max_absolute_deviation_percent"]} for row in derived]
    summary.verify_trace(saved, derived)
    saved[-1]["max_deviation_people"] = 0
    with pytest.raises(ValueError, match="metric disagrees"):
        summary.verify_trace(saved, derived)


def test_runner_trace_initial_aliases_and_later_exact_numerator(replay_case):
    source, start, move = replay_case
    _, derived = summary.replay_moves(start, [move], source)
    saved = [{"moves": row["moves"], "populations": row["district_populations"],
              "max_deviation_people": row["max_absolute_deviation_people"],
              "max_deviation_percent": row["max_absolute_deviation_percent"]} for row in derived]
    # The runner's initial trace has no squared numerator; replayed moves do.
    saved[1]["squared_deviation_numerator"] = derived[1]["squared_deviation_numerator"]
    summary.verify_trace(saved, derived)
    saved[1]["squared_deviation_numerator"] += 1
    with pytest.raises(ValueError, match="Exact population metric"):
        summary.verify_trace(saved, derived)


def test_concrete_runner_verification_report_schema(tmp_path, monkeypatch):
    """Exercise the actual file/field contract without requiring census caches."""
    original_dir = tmp_path / "original"
    original_dir.mkdir()
    run_dir = tmp_path / "cached-100"
    run_dir.mkdir()
    monkeypatch.setattr(summary, "ORIGINAL", original_dir)
    geoids = [f"54{i:013d}" for i in range(103)]
    source = {geoids[0]: 100, geoids[1]: 0, geoids[2]: 100,
              **{geoids[n + 3]: 1 for n in range(100)}}
    initial = {g: (0 if g == geoids[0] else 1 if g == geoids[1] else 2) for g in source}
    moves = [{"units": [i + 3], "geoids": [geoids[i + 3]],
              "source_district": 2, "target_district": 1, "population": 1} for i in range(100)]
    final, trace = summary.replay_moves(initial, moves, source)

    def save(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    save(original_dir / "benchmark.json", {"status": "complete"})
    save(original_dir / "solver-result.json", {"assignments": initial})
    saved_trace = [{"moves": p["moves"], "populations": p["district_populations"],
                    "max_deviation_people": p["max_absolute_deviation_people"],
                    "max_deviation_percent": p["max_absolute_deviation_percent"],
                    **({"squared_deviation_numerator": p["squared_deviation_numerator"]} if i else {})}
                   for i, p in enumerate(trace)]
    save(run_dir / "trace.json", saved_trace)
    save(run_dir / "solver-result.json", {"assignments": final, "source_sha256": summary.SOURCE_SHA,
         "original_assignments_sha256": summary.sha256(original_dir / "solver-result.json")})
    save(run_dir / "move-audit.json", {"repair_moves": [], "rebalance_moves": moves,
         "original_cumulative_moves": 1000, "total_cumulative_moves": 1100})
    save(run_dir / "checkpoint-00100.json", {"assignments": final, "additional_moves": 100,
         "status": "checkpoint_not_accepted", "source_sha256": summary.SOURCE_SHA})
    report = {"status": "complete", "stage": "cached-100", "state_fips": "54", "district_count": 3,
        "house_sizes": [574], "config": {"cache_connectivity": True, "max_additional_moves": 100, "chunk_size": 100},
        "numerical_solver_rerun": False, "full_end_to_end_run": False, "preservation_unchanged": True,
        "code_sha256": {"current.py": "f" * 64}, "source": {"archive_sha256": summary.SOURCE_SHA},
        "input": {"block_count": len(source), "total_population": 300},
        "graph_cache": {"identity": summary._identity(list(source), summary.SOURCE_SHA)},
        "original_run": {"benchmark_sha256": summary.sha256(original_dir / "benchmark.json")},
        "initial_plan": summary.population_audit(initial, source),
        "final_plan": {**summary.population_audit(final, source), "shared_edge_components": [1, 1, 1]},
        "repair_move_count": 0, "rebalance_move_count": 100, "stop_reason": "max_moves",
        "rebalance_seconds": 1.4, "timed_pipeline_wall_seconds": 2.1, "peak_process_working_set_bytes": 100000,
        "chunks": [{"moves": 100, "cumulative_additional_moves": 100, "wall_seconds": 1.4, "stop_reason": "max_moves"}],
        "accepted_map": False, "finished_at": "finish"}
    report["artifact_sha256"] = {p.name: summary.sha256(p) for p in run_dir.iterdir()}
    save(run_dir / "benchmark.json", report)
    save(run_dir / "progress.json", {"status": "complete", "accepted_map": False,
         "rebalance_move_count": 100, "finished_at": "finish"})
    graph = [tuple(j for j in range(len(source)) if j != i) for i in range(len(source))]
    validated = summary.validate_run(run_dir, report, source, graph, initial, "cached-100", report["code_sha256"])
    assert validated["final"]["district_populations"] == [100, 100, 100]
    assert validated["accepted_map"] is False
    assert validated["additional_moves"] == 100
    report["accepted_map"] = True
    save(run_dir / "progress.json", {"status": "complete", "accepted_map": True,
         "rebalance_move_count": 100, "finished_at": "finish"})
    with pytest.raises(ValueError, match="Verification runs must not"):
        summary.validate_run(run_dir, report, source, graph, initial, "cached-100", report["code_sha256"])


@pytest.mark.parametrize("name", ["../original/benchmark.json", "/outside.json", ""])
def test_artifact_paths_are_confined(tmp_path, name):
    with pytest.raises(ValueError):
        summary.safe_path(tmp_path, name)


def test_duplicate_json_geoid_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "assignments.json"
    path.write_text('{"a":0,"a":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON"):
        summary.read(path)


@pytest.fixture
def manifest():
    jobs = [{"id": name, "status": "complete", "pid": i + 20, "child_pid": i + 20,
             "returncode": 0, "report": path, "started_at": "start", "finished_at": "finish", "elapsed_seconds": 1.0}
            for i, (name, path) in enumerate(zip(("traversal-100", "cached-100", "continuation"), summary.JOB_PATHS, strict=True))]
    return {"status": "complete", "finished_at": "finish", "preservation_unchanged": True, "pid": 10, "jobs": jobs}


@pytest.mark.parametrize("state", ["running", "failed", "pending"])
def test_nonterminal_or_failed_parent_blocks_summary(manifest, state):
    manifest["status"] = state
    with pytest.raises(ValueError, match="completed, preserved"):
        summary.verify_manifest(manifest)


def test_stale_or_unconfirmed_child_exit_blocks_summary(manifest):
    summary.verify_manifest(manifest)
    manifest["jobs"][1]["returncode"] = 1
    with pytest.raises(ValueError, match="confirmed exit"):
        summary.verify_manifest(manifest)


def test_parent_selected_report_hash_is_required(tmp_path):
    path = tmp_path / "benchmark.json"
    path.write_text('{"status":"complete"}', encoding="utf-8")
    job = {"report": "benchmark.json", "report_sha256": summary.sha256(path)}
    assert summary.select_report(job, tmp_path)[1]["status"] == "complete"
    path.write_text('{"status":"failed"}', encoding="utf-8")
    with pytest.raises(ValueError, match="selected terminal report changed"):
        summary.select_report(job, tmp_path)


def test_live_or_reused_pid_requires_inspection(manifest, monkeypatch):
    reports = [{"pid": j["child_pid"]} for j in manifest["jobs"]]
    if summary.os.name != "nt":
        pytest.skip("Windows process evidence adapter")
    monkeypatch.setattr(summary, "windows_pid_status", lambda ids: [{"pid": p, "active": p == 10} for p in ids])
    with pytest.raises(ValueError, match="active or its PID was reused"):
        summary.process_audit(manifest, reports)


@pytest.fixture
def map_case(tmp_path):
    directory = tmp_path / "run"
    maps = directory / "maps"
    maps.mkdir(parents=True)
    geometries = [box(i, 0, i + 1, 1) for i in range(3)]
    source = {"a": 10, "b": 20, "c": 30}
    assignments = {g: i for i, g in enumerate(source)}
    county = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(geometries[i]),
         "properties": {"geoid": g, "district_id": i, "population": source[g]}}
        for i, g in enumerate(source)]}
    full = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(geometries[i]),
         "properties": {"district_id": i, "population": source[g], "block_count": 1}}
        for i, g in enumerate(source)]}

    def write(county_payload=county, full_payload=full):
        artifacts = []
        for name, payload in (("county-001.geojson.gz", county_payload), ("districts-full.geojson.gz", full_payload)):
            raw = json.dumps(payload).encode()
            packed = gzip.compress(raw)
            (maps / name).write_bytes(packed)
            artifacts.append({"gzip_path": name, "gzip_bytes": len(packed), "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest()})
        return {"storage": {"artifacts": artifacts}}

    return directory, write, source, assignments, geometries, county, full


def test_delivered_geometry_and_population_reconciled_independently(map_case):
    directory, write, source, assignments, geometries, _, _ = map_case
    report = summary.compressed_maps(directory, write(), assignments, source, geometries)
    assert report["strict_polygon_components"] == [1, 1, 1]
    assert report["verified_compressed_artifact_count"] == 2


@pytest.mark.parametrize("corruption", ["population", "district", "geometry", "missing"])
def test_rehashed_but_wrong_county_payload_fails_source_audit(map_case, corruption):
    directory, write, source, assignments, geometries, county, _ = map_case
    county = deepcopy(county)
    feature = county["features"][0]
    if corruption == "population": feature["properties"]["population"] = 11
    if corruption == "district": feature["properties"]["district_id"] = 1
    if corruption == "geometry": feature["geometry"] = mapping(box(0, 0, .9, 1))
    if corruption == "missing": county["features"].pop()
    with pytest.raises(ValueError):
        summary.compressed_maps(directory, write(county_payload=county), assignments, source, geometries)


def test_rehashed_wrong_full_district_geometry_rejected(map_case):
    directory, write, source, assignments, geometries, _, full = map_case
    full = deepcopy(full)
    full["features"][0]["geometry"] = mapping(box(0, 0, .9, 1))
    with pytest.raises(ValueError, match="strict polygon/assignment"):
        summary.compressed_maps(directory, write(full_payload=full), assignments, source, geometries)


def test_unvalidated_or_pending_map_cannot_be_published(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, "OUTPUT", tmp_path)
    with pytest.raises(ValueError, match="Refusing to publish"):
        summary.write_outputs({"status": "running", "correction": {"accepted_map": True}})
    with pytest.raises(ValueError, match="Refusing to publish"):
        summary.write_outputs({"status": "independently_validated", "correction": {"accepted_map": False}})
    assert list(tmp_path.iterdir()) == []


def test_speedup_uses_fresh_matched_timings_not_old_profiled_probe():
    record = {"passed": True, "ordered_moves_equal": True, "assignments_equal": True,
              "stop_reasons_equal": True, "matches_preserved_probe": True, "fresh_processes": True,
              "profiling_enabled": False, "move_count": 100, "traversal_seconds": 200.0,
              "cached_seconds": 10.0, "measured_speedup": 20.0}
    assert summary.verify_equivalence_record(record, {"rebalance_seconds": 200.0}, {"rebalance_seconds": 10.0}) == 20
    record["measured_speedup"] = 244.189 / 10
    with pytest.raises(ValueError, match="timing comparison differs"):
        summary.verify_equivalence_record(record, {"rebalance_seconds": 200.0}, {"rebalance_seconds": 10.0})
