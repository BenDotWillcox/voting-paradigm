"""Benchmark one apportioned Kansas block plan, reusing the validated edge graph.

Each invocation is a new process for one House size. Numerical solver,
connectivity heuristic, and map exporter are the same as the original Kansas
experiment. The initial solve is checkpointed before graph loading or repair.
Large artifacts remain under .cache; earlier benchmark runs are preserved.
"""

from __future__ import annotations

import argparse
from collections import deque
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from numbers import Integral
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from districting import algorithm
from districting import balanced_power_diagram
from apportionment import apportion_us_2020
from districting.connectivity import repair_and_rebalance
from scripts.benchmark_kansas_blocks import (
    EXPECTED_BLOCKS, EXPECTED_POPULATION, Measurements, load_units,
    prepare_source, process_memory, sha256,
)
from scripts.district_block_map_export import export_maps


ANCHOR_HOUSE_SIZES = (435, 574, 692, 1000, 11037)
SEED = 20200955
OUTER_ITERATION_LIMIT = 80
INNER_ITERATION_LIMIT = 300


def _write_json(path: Path, data: Any, *, compact: bool = False) -> None:
    """Replace a report/checkpoint atomically so interrupted writes are obvious."""
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(
            data, output, allow_nan=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        )
        output.write("\n")
    temporary.replace(path)


def population_metrics(populations: Sequence[int]) -> dict[str, Any]:
    """Use exact deviation numerators, including when the ideal is fractional.

    The floor/ceiling bound assumes people can be individually assigned. Whole
    blocks and connectivity can prevent attaining it; it is a lower bound, not
    a promise about a feasible Kansas plan.
    """
    if not populations or any(
        isinstance(population, bool) or not isinstance(population, Integral) or population < 0
        for population in populations
    ):
        raise ValueError("District populations must be nonnegative integers.")
    actual = [int(population) for population in populations]
    total = sum(actual)
    if total <= 0:
        raise ValueError("Total population must be positive.")
    n_districts = len(actual)
    floor, remainder = divmod(total, n_districts)
    ceil = floor + int(remainder > 0)
    scaled = [n_districts * population - total for population in actual]
    largest_scaled = max(abs(deviation) for deviation in scaled)
    integer_bound_scaled = max(remainder, n_districts - remainder) if remainder else 0
    integer_bound_reached = all(population in (floor, ceil) for population in actual)
    return {
        "district_populations": actual,
        "total_population": total,
        "target_population": total / n_districts,
        "ideal_population_exact": {"numerator": total, "denominator": n_districts},
        "deviation_numerators": scaled,
        "deviation_denominator": n_districts,
        "deviations_people": [deviation / n_districts for deviation in scaled],
        "max_absolute_deviation_numerator": largest_scaled,
        "max_absolute_deviation_people": largest_scaled / n_districts,
        "max_absolute_deviation_percent": 100 * largest_scaled / total,
        "squared_deviation_numerator": sum(deviation * deviation for deviation in scaled),
        "squared_deviation_denominator": n_districts * n_districts,
        "total_range_people": max(actual) - min(actual),
        "total_range_percent": 100 * n_districts * (max(actual) - min(actual)) / total,
        "exact_equal_populations": largest_scaled == 0,
        "integer_population_lower_bound": {
            "floor_population": floor,
            "ceiling_population": ceil,
            "districts_at_floor": n_districts - remainder,
            "districts_at_ceiling": remainder,
            "max_deviation_numerator": integer_bound_scaled,
            "deviation_denominator": n_districts,
            "max_absolute_deviation_people": integer_bound_scaled / n_districts,
            "reached": integer_bound_reached,
            "whole_block_feasibility_assumed": False,
        },
    }


