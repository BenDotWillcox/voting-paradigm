"""General-state orchestration, strict topology policy, and durable resume."""

from __future__ import annotations

import json
import gzip
import hashlib
from pathlib import Path
from typing import Any

import pytest

from districting import Unit
from districting.algorithm import DistrictingOptimizationError
from districting.part_connectivity import PartGraph
from scripts import benchmark_state_blocks as benchmark


def install_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, disconnected: bool = False, antimeridian: bool = False, overlaps: int = 0, populations: tuple[int, int, int] = (4, 4, 4)) -> list[Unit]:
    units = [Unit(f"10001000100{index:04d}", (float(index), 0.0), population) for index, population in enumerate(populations)]
    monkeypatch.setitem(benchmark.EXPECTED_BLOCK_COUNTS, "10", 3)
    monkeypatch.setitem(benchmark.EXPECTED_RESIDENT_POPULATIONS, "10", 12)
    monkeypatch.setattr(benchmark, "prepare_source", lambda *args: (tmp_path / "source.shp", {"archive_sha256": "a" * 64}))
    monkeypatch.setattr(benchmark, "load_units", lambda *args: (
        units, {unit.geoid: unit.population for unit in units},
        {"block_count": 3, "total_population": 12, "source_crosses_antimeridian": antimeridian},
    ))
    adjacency = ((1,), (0,), ()) if disconnected else ((1,), (0, 2), (1,))
    monkeypatch.setattr(benchmark, "load_or_build_shared_edge_graph", lambda *args, **kwargs: (
        adjacency, {"component_count": 2 if disconnected else 1, "interior_overlap_pair_count": overlaps},
        {"cache_hit": True, "status": "hit"},
    ))
    monkeypatch.setattr(benchmark, "load_or_build_shared_edge_part_graph", lambda *args, **kwargs: (
        PartGraph(adjacency, (0, 1, 2)),
        {"component_count": 2 if disconnected else 1, "interior_overlap_pair_count": overlaps},
        {"cache_hit": True, "status": "hit"},
    ))
    return units


def fail_if_called(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("Numerical work must not run in this test.")


def test_house_sizes_with_same_k_share_a_plan() -> None:
    assert benchmark.house_links("10", 1, (435, 574, 692, 1000)) == [435]
    # Wyoming remains a one-seat state at both of these anchors.
    assert benchmark.house_links("56", 1, (435, 574)) == [435, 574]
    with pytest.raises(ValueError, match="does not match"):
        benchmark.house_links("10", 98, (435,))
    with pytest.raises(ValueError, match="drawn from"):
        benchmark.house_links("10", 1, (11037,))


def test_component_population_audit_preserves_zero_population_island() -> None:
    result = benchmark.component_population_summary(((1,), (0,), ()), [4, 5, 0], ["a", "b", "c"])
    assert result == [
        {"block_count": 2, "population": 9, "example_geoid": "a"},
        {"block_count": 1, "population": 0, "example_geoid": "c"},
    ]


def test_disconnected_graph_stops_before_solver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path, disconnected=True)
    monkeypatch.setattr(benchmark, "balanced_power_diagram", fail_if_called)
    monkeypatch.setattr(benchmark, "repair_and_rebalance", fail_if_called)
    result = benchmark.run_benchmark("10", 1, tmp_path / "run", house_sizes=[435], skip_export=True)
    assert result["status"] == "unsupported_topology"
    assert result["unsupported_reason"]["code"] == "disconnected_source_graph"
    assert result["source_components"] == [
        {"block_count": 2, "population": 8, "example_geoid": "100010001000000"},
        {"block_count": 1, "population": 4, "example_geoid": "100010001000002"},
    ]
    assert "solver" not in result
    assert not (tmp_path / "run/initial-solver-result.json").exists()
    assert json.loads((tmp_path / "run/progress.json").read_text())["status"] == "unsupported_topology"


def test_overlap_stops_before_solver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path, overlaps=1)
    monkeypatch.setattr(benchmark, "balanced_power_diagram", fail_if_called)
    result = benchmark.run_benchmark("10", 1, tmp_path / "run", house_sizes=[435], skip_export=True)
    assert result["status"] == "unsupported_topology"
    assert result["unsupported_reason"]["code"] == "overlapping_block_interiors"


