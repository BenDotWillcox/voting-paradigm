"""Generalized population accounting and recoverability of the anchor runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from districting import Unit, balanced_power_diagram
from districting import algorithm
from districting.algorithm import DistrictingOptimizationError
from apportionment import apportion_us_2020
from scripts import benchmark_kansas_anchors as benchmark
from scripts import district_block_graph_cache


@pytest.mark.parametrize(("house_size", "expected_districts"), [(435, 4), (574, 5), (692, 6), (1000, 9), (11037, 98)])
def test_real_apportionment_drives_each_anchor(house_size: int, expected_districts: int) -> None:
    assert apportion_us_2020(house_size)["20"] == expected_districts


@pytest.mark.parametrize(("district_count", "expected_scaled_bound"), [(4, 0), (5, 0), (6, 4), (9, 8), (98, 62)])
def test_integer_lower_bound_uses_fractional_ideal(district_count: int, expected_scaled_bound: int) -> None:
    floor, remainder = divmod(benchmark.EXPECTED_POPULATION, district_count)
    populations = [floor + int(index < remainder) for index in range(district_count)]
    result = benchmark.population_metrics(populations)
    assert result["deviation_denominator"] == district_count
    assert result["max_absolute_deviation_numerator"] == expected_scaled_bound
    assert result["integer_population_lower_bound"]["max_deviation_numerator"] == expected_scaled_bound
    assert result["integer_population_lower_bound"]["reached"] is True
    assert result["exact_equal_populations"] is (remainder == 0)
    assert sum(result["deviation_numerators"]) == 0
    assert result["max_absolute_deviation_percent"] == pytest.approx(100 * expected_scaled_bound / benchmark.EXPECTED_POPULATION)


def test_population_bound_does_not_claim_whole_block_feasibility() -> None:
    result = benchmark.population_metrics([5, 5, 1])
    assert result["target_population"] == pytest.approx(11 / 3)
    assert result["deviation_numerators"] == [4, 4, -8]
    assert result["max_absolute_deviation_people"] == pytest.approx(8 / 3)
    assert result["squared_deviation_numerator"] == 96
    assert result["squared_deviation_denominator"] == 9
    assert result["integer_population_lower_bound"]["reached"] is False
    assert result["integer_population_lower_bound"]["whole_block_feasibility_assumed"] is False


def test_stage_metrics_handle_variable_districts_zero_population_and_fractional_ideal() -> None:
    result = benchmark.stage_metrics(
        [0, 0, 1, 2, 2], [3, 0, 4, 2, 2],
        [[1], [0, 2], [1, 3], [2, 4], [3]],
        [f"20001000100{index:04d}" for index in range(5)],
        n_districts=3, expected_population=11, expected_blocks=5,
    )
    assert result["district_populations"] == [3, 4, 4]
    assert result["district_block_counts"] == [2, 1, 2]
    assert result["shared_edge_components"] == [1, 1, 1]
    assert result["all_districts_shared_edge_connected"] is True
    assert result["all_blocks_assigned_once"] is True
    assert result["population_sum_matches_source"] is True
    assert result["tracts_split_across_districts"] == 1
    assert result["deviation_numerators"] == [-2, 1, 1]
    assert result["integer_population_lower_bound"]["reached"] is True


def test_stage_metrics_detect_disconnected_and_empty_districts() -> None:
    result = benchmark.stage_metrics(
        [0, 1, 0], [1, 1, 1], [[1], [0, 2], [1]], ["a", "b", "c"],
        n_districts=3, expected_population=3,
    )
    assert result["shared_edge_components"] == [2, 1, 0]
    assert result["all_districts_shared_edge_connected"] is False
    assert result["all_districts_nonempty"] is False


@pytest.mark.parametrize(
    ("labels", "populations", "adjacency", "geoids", "expected_population", "message"),
    [
        ([0], [1, 1], [[]], ["a"], 1, "equal lengths"),
        ([0, 1], [1, 1], [[1], [0]], ["a", "a"], 2, "unique"),
        ([0], [1], [[]], ["a"], 2, "reconciliation"),
        ([3], [1], [[]], ["a"], 1, "assignment"),
        ([0], [-1], [[]], ["a"], 1, "nonnegative"),
        ([0], [1], [[3]], ["a"], 1, "invalid block"),
    ],
)
def test_stage_metrics_reject_incomplete_or_invalid_inputs(
    labels: list[int], populations: list[int], adjacency: list[list[int]],
    geoids: list[str], expected_population: int, message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        benchmark.stage_metrics(labels, populations, adjacency, geoids, n_districts=2, expected_population=expected_population)


def test_progress_observer_preserves_numerical_results_and_restores_functions() -> None:
    # This test compares successful executions; weighted midpoint ties belong
    # to the explicit numerical-failure observation case below.
    units = [Unit(str(index), (float(index % 3), float(index // 3)), 1) for index in range(6)]
    expected = balanced_power_diagram(units, 2, seed=17, max_outer_iterations=3, inner_max_iterations=7)
    balance_before, minimize_before = algorithm._balance_weights, algorithm.minimize
    progress: list[dict[str, Any]] = []
    with benchmark.observe_solver(progress):
        actual = balanced_power_diagram(units, 2, seed=17, max_outer_iterations=3, inner_max_iterations=7)
    assert actual == expected
    assert algorithm._balance_weights is balance_before
    assert algorithm.minimize is minimize_before
    assert len(progress) == actual.iterations + 1
    assert all("inner_optimizer" in record and "wall_seconds" in record for record in progress)
    assert all(record["inner_optimizer"]["success"] for record in progress)


def test_progress_observer_records_real_nonsmooth_failure_and_restores_functions() -> None:
    units = [Unit(str(index), (float(index % 3), float(index // 3)), index + 1) for index in range(6)]
    balance_before, minimize_before = algorithm._balance_weights, algorithm.minimize
    progress: list[dict[str, Any]] = []
    with pytest.raises(DistrictingOptimizationError):
        with benchmark.observe_solver(progress):
            balanced_power_diagram(units, 2, seed=17, max_outer_iterations=3, inner_max_iterations=7)
    assert algorithm._balance_weights is balance_before
    assert algorithm.minimize is minimize_before
    assert progress[-1]["inner_optimizer"]["success"] is False
    assert progress[-1]["inner_optimizer"]["status"] in (1, 2)
    assert "wall_seconds" in progress[-1]


def test_progress_observer_restores_functions_after_failure() -> None:
    balance_before, minimize_before = algorithm._balance_weights, algorithm.minimize
    with pytest.raises(RuntimeError, match="deliberate"):
        with benchmark.observe_solver([]):
            raise RuntimeError("deliberate")
    assert algorithm._balance_weights is balance_before
    assert algorithm.minimize is minimize_before


def test_initial_checkpoint_survives_failure_before_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    units = [Unit(f"20001000100{index:04d}", (float(index), 0.0), benchmark.EXPECTED_POPULATION // 4) for index in range(4)]
    monkeypatch.setattr(benchmark, "prepare_source", lambda *args: (tmp_path / "source.shp", {"archive_sha256": "test-source"}))
    monkeypatch.setattr(benchmark, "load_units", lambda *args: (units, {unit.geoid: unit.population for unit in units}, {"block_count": 4}))

    def fail_graph(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("deliberate graph failure")

    monkeypatch.setattr(district_block_graph_cache, "load_or_build_shared_edge_graph", fail_graph)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="deliberate graph failure"):
        benchmark.run_benchmark(435, output, skip_export=True)
    initial = json.loads((output / "initial-solver-result.json").read_text())
    report = json.loads((output / "benchmark.json").read_text())
    assert initial["plan_kind"] == "initial-power-diagram"
    assert set(initial["assignments"]) == {unit.geoid for unit in units}
    assert initial["source_sha256"] == "test-source"
    assert initial["settings_sha256"] == report["settings_sha256"]
    assert report["status"] == "failed"
    assert report["failed_phase"] == "load_or_build_shared_edge_graph"
    assert report["artifacts"]["initial_checkpoint"] == "initial-solver-result.json"
    assert report["peak_process_working_set_bytes"] > 0


def test_existing_output_is_preserved(tmp_path: Path) -> None:
    (tmp_path / "benchmark.json").write_text("original")
    with pytest.raises(ValueError, match="empty"):
        benchmark.run_benchmark(435, tmp_path)
    assert (tmp_path / "benchmark.json").read_text() == "original"