def stage_metrics(
    assignments: Sequence[int], populations: Sequence[int],
    adjacency: Sequence[Sequence[int]], geoids: Sequence[str], *,
    n_districts: int, expected_population: int = EXPECTED_POPULATION,
    expected_blocks: int | None = None,
) -> dict[str, Any]:
    """Independent all-unit population reconciliation and district BFS audit."""
    count = len(geoids)
    if n_districts < 1:
        raise ValueError("n_districts must be positive.")
    if not (len(assignments) == len(populations) == len(adjacency) == count):
        raise ValueError("Assignments, populations, adjacency, and GEOIDs must have equal lengths.")
    if expected_blocks is not None and count != expected_blocks:
        raise ValueError("Block coverage differs from the source count.")
    if len(set(geoids)) != count:
        raise ValueError("GEOIDs must be unique; every source block is audited exactly once.")
    actual = [0] * n_districts
    blocks = [0] * n_districts
    components = [0] * n_districts
    tracts: dict[str, set[int]] = {}
    for index, district in enumerate(assignments):
        if isinstance(district, bool) or not isinstance(district, Integral) or not 0 <= district < n_districts:
            raise ValueError("Invalid district assignment.")
        population = populations[index]
        if isinstance(population, bool) or not isinstance(population, Integral) or population < 0:
            raise ValueError("Population values must be nonnegative integers.")
        actual[district] += int(population)
        blocks[district] += 1
        tracts.setdefault(geoids[index][:11], set()).add(district)
    if sum(actual) != expected_population:
        raise ValueError("Population reconciliation failed.")
    seen = bytearray(count)
    for start, district in enumerate(assignments):
        if seen[start]:
            continue
        components[district] += 1
        seen[start] = 1
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for other in adjacency[current]:
                if isinstance(other, bool) or not isinstance(other, Integral) or not 0 <= other < count:
                    raise ValueError("Adjacency refers to an invalid block index.")
                if not seen[other] and assignments[other] == district:
                    seen[other] = 1
                    queue.append(other)
    if sum(seen) != count:
        raise ValueError("Block coverage reconciliation failed.")
    return {
        **population_metrics(actual),
        "district_count": n_districts,
        "district_block_counts": blocks,
        "shared_edge_components": components,
        "all_districts_nonempty": all(blocks),
        "all_districts_shared_edge_connected": components == [1] * n_districts,
        "all_blocks_assigned_once": True,
        "population_sum_matches_source": True,
        "tracts_split_across_districts": sum(len(districts) > 1 for districts in tracts.values()),
    }


@contextmanager
def observe_solver(progress: list[dict[str, Any]]) -> Iterator[None]:
    """Observe inner solve results without changing inputs, outputs, or RNG use.

    The solver exposes no callback. Temporary wrappers record existing SciPy
    status and pass timing, then restore both functions even after failure.
    Each pass is persisted in telemetry; stdout is throttled to avoid noise.
    """
    original_balance = algorithm._balance_weights
    original_minimize = algorithm.minimize
    current_pass = 0
    last_log = time.perf_counter()

    def observed_minimize(*args: Any, **kwargs: Any) -> Any:
        result = original_minimize(*args, **kwargs)
        progress[-1]["inner_optimizer"] = {
            "success": bool(result.success), "status": int(result.status),
            "message": str(result.message), "iterations": int(result.nit),
            "function_evaluations": int(result.nfev),
            "iteration_limit_reached": int(result.nit) >= INNER_ITERATION_LIMIT,
        }
        return result

    def observed_balance(*args: Any, **kwargs: Any) -> Any:
        nonlocal current_pass, last_log
        current_pass += 1
        record: dict[str, Any] = {"balance_pass": current_pass}
        progress.append(record)
        started = time.perf_counter()
        try:
            return original_balance(*args, **kwargs)
        finally:
            record["wall_seconds"] = time.perf_counter() - started
            now = time.perf_counter()
            if current_pass == 1 or current_pass % 5 == 0 or now - last_log >= 20:
                optimizer = record.get("inner_optimizer", {})
                print(
                    f"Solver balance pass {current_pass}: {record['wall_seconds']:.2f}s, "
                    f"inner iterations={optimizer.get('iterations', 'incomplete')}, "
                    f"success={optimizer.get('success', False)}", flush=True,
                )
                last_log = now

    algorithm._balance_weights = observed_balance
    algorithm.minimize = observed_minimize
    try:
        yield
    finally:
        algorithm._balance_weights = original_balance
        algorithm.minimize = original_minimize


