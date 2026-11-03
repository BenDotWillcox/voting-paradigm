"""Run one state's block plan for one distinct apportioned district count.

House sizes that apportion the same district count share a plan. Strict source
topology is checked before numerical work. Unsupported geography is reported
explicitly; no edges are invented between disconnected land or water blocks.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
import gzip
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from districting import balanced_power_diagram
from apportionment import apportion_us_2020
from districting.connectivity import repair_and_rebalance
from districting.part_connectivity import PartGraph, part_component_counts
from scripts.benchmark_kansas_anchors import (
    INNER_ITERATION_LIMIT, OUTER_ITERATION_LIMIT, SEED,
    observe_solver, population_metrics, stage_metrics,
)
from scripts.benchmark_kansas_blocks import Measurements, process_memory, sha256
from scripts.district_block_graph_cache import load_or_build_shared_edge_graph
from scripts.district_block_part_graph import load_or_build_shared_edge_part_graph
from scripts.district_block_sources import (
    EXPECTED_BLOCK_COUNTS, EXPECTED_RESIDENT_POPULATIONS, STATE_NAMES,
    load_units, normalize_state_fips, prepare_source,
)
from scripts.state_block_map_export import export_state_block_maps
from scripts.state_block_execution_lock import state_execution_lock


HOUSE_SIZES = (435, 574, 692, 1000)
CODE_PATHS = (
    "districting/algorithm.py", "districting/connectivity.py", "districting/part_connectivity.py", "apportionment/methods.py",
    "apportionment/data/apportionment_2020.py", "scripts/benchmark_state_blocks.py",
    "scripts/benchmark_kansas_blocks.py", "scripts/benchmark_kansas_anchors.py",
    "scripts/district_block_sources.py", "scripts/district_block_adjacency.py",
    "scripts/district_block_graph_cache.py", "scripts/district_block_map_export.py",
    "scripts/state_block_map_export.py",
    "scripts/state_block_execution_lock.py",
    "scripts/district_block_part_graph.py",
)


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, allow_nan=False, indent=None if compact else 2,
                  separators=(",", ":") if compact else None)
        stream.write("\n")
    temporary.replace(path)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def house_links(state_fips: str, n_districts: int, house_sizes: Sequence[int]) -> list[int]:
    if not house_sizes or any(size not in HOUSE_SIZES for size in house_sizes):
        raise ValueError(f"House sizes must be drawn from {HOUSE_SIZES}.")
    result = sorted({size for size in house_sizes if apportion_us_2020(size)[state_fips] == n_districts})
    if not result:
        raise ValueError("District count does not match this state's requested House-size anchors.")
    return result


def component_population_summary(
    adjacency: Sequence[Sequence[int]], populations: Sequence[int], geoids: Sequence[str],
) -> list[dict[str, Any]]:
    """Describe all geographic components, including unpopulated components."""
    if len(adjacency) != len(populations) or len(geoids) != len(populations):
        raise ValueError("Topology coverage does not match the source units.")
    seen = bytearray(len(adjacency))
    components = []
    for start in range(len(adjacency)):
        if seen[start]:
            continue
        count = 0
        population = 0
        seen[start] = 1
        stack = [start]
        while stack:
            current = stack.pop()
            count += 1
            population += populations[current]
            for neighbor in adjacency[current]:
                if not 0 <= neighbor < len(adjacency):
                    raise ValueError("Topology contains an invalid unit index.")
                if not seen[neighbor]:
                    seen[neighbor] = 1
                    stack.append(neighbor)
        components.append({"block_count": count, "population": population, "example_geoid": geoids[start]})
    return sorted(components, key=lambda component: (-component["population"], -component["block_count"], component["example_geoid"]))


def add_part_audit(metrics: dict[str, Any], graph: PartGraph, labels: Sequence[int], n_districts: int) -> None:
    """Keep the independent block audit and expose the stronger part audit."""
    counts = part_component_counts(graph, labels, n_districts=n_districts)
    metrics["shared_edge_part_components"] = list(counts)
    metrics["all_districts_part_connected"] = all(count == 1 for count in counts)


class RunProgress:
    """Persist phase boundaries and a lightweight heartbeat during long stages."""

    def __init__(self, report: dict[str, Any], output: Path, measurements: Measurements) -> None:
        self.report = report
        self.output = output
        self.measurements = measurements
        self.started = time.perf_counter()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    def _heartbeat(self) -> None:
        while not self.stop.wait(10):
            self.write_progress()

    def write_progress(self) -> None:
        # Take shallow snapshots; completed optimizer records are immutable.
        passes = [dict(record) for record in self.report.get("solver_progress", [])]
        write_json(self.output / "progress.json", {
            "state_fips": self.report["state_fips"], "district_count": self.report["district_count"],
            "status": self.report["status"], "active_phase": self.measurements.active,
            "elapsed_seconds": time.perf_counter() - self.started,
            "resident_bytes": process_memory()[0], "solver_progress": passes,
        })

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        self.report["active_phase"] = name
        write_json(self.output / "benchmark.json", self.report)
        try:
            with self.measurements.phase(name):
                yield
        finally:
            self.report["phases"] = dict(self.measurements.phases)
            write_json(self.output / "benchmark.json", self.report)

    def close(self) -> None:
        self.stop.set()
        self.thread.join()
        self.write_progress()


def _load_checkpoint(
    path: Path, provenance: dict[str, Any], geoids: Sequence[str], n_districts: int,
    plan_kind: str,
) -> tuple[dict[str, Any], tuple[int, ...]]:
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved.get("provenance") != provenance or saved.get("plan_kind") != plan_kind:
        raise ValueError(f"Checkpoint provenance or kind mismatch: {path.name}")
    assignments = saved.get("assignments", {})
    if set(assignments) != set(geoids) or any(
        isinstance(label, bool) or not isinstance(label, int) or not 0 <= label < n_districts
        for label in assignments.values()
    ):
        raise ValueError(f"Checkpoint assignments fail exact source coverage: {path.name}")
    return saved, tuple(assignments[geoid] for geoid in geoids)


def _new_map_directory(output: Path) -> Path:
    destination = output / "maps"
    attempt = 1
    while destination.exists() and any(destination.iterdir()):
        attempt += 1
        destination = output / f"maps-attempt-{attempt}"
    return destination


def verify_saved_artifact(report: dict[str, Any], path: Path, output: Path) -> None:
    """Bind stored claims to the exact checkpoint/audit bytes originally saved."""
    relative_path = path.relative_to(output).as_posix()
    expected = report.get("artifact_sha256", {}).get(relative_path)
    if not path.is_file() or not expected or sha256(path) != expected:
        raise ValueError(f"Saved artifact content digest mismatch or missing integrity record: {relative_path}")


def completed_result_reusable(report: dict[str, Any], output: Path, *, require_export: bool) -> bool:
    """Validate durable artifacts before returning a completed run unchanged.

    Source and gzip hashes are streamed. No geometry is loaded, no numerical
    work runs, and original measurements are preserved. Missing artifacts fall
    back to checkpoint resume; changed source identity fails explicitly.
    """
    if report.get("status") != "complete" or (require_export and report.get("map_export_skipped", True)):
        return False
    source = report.get("source", {})
    archive_name, manifest_name = source.get("archive_path"), source.get("manifest_path")
    if not archive_name or not manifest_name:
        return False
    archive, source_manifest = Path(archive_name), Path(manifest_name)
    if not archive.is_file() or not source_manifest.is_file():
        return False
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_hash = sha256(archive)
    if source_hash != source.get("archive_sha256") or manifest.get("archive_sha256") != source_hash or manifest.get("state_fips") != report["state_fips"]:
        raise ValueError("Completed source archive identity differs from its recorded manifest.")
    stage_paths = [output / name for name in ("initial-solver-result.json", "after-repair-result.json", "solver-result.json", "move-audit.json")]
    if not all(path.is_file() for path in stage_paths):
        return False
    for path in stage_paths:
        verify_saved_artifact(report, path, output)
    initial = json.loads(stage_paths[0].read_text(encoding="utf-8"))
    geoids = list(initial.get("assignments", {}))
    if len(geoids) != EXPECTED_BLOCK_COUNTS[report["state_fips"]] or any(not geoid.startswith(report["state_fips"]) or len(geoid) != 15 or not geoid.isascii() or not geoid.isdigit() for geoid in geoids):
        raise ValueError("Completed checkpoint block universe fails source coverage validation.")
    provenance = {
        "settings_sha256": report["settings_sha256"], "code_sha256": report["code_sha256"],
        "source_sha256": source_hash, "ordered_geoids_sha256": _digest(geoids),
        "state_fips": report["state_fips"], "district_count": report["district_count"],
    }
    for path, kind in zip(stage_paths[:3], ("initial", "after_repair", "final"), strict=True):
        _load_checkpoint(path, provenance, geoids, report["district_count"], kind)
    audit = json.loads(stage_paths[3].read_text(encoding="utf-8"))
    if audit.get("provenance") != provenance or audit.get("stop_reason") != report.get("stop_reason"):
        raise ValueError("Completed move audit provenance differs from its report.")
    if not report.get("final_plan", {}).get("all_districts_shared_edge_connected"):
        return False
    if not report.get("final_plan", {}).get("all_districts_part_connected"):
        return False
    if sum(report["final_plan"]["district_populations"]) != EXPECTED_RESIDENT_POPULATIONS[report["state_fips"]]:
        raise ValueError("Completed population totals fail source reconciliation.")
    if not report.get("map_export_skipped", True):
        relative_manifest = report.get("artifacts", {}).get("map_manifest")
        if not relative_manifest:
            return False
        map_manifest_path = (output / relative_manifest).resolve()
        if not map_manifest_path.is_relative_to(output.resolve()) or not map_manifest_path.is_file():
            return False
        maps = json.loads(map_manifest_path.read_text(encoding="utf-8"))
        if maps != report.get("maps") or not maps.get("strict_validation", {}).get("passed"):
            return False
        map_root = map_manifest_path.parent
        artifacts = maps.get("storage", {}).get("artifacts", [])
        if not artifacts:
            return False
        index = maps.get("block_index", {})
        if not index.get("path") or not (map_root / index["path"]).is_file():
            return False
        for artifact in artifacts:
            compressed = (map_root / artifact["gzip_path"]).resolve()
            if not compressed.is_relative_to(map_root) or not compressed.is_file() or compressed.stat().st_size != artifact["gzip_bytes"]:
                return False
            digest = hashlib.sha256()
            raw_bytes = 0
            try:
                with gzip.open(compressed, "rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                        raw_bytes += len(chunk)
            except (OSError, EOFError):
                return False
            if digest.hexdigest() != artifact["raw_sha256"] or raw_bytes != artifact["raw_bytes"]:
                return False
    return True


def run_benchmark(
    state_fips: str, n_districts: int, output: Path, *,
    house_sizes: Sequence[int] = HOUSE_SIZES, max_moves: int = 1000,
    skip_export: bool = False, resume: bool = False,
    source_cache_dir: Path | None = None, graph_cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Run a unique state/K plan; unsupported topology is a reported outcome."""
    state_fips = normalize_state_fips(state_fips)
    if isinstance(n_districts, bool) or not isinstance(n_districts, int) or n_districts < 1:
        raise ValueError("district_count must be a positive integer.")
    if max_moves < 0:
        raise ValueError("max_moves must be nonnegative.")
    links = house_links(state_fips, n_districts, house_sizes)
    output = output.resolve()
    settings = {
        "state_fips": state_fips, "district_count": n_districts,
        "seed": SEED, "max_outer_iterations": OUTER_ITERATION_LIMIT,
        "inner_max_iterations": INNER_ITERATION_LIMIT, "center_tolerance_m": 1e-4,
        "max_rebalance_moves": max_moves,
        "adjacency_rule": "Disjoint interiors and positive-length shared boundary; DE-9IM F***1****",
        "topology_policy": "all source polygon parts; whole-block assignments; no synthetic bridges; connected state part graph required",
    }
    code_hashes = {path: sha256(ROOT / path) for path in CODE_PATHS}
    settings_hash = _digest(settings)
    prior: dict[str, Any] | None = None
    if output.exists() and any(output.iterdir()):
        if not resume or not (output / "benchmark.json").exists():
            raise ValueError("Output must be empty unless --resume names an existing benchmark.")
        prior = json.loads((output / "benchmark.json").read_text(encoding="utf-8"))
        if prior.get("settings_sha256") != settings_hash or prior.get("code_sha256") != code_hashes:
            raise ValueError("Resume settings/code hashes differ from the saved benchmark.")
        if completed_result_reusable(prior, output, require_export=not skip_export):
            print(f"Reused completed result after source/checkpoint/artifact validation: {output / 'benchmark.json'}", flush=True)
            return prior
    output.mkdir(parents=True, exist_ok=True)
    if prior is not None:
        attempts = output / "attempts"
        attempts.mkdir(exist_ok=True)
        index = 1
        while (attempts / f"benchmark-{index}.json").exists():
            index += 1
        write_json(attempts / f"benchmark-{index}.json", prior)
    source_cache_dir = source_cache_dir or ROOT / f".cache/state-block-benchmark/source/{state_fips}"
    graph_cache_dir = graph_cache_dir or ROOT / f".cache/state-block-benchmark/graph-cache/{state_fips}"
    report: dict[str, Any] = {
        "status": "running", "state": STATE_NAMES[state_fips], "state_fips": state_fips,
        "source_year": 2020, "unit": "census_block", "district_count": n_districts,
        "house_sizes": links, "requested_house_sizes": sorted(set(house_sizes)),
        "configuration": settings, "settings_sha256": settings_hash, "code_sha256": code_hashes,
        "solver_progress": [], "artifacts": {}, "resumed_stages": [],
        "artifact_sha256": dict(prior.get("artifact_sha256", {})) if prior is not None else {},
        "environment": {
            "python": sys.version, "platform": platform.platform(), "logical_cpu_count": os.cpu_count(),
            "packages": {name: version(name) for name in ("numpy", "scipy", "pyshp", "shapely")},
        },
        "measurement_notes": [
            "One unique state/district-count plan is shared by every listed House size; duplicate counts are not recomputed.",
            "Source identity, totals, geometry topology and graph cache are checked before solving.",
            "All units, including zero-population and water blocks, must remain assigned; no invented adjacency is allowed.",
            "Antimeridian source coverage is unsupported by the current graph/export adapters and stops before graph building.",
            "Disconnected source graphs are unsupported by this workflow, not a proof that all geographic policies are infeasible.",
            "Population deviations use the fractional resident-population ideal; apportionment uses its separate official population series.",
            "Integer floor/ceiling balance is only a lower bound; whole blocks can prevent reaching it.",
            "Numerical solver is unchanged. Whole-block repair now checks polygon-part connectivity, including zero-population topology moves; balance moves preserve both donor and recipient part connectivity.",
            "Resume timings measure this attempt only; earlier phase measurements stay attached to saved stages and attempt reports.",
            "Independent jobs may run concurrently; wall times reflect shared desktop CPU/memory contention rather than isolated benchmark conditions.",
            "OS peak working set covers this process; phase peaks are sampled every 100 ms.",
        ],
    }
    if prior is not None:
        report["previous_attempt_status"] = prior.get("status")
    measurements = Measurements()
    progress = RunProgress(report, output, measurements)
    started = time.perf_counter()
    write_json(output / "benchmark.json", report)
    try:
        # Source helper owns acquisition/extraction phases, so benchmark and
        # heartbeat still expose its active phase while a download is running.
        report["active_phase"] = "prepare_source"
        source, report["source"] = prepare_source(state_fips, source_cache_dir, measurements)
        with progress.phase("load_and_validate_block_records"):
            units, population_map, report["input"] = load_units(source, state_fips)
            geoids = [unit.geoid for unit in units]
            populations = [unit.population for unit in units]
            expected_population = EXPECTED_RESIDENT_POPULATIONS[state_fips]
            expected_blocks = EXPECTED_BLOCK_COUNTS[state_fips]
            if len(geoids) != expected_blocks or sum(populations) != expected_population:
                raise ValueError("Loaded block count or resident population differs from official source totals.")
        if report["input"].get("source_crosses_antimeridian", False):
            report["status"] = "unsupported_antimeridian_topology"
            report["unsupported_reason"] = {
                "code": "antimeridian_coverage_requires_geographic_normalization",
                "message": "Current raw-coordinate shared-edge and planar export adapters cannot certify this antimeridian-spanning coverage.",
                "required_next_step": "Normalize antimeridian geometry and independently validate topology/export before running the solver.",
            }
            return report
        with progress.phase("load_or_build_shared_edge_graph"):
            adjacency, report["graph"], report["graph_cache"] = load_or_build_shared_edge_graph(
                source, geoids, source_sha256=report["source"]["archive_sha256"], cache_dir=graph_cache_dir,
            )
        with progress.phase("audit_source_topology"):
            components = component_population_summary(adjacency, populations, geoids)
            report["source_components"] = components
            if len(components) != report["graph"]["component_count"]:
                raise ValueError("Independent component audit differs from graph metadata.")
            if sum(component["block_count"] for component in components) != expected_blocks or sum(component["population"] for component in components) != expected_population:
                raise ValueError("Component totals do not reconcile to the source universe.")
        if report["graph"]["interior_overlap_pair_count"] or len(components) != 1:
            report["status"] = "unsupported_topology"
            report["unsupported_reason"] = {
                "code": "overlapping_block_interiors" if report["graph"]["interior_overlap_pair_count"] else "disconnected_source_graph",
                "message": "The current workflow requires one connected, nonoverlapping shared-edge graph before computing district plans.",
                "component_count": len(components),
                "required_next_step": "Inspect the saved source components and explicitly choose a geographic policy; no synthetic edges were added.",
            }
            return report
        with progress.phase("load_or_build_shared_edge_part_graph"):
            part_graph, report["part_graph"], report["part_graph_cache"] = load_or_build_shared_edge_part_graph(
                source, geoids, source_sha256=report["source"]["archive_sha256"], cache_dir=graph_cache_dir,
            )
        with progress.phase("audit_source_part_topology"):
            source_part_components = part_component_counts(part_graph, [0] * len(geoids), n_districts=1)[0]
            if source_part_components != report["part_graph"]["component_count"]:
                raise ValueError("Independent part audit differs from graph metadata.")
            report["source_part_component_count"] = source_part_components
        if report["part_graph"]["interior_overlap_pair_count"] or source_part_components != 1:
            report["status"] = "unsupported_topology"
            report["unsupported_reason"] = {
                "code": "overlapping_polygon_part_interiors" if report["part_graph"]["interior_overlap_pair_count"] else "disconnected_source_part_graph",
                "message": "The current workflow requires one connected, nonoverlapping source polygon-part graph. Whole-block nodes may hide disconnections.",
                "component_count": source_part_components,
                "required_next_step": "Inspect source polygon parts; no synthetic connections were added. This workflow rejection is not proof that no connected partition exists.",
            }
            return report
        provenance = {
            "settings_sha256": settings_hash, "code_sha256": code_hashes,
            "source_sha256": report["source"]["archive_sha256"],
            "ordered_geoids_sha256": _digest(geoids),
            "state_fips": state_fips, "district_count": n_districts,
        }
        initial_path = output / "initial-solver-result.json"
        initial_committed = initial_path.name in report["artifact_sha256"]
        if resume and initial_path.exists() and initial_committed:
            with progress.phase("load_initial_checkpoint"):
                verify_saved_artifact(report, initial_path, output)
                initial_saved, labels = _load_checkpoint(initial_path, provenance, geoids, n_districts, "initial")
                report["solver"] = initial_saved["solver"]
                report["solver_progress"] = initial_saved["solver_progress"]
                centers = initial_saved["centers"]
                report["resumed_stages"].append("initial_solve")
                report["prior_solve_measurement"] = initial_saved["solve_measurement"]
        else:
            if resume and initial_path.exists() and not initial_committed:
                # A crash can land after atomic checkpoint replacement but
                # before its digest is committed in benchmark.json. Recompute
                # this uncommitted stage; never silently trust those bytes.
                report.setdefault("uncommitted_checkpoints_recomputed", []).append(initial_path.name)
            if n_districts == 1:
                with progress.phase("trivial_single_district"):
                    labels = (0,) * len(geoids)
                    centers = []
                    report["solver"] = {
                        "kind": "trivial_single_district", "outer_iterations": 0,
                        "centers_converged": None, "balance_pass_count": 0,
                        "outer_iteration_limit_reached": False,
                        "not_applicable_reason": "One district contains the complete connected source graph; no numerical solve is needed.",
                        "population_balance": population_metrics([expected_population]),
                    }
                solve_measurement = measurements.phases["trivial_single_district"]
            else:
                with progress.phase("solve"):
                    with observe_solver(report["solver_progress"]):
                        initial = balanced_power_diagram(
                            units, n_districts, seed=SEED,
                            max_outer_iterations=OUTER_ITERATION_LIMIT, inner_max_iterations=INNER_ITERATION_LIMIT,
                        )
                if set(initial.assignments) != set(geoids):
                    raise ValueError("Initial assignments do not cover the source universe.")
                labels = tuple(initial.assignments[geoid] for geoid in geoids)
                centers = [asdict(center) for center in initial.centers]
                report["solver"] = {
                    "kind": "balanced_power_diagram", "outer_iterations": initial.iterations,
                    "centers_converged": initial.converged,
                    "outer_iteration_limit_reached": initial.iterations >= OUTER_ITERATION_LIMIT,
                    "balance_pass_count": len(report["solver_progress"]),
                    "unsuccessful_inner_passes": sum(not record.get("inner_optimizer", {}).get("success", False) for record in report["solver_progress"]),
                    "inner_passes_reaching_iteration_limit": sum(record.get("inner_optimizer", {}).get("iteration_limit_reached", False) for record in report["solver_progress"]),
                    "solver_integer_target_max_imbalance": initial.max_population_imbalance,
                    "population_balance": population_metrics([initial.populations[index] for index in range(n_districts)]),
                }
                solve_measurement = measurements.phases["solve"]
            with progress.phase("save_initial_checkpoint"):
                write_json(initial_path, {
                    "provenance": provenance, "plan_kind": "initial", "solver": report["solver"],
                    "assignments": dict(zip(geoids, labels, strict=True)), "centers": centers,
                    "solver_progress": report["solver_progress"], "solve_measurement": solve_measurement,
                }, compact=True)
                report["artifact_sha256"][initial_path.name] = sha256(initial_path)
        report["artifacts"]["initial_checkpoint"] = initial_path.name
        del units
        with progress.phase("audit_initial_connectivity"):
            report["initial_plan"] = stage_metrics(labels, populations, adjacency, geoids, n_districts=n_districts,
                                                   expected_population=expected_population, expected_blocks=expected_blocks)
            add_part_audit(report["initial_plan"], part_graph, labels, n_districts)
            if report["initial_plan"]["district_populations"] != report["solver"]["population_balance"]["district_populations"]:
                raise ValueError("Independent initial population reconciliation failed.")
        final_path = output / "solver-result.json"
        repair_path = output / "after-repair-result.json"
        audit_path = output / "move-audit.json"
        correction_committed = all(path.name in report["artifact_sha256"] for path in (final_path, repair_path, audit_path))
        if resume and final_path.exists() and correction_committed:
            with progress.phase("load_corrected_checkpoints"):
                for path in (final_path, repair_path, audit_path):
                    verify_saved_artifact(report, path, output)
                final_saved, final_labels = _load_checkpoint(final_path, provenance, geoids, n_districts, "final")
                _, repair_labels = _load_checkpoint(repair_path, provenance, geoids, n_districts, "after_repair")
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                if audit.get("provenance") != provenance or audit.get("stop_reason") not in ("local_optimum", "max_moves"):
                    raise ValueError("Saved move audit has mismatched provenance or stop reason.")
                report["prior_repair_measurement"] = final_saved["repair_measurement"]
                report["resumed_stages"].append("repair_and_rebalance")
        else:
            if resume and final_path.exists() and not correction_committed:
                report.setdefault("uncommitted_checkpoints_recomputed", []).append(final_path.name)
            with progress.phase("repair_and_rebalance"):
                corrected = repair_and_rebalance(adjacency, labels, populations, n_districts=n_districts, max_moves=max_moves, part_graph=part_graph)
                repair_labels, final_labels = corrected.repaired_assignments, corrected.assignments
                audit = {
                    "provenance": provenance, "stop_reason": corrected.stop_reason,
                    "repair_moves": [{**asdict(move), "geoids": [geoids[index] for index in move.units]} for move in corrected.repair_moves],
                    "part_repair_moves": [{**asdict(move), "geoids": [geoids[index] for index in move.units]} for move in corrected.part_repair_moves],
                    "rebalance_moves": [{**asdict(move), "geoids": [geoids[index] for index in move.units]} for move in corrected.rebalance_moves],
                }
            with progress.phase("save_corrected_checkpoints"):
                write_json(repair_path, {"provenance": provenance, "plan_kind": "after_repair", "assignments": dict(zip(geoids, repair_labels, strict=True))}, compact=True)
                write_json(audit_path, audit)
                # Final file is last, so its presence means every stage is saved.
                write_json(final_path, {
                    "provenance": provenance, "plan_kind": "final", "assignments": dict(zip(geoids, final_labels, strict=True)),
                    "initial_power_centers_for_provenance_only": centers,
                    "repair_measurement": measurements.phases["repair_and_rebalance"],
                }, compact=True)
                for path in (repair_path, audit_path, final_path):
                    report["artifact_sha256"][path.name] = sha256(path)
        report["artifacts"].update({"repair_checkpoint": repair_path.name, "final_checkpoint": final_path.name, "move_audit": audit_path.name})
        with progress.phase("audit_corrected_connectivity"):
            for name, stage_labels in (("after_repair", repair_labels), ("final_plan", final_labels)):
                report[name] = stage_metrics(stage_labels, populations, adjacency, geoids, n_districts=n_districts,
                                             expected_population=expected_population, expected_blocks=expected_blocks)
                add_part_audit(report[name], part_graph, stage_labels, n_districts)
                if not report[name]["all_districts_shared_edge_connected"] or not report[name]["all_districts_part_connected"]:
                    raise ValueError(f"{name} failed independent shared-edge connectivity.")
        report.update({
            "repair_move_count": len(audit["repair_moves"]), "rebalance_move_count": len(audit["rebalance_moves"]),
            "stop_reason": audit["stop_reason"], "rebalance_move_limit_reached": audit["stop_reason"] == "max_moves",
            "blocks_changed_vs_initial": sum(before != after for before, after in zip(labels, final_labels, strict=True)),
            "population_reassigned_vs_initial": sum(populations[index] for index in range(len(labels)) if labels[index] != final_labels[index]),
        })
        del adjacency
        if not skip_export:
            maps_directory = _new_map_directory(output)
            with progress.phase("geometry_validation_and_map_export"):
                report["maps"] = export_state_block_maps(
                    source, dict(zip(geoids, final_labels, strict=True)), population_map, maps_directory,
                    state_fips=state_fips, state_name=STATE_NAMES[state_fips], n_districts=n_districts,
                )
            districts = report["maps"]["quality"]["districts"]
            if set(districts) != {str(index) for index in range(n_districts)} or any(district["polygon_components"] != 1 for district in districts.values()):
                raise ValueError("Map export must preserve every district as one polygon component.")
            if any(districts[str(index)]["population"] != report["final_plan"]["district_populations"][index] for index in range(n_districts)):
                raise ValueError("Map population totals differ from the graph audit.")
            report["artifacts"]["map_manifest"] = (maps_directory / "map-manifest.json").relative_to(output).as_posix()
        report["map_export_skipped"] = skip_export
        report["full_end_to_end_run"] = not report["resumed_stages"] and not skip_export
        report["status"] = "complete"
    except BaseException as error:
        report["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        report["failed_phase"] = measurements.active
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["phases"] = dict(measurements.phases)
        report["timed_pipeline_wall_seconds"] = time.perf_counter() - started
        report["peak_process_working_set_bytes"] = process_memory()[1]
        report["active_phase"] = measurements.active
        progress.close()
        measurements.close()
        write_json(output / "benchmark.json", report)
        print(f"Report: {output / 'benchmark.json'}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-fips", required=True)
    parser.add_argument("--district-count", type=int, required=True)
    parser.add_argument("--house-sizes", type=int, nargs="+", default=list(HOUSE_SIZES))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-moves", type=int, default=1000)
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--source-cache-dir", type=Path)
    parser.add_argument("--graph-cache-dir", type=Path)
    args = parser.parse_args()
    # Hold ownership before reading prior artifacts or touching shared source
    # files, including completed-result validation and every resume path.
    with state_execution_lock(args.state_fips):
        run_benchmark(args.state_fips, args.district_count, args.output, house_sizes=args.house_sizes,
                      max_moves=args.max_moves, skip_export=args.skip_export, resume=args.resume,
                      source_cache_dir=args.source_cache_dir, graph_cache_dir=args.graph_cache_dir)


if __name__ == "__main__":
    main()
