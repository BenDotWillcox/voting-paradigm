"""Run New York plans with explicit Liberty water and Ellis exclave connections.

Fresh attempts live only under policies/new-york-links-v1. Historical strict
exceptions, topology diagnosis, and all prior policy/correction evidence are
hashed and preserved. The source polygons remain unchanged; each conceptual
connection keeps its geographic classification and is never represented as a
physical shared edge.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from fractions import Fraction
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
    INNER_ITERATION_LIMIT, OUTER_ITERATION_LIMIT, SEED,
    observe_solver, population_metrics, stage_metrics,
)
from scripts.benchmark_kansas_blocks import Measurements, process_memory, sha256
from scripts.benchmark_state_blocks import CODE_PATHS, house_links
from scripts.correct_state_block_parts import block_adjacency, write_json
from scripts.new_york_recorded_links import POLICY as LINK_POLICY, build_new_york_connections
from scripts.district_block_part_graph import load_or_build_shared_edge_part_graph
from scripts.district_block_sources import load_units, prepare_source
from scripts.state_block_execution_lock import state_execution_lock
from scripts.state_block_map_export import export_state_block_maps

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
POLICY = 'shared_edges_plus_recorded_mixed_connections'
EXTRA_CODE = (
    'scripts/benchmark_new_york_links.py',
    'scripts/run_new_york_link_suite.py',
    'scripts/new_york_recorded_links.py',
    'scripts/hawaii_population_links.py',
    'scripts/district_block_island_links.py',
    'scripts/correct_state_block_parts.py',
    'scripts/assets/new-york-block-viewer.html',
    'districting/__init__.py',
)


def protected_inventory() -> dict[str, str]:
    """Protect historical evidence trees while excluding this new namespace."""
    required = [SUITE / 'suite.json', SUITE / 'diagnostics/new-york/diagnosis.json',
        SUITE / 'states/36/districts-26/benchmark.json',
        *(ROOT / f'.cache/state-block-benchmark/source/{state}/tl_2020_{state}_tabblock20.zip'
          for state in ('36', '21', '44', '15'))]
    directories = [SUITE / name for name in (
        'states/36', 'states/21', 'states/44', 'states/15',
        'diagnostics/new-york', 'diagnostics/kentucky', 'diagnostics/rhode-island', 'diagnostics/hawaii',
        'policies/island-water-v1', 'policies/hawaii-water-v1', 'policies/kentucky-exclave-v1',
        'corrections/hawaii-optimizer-v1', 'corrections/part-connectivity-v1')]
    if any(not path.is_file() for path in required) or any(not path.is_dir() for path in directories):
        raise ValueError('Required preserved New York and prior policy evidence is missing.')
    paths = set(required)
    for directory in directories:
        paths.update(path for path in directory.rglob('*') if path.is_file())
    for pattern in ('hawaii*', 'rhode-island*', 'kentucky*', 'new-york-topology*', 'maryland-virginia*'):
        paths.update(path for path in (ROOT / 'prompts').glob(pattern) if path.is_file())
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(paths)}


def validate_output(output: Path, n_districts: int) -> None:
    expected = (SUITE / f'policies/new-york-links-v1/states/36/districts-{n_districts}').resolve()
    if output.resolve() != expected:
        raise ValueError('Output must be the matching new run below policies/new-york-links-v1/states/36.')
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
            'status': self.report['status'], 'active_phase': self.measurements.active,
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
            f'{k} districts connected under the recorded water-and-exclave policy. '
            f'Maximum population deviation {report["final_plan"]["max_absolute_deviation_percent"]:.6f}%. '
            'Liberty uses a recorded water link; Ellis uses an exclave link across New Jersey land and water. '
            'Original strict results preserved.'),
        '__ANCHOR_NAVIGATION__': '<a href="../../../">Comparison</a> '
            + ' '.join(f'<a href="../districts-{count}/">{count} districts</a>' for count in (26, 35, 42, 61))
            + ' <a href="../../../../../diagnostics/new-york/">Original diagnosis</a>',
        '__LON0__': str(projection['lon0']), '__LAT0__': str(projection['lat0']),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    (output / 'index.html').write_text(template, encoding='utf-8')


def run(n_districts: int, output: Path, *, max_moves: int = 1000) -> dict[str, Any]:
    if n_districts not in (26, 35, 42, 61) or max_moves < 0:
        raise ValueError('This benchmark supports New York K26/K35/K42/K61 with nonnegative max_moves.')
    output = output.resolve()
    validate_output(output, n_districts)
    with state_execution_lock('36'):
        return _run_locked(n_districts, output, max_moves)


def _run_locked(n_districts: int, output: Path, max_moves: int) -> dict[str, Any]:
    before = protected_inventory()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'preserved-file-inventory.json', before)
    ideal = Fraction(20201249, n_districts)
    # Population budget guides root retention and connection choices only.
    # Actual final deviations are measured independently of this preflight.
    minimum = ideal * Fraction(99, 100)
    measurements = Measurements()
    started = time.perf_counter()
    report: dict[str, Any] = {
        'status': 'running', 'run_kind': 'new_york_recorded_mixed_policy_v1',
        'state': 'New York', 'state_fips': '36', 'district_count': n_districts,
        'house_sizes': house_links('36', n_districts, (435, 574, 692, 1000)),
        'source_year': 2020, 'unit': 'census_block', 'policy': POLICY,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'configuration': {
            'seed': SEED, 'max_outer_iterations': OUTER_ITERATION_LIMIT,
            'inner_max_iterations': INNER_ITERATION_LIMIT, 'center_tolerance_m': 1e-4,
            'physical_adjacency_rule': 'polygon parts; disjoint interiors; positive-length shared boundary; F***1****',
            'connection_policy': LINK_POLICY,
            'connection_kinds': ['recorded-water-connection', 'recorded-exclave-connection'],
            'max_rebalance_moves': max_moves, 'root_eligibility_relative_band': 0.01,
            'group_population_preflight_tolerance': 0.01,
            'minimum_district_population_for_root_classification': float(minimum),
            'minimum_district_population_exact': str(minimum),
            'eligibility_note': '99% of ideal classifies original eligible roots; root groups must admit integer district allocations within a 1% optimistic population budget. Neither is final-plan acceptance.',
            'boundary_metric': 'source census coverage, including retained water blocks; no shoreline substitution',
        },
        'code_sha256': {name: sha256(ROOT / name) for name in (*CODE_PATHS, *EXTRA_CODE)},
        'solver_progress': [], 'artifacts': {}, 'artifact_sha256': {},
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'packages': {name: version(name) for name in ('numpy', 'scipy', 'pyshp', 'shapely')}},
        'measurement_notes': [
            'Full new run with the fixed normalized optimizer and explicit failure handling, fresh process for each district count.',
            'Source archive and physical part graph are already cached; cache hits and preparation phases remain measured.',
            'Runs execute serially; shared-desktop timings are not isolated hardware measurements.',
            'Timed pipeline excludes imports, initial preservation inventory, and final report flush; the suite launcher separately measures child wall time.',
            'Original strict run rejected topology before solving. Its elapsed time is not a strict-solver baseline.',
            'Policy connectivity and physical polygon connectivity are reported separately. Liberty uses a water link; Ellis uses an exclave link crossing New Jersey land and water. No source polygon is changed and no New Jersey territory is assigned.',
            'Population quality is an independently measured outcome; whole-block local rebalancing need not attain the global optimum.',
        ],
    }
    report['configuration']['inner_optimization'] = {
        'normalization': 'population-mass and geometry-derived shifted squared costs; mean-zero weight gauge',
        'public_units': 'centers in source coordinate units; weights in squared source coordinate units',
        'max_line_search_steps': 100,
        'failure_policy': 'raise on unsuccessful termination or nonfinite output; no completed plan returned',
    }
    strict = SUITE / 'states/36/districts-26/benchmark.json'
    diagnosis = SUITE / 'diagnostics/new-york/diagnosis.json'
    report['comparison_baseline'] = {
        'strict_report_path': strict.relative_to(ROOT).as_posix(),
        'strict_report_sha256': sha256(strict),
        'diagnosis_path': diagnosis.relative_to(ROOT).as_posix(),
        'diagnosis_sha256': sha256(diagnosis),
        'strict_solver_ran': False,
        'note': 'K26 rejected disconnected topology; K35/K42/K61 reused that exception without solving.',
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
            adjacency = block_adjacency(augmented, len(geoids))
        provenance = {'source_sha256': report['source']['archive_sha256'],
                      'code_sha256': report['code_sha256'], 'configuration': report['configuration'],
                      'recorded_connections_sha256': report['artifact_sha256']['recorded-connections.json']}
        with progress.phase('solve'):
            with observe_solver(report['solver_progress']):
                initial = balanced_power_diagram(units, n_districts, seed=SEED,
                    max_outer_iterations=OUTER_ITERATION_LIMIT, inner_max_iterations=INNER_ITERATION_LIMIT)
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
    parser.add_argument('--district-count', type=int, required=True, choices=(26, 35, 42, 61))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-moves', type=int, default=1000)
    args = parser.parse_args()
    run(args.district_count, args.output, max_moves=args.max_moves)


if __name__ == '__main__':
    main()