def test_multipart_source_disconnection_stops_before_solver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    # Whole-block path 0--1--2 is connected, but the second part of block 1
    # has no real edge to the first component. It must not be joined by fiat.
    monkeypatch.setattr(benchmark, "load_or_build_shared_edge_part_graph", lambda *args, **kwargs: (
        PartGraph(((1,), (0, 2), (1,), ()), (0, 1, 2, 1)),
        {"component_count": 2, "interior_overlap_pair_count": 0}, {"cache_hit": True},
    ))
    monkeypatch.setattr(benchmark, "balanced_power_diagram", fail_if_called)
    result = benchmark.run_benchmark("10", 2, tmp_path / "run", house_sizes=[574], skip_export=True)
    assert result["status"] == "unsupported_topology"
    assert result["unsupported_reason"]["code"] == "disconnected_source_part_graph"
    assert "solver" not in result


def test_antimeridian_stops_before_graph_or_solver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path, antimeridian=True)
    monkeypatch.setattr(benchmark, "load_or_build_shared_edge_graph", fail_if_called)
    monkeypatch.setattr(benchmark, "balanced_power_diagram", fail_if_called)
    result = benchmark.run_benchmark("10", 1, tmp_path / "run", house_sizes=[435], skip_export=True)
    assert result["status"] == "unsupported_antimeridian_topology"
    assert "graph" not in result
    assert "solver" not in result


def test_one_district_uses_connected_state_without_numerical_solver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    monkeypatch.setattr(benchmark, "balanced_power_diagram", fail_if_called)
    result = benchmark.run_benchmark("10", 1, tmp_path / "run", house_sizes=[435], skip_export=True)
    assert result["status"] == "complete"
    assert result["solver"]["kind"] == "trivial_single_district"
    assert result["solver"]["centers_converged"] is None
    assert result["solver"]["outer_iterations"] == 0
    assert result["final_plan"]["district_populations"] == [12]
    assert result["final_plan"]["shared_edge_components"] == [1]
    assert result["final_plan"]["shared_edge_part_components"] == [1]
    assert result["final_plan"]["all_districts_part_connected"] is True
    assert result["final_plan"]["all_blocks_assigned_once"] is True
    assert result["house_sizes"] == [435]
    assert result["full_end_to_end_run"] is False


def test_multiple_districts_preflight_graph_before_unchanged_solver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path, populations=(3, 3, 6))
    calls: list[str] = []
    original_graph = benchmark.load_or_build_shared_edge_graph
    original_solver = benchmark.balanced_power_diagram

    def graph(*args: Any, **kwargs: Any) -> Any:
        calls.append("graph")
        return original_graph(*args, **kwargs)

    def solver(*args: Any, **kwargs: Any) -> Any:
        calls.append("solve")
        assert kwargs == {"seed": benchmark.SEED, "max_outer_iterations": 80, "inner_max_iterations": 300}
        return original_solver(*args, **kwargs)

    monkeypatch.setattr(benchmark, "load_or_build_shared_edge_graph", graph)
    monkeypatch.setattr(benchmark, "balanced_power_diagram", solver)
    result = benchmark.run_benchmark("10", 2, tmp_path / "run", house_sizes=[574], skip_export=True)
    assert calls == ["graph", "solve"]
    assert result["status"] == "complete"
    assert result["solver"]["kind"] == "balanced_power_diagram"
    assert result["final_plan"]["shared_edge_components"] == [1, 1]
    assert sum(result["final_plan"]["district_populations"]) == 12


def test_nonsmooth_optimizer_failure_is_persisted_without_completed_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Three indivisible 4-person blocks cannot attain targets6/6. The old
    # runner silently accepted this fixture after an ABNORMAL inner solve.
    install_source(monkeypatch, tmp_path, populations=(4, 4, 4))
    monkeypatch.setattr(benchmark, "repair_and_rebalance", fail_if_called)
    output = tmp_path / "run"
    with pytest.raises(DistrictingOptimizationError):
        benchmark.run_benchmark("10", 2, output, house_sizes=[574], skip_export=True)
    report = json.loads((output / "benchmark.json").read_text())
    assert report["status"] == "failed"
    assert report["failed_phase"] == "solve"
    assert report["solver_progress"][-1]["inner_optimizer"]["success"] is False
    assert "final_plan" not in report
    assert not (output / "initial-solver-result.json").exists()
    assert not (output / "solver-result.json").exists()


