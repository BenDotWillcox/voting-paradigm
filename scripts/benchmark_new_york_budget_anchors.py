"""Controlled New York K35/K42/K61 reruns with a 1,000-iteration inner budget.

The failed 300-iteration attempt and its complete evidence tree are immutable.
Only the inner iteration limit changes; observational tracing adds no objective
calls or stopping rules. Every run refuses an existing output directory.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import threading
import time
from typing import Any

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
from scripts.benchmark_state_blocks import house_links
from scripts.correct_state_block_parts import block_adjacency, write_json
from scripts.new_york_recorded_links import build_new_york_connections
from scripts.district_block_part_graph import load_or_build_shared_edge_part_graph
from scripts.district_block_sources import load_units, prepare_source
from scripts.state_block_execution_lock import state_execution_lock
from scripts.district_optimizer_trace import trace_optimizer
from scripts.state_block_map_export import export_state_block_maps

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
POLICY = 'shared_edges_plus_recorded_mixed_connections'
INNER_ITERATION_LIMIT = 1000
COUNTS = (35, 42, 61)
BASELINE_REPORT_SHA256 = {
    35: '4336e1bda980a413fe280f1a8907a6337638f2743f7257cd20e5c4d46db621dd',
    42: '4c401a542d90f88e0070c88a7dd63b8d1ccbb0bd4113276803cdc20a933d4c45',
    61: 'fd1bf5e38f699181c04c8e76c7e18fc1de813575864d5be13dff7e92d4365be5',
}
K26_REPORT_SHA256 = '6332da0dbe1f8fd202a6f281267407876ed458bed3806a482e3aeca46292b36b'
BASELINE_INVENTORY_SHA256 = '3fd3f2e1e5f89baec9fb5c18b0b476b7063b4a32f0fad451d8fb797bc0179bef'
EXTRA_CODE = ('scripts/benchmark_new_york_budget_anchors.py', 'scripts/run_new_york_budget_anchors.py')


def baseline_directory(n_districts: int) -> Path:
    if n_districts not in COUNTS:
        raise ValueError('Only New York K35/K42/K61 are authorized for this suite.')
    return SUITE / f'policies/new-york-links-v1/states/36/districts-{n_districts}'


def reference_directory() -> Path:
    return SUITE / 'corrections/new-york-inner-budget-v1/states/36/districts-26'


def load_strict_baseline(n_districts: int) -> dict[str, Any]:
    """Resolve each strict job's reused topology evidence before creating output."""
    if n_districts not in COUNTS:
        raise ValueError('Only New York K35/K42/K61 are authorized for this suite.')
    suite_path = SUITE / 'suite.json'
    suite = json.loads(suite_path.read_text(encoding='utf-8'))
    states = [state for state in suite['states'] if state['state_fips'] == '36']
    if len(states) != 1:
        raise ValueError('The preserved suite must contain exactly one New York state entry.')
    jobs = [job for job in states[0]['jobs'] if job['district_count'] == n_districts]
    if (len(jobs) != 1 or jobs[0]['status'] != 'unsupported_topology'
            or jobs[0].get('topology_report') != 'states/36/districts-26/benchmark.json'):
        raise ValueError('Expected the matching strict job to reuse the original K26 topology exception.')
    path = (SUITE / jobs[0]['topology_report']).resolve()
    if not path.is_relative_to(SUITE.resolve()):
        raise ValueError('Strict topology evidence escaped the preserved suite.')
    strict = json.loads(path.read_text(encoding='utf-8'))
    if (strict['state_fips'] != '36' or strict['district_count'] != 26
            or strict['status'] != 'unsupported_topology'):
        raise ValueError('The original strict source-preflight report does not match its manifest reference.')
    return {
        'strict_report_path': path.relative_to(ROOT).as_posix(),
        'strict_report_sha256': sha256(path), 'strict_preflight_reused': True,
        'strict_suite_path': suite_path.relative_to(ROOT).as_posix(),
        'strict_suite_sha256': sha256(suite_path), 'strict_suite_job': deepcopy(jobs[0]),
        'strict_solver_ran': False,
    }