def run_benchmark(
    house_size: int, output: Path, *, max_moves: int = 1000,
    skip_export: bool = False, graph_cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Run one fresh process workload; write a partial report on any failure."""
    if house_size not in ANCHOR_HOUSE_SIZES:
        raise ValueError(f"House size must be one of {ANCHOR_HOUSE_SIZES}.")
    if max_moves < 0:
        raise ValueError("max_moves must be nonnegative.")
    output = output.resolve()
    protected = [ROOT / ".cache/kansas-block-benchmark" / name for name in ("run-435", "run-435-connected")]
    if output in [path.resolve() for path in protected]:
        raise ValueError("Use a new output directory to preserve the earlier benchmarks.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty; prior artifacts are never overwritten.")
    output.mkdir(parents=True, exist_ok=True)
    graph_cache_dir = graph_cache_dir or ROOT / ".cache/kansas-block-benchmark/graph-cache"
    apportionment = apportion_us_2020(house_size)
    n_districts = apportionment["20"]
    settings = {
        "house_size": house_size, "district_count": n_districts,
        "seed": SEED, "max_outer_iterations": OUTER_ITERATION_LIMIT,
        "inner_max_iterations": INNER_ITERATION_LIMIT, "center_tolerance_m": 1e-4,
        "max_rebalance_moves": max_moves, "export_maps": not skip_export,
        "adjacency_rule": "Disjoint polygon interiors and shared boundary dimension 1; DE-9IM F***1****",
    }
    code_paths = [
        "districting/algorithm.py", "districting/connectivity.py", "apportionment/methods.py",
        "apportionment/data/apportionment_2020.py", "scripts/benchmark_kansas_blocks.py",
        "scripts/benchmark_kansas_anchors.py", "scripts/district_block_adjacency.py",
        "scripts/district_block_graph_cache.py", "scripts/district_block_map_export.py",
    ]
    settings_hash = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report: dict[str, Any] = {
        "status": "running", "state": "Kansas", "state_fips": "20", "source_year": 2020,
        "unit": "census_block", "house_size": house_size, "district_count": n_districts,
        "configuration": settings, "settings_sha256": settings_hash,
        "code_sha256": {path: sha256(ROOT / path) for path in code_paths},
        "apportionment": {"method": "Huntington-Hill", "state_seat_counts": apportionment},
        "environment": {
            "python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "packages": {name: version(name) for name in ("numpy", "scipy", "pyshp", "shapely")},
        },
        "solver_progress": [], "artifacts": {},
        "measurement_notes": [
            "One House size per fresh Python process; timings include instrumentation and checkpoint writes.",
            "Graph cache status and load/build time are recorded explicitly; source validation still runs.",
            "State seats use 2020 apportionment populations; district balance uses Kansas resident block population 2,937,880.",
            "Balance uses the exact fractional ideal total/K; floor/ceiling is an integer-person lower bound whose whole-block feasibility is not assumed.",
            "All blocks, including water and zero-population blocks, retain exactly one assignment.",
            "The unmodified solver's per-district integer targets differ from the common fractional ideal when total/K is not integral.",
            "Center convergence, inner-optimizer success, graph connectivity, and population balance are reported separately.",
            "Rebalancing is a deterministic local search over improving single populated-block transfers; a move cap is not convergence.",
            "Final assignments are a postprocessed plan and need not remain a power diagram.",
            "Overall peak is OS-reported Python working set; phase peaks are sampled every 100 ms.",
        ],
    }
    measurement = Measurements()
    started = time.perf_counter()
    _write_json(output / "benchmark.json", report)
    try:
        from scripts.district_block_graph_cache import load_or_build_shared_edge_graph

        source, report["source"] = prepare_source(ROOT / ".cache/kansas-block-benchmark/source", measurement)
        with measurement.phase("load_and_validate_block_records"):
            units, population_map, report["input"] = load_units(source)
            geoids = [unit.geoid for unit in units]
            populations = [unit.population for unit in units]
        with measurement.phase("solve"):
            with observe_solver(report["solver_progress"]):
                initial = balanced_power_diagram(
                    units, n_districts, seed=SEED,
                    max_outer_iterations=OUTER_ITERATION_LIMIT,
                    inner_max_iterations=INNER_ITERATION_LIMIT,
                )
        labels = tuple(initial.assignments[geoid] for geoid in geoids)
        if set(initial.assignments) != set(geoids):
            raise ValueError("Initial assignments differ from the source block universe.")
        report["solver"] = {
            "outer_iterations": initial.iterations, "centers_converged": initial.converged,
            "outer_iteration_limit_reached": initial.iterations >= OUTER_ITERATION_LIMIT,
            "balance_pass_count": len(report["solver_progress"]),
            "unsuccessful_inner_passes": sum(
                not record.get("inner_optimizer", {}).get("success", False)
                for record in report["solver_progress"]
            ),
            "inner_passes_reaching_iteration_limit": sum(
                record.get("inner_optimizer", {}).get("iteration_limit_reached", False)
                for record in report["solver_progress"]
            ),
            "solver_integer_target_max_imbalance": initial.max_population_imbalance,
            "population_balance": population_metrics([initial.populations[index] for index in range(n_districts)]),
        }
        provenance = {
            "configuration": settings, "settings_sha256": settings_hash,
            "code_sha256": report["code_sha256"], "source_sha256": report["source"]["archive_sha256"],
        }
        with measurement.phase("save_initial_checkpoint"):
            _write_json(output / "initial-solver-result.json", {
                **provenance, "plan_kind": "initial-power-diagram", "solver": report["solver"],
                "assignments": dict(initial.assignments), "centers": [asdict(center) for center in initial.centers],
                "solve_measurement": measurement.phases["solve"],
            }, compact=True)
            report["artifacts"]["initial_checkpoint"] = "initial-solver-result.json"
        if house_size == 435:
            baseline_path = ROOT / ".cache/kansas-block-benchmark/run-435/solver-result.json"
            if baseline_path.exists():
                baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
                report["warm_control_comparison"] = {
                    "initial_reference": str(baseline_path.relative_to(ROOT)),
                    "same_initial_source_archive": baseline["source_sha256"] == report["source"]["archive_sha256"],
                    "initial_assignments_identical": dict(initial.assignments) == baseline["assignments"],
                }
                del baseline
        del units
        with measurement.phase("load_or_build_shared_edge_graph"):
            adjacency, report["graph"], report["graph_cache"] = load_or_build_shared_edge_graph(
                source, geoids, source_sha256=report["source"]["archive_sha256"], cache_dir=graph_cache_dir,
            )
            if report["graph"]["interior_overlap_pair_count"]:
                raise ValueError("Source block interiors overlap; connectivity audit is insufficient.")
        with measurement.phase("audit_initial_connectivity"):
            report["initial_plan"] = stage_metrics(
                labels, populations, adjacency, geoids, n_districts=n_districts, expected_blocks=EXPECTED_BLOCKS,
            )
            if report["initial_plan"]["district_populations"] != report["solver"]["population_balance"]["district_populations"]:
                raise ValueError("Initial solver population totals failed independent reconciliation.")
        _write_json(output / "benchmark.json", {**report, "phases": measurement.phases})
        print(
            f"Kansas at House {house_size}: {n_districts} districts, "
            f"initial components={report['initial_plan']['shared_edge_components']}, "
            f"maximum deviation={report['initial_plan']['max_absolute_deviation_people']:.6f} people", flush=True,
        )
        with measurement.phase("repair_and_rebalance"):
            corrected = repair_and_rebalance(
                adjacency, labels, populations, n_districts=n_districts, max_moves=max_moves,
            )
        with measurement.phase("save_corrected_checkpoints"):
            assignments = dict(zip(geoids, corrected.assignments, strict=True))
            _write_json(output / "after-repair-result.json", {
                **provenance, "plan_kind": "shared-edge-repaired-before-rebalance",
                "assignments": dict(zip(geoids, corrected.repaired_assignments, strict=True)),
            }, compact=True)
            _write_json(output / "solver-result.json", {
                **provenance, "plan_kind": "shared-edge-repaired-and-rebalanced", "assignments": assignments,
                "initial_power_centers_for_provenance_only": [asdict(center) for center in initial.centers],
            }, compact=True)
            _write_json(output / "move-audit.json", {
                "repair_moves": [{**asdict(move), "geoids": [geoids[index] for index in move.units]} for move in corrected.repair_moves],
                "rebalance_moves": [{**asdict(move), "geoids": [geoids[index] for index in move.units]} for move in corrected.rebalance_moves],
                "stop_reason": corrected.stop_reason,
            })
            report["artifacts"].update({
                "repair_checkpoint": "after-repair-result.json", "final_checkpoint": "solver-result.json",
                "move_audit": "move-audit.json",
            })
        with measurement.phase("audit_corrected_connectivity"):
            for name, stage_labels in (("after_repair", corrected.repaired_assignments), ("final_plan", corrected.assignments)):
                report[name] = stage_metrics(
                    stage_labels, populations, adjacency, geoids,
                    n_districts=n_districts, expected_blocks=EXPECTED_BLOCKS,
                )
                if not report[name]["all_districts_shared_edge_connected"]:
                    raise ValueError(f"{name} failed the independent shared-edge connectivity audit.")
        report.update({
            "repair_move_count": len(corrected.repair_moves),
            "rebalance_move_count": len(corrected.rebalance_moves), "stop_reason": corrected.stop_reason,
            "rebalance_move_limit_reached": corrected.stop_reason == "max_moves",
            "blocks_changed_vs_initial": sum(before != after for before, after in zip(labels, corrected.assignments, strict=True)),
            "population_reassigned_vs_initial": sum(populations[index] for index in range(len(labels)) if labels[index] != corrected.assignments[index]),
        })
        if house_size == 435:
            connected_path = ROOT / ".cache/kansas-block-benchmark/run-435-connected/solver-result.json"
            if connected_path.exists():
                connected = json.loads(connected_path.read_text(encoding="utf-8"))
                report.setdefault("warm_control_comparison", {}).update({
                    "final_reference": str(connected_path.relative_to(ROOT)),
                    "same_final_source_archive": connected["source_sha256"] == report["source"]["archive_sha256"],
                    "final_assignments_identical": assignments == connected["assignments"],
                })
                del connected
        _write_json(output / "benchmark.json", {**report, "phases": measurement.phases})
        del adjacency
        if not skip_export:
            with measurement.phase("geometry_validation_and_map_export"):
                report["maps"] = export_maps(source, assignments, population_map, output / "maps")
            districts = report["maps"]["quality"]["districts"]
            if set(districts) != {str(index) for index in range(n_districts)}:
                raise ValueError("Map export did not preserve every district.")
            if any(district["polygon_components"] != 1 for district in districts.values()):
                raise ValueError("Final dissolved geometry has multiple polygon components.")
            if any(districts[str(index)]["population"] != report["final_plan"]["district_populations"][index] for index in range(n_districts)):
                raise ValueError("Map export population totals differ from the final graph audit.")
            report["artifacts"]["map_manifest"] = "maps/map-manifest.json"
        report["map_export_skipped"] = skip_export
        report["status"] = "complete"
    except BaseException as error:
        report["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        report["failed_phase"] = measurement.active
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["phases"] = measurement.phases
        report["timed_pipeline_wall_seconds"] = time.perf_counter() - started
        report["peak_process_working_set_bytes"] = process_memory()[1]
        measurement.close()
        _write_json(output / "benchmark.json", report)
        print(f"Report: {output / 'benchmark.json'}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--house-size", type=int, choices=ANCHOR_HOUSE_SIZES, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-moves", type=int, default=1000)
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--graph-cache-dir", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / f".cache/kansas-block-benchmark/anchors/run-{args.house_size}"
    run_benchmark(args.house_size, output, max_moves=args.max_moves, skip_export=args.skip_export, graph_cache_dir=args.graph_cache_dir)


if __name__ == "__main__":
    main()