def test_resume_reuses_initial_and_final_checkpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    output = tmp_path / "run"
    first = benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True)
    monkeypatch.setattr(benchmark, "balanced_power_diagram", fail_if_called)
    monkeypatch.setattr(benchmark, "repair_and_rebalance", fail_if_called)
    second = benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True, resume=True)
    assert second["status"] == "complete"
    assert second["resumed_stages"] == ["initial_solve", "repair_and_rebalance"]
    assert first["final_plan"] == second["final_plan"]
    assert (output / "attempts/benchmark-1.json").exists()
    assert "prior_solve_measurement" in second
    assert "prior_repair_measurement" in second


def test_completed_resume_verifies_archive_and_reuses_original_timings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"verified source archive fixture")
    digest = benchmark.sha256(archive)
    manifest = tmp_path / "source.manifest.json"
    manifest.write_text(json.dumps({"state_fips": "10", "archive_sha256": digest}))
    source_metadata = {"archive_sha256": digest, "archive_path": str(archive), "manifest_path": str(manifest)}
    monkeypatch.setattr(benchmark, "prepare_source", lambda *args: (tmp_path / "source.shp", source_metadata))
    output = tmp_path / "run"
    first = benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True)
    original_report_bytes = (output / "benchmark.json").read_bytes()
    monkeypatch.setattr(benchmark, "prepare_source", fail_if_called)
    monkeypatch.setattr(benchmark, "repair_and_rebalance", fail_if_called)
    second = benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True, resume=True)
    assert second == first
    assert (output / "benchmark.json").read_bytes() == original_report_bytes
    assert not (output / "attempts").exists()
    assert not benchmark.completed_result_reusable(first, output, require_export=True)

    # Add a minimal compressed-only completed map and check physical files,
    # rather than requiring the deliberately removed logical GeoJSON path.
    maps = output / "maps"
    maps.mkdir()
    raw = b'{"type":"FeatureCollection","features":[]}'
    compressed = maps / "districts-full.geojson.gz"
    compressed.write_bytes(gzip.compress(raw))
    (maps / "block-index.json").write_text("{}")
    map_manifest = {
        "strict_validation": {"passed": True}, "block_index": {"path": "block-index.json"},
        "storage": {"artifacts": [{
            "gzip_path": compressed.name, "gzip_bytes": compressed.stat().st_size,
            "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest(),
        }]},
    }
    (maps / "map-manifest.json").write_text(json.dumps(map_manifest))
    first["maps"] = map_manifest
    first["artifacts"]["map_manifest"] = "maps/map-manifest.json"
    first["map_export_skipped"] = False
    assert benchmark.completed_result_reusable(first, output, require_export=True)
    compressed.write_bytes(b"corrupt")
    assert not benchmark.completed_result_reusable(first, output, require_export=True)


def test_completed_resume_rejects_valid_label_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path, populations=(3, 3, 6))
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"source fixture")
    digest = benchmark.sha256(archive)
    manifest = tmp_path / "source.manifest.json"
    manifest.write_text(json.dumps({"state_fips": "10", "archive_sha256": digest}))
    monkeypatch.setattr(benchmark, "prepare_source", lambda *args: (
        tmp_path / "source.shp", {"archive_sha256": digest, "archive_path": str(archive), "manifest_path": str(manifest)},
    ))
    output = tmp_path / "run"
    benchmark.run_benchmark("10", 2, output, house_sizes=[574], skip_export=True)
    checkpoint = output / "solver-result.json"
    saved = json.loads(checkpoint.read_text())
    geoid = next(iter(saved["assignments"]))
    saved["assignments"][geoid] = 1 - saved["assignments"][geoid]
    checkpoint.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="content digest"):
        benchmark.run_benchmark("10", 2, output, house_sizes=[574], skip_export=True, resume=True)


