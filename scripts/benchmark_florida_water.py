"""Run fresh Florida block plans with explicitly recorded water connections.

Original strict preflight and diagnostic evidence remain immutable. Fixed
numerical settings, observational traces and full polygon validation accompany
each serial first attempt. Physical and policy connectivity stay distinct.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
from typing import Any

import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from districting import DistrictingOptimizationError, balanced_power_diagram
from districting.connectivity import repair_and_rebalance
from districting.part_connectivity import PartGraph, part_component_counts
from scripts.benchmark_kansas_anchors import (
    OUTER_ITERATION_LIMIT, SEED,
    population_metrics, stage_metrics,
)
from scripts.benchmark_kansas_blocks import Measurements, process_memory, sha256
from scripts.benchmark_state_blocks import CODE_PATHS, house_links
from scripts.correct_state_block_parts import block_adjacency, write_json
from scripts.florida_recorded_links import build_florida_connections
from scripts.district_block_part_graph import load_or_build_shared_edge_part_graph
from scripts.district_block_sources import load_units, prepare_source
from scripts.state_block_execution_lock import state_execution_lock
from scripts.district_optimizer_trace import trace_optimizer
from scripts.state_block_map_export import export_state_block_maps

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'policies/florida-water-v1'
POLICY = 'shared_edges_plus_recorded_water_connections'
TOTAL, BLOCKS = 21_538_187, 390_066
INNER_ITERATION_LIMIT = 1000
CENTER_TOLERANCE_M = 1e-4
COUNTS = (28, 37, 45, 65)
EXTRA_CODE = (
    'scripts/benchmark_florida_water.py', 'scripts/florida_recorded_links.py',
    'scripts/run_florida_water_suite.py', 'scripts/assets/florida-block-viewer.html',
    'scripts/hawaii_population_links.py', 'scripts/district_block_island_links.py',
    'scripts/diagnose_hawaii_topology.py', 'scripts/correct_state_block_parts.py',
    'scripts/district_optimizer_trace.py', 'districting/__init__.py',
)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def environment_snapshot() -> dict[str, Any]:
    return {'python': sys.version, 'platform': platform.platform(),
            'packages': {name: version(name) for name in ('numpy', 'scipy', 'pyshp', 'shapely')},
            'geos': shapely.geos_version_string}


def runtime_code() -> dict[str, str]:
    return {name: sha256(ROOT / name) for name in (*CODE_PATHS, *EXTRA_CODE)}


def protected_inventory() -> dict[str, str]:
    """Protect the original Florida strict results, source and full diagnosis."""
    required = [SUITE / 'suite.json', SUITE / 'states/12/districts-28/benchmark.json',
        SUITE / 'diagnostics/florida/diagnosis.json',
        ROOT / 'prompts/florida-topology-diagnosis.json',
        ROOT / '.cache/state-block-benchmark/source/12/tl_2020_12_tabblock20.zip']
    directories = [SUITE / 'states/12', SUITE / 'diagnostics/florida']
    if any(not path.is_file() for path in required) or any(not path.is_dir() for path in directories):
        raise ValueError('Required preserved Florida strict or diagnostic evidence is missing.')
    paths = set(required)
    for directory in directories:
        paths.update(path for path in directory.rglob('*') if path.is_file())
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(paths)}


def configuration_for_run(n_districts: int) -> dict[str, Any]:
    if type(n_districts) is not int or n_districts not in COUNTS:
        raise ValueError('Only Florida K28/K37/K45/K65 are authorized.')
    minimum = Fraction(TOTAL, n_districts) * Fraction(99, 100)
    return {
        'seed': SEED, 'max_outer_iterations': OUTER_ITERATION_LIMIT,
        'inner_max_iterations': INNER_ITERATION_LIMIT, 'center_tolerance_m': CENTER_TOLERANCE_M,
        'max_rebalance_moves': 1000,
        'physical_adjacency_rule': 'polygon parts; disjoint interiors; positive-length shared boundary; F***1****',
        'connection_policy': 'population-aware-rooted-boundary-forest-v1',
        'connection_kinds': ['recorded-water-connection'],
        'root_eligibility_relative_band': .01, 'group_population_preflight_tolerance': .01,
        'minimum_district_population_for_root_classification': float(minimum),
        'minimum_district_population_exact': str(minimum),
        'eligibility_note': 'The 99% root threshold and 1% optimistic integer-seat preflight guide link selection only; they do not guarantee final whole-block population balance.',
        'boundary_metric': 'source census coverage including retained water blocks; no shoreline substitution',
        'inner_optimization': {
            'normalization': 'population-mass and geometry-derived shifted squared costs; mean-zero weight gauge',
            'public_units': 'centers in source coordinate units; weights in squared source coordinate units',
            'max_line_search_steps': 100,
            'failure_policy': 'raise on unsuccessful termination or nonfinite output; no completed plan returned',
        },
    }


def load_strict_baseline(n_districts: int) -> dict[str, Any]:
    if n_districts not in COUNTS:
        raise ValueError('Only Florida K28/K37/K45/K65 are authorized.')
    suite_path = SUITE / 'suite.json'
    suite = json.loads(suite_path.read_text(encoding='utf-8'))
    states = [state for state in suite['states'] if state['state_fips'] == '12']
    if len(states) != 1:
        raise ValueError('Expected one original Florida state entry.')
    jobs = [job for job in states[0]['jobs'] if job['district_count'] == n_districts]
    expected = 'states/12/districts-28/benchmark.json'
    key = 'report' if n_districts == 28 else 'topology_report'
    if len(jobs) != 1 or jobs[0]['status'] != 'unsupported_topology' or jobs[0].get(key) != expected:
        raise ValueError('Strict Florida job does not reference its original K28 topology preflight.')
    path = SUITE / expected
    old = json.loads(path.read_text(encoding='utf-8'))
    if (old['state_fips'] != '12' or old['district_count'] != 28
            or old['status'] != 'unsupported_topology' or old.get('solver_progress')):
        raise ValueError('Expected the unsolved original Florida strict preflight.')
    return {'strict_report_path': path.relative_to(ROOT).as_posix(), 'strict_report_sha256': sha256(path),
            'strict_status': old['status'], 'strict_preflight_reused': n_districts != 28,
            'strict_solver_ran': False, 'strict_pipeline_wall_seconds': old['timed_pipeline_wall_seconds'],
            'strict_suite_path': suite_path.relative_to(ROOT).as_posix(), 'strict_suite_sha256': sha256(suite_path),
            'strict_suite_job': deepcopy(jobs[0]), 'source_archive_sha256': old['source']['archive_sha256'],
            'controlled_inner_budget_comparison': False,
            'note': 'The original K28 strict run stopped at source topology before solving; other anchors reused that exception. This is a fresh water-policy plan, not a controlled iteration-budget rerun.'}


def validate_output(output: Path, n_districts: int) -> None:
    expected = (SUITE / f'policies/florida-water-v1/states/12/districts-{n_districts}').resolve()
    if type(n_districts) is not int or n_districts not in COUNTS or output.resolve() != expected:
        raise ValueError('Output must be the matching new Florida water-policy anchor directory.')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Output must be absent or empty; earlier attempts are preserved.')


def write_terminal_report(output: Path, report: dict[str, Any]) -> Path:
    """Retain terminal status even if Windows denies the normal replacement.

    The exclusive fallback is a new authoritative record, never a rerun or an
    overwrite of historical evidence. The launcher reads it only after exit.
    """
    try:
        write_json(output / 'benchmark.json', report)
        return output / 'benchmark.json'
    except OSError as error:
        report['terminal_report_write_error'] = f'{type(error).__name__}: {error}'
        report['authoritative_terminal_report'] = 'terminal-report.json'
        fallback = output / 'terminal-report.json'
        with fallback.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        print(f'Authoritative terminal fallback: {fallback}', flush=True)
        return fallback


class Progress:
    def __init__(self, output: Path, report: dict[str, Any], measurements: Measurements) -> None:
        self.output, self.report, self.measurements = output, report, measurements
        self.started = time.perf_counter()
        self.stop = threading.Event()
        self.errors: list[str] = []
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    def snapshot(self) -> None:
        write_json(self.output / 'progress.json', {
            'status': self.report['status'], 'active_phase': self.report.get('active_phase'),
            'district_count': self.report['district_count'], 'policy': POLICY,
            'elapsed_seconds': time.perf_counter() - self.started,
            'resident_bytes': process_memory()[0],
            'solver_progress': [dict(item) for item in self.report['solver_progress']],
        })

    def _heartbeat(self) -> None:
        while not self.stop.wait(10):
            try:
                self.snapshot()
            except OSError as error:
                self.errors.append(f'{type(error).__name__}: {error}')

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        self.report['active_phase'] = name
        write_json(self.output / 'benchmark.json', self.report)
        print(f'Phase: {name}', flush=True)
        try:
            with self.measurements.phase(name):
                yield
        finally:
            self.report['phases'] = dict(self.measurements.phases)
            write_json(self.output / 'benchmark.json', self.report)

    def close(self) -> None:
        self.stop.set()
        self.thread.join()
        self.snapshot()


def audit_plan(
    labels: Sequence[int], populations: Sequence[int], geoids: Sequence[str],
    physical: PartGraph, augmented: PartGraph, n_districts: int,
) -> dict[str, Any]:
    """Never label augmented connectivity as physical shared-edge connectivity."""
    result = stage_metrics(labels, populations, block_adjacency(physical, len(geoids)), geoids,
                           n_districts=n_districts, expected_population=sum(populations), expected_blocks=len(geoids))
    raw = part_component_counts(physical, labels, n_districts=n_districts)
    connected = part_component_counts(augmented, labels, n_districts=n_districts)
    result['physical_part_components'] = list(raw)
    result['all_districts_physically_part_connected'] = all(value == 1 for value in raw)
    result['policy_part_components'] = list(connected)
    result['all_districts_policy_connected'] = all(value == 1 for value in connected)
    return result


def write_viewer(output: Path, report: dict[str, Any]) -> None:
    template = (ROOT / 'scripts/assets/florida-block-viewer.html').read_text(encoding='utf-8')
    projection = report['input']['projection']
    replacements = {
        '__STATE_NAME__': 'Florida', '__DISTRICT_COUNT__': str(report['district_count']),
        '__RESULT_SUMMARY__': (
            f'{report["district_count"]} districts; inner iteration ceiling 1,000; connected under the recorded water-link policy. '
            f'Maximum population deviation {report["final_plan"]["max_absolute_deviation_percent"]:.6f}%. '
            'Physical polygons remain unchanged. Original strict preflight preserved; it did not solve a plan.'),
        '__ANCHOR_NAVIGATION__': '<a href="../../../">Florida comparison</a> ' + ' '.join(
            f'<a href="../districts-{count}/"' + (' aria-current="page"' if count == report['district_count'] else '')
            + f'>{count} districts</a>' for count in COUNTS)
            + ' <a href="../../../../../diagnostics/florida/">Original topology diagnosis</a>',
        '__LON0__': str(projection['lon0']), '__LAT0__': str(projection['lat0']),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    (output / 'index.html').write_text(template, encoding='utf-8')


def run(n_districts: int, output: Path, *, max_moves: int = 1000) -> dict[str, Any]:
    if n_districts not in COUNTS or max_moves != 1000:
        raise ValueError('This Florida suite requires K28/K37/K45/K65 and 1,000 rebalance moves.')
    output = output.resolve()
    validate_output(output, n_districts)
    with state_execution_lock('12'):
        return _run_locked(n_districts, output, max_moves)


def _run_locked(n_districts: int, output: Path, max_moves: int) -> dict[str, Any]:
    # Recheck after acquiring the state lock; another attempt may have finished
    # while this process waited. Never resume or overwrite any earlier attempt.
    validate_output(output, n_districts)
    output.mkdir(parents=True, exist_ok=True)
    measurements = Measurements()
    started = time.perf_counter()
    before: dict[str, str] | None = None
    report: dict[str, Any] = {
        'status': 'running', 'run_kind': 'florida_population_aware_water_v1',
        'state': 'Florida', 'state_fips': '12', 'district_count': n_districts,
        'house_sizes': house_links('12', n_districts, (435, 574, 692, 1000)),
        'source_year': 2020, 'unit': 'census_block', 'policy': POLICY,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'configuration': {}, 'code_sha256': {},
        'solver_progress': [], 'artifacts': {}, 'artifact_sha256': {},
        'environment': environment_snapshot(),
        'measurement_notes': [
            'A fresh Florida water-policy anchor with the fixed normalized optimizer, 1,000 inner iterations, seed, tolerances and postprocessing. No controlled 300-versus-1,000 claim.',
            'Original strict K28 rejected disconnected source topology before solving; K37/K45/K65 reused that exception. No strict completed map or solver runtime exists for comparison.',
            'Observational accepted-iteration tracing adds callback and JSONL I/O overhead without adding objective evaluations or changing stopping rules.',
            'Source archive and physical part graph are already cached; cache hits and preparation phases remain measured.',
            'One serial process on a shared desktop; timings are not isolated hardware measurements.',
            'Timed pipeline includes provenance inventory and preservation checks, but excludes imports, state-lock wait and final report flush.',
            'Physical shared-edge connectivity, connectivity under recorded water links, and population quality are separate outcomes. Source polygons are unchanged.',
            'Candidate connections describe gaps between Census coverage boundaries, not coastlines, travel routes or certified geodesic minima.',
        ],
    }
    progress = Progress(output, report, measurements)
    def save(name: str, value: Any) -> None:
        write_json(output / name, value)
        report['artifacts'][name] = name
        report['artifact_sha256'][name] = sha256(output / name)
    try:
        with progress.phase('preserve_evidence_and_fingerprint_code'):
            report['configuration'] = configuration_for_run(n_districts)
            report['configuration_sha256'] = _digest(report['configuration'])
            before = protected_inventory()
            write_json(output / 'preserved-file-inventory.json', before)
            report['artifact_sha256']['preserved-file-inventory.json'] = sha256(output / 'preserved-file-inventory.json')
            report['code_sha256'] = runtime_code()
            report['comparison_baseline'] = load_strict_baseline(n_districts)
        report['active_phase'] = 'source_preparation'
        source, report['source'] = prepare_source('12', ROOT / '.cache/state-block-benchmark/source/12', measurements)
        if (report['source']['archive_sha256'] != before['.cache/state-block-benchmark/source/12/tl_2020_12_tabblock20.zip']
                or report['source']['archive_sha256'] != report['comparison_baseline']['source_archive_sha256']):
            raise ValueError('Source archive identity changed.')
        with progress.phase('load_and_validate_blocks'):
            units, population_map, report['input'] = load_units(source, '12')
            geoids = [unit.geoid for unit in units]
            populations = [unit.population for unit in units]
        with progress.phase('load_or_build_physical_part_graph'):
            physical, report['physical_part_graph'], report['physical_part_graph_cache'] = load_or_build_shared_edge_part_graph(
                source, geoids, source_sha256=report['source']['archive_sha256'],
                cache_dir=ROOT / '.cache/state-block-benchmark/graph-cache/12')
            if report['physical_part_graph'].get('interior_overlap_pair_count', 0):
                raise ValueError('Overlapping source interiors cannot form a valid district partition.')
        with progress.phase('prepare_population_aware_water_connections'):
            augmented, connections, report['island_policy_audit'] = build_florida_connections(
                source, geoids, populations, physical, district_count=n_districts)
            selection = report['island_policy_audit']['population_selection']
            if (report['island_policy_audit']['district_count'] != n_districts
                    or selection['district_count'] != n_districts
                    or selection['ideal_population'] != sum(populations) / n_districts
                    or selection['minimum_root_population'] != report['configuration']['minimum_district_population_for_root_classification']
                    or sum(group['district_count'] for group in selection['groups']) != n_districts):
                raise ValueError('Water-policy population preflight does not match this district count.')
            if part_component_counts(augmented, [0] * len(geoids), n_districts=1) != (1,):
                raise ValueError('Florida water-link policy must yield one connected source graph.')
            save('water-connections.json', {'policy': POLICY, 'connections': list(connections),
                                          'source_sha256': report['source']['archive_sha256']})
            report['water_connections'] = list(connections)
            adjacency = block_adjacency(augmented, len(geoids))
        provenance = {'source_sha256': report['source']['archive_sha256'],
                      'code_sha256': report['code_sha256'], 'configuration': report['configuration'],
                      'water_connections_sha256': report['artifact_sha256']['water-connections.json']}
        with progress.phase('solve'):
            trace = None
            try:
                with trace_optimizer(output / 'optimizer-trace.jsonl') as trace:
                    report['solver_progress'] = trace.passes
                    initial = balanced_power_diagram(units, n_districts, seed=SEED,
                        max_outer_iterations=OUTER_ITERATION_LIMIT, center_tol=CENTER_TOLERANCE_M,
                        inner_max_iterations=INNER_ITERATION_LIMIT)
            finally:
                if trace is not None:
                    report['optimizer_trace'] = trace.summary()
                    report['artifacts']['optimizer-trace.jsonl'] = 'optimizer-trace.jsonl'
                    if (output / 'optimizer-trace.jsonl').is_file():
                        report['artifact_sha256']['optimizer-trace.jsonl'] = sha256(output / 'optimizer-trace.jsonl')
            if trace is None or not trace.observation_ok:
                raise ValueError('Optimizer diagnostics were not recorded successfully; preserve this attempt.')
        if set(initial.assignments) != set(geoids):
            raise ValueError('Initial solver assignments differ from the source universe.')
        labels = tuple(initial.assignments[geoid] for geoid in geoids)
        centers = [asdict(center) for center in initial.centers]
        report['solver'] = {'kind': 'balanced_power_diagram', 'outer_iterations': initial.iterations,
                            'centers_converged': initial.converged,
                            'outer_iteration_limit_reached': initial.iterations >= OUTER_ITERATION_LIMIT,
                            'population_balance': population_metrics([initial.populations[i] for i in range(n_districts)])}
        passes = report['solver_progress']
        if not passes or not all(item.get('inner_optimizer', {}).get('success') for item in passes):
            raise ValueError('A completed plan requires every inner optimizer pass to succeed.')
        report['solver']['all_inner_optimizer_passes_succeeded'] = True
        report['solver']['normalization'] = report['configuration']['inner_optimization']
        save('initial-solver-result.json', {'plan_kind': 'initial', 'provenance': provenance,
             'assignments': dict(zip(geoids, labels, strict=True)), 'centers': centers})
        del units
        with progress.phase('audit_initial_plan'):
            report['initial_plan'] = audit_plan(labels, populations, geoids, physical, augmented, n_districts)
            if report['initial_plan']['district_populations'] != report['solver']['population_balance']['district_populations']:
                raise ValueError('Initial population reconciliation failed.')
        with progress.phase('repair_and_rebalance'):
            corrected = repair_and_rebalance(adjacency, labels, populations, n_districts=n_districts,
                                             max_moves=max_moves, part_graph=augmented)
        with progress.phase('save_and_audit_final_plan'):
            for stage, stage_labels in [('after_repair', corrected.repaired_assignments), ('final', corrected.assignments)]:
                metrics = audit_plan(stage_labels, populations, geoids, physical, augmented, n_districts)
                if not metrics['all_districts_policy_connected']:
                    raise ValueError(f'{stage} failed the recorded-policy part graph audit.')
                report[f'{stage}_plan'] = metrics
                save('solver-result.json' if stage == 'final' else 'after-repair-result.json', {
                    'plan_kind': stage, 'provenance': provenance,
                    'assignments': dict(zip(geoids, stage_labels, strict=True)),
                    'initial_power_centers_for_provenance_only': centers})
            def moves(items: Any) -> list[dict[str, Any]]:
                return [{**asdict(move), 'geoids': [geoids[i] for i in move.units]} for move in items]
            save('move-audit.json', {'provenance': provenance, 'stop_reason': corrected.stop_reason,
                 'repair_moves': moves(corrected.repair_moves), 'part_repair_moves': moves(corrected.part_repair_moves),
                 'rebalance_moves': moves(corrected.rebalance_moves)})
            report['postprocessing'] = {'stop_reason': corrected.stop_reason,
                'repair_move_count': len(corrected.repair_moves), 'part_repair_move_count': len(corrected.part_repair_moves),
                'rebalance_move_count': len(corrected.rebalance_moves)}
        with progress.phase('independent_polygon_validation_and_map_export'):
            manifest = export_state_block_maps(source, dict(zip(geoids, corrected.assignments, strict=True)),
                population_map, output / 'maps', state_fips='12', state_name='Florida',
                n_districts=n_districts, water_connections=connections)
            report['maps'] = manifest
            if (not manifest['connectivity_validation']['passed']
                    or manifest['connectivity_validation']['policy'] != POLICY):
                raise ValueError('Independent polygon and water-connection validation failed.')
            report['artifact_sha256']['maps/map-manifest.json'] = sha256(output / 'maps/map-manifest.json')
        with progress.phase('write_viewer_and_verify_preservation'):
            if protected_inventory() != before:
                raise ValueError('Preserved strict artifacts or source archive changed.')
            if any(sha256(ROOT / name) != expected for name, expected in report['code_sha256'].items()):
                raise ValueError('Run source code changed after its starting provenance snapshot.')
            write_viewer(output, report)
            report['artifact_sha256']['index.html'] = sha256(output / 'index.html')
            report['preservation_audit'] = {'all_original_strict_files_byte_identical': True,
                'national_suite_byte_identical': True, 'source_archive_byte_identical': True,
                'run_code_unchanged': True, 'protected_file_count': len(before)}
            report['preservation_audit'].update(
                all_original_diagnostic_files_byte_identical=True,
            )
        report['status'] = 'complete_under_island_water_policy'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = f'{type(error).__name__}: {error}'
        report['failed_phase'] = report.get('active_phase')
        if isinstance(error, DistrictingOptimizationError):
            report['optimizer_failure'] = {
                'reason': error.reason, 'status': error.status, 'message': error.optimizer_message,
                'iterations': error.iterations, 'function_evaluations': error.function_evaluations,
                'balance_pass': len(report['solver_progress']),
                'plan_returned': False,
            }
        raise
    finally:
        if 'preservation_audit' not in report:
            try:
                unchanged = before is not None and protected_inventory() == before
                code_unchanged = bool(report['code_sha256']) and all(
                    sha256(ROOT / name) == expected for name, expected in report['code_sha256'].items())
                report['preservation_audit'] = {
                    'all_original_strict_files_byte_identical': unchanged,
                    'all_original_diagnostic_files_byte_identical': unchanged,
                    'national_suite_byte_identical': unchanged,
                    'source_archive_byte_identical': unchanged,
                    'run_code_unchanged': code_unchanged,
                    'preservation_snapshot_completed': before is not None,
                    'protected_file_count': len(before) if before is not None else 0,
                }
                if before is not None and (not unchanged or not code_unchanged):
                    report['preservation_error'] = 'Original evidence or run code changed during this failed attempt.'
            except Exception as preservation_error:
                report['preservation_error'] = f'{type(preservation_error).__name__}: {preservation_error}'
        report['timed_pipeline_wall_seconds'] = time.perf_counter() - started
        report['peak_process_working_set_bytes'] = process_memory()[1]
        report['phases'] = dict(measurements.phases)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['active_phase'] = None
        report['final_progress_snapshot_written'] = False
        try:
            progress.close()
            report['final_progress_snapshot_written'] = True
        except OSError as error:
            # A failed display heartbeat must not suppress the authoritative
            # terminal report or memory sampler cleanup after completed work.
            progress.errors.append(f'Final progress write: {type(error).__name__}: {error}')
        finally:
            measurements.close()
        report['progress_write_errors'] = list(progress.errors)
        terminal_path = write_terminal_report(output, report)
        print(f'Report: {terminal_path}', flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--district-count', type=int, required=True, choices=COUNTS)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.district_count, args.output)


if __name__ == '__main__':
    main()
