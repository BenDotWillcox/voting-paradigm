"""Run Kansas block districting, shared-edge repair, rebalance, and map export.

Preserves the original run-435 benchmark. The shared-edge graph is rebuilt in
every measured run; no graph cache is silently reused.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any, Sequence

from benchmark_kansas_blocks import (
    EXPECTED_POPULATION, ROOT, Measurements, load_units, prepare_source,
    process_memory, sha256,
)
from districting import balanced_power_diagram
from districting.connectivity import repair_and_rebalance
from district_block_adjacency import build_shared_edge_adjacency
from district_block_map_export import export_maps


def stage_metrics(
    assignments: Sequence[int], populations: Sequence[int],
    adjacency: Sequence[Sequence[int]], geoids: Sequence[str],
) -> dict[str, Any]:
    """Independent whole-graph audit after each algorithm stage."""
    actual = [0] * 4
    blocks = [0] * 4
    components = [0] * 4
    tracts: dict[str, set[int]] = {}
    for i, district in enumerate(assignments):
        if not 0 <= district < 4:
            raise ValueError("Invalid district assignment")
        actual[district] += populations[i]
        blocks[district] += 1
        tracts.setdefault(geoids[i][:11], set()).add(district)
    seen: set[int] = set()
    for start, district in enumerate(assignments):
        if start in seen:
            continue
        components[district] += 1
        seen.add(start)
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for other in adjacency[current]:
                if other not in seen and assignments[other] == district:
                    seen.add(other)
                    queue.append(other)
    target = EXPECTED_POPULATION // 4
    if sum(actual) != EXPECTED_POPULATION or len(seen) != len(assignments):
        raise ValueError("Population or coverage reconciliation failed")
    return {
        "district_populations": actual, "district_block_counts": blocks,
        "shared_edge_components": components,
        "all_districts_shared_edge_connected": components == [1] * 4,
        "all_blocks_assigned_once": True, "population_sum_matches_source": True,
        "target_population": target,
        "deviations_people": [p - target for p in actual],
        "max_absolute_deviation_people": max(abs(p - target) for p in actual),
        "max_absolute_deviation_percent": 100 * max(abs(p - target) for p in actual) / target,
        "total_range_people": max(actual) - min(actual),
        "total_range_percent": 100 * (max(actual) - min(actual)) / target,
        "tracts_split_across_districts": sum(len(s) > 1 for s in tracts.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/kansas-block-benchmark/run-435-connected")
    parser.add_argument("--max-moves", type=int, default=1000)
    parser.add_argument("--skip-export", action="store_true")
    args = parser.parse_args()
    if args.output.resolve() == (ROOT / ".cache/kansas-block-benchmark/run-435").resolve():
        parser.error("Use a new output directory to preserve the original benchmark")
    args.output.mkdir(parents=True, exist_ok=True)
    measurement = Measurements()
    start = time.perf_counter()
    report: dict[str, Any] = {
        "status": "running", "state": "Kansas", "source_year": 2020,
        "unit": "census_block", "house_size": 435, "district_count": 4,
        "configuration": {
            "seed": 20200955, "max_outer_iterations": 80, "inner_max_iterations": 300,
            "center_tolerance_m": 1e-4, "max_rebalance_moves": args.max_moves,
            "adjacency_rule": "Disjoint polygon interiors and shared boundary dimension 1; DE-9IM F***1****",
            "solver_sha256": sha256(ROOT / "districting/algorithm.py"),
            "connectivity_sha256": sha256(ROOT / "districting/connectivity.py"),
            "adjacency_builder_sha256": sha256(ROOT / "scripts/district_block_adjacency.py"),
            "exporter_sha256": sha256(ROOT / "scripts/district_block_map_export.py"),
        },
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "packages": {name: version(name) for name in ("numpy", "scipy", "pyshp", "shapely")}},
        "notes": [
            "One local run; compare with prior desktop observation, not a controlled multi-run benchmark.",
            "Source archive cached; all geometry adjacency rebuilt and timed in this run.",
            "Original numerical solver unchanged; its docstrings now distinguish power cells from whole-block polygons.",
            "Every accepted rebalance move decreases maximum deviation or, at the same maximum, squared population error.",
            "Graph correction makes these assignments a postprocessed district plan, not an exact power diagram.",
            "Overall peak is OS-reported Python working set; phase memory sampled every 100 ms.",
        ],
    }
    try:
        source, report["source"] = prepare_source(ROOT / ".cache/kansas-block-benchmark/source", measurement)
        with measurement.phase("load_and_validate_block_records"):
            units, population_map, report["input"] = load_units(source)
            geoids = [unit.geoid for unit in units]
            populations = [unit.population for unit in units]
        with measurement.phase("solve"):
            initial = balanced_power_diagram(units, 4, seed=20200955,
                max_outer_iterations=80, inner_max_iterations=300)
        labels = tuple(initial.assignments[geoid] for geoid in geoids)
        report["solver_iterations"] = initial.iterations
        report["centers_converged"] = initial.converged
        baseline_path = ROOT / ".cache/kansas-block-benchmark/run-435/solver-result.json"
        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_text())
            report["comparison"] = {
                "same_source_archive": baseline["source_sha256"] == report["source"]["archive_sha256"],
                "initial_assignments_identical_to_original_run": dict(initial.assignments) == baseline["assignments"],
                "original_report": "prompts/kansas-block-benchmark.json",
            }
            if not all(report["comparison"][key] for key in (
                "same_source_archive", "initial_assignments_identical_to_original_run")):
                raise ValueError("Initial source/assignments differ from the comparison baseline")
            del baseline
        del units
        with measurement.phase("build_shared_edge_graph"):
            adjacency, report["graph"] = build_shared_edge_adjacency(source, geoids)
            if report["graph"]["interior_overlap_pair_count"]:
                raise ValueError("Source block interiors overlap; connectivity audit is not sufficient")
        with measurement.phase("audit_initial_connectivity"):
            report["initial_plan"] = stage_metrics(labels, populations, adjacency, geoids)
        print("Initial graph audit: " + json.dumps(report["initial_plan"]), flush=True)
        with measurement.phase("repair_and_rebalance"):
            corrected = repair_and_rebalance(adjacency, labels, populations, n_districts=4, max_moves=args.max_moves)
        with measurement.phase("audit_corrected_connectivity"):
            report["after_repair"] = stage_metrics(corrected.repaired_assignments, populations, adjacency, geoids)
            report["final_plan"] = stage_metrics(corrected.assignments, populations, adjacency, geoids)
            if not report["after_repair"]["all_districts_shared_edge_connected"] or not report["final_plan"]["all_districts_shared_edge_connected"]:
                raise ValueError("Repair/rebalance failed independent shared-edge connectivity audit")
        report["repair_move_count"] = len(corrected.repair_moves)
        report["rebalance_move_count"] = len(corrected.rebalance_moves)
        report["stop_reason"] = corrected.stop_reason
        report["blocks_changed_vs_initial"] = sum(a != b for a, b in zip(labels, corrected.assignments, strict=True))
        report["population_reassigned_vs_initial"] = sum(populations[i] for i in range(len(labels)) if labels[i] != corrected.assignments[i])
        audit = {
            "repair_moves": [{**asdict(move), "geoids": [geoids[i] for i in move.units]} for move in corrected.repair_moves],
            "rebalance_moves": [{**asdict(move), "geoids": [geoids[i] for i in move.units]} for move in corrected.rebalance_moves],
            "stop_reason": corrected.stop_reason,
        }
        (args.output / "move-audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        assignments = dict(zip(geoids, corrected.assignments, strict=True))
        checkpoint = {
            "configuration": report["configuration"], "source_sha256": report["source"]["archive_sha256"],
            "solver": report["final_plan"], "assignments": assignments,
            "plan_kind": "shared-edge-repaired-and-rebalanced",
            "initial_power_centers_for_provenance_only": [asdict(center) for center in initial.centers],
        }
        (args.output / "solver-result.json").write_text(json.dumps(checkpoint, separators=(",", ":")), encoding="utf-8")
        print("Final graph audit: " + json.dumps(report["final_plan"]), flush=True)
        del adjacency
        if not args.skip_export:
            with measurement.phase("geometry_validation_and_map_export"):
                report["maps"] = export_maps(source, assignments, population_map, args.output / "maps")
            if any(district["polygon_components"] != 1 for district in report["maps"]["quality"]["districts"].values()):
                raise ValueError("Final dissolved geometry still has multiple polygon components")
        report["status"] = "complete"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["phases"] = measurement.phases
        report["timed_pipeline_wall_seconds"] = time.perf_counter() - start
        report["peak_process_working_set_bytes"] = process_memory()[1]
        report["script_sha256"] = sha256(Path(__file__))
        measurement.close()
        (args.output / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {args.output / 'benchmark.json'}", flush=True)


if __name__ == "__main__":
    main()