def load_reference() -> dict[str, Any]:
    path = reference_directory() / 'benchmark.json'
    if sha256(path) != K26_REPORT_SHA256:
        raise ValueError('Completed K26 reference report changed.')
    reference = json.loads(path.read_text(encoding='utf-8'))
    if reference['status'] != 'complete_under_recorded_mixed_policy' or len(reference['code_sha256']) != 25:
        raise ValueError('Expected the preserved complete K26 reference and its 25 frozen source files.')
    for name, expected in reference['code_sha256'].items():
        if sha256(ROOT / name) != expected:
            raise ValueError(f'Completed K26 frozen code changed: {name}')
    return reference


def load_baseline(n_districts: int) -> dict[str, Any]:
    """Pin the actual failed attempt, its 23 source files and original inventory."""
    path = baseline_directory(n_districts) / 'benchmark.json'
    if sha256(path) != BASELINE_REPORT_SHA256[n_districts]:
        raise ValueError('Preserved failed New York baseline report changed.')
    baseline = json.loads(path.read_text(encoding='utf-8'))
    if (baseline['status'] != 'failed' or baseline['failed_phase'] != 'solve'
            or baseline['district_count'] != n_districts
            or baseline['optimizer_failure']['iterations'] != 300
            or baseline['optimizer_failure']['balance_pass'] != (1 if n_districts == 61 else 2)
            or baseline['optimizer_failure']['plan_returned'] is not False
            or baseline['configuration']['inner_max_iterations'] != 300):
        raise ValueError('Expected the matching failed New York inner-300 baseline.')
    if len(baseline['code_sha256']) != 23:
        raise ValueError('Expected all 23 frozen pipeline source hashes.')
    for name, expected in baseline['code_sha256'].items():
        if sha256(ROOT / name) != expected:
            raise ValueError(f'Frozen baseline code changed: {name}')
    if baseline['environment']['python'] != sys.version:
        raise ValueError('Python runtime differs from the failed baseline.')
    current_packages = {name: version(name) for name in ('numpy', 'scipy', 'pyshp', 'shapely')}
    if baseline['environment']['packages'] != current_packages:
        raise ValueError('Numerical or geometry package versions differ from the failed baseline.')
    path = baseline_directory(n_districts) / 'preserved-file-inventory.json'
    if sha256(path) != BASELINE_INVENTORY_SHA256:
        raise ValueError('Original 1,052-file preservation inventory changed.')
    original = json.loads(path.read_text(encoding='utf-8'))
    if len(original) != 1052:
        raise ValueError('Expected all 1,052 original protected files.')
    for name, expected in original.items():
        if sha256(ROOT / name) != expected:
            raise ValueError(f'Original protected evidence changed: {name}')
    reference = load_reference()
    if any(reference['code_sha256'].get(name) != digest for name, digest in baseline['code_sha256'].items()):
        raise ValueError('Original failed and completed K26 pipeline source hashes differ.')
    load_strict_baseline(n_districts)
    return baseline


def protected_inventory() -> dict[str, str]:
    """Protect historical strict, failed policy and completed K26 evidence."""
    original = json.loads((baseline_directory(35) / 'preserved-file-inventory.json').read_text(encoding='utf-8'))
    paths = {ROOT / name for name in original}
    paths.update(path for path in (SUITE / 'policies/new-york-links-v1').rglob('*') if path.is_file())
    paths.update(path for path in (SUITE / 'corrections/new-york-inner-budget-v1').rglob('*') if path.is_file())
    paths.update(path for path in (ROOT / 'prompts').glob('new-york-links*') if path.is_file())
    for suffix in ('.md', '.json'):
        path = ROOT / ('prompts/new-york-inner-budget-benchmark' + suffix)
        if not path.is_file():
            raise ValueError('The completed K26 durable report is missing.')
        paths.add(path)
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(paths)}


def configuration_for_experiment(baseline: dict[str, Any]) -> dict[str, Any]:
    configuration = deepcopy(baseline['configuration'])
    if (configuration['seed'] != SEED
            or configuration['max_outer_iterations'] != OUTER_ITERATION_LIMIT
            or configuration['max_rebalance_moves'] != 1000
            or configuration['center_tolerance_m'] != 1e-4
            or configuration['inner_optimization']['max_line_search_steps'] != 100):
        raise ValueError('Fixed baseline solver settings differ from the preserved pipeline.')
    configuration['inner_max_iterations'] = INNER_ITERATION_LIMIT
    return configuration


