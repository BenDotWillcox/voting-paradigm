"""Run new Hawaii block plans with population-aware island connections.

Original strict exceptions and diagnostic witnesses remain immutable. Each K
runs in a fresh process and output directory; this entry point never resumes or
rewrites historical suite status. A correction profile preserves the original
water-policy runs while exercising the normalized numerical solver.
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
from scripts.hawaii_population_links import build_hawaii_connections
from scripts.district_block_part_graph import load_or_build_shared_edge_part_graph
from scripts.district_block_sources import load_units, prepare_source
from scripts.state_block_execution_lock import state_execution_lock
from scripts.state_block_map_export import export_state_block_maps

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
POLICY = 'shared_edges_plus_recorded_water_connections'
EXTRA_CODE = (
    'scripts/benchmark_hawaii_water.py',
    'scripts/hawaii_population_links.py',
    'scripts/district_block_island_links.py',
    'scripts/correct_state_block_parts.py',
    'scripts/diagnose_hawaii_topology.py',
    'scripts/assets/hawaii-block-viewer.html',
)


def protected_inventory(*, optimizer_correction: bool = False, district_count: int = 2) -> dict[str, str]:
    """Snapshot strict runs, national manifest, diagnosis and source archive."""
    paths = [SUITE / 'suite.json', SUITE / 'diagnostics/hawaii/diagnosis.json',
             SUITE / 'diagnostics/hawaii/components.geojson',
             SUITE / 'diagnostics/hawaii/links.geojson',
             ROOT / '.cache/state-block-benchmark/source/15/tl_2020_15_tabblock20.zip']
    for directory in [SUITE / 'states/15']:
        paths.extend(path for path in directory.rglob('*') if path.is_file())
    if optimizer_correction:
        original = SUITE / 'policies/hawaii-water-v1'
        if not (original / 'states/15/districts-2/benchmark.json').is_file():
            raise ValueError('The original Hawaii water-policy run must exist.')
        paths.extend(path for path in original.rglob('*') if path.is_file())
        paths.extend(ROOT / f'prompts/hawaii-water-benchmark.{suffix}' for suffix in ('md', 'json'))
        if district_count != 2:
            prior = SUITE / 'corrections/hawaii-optimizer-v1'
            paths.extend(path for path in (prior / 'states/15/districts-2').rglob('*') if path.is_file())
            paths.extend(path for path in (prior / 'baseline-code').rglob('*') if path.is_file())
            paths.extend(prior / name for name in ('index.html', 'comparison.json', 'districts-2.log', 'hawaii-corrected-map.png'))
            paths.extend(ROOT / f'prompts/hawaii-optimizer-fix.{suffix}' for suffix in ('md', 'json'))
    if any(not path.is_file() for path in paths):
        raise ValueError('Required preserved strict evidence is missing.')
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(set(paths))}


def validate_output(output: Path, *, optimizer_correction: bool = False) -> None:
    namespace = 'corrections/hawaii-optimizer-v1' if optimizer_correction else 'policies/hawaii-water-v1'
    owned = (SUITE / namespace / 'states/15').resolve()
    if not output.is_relative_to(owned) or output == owned:
        raise ValueError(f'Output must be a new run below {namespace}/states/15.')
    if output.exists() and any(output.iterdir()):
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
    template = (ROOT / 'scripts/assets/hawaii-block-viewer.html').read_text(encoding='utf-8')
    projection = report['input']['projection']
    k = report['district_count']
    replacements = {
        '__STATE_NAME__': 'Hawaii', '__DISTRICT_COUNT__': str(k),
        '__RESULT_SUMMARY__': (
            f'{k} districts connected under the recorded water-link policy. '
            f'Maximum population deviation {report["final_plan"]["max_absolute_deviation_percent"]:.6f}%. '
            'Physical polygons remain separate across water. Original strict results preserved.'),
        '__ANCHOR_NAVIGATION__': '<a href="../../../">Comparison</a> <a href="../districts-2/">2 districts</a> '
                                 '<a href="../districts-3/">3 districts</a> '
                                 '<a href="../districts-4/">4 districts</a> '
                                 '<a href="../../../../../diagnostics/hawaii/">Original diagnosis</a>',
        '__LON0__': str(projection['lon0']), '__LAT0__': str(projection['lat0']),
    }
    if report['run_kind'] == 'hawaii_optimizer_scaling_correction_v1':
        replacements['__RESULT_SUMMARY__'] += f' Original {k}-district water-policy run also preserved.'
        comparison = '../../../' if k == 2 else '../../../anchors-3-4/'
        replacements['__ANCHOR_NAVIGATION__'] = (
            f'<a href="{comparison}">Before / after comparison</a> '
            f'<a href="../../../../../policies/hawaii-water-v1/states/15/districts-{k}/">Original {k}-district map</a> '
            '<a href="../../../../../diagnostics/hawaii/">Original topology diagnosis</a>'
        )
    for key, value in replacements.items():
        template = template.replace(key, value)
    (output / 'index.html').write_text(template, encoding='utf-8')


def run(n_districts: int, output: Path, *, max_moves: int = 1000,
        optimizer_correction: bool = False) -> dict[str, Any]:
    if n_districts not in (2, 3, 4) or max_moves < 0:
        raise ValueError('This benchmark supports Hawaii K2/K3/K4 with nonnegative max_moves.')
    output = output.resolve()
    validate_output(output, optimizer_correction=optimizer_correction)
    with state_execution_lock('15'):
        return _run_locked(n_districts, output, max_moves, optimizer_correction=optimizer_correction)


def _run_locked(n_districts: int, output: Path, max_moves: int, *,
                optimizer_correction: bool = False) -> dict[str, Any]:
    before = protected_inventory(optimizer_correction=optimizer_correction, district_count=n_districts)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'preserved-file-inventory.json', before)
    ideal = Fraction(1455271, n_districts)
    # Population budget guides root retention and connection choices only.
    # Actual final deviations are measured independently of this preflight.
    minimum = ideal * Fraction(99, 100)
    measurements = Measurements()
    started = time.perf_counter()
    report: dict[str, Any] = {
        'status': 'running', 'run_kind': ('hawaii_optimizer_scaling_correction_v1'
            if optimizer_correction else 'hawaii_population_aware_water_policy_v1'),
        'state': 'Hawaii', 'state_fips': '15', 'district_count': n_districts,
        'house_sizes': house_links('15', n_districts, (435, 574, 692, 1000)),
        'source_year': 2020, 'unit': 'census_block', 'policy': POLICY,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'configuration': {
            'seed': SEED, 'max_outer_iterations': OUTER_ITERATION_LIMIT,
            'inner_max_iterations': INNER_ITERATION_LIMIT, 'center_tolerance_m': 1e-4,
            'max_rebalance_moves': max_moves, 'island_eligibility_relative_band': 0.01,
            'island_population_preflight_tolerance': 0.01,
            'minimum_district_population_for_island_classification': float(minimum),
            'minimum_district_population_exact': str(minimum),
            'eligibility_note': '99% of ideal classifies original eligible roots; root groups must admit integer district allocations within a 1% optimistic population budget. Neither is final-plan acceptance.',
            'boundary_metric': 'source census coverage, including retained water blocks; no shoreline substitution',
        },
        'code_sha256': {name: sha256(ROOT / name) for name in (*CODE_PATHS, *EXTRA_CODE)},
        'solver_progress': [], 'artifacts': {}, 'artifact_sha256': {},
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'packages': {name: version(name) for name in ('numpy', 'scipy', 'pyshp', 'shapely')}},
        'measurement_notes': [
            'Full new run, unchanged numerical solver settings, fresh process for each district count.',
            'Source archive and physical part graph are already cached; cache hits and preparation phases remain measured.',
            'Runs execute serially; shared-desktop timings are not isolated hardware measurements.',
            'Original strict run rejected topology before solving. Its elapsed time is not a strict-solver baseline.',
            'Policy connectivity and physical polygon connectivity are reported separately. No source polygon is stretched or joined across water.',
            'Population quality is an independently measured outcome; whole-block local rebalancing need not attain the global optimum.',
        ],
    }
    if optimizer_correction:
        original_path = SUITE / f'policies/hawaii-water-v1/states/15/districts-{n_districts}/benchmark.json'
        original = json.loads(original_path.read_text(encoding='utf-8'))
        if original.get('state_fips') != '15' or original.get('district_count') != n_districts:
            raise ValueError('Original benchmark does not match this Hawaii district count.')
        report['comparison_baseline'] = {
            'benchmark_path': original_path.relative_to(ROOT).as_posix(),
            'benchmark_sha256': sha256(original_path),
            'water_connections_sha256': original['artifact_sha256']['water-connections.json'],
        }
        report['preserved_baseline_code'] = {}
        for name in ('districting/algorithm.py', 'scripts/benchmark_hawaii_water.py'):
            snapshot = SUITE / 'corrections/hawaii-optimizer-v1/baseline-code' / name
            if sha256(snapshot) != original['code_sha256'][name]:
                raise ValueError(f'Original code snapshot does not match the original benchmark: {name}')
            report['preserved_baseline_code'][name] = {
                'path': snapshot.relative_to(ROOT).as_posix(), 'sha256': sha256(snapshot),
            }
        report['code_sha256']['scripts/benchmark_hawaii_optimizer.py'] = sha256(ROOT / 'scripts/benchmark_hawaii_optimizer.py')
        report['code_sha256']['districting/__init__.py'] = sha256(ROOT / 'districting/__init__.py')
        report['configuration']['inner_optimization'] = {
            'normalization': 'population-mass and geometry-derived shifted squared costs; mean-zero weight gauge',
            'public_units': 'centers in source coordinate units; weights in squared source coordinate units',
            'max_line_search_steps': 100,
            'failure_policy': 'raise on unsuccessful termination or nonfinite output; no completed plan returned',
        }
        report['measurement_notes'][0] = ('Fresh run with normalized inner optimization and explicit failure handling; '
            f'seed, outer/inner iteration budgets, water policy and postprocessing settings match the original K{n_districts} run.')
    progress = Progress(output, report, measurements)
    def save(name: str, value: Any) -> None:
        write_json(output / name, value)
        report['artifacts'][name] = name
        report['artifact_sha256'][name] = sha256(output / name)
    try:
        source, report['source'] = prepare_source('15', ROOT / '.cache/state-block-benchmark/source/15', measurements)
        if report['source']['archive_sha256'] != before['.cache/state-block-benchmark/source/15/tl_2020_15_tabblock20.zip']:
            raise ValueError('Source archive identity changed.')
        with progress.phase('load_and_validate_blocks'):
            units, population_map, report['input'] = load_units(source, '15')
            geoids = [unit.geoid for unit in units]
            populations = [unit.population for unit in units]
        with progress.phase('load_or_build_physical_part_graph'):
            physical, report['physical_part_graph'], report['physical_part_graph_cache'] = load_or_build_shared_edge_part_graph(
                source, geoids, source_sha256=report['source']['archive_sha256'],
                cache_dir=ROOT / '.cache/state-block-benchmark/graph-cache/15')
        with progress.phase('prepare_population_aware_water_connections'):
            augmented, connections, report['island_policy_audit'] = build_hawaii_connections(
                source, geoids, populations, physical, district_count=n_districts,
                population_tolerance=0.01)
            if part_component_counts(augmented, [0] * len(geoids), n_districts=1) != (1,):
                raise ValueError('These Hawaii anchors must yield one connected source graph; disconnected groups require separate allocated solves.')
            save('water-connections.json', {'policy': POLICY, 'connections': list(connections),
                                          'source_sha256': report['source']['archive_sha256']})
            if optimizer_correction and report['artifact_sha256']['water-connections.json'] != report['comparison_baseline']['water_connections_sha256']:
                raise ValueError(f'Water connections changed from the original K{n_districts} policy run.')
            report['water_connections'] = list(connections)
            adjacency = block_adjacency(augmented, len(geoids))
        provenance = {'source_sha256': report['source']['archive_sha256'],
                      'code_sha256': report['code_sha256'], 'configuration': report['configuration'],
                      'water_connections_sha256': report['artifact_sha256']['water-connections.json']}
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
        if optimizer_correction:
            passes = report['solver_progress']
            if not passes or not all(item.get('inner_optimizer', {}).get('success') for item in passes):
                raise ValueError('A correction cannot be accepted after an unsuccessful inner optimizer pass.')
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
                    raise ValueError(f'{stage} failed the water-policy part graph audit.')
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
                population_map, output / 'maps', state_fips='15', state_name='Hawaii',
                n_districts=n_districts, water_connections=connections)
            report['maps'] = manifest
            if not manifest['connectivity_validation']['passed']:
                raise ValueError('Independent polygon and water-connection validation failed.')
            report['artifact_sha256']['maps/map-manifest.json'] = sha256(output / 'maps/map-manifest.json')
        with progress.phase('write_viewer_and_verify_preservation'):
            write_viewer(output, report)
            report['artifact_sha256']['index.html'] = sha256(output / 'index.html')
            if protected_inventory(optimizer_correction=optimizer_correction, district_count=n_districts) != before:
                raise ValueError('Preserved strict artifacts or source archive changed.')
            if any(sha256(ROOT / name) != expected for name, expected in report['code_sha256'].items()):
                raise ValueError('Run source code changed after its starting provenance snapshot.')
            report['preservation_audit'] = {'all_original_strict_files_byte_identical': True,
                'national_suite_byte_identical': True, 'source_archive_byte_identical': True,
                'run_code_unchanged': True, 'protected_file_count': len(before)}
            if optimizer_correction:
                report['preservation_audit'].update(all_original_water_policy_files_byte_identical=True,
                    original_run_bytes_verified=True)
                if n_districts != 2:
                    report['preservation_audit']['prior_k2_correction_byte_identical'] = True
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
    parser.add_argument('--district-count', type=int, required=True, choices=(2, 3, 4))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-moves', type=int, default=1000)
    args = parser.parse_args()
    run(args.district_count, args.output, max_moves=args.max_moves)


if __name__ == '__main__':
    main()