def test_incomplete_run_resume_rejects_changed_initial_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path, populations=(3, 3, 6))
    output = tmp_path / "run"

    def fail_repair(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("deliberate correction failure")

    monkeypatch.setattr(benchmark, "repair_and_rebalance", fail_repair)
    with pytest.raises(RuntimeError, match="deliberate"):
        benchmark.run_benchmark("10", 2, output, house_sizes=[574], skip_export=True)
    checkpoint = output / "initial-solver-result.json"
    saved = json.loads(checkpoint.read_text())
    geoid = next(iter(saved["assignments"]))
    saved["assignments"][geoid] = 1 - saved["assignments"][geoid]
    checkpoint.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="content digest"):
        benchmark.run_benchmark("10", 2, output, house_sizes=[574], skip_export=True, resume=True)


def test_resume_recomputes_checkpoint_saved_before_digest_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    output = tmp_path / "run"
    benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True)
    report_path = output / "benchmark.json"
    saved_report = json.loads(report_path.read_text())
    saved_report["status"] = "interrupted"
    saved_report["artifact_sha256"] = {}
    report_path.write_text(json.dumps(saved_report))
    resumed = benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True, resume=True)
    assert resumed["status"] == "complete"
    assert resumed["resumed_stages"] == []
    assert resumed["uncommitted_checkpoints_recomputed"] == ["initial-solver-result.json", "solver-result.json"]
    assert len(resumed["artifact_sha256"]) == 4


def test_failure_preserves_initial_checkpoint_and_resume_can_finish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    output = tmp_path / "run"
    real_repair = benchmark.repair_and_rebalance

    def fail_repair(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("synthetic interrupted correction")

    monkeypatch.setattr(benchmark, "repair_and_rebalance", fail_repair)
    with pytest.raises(RuntimeError, match="synthetic interrupted"):
        benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True)
    partial = json.loads((output / "benchmark.json").read_text())
    assert partial["status"] == "failed"
    assert partial["failed_phase"] == "repair_and_rebalance"
    assert (output / "initial-solver-result.json").exists()
    assert not (output / "solver-result.json").exists()
    monkeypatch.setattr(benchmark, "repair_and_rebalance", real_repair)
    monkeypatch.setattr(benchmark, "balanced_power_diagram", fail_if_called)
    resumed = benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True, resume=True)
    assert resumed["status"] == "complete"
    assert resumed["resumed_stages"] == ["initial_solve"]


def test_resume_rejects_changed_source_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    output = tmp_path / "run"
    benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True)
    monkeypatch.setattr(benchmark, "prepare_source", lambda *args: (tmp_path / "source.shp", {"archive_sha256": "b" * 64}))
    with pytest.raises(ValueError, match="provenance"):
        benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True, resume=True)


def test_existing_outputs_require_explicit_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    (tmp_path / "benchmark.json").write_text("original")
    with pytest.raises(ValueError, match="empty"):
        benchmark.run_benchmark("10", 1, tmp_path, house_sizes=[435], skip_export=True)
    assert (tmp_path / "benchmark.json").read_text() == "original"


def test_export_resume_preserves_partial_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_source(monkeypatch, tmp_path)
    output = tmp_path / "run"
    benchmark.run_benchmark("10", 1, output, house_sizes=[435], skip_export=True)
    (output / "maps").mkdir()
    (output / "maps/partial.geojson.gz").write_bytes(b"partial")
    destinations: list[Path] = []

    def export(*args: Any, **kwargs: Any) -> dict[str, Any]:
        destinations.append(args[3])
        return {"quality": {"districts": {"0": {"polygon_components": 1, "population": 12}}}}

    monkeypatch.setattr(benchmark, "export_state_block_maps", export)
    result = benchmark.run_benchmark("10", 1, output, house_sizes=[435], resume=True)
    assert result["status"] == "complete"
    assert destinations == [output / "maps-attempt-2"]
    assert result["artifacts"]["map_manifest"] == "maps-attempt-2/map-manifest.json"
    assert (output / "maps/partial.geojson.gz").read_bytes() == b"partial"