def validate_output(output: Path, n_districts: int) -> None:
    expected = (SUITE / f'corrections/new-york-inner-budget-anchors-v1/states/36/districts-{n_districts}').resolve()
    if n_districts not in COUNTS or output.resolve() != expected:
        raise ValueError('Output must be the matching new anchor run below corrections/new-york-inner-budget-anchors-v1.')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Output must be absent or empty; earlier attempts are preserved.')


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
            'status': self.report['status'],
            'active_phase': self.measurements.active if self.report['status'] == 'running' else None,
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
    template = (ROOT / 'scripts/assets/new-york-block-viewer.html').read_text(encoding='utf-8')
    projection = report['input']['projection']
    k = report['district_count']
    replacements = {
        '__STATE_NAME__': 'New York', '__DISTRICT_COUNT__': str(k),
        '__RESULT_SUMMARY__': (
            f'{k} districts; inner iteration budget 1,000; connected under the recorded water-and-exclave policy. '
            f'Maximum population deviation {report["final_plan"]["max_absolute_deviation_percent"]:.6f}%. '
            'Liberty uses a recorded water link; Ellis uses an exclave link across New Jersey land and water. '
            'Original strict and failed 300-iteration results preserved.'),
        '__ANCHOR_NAVIGATION__': '<a href="../../../">Iteration-budget comparison</a> '
            '<a href="../../../../new-york-inner-budget-v1/states/36/districts-26/">Completed K26 reference</a> '
            '<a href="../../../../../policies/new-york-links-v1/">Original failed attempts</a> '
            '<a href="../../../../../diagnostics/new-york/">Original diagnosis</a>',
        '__LON0__': str(projection['lon0']), '__LAT0__': str(projection['lat0']),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    (output / 'index.html').write_text(template, encoding='utf-8')


def run(n_districts: int, output: Path, *, max_moves: int = 1000) -> dict[str, Any]:
    if n_districts not in COUNTS or max_moves != 1000:
        raise ValueError('This controlled experiment requires K35/K42/K61 and unchanged 1,000 rebalance moves.')
    output = output.resolve()
    validate_output(output, n_districts)
    with state_execution_lock('36'):
        return _run_locked(n_districts, output, max_moves)


def _run_locked(n_districts: int, output: Path, max_moves: int) -> dict[str, Any]:
    baseline = load_baseline(n_districts)
    reference = load_reference()
    strict_baseline = load_strict_baseline(n_districts)
    configuration = configuration_for_experiment(baseline)
    before = protected_inventory()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'preserved-file-inventory.json', before)
    measurements = Measurements()
    started = time.perf_counter()
    report: dict[str, Any] = {
        'status': 'running', 'run_kind': 'new_york_inner_budget_anchors_experiment_v1',
        'state': 'New York', 'state_fips': '36', 'district_count': n_districts,
        'house_sizes': house_links('36', n_districts, (435, 574, 692, 1000)),
        'source_year': 2020, 'unit': 'census_block', 'policy': POLICY,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'configuration': configuration,
        'controlled_changes': {'inner_max_iterations': {'before': 300, 'after': 1000}},
        'code_sha256': {**reference['code_sha256'], **{name: sha256(ROOT / name) for name in EXTRA_CODE}},
        'solver_progress': [], 'artifacts': {}, 'artifact_sha256': {},
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'packages': {name: version(name) for name in ('numpy', 'scipy', 'pyshp', 'shapely')}},
        'measurement_notes': [
            f'Controlled K{n_districts} rerun: only the inner iteration budget changes from 300 to 1,000; unchanged normalized optimizer, tolerances, seed, outer budget, connection records, and postprocessing.',
            'Observational accepted-iteration tracing adds callback and JSONL I/O overhead, reported separately; runtime is not a budget-only isolated hardware comparison.',
            'Source archive and physical part graph are already cached; cache hits and preparation phases remain measured.',
            'Runs execute serially; shared-desktop timings are not isolated hardware measurements.',
            'Timed pipeline excludes imports, initial preservation inventory, and final report flush; the suite launcher separately measures child wall time.',
            'Original strict run rejected topology before solving. Its elapsed time is not a strict-solver baseline.',
            'Policy connectivity and physical polygon connectivity are reported separately. Liberty uses a water link; Ellis uses an exclave link crossing New Jersey land and water. No source polygon is changed and no New Jersey territory is assigned.',
            'Population quality is an independently measured outcome; whole-block local rebalancing need not attain the global optimum.',
        ],
    }
    diagnosis = SUITE / 'diagnostics/new-york/diagnosis.json'
    report['comparison_baseline'] = {
        **strict_baseline,
        'diagnosis_path': diagnosis.relative_to(ROOT).as_posix(),
        'diagnosis_sha256': sha256(diagnosis),
        'note': f'The original strict K{n_districts} manifest job reused K26 source-preflight topology rejection without running a solver or writing a separate benchmark. The matching mixed-policy K{n_districts} baseline failed at 300 inner iterations. Neither returned a completed district plan.',
        'failed_policy_report_path': (baseline_directory(n_districts) / 'benchmark.json').relative_to(ROOT).as_posix(),
        'failed_policy_report_sha256': BASELINE_REPORT_SHA256[n_districts],
        'failed_policy_status': baseline['status'],
        'failed_policy_pipeline_wall_seconds': baseline['timed_pipeline_wall_seconds'],
        'failed_policy_solver_progress': baseline['solver_progress'],
        'failed_policy_optimizer_failure': baseline['optimizer_failure'],
        'all_23_original_code_hashes_unchanged': True,
        'configuration_difference': {'inner_max_iterations': {'before': 300, 'after': 1000}},
    }
    report['completed_k26_reference'] = {
        'report_path': (reference_directory() / 'benchmark.json').relative_to(ROOT).as_posix(),
        'report_sha256': K26_REPORT_SHA256, 'reused_without_rerun': True,
        'original_pipeline_wall_seconds': reference['timed_pipeline_wall_seconds'],
        'note': 'Previously completed K26 reference only; its original runtime is reused, not measured in this suite.',
    }
    progress = Progress(output, report, measurements)
    def save(name: str, value: Any) -> None:
        write_json(output / name, value)
        report['artifacts'][name] = name
        report['artifact_sha256'][name] = sha256(output / name)
    try:
        source, report['source'] = prepare_source('36', ROOT / '.cache/state-block-benchmark/source/36', measurements)
        if report['source']['archive_sha256'] != before['.cache/state-block-benchmark/source/36/tl_2020_36_tabblock20.zip']:
            raise ValueError('Source archive identity changed.')
        with progress.phase('load_and_validate_blocks'):
            units, population_map, report['input'] = load_units(source, '36')
            geoids = [unit.geoid for unit in units]
            populations = [unit.population for unit in units]
        with progress.phase('load_or_build_physical_part_graph'):
            physical, report['physical_part_graph'], report['physical_part_graph_cache'] = load_or_build_shared_edge_part_graph(
                source, geoids, source_sha256=report['source']['archive_sha256'],
                cache_dir=ROOT / '.cache/state-block-benchmark/graph-cache/36')
        with progress.phase('prepare_recorded_mixed_connections'):
            augmented, connections, report['recorded_policy_audit'] = build_new_york_connections(
                source, geoids, populations, physical, district_count=n_districts)
            if part_component_counts(augmented, [0] * len(geoids), n_districts=1) != (1,):
                raise ValueError('New York mixed-link policy must yield one connected source graph.')
            save('recorded-connections.json', {'policy': POLICY, 'connections': list(connections),
                                          'source_sha256': report['source']['archive_sha256']})
            report['recorded_connections'] = list(connections)
            if (report['recorded_connections'] != baseline['recorded_connections']
                    or report['artifact_sha256']['recorded-connections.json'] != baseline['artifact_sha256']['recorded-connections.json']):
                raise ValueError('Recorded connections differ from the failed baseline.')
            report['recorded_connections_byte_identical_to_baseline'] = True
            adjacency = block_adjacency(augmented, len(geoids))
        provenance = {'source_sha256': report['source']['archive_sha256'],
                      'code_sha256': report['code_sha256'], 'configuration': report['configuration'],
                      'recorded_connections_sha256': report['artifact_sha256']['recorded-connections.json']}
        with progress.phase('solve'):
            trace = None
            try:
                with trace_optimizer(output / 'optimizer-trace.jsonl') as trace:
                    report['solver_progress'] = trace.passes
                    initial = balanced_power_diagram(units, n_districts, seed=SEED,
                        max_outer_iterations=OUTER_ITERATION_LIMIT, inner_max_iterations=INNER_ITERATION_LIMIT)
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
                population_map, output / 'maps', state_fips='36', state_name='New York',
                n_districts=n_districts, recorded_connections=connections)
            report['maps'] = manifest
            if (not manifest['connectivity_validation']['passed']
                    or manifest['connectivity_validation']['policy'] != POLICY):
                raise ValueError('Independent polygon and recorded-connection validation failed.')
            report['artifact_sha256']['maps/map-manifest.json'] = sha256(output / 'maps/map-manifest.json')
        with progress.phase('write_viewer_and_verify_preservation'):
            write_viewer(output, report)
            report['artifact_sha256']['index.html'] = sha256(output / 'index.html')
            if protected_inventory() != before:
                raise ValueError('Preserved strict artifacts or source archive changed.')
            if any(sha256(ROOT / name) != expected for name, expected in report['code_sha256'].items()):
                raise ValueError('Run source code changed after its starting provenance snapshot.')
            report['preservation_audit'] = {'all_original_strict_files_byte_identical': True,
                'national_suite_byte_identical': True, 'source_archive_byte_identical': True,
                'run_code_unchanged': True, 'protected_file_count': len(before)}
            report['preservation_audit'].update(
                all_original_diagnostic_files_byte_identical=True,
                prior_policy_and_correction_evidence_byte_identical=True,
                original_failed_policy_tree_byte_identical=True,
                completed_k26_tree_byte_identical=True,
                baseline_configuration_only_inner_budget_changed=True,
                recorded_connections_byte_identical=report.get('recorded_connections_byte_identical_to_baseline', False),
            )
        report['status'] = 'complete_under_recorded_mixed_policy'
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
                unchanged = protected_inventory() == before
                code_unchanged = all(sha256(ROOT / name) == expected for name, expected in report['code_sha256'].items())
                report['preservation_audit'] = {
                    'all_original_strict_files_byte_identical': unchanged,
                    'all_original_diagnostic_files_byte_identical': unchanged,
                    'national_suite_byte_identical': unchanged,
                    'source_archive_byte_identical': unchanged,
                    'prior_policy_and_correction_evidence_byte_identical': unchanged,
                    'original_failed_policy_tree_byte_identical': unchanged,
                    'completed_k26_tree_byte_identical': unchanged,
                    'baseline_configuration_only_inner_budget_changed': configuration == configuration_for_experiment(baseline),
                    'recorded_connections_byte_identical': report.get('recorded_connections_byte_identical_to_baseline', False),
                    'run_code_unchanged': code_unchanged, 'protected_file_count': len(before),
                }
                if not unchanged or not code_unchanged:
                    report['preservation_error'] = 'Original evidence or run code changed during this failed attempt.'
            except Exception as preservation_error:
                report['preservation_error'] = f'{type(preservation_error).__name__}: {preservation_error}'
        report['timed_pipeline_wall_seconds'] = time.perf_counter() - started
        report['peak_process_working_set_bytes'] = process_memory()[1]
        report['phases'] = dict(measurements.phases)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['active_phase'] = None
        try:
            progress.close()
        except OSError as error:
            # A failed display heartbeat must not suppress the authoritative
            # terminal report or memory sampler cleanup after completed work.
            progress.errors.append(f'Final progress write: {type(error).__name__}: {error}')
        finally:
            measurements.close()
        report['progress_write_errors'] = list(progress.errors)
        write_json(output / 'benchmark.json', report)
        print(f'Report: {output / "benchmark.json"}', flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--district-count', type=int, required=True, choices=COUNTS)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.district_count, args.output)


if __name__ == '__main__':
    main()
