"""Run New York K35/K42/K61 once, serially, with the fixed 1,000 inner budget.

Each child owns the state lock while it runs. The parent owns this one-shot
manifest, waits for every launched child and validates terminal evidence before
advancing. Verified optimizer failures are outcomes; operational ambiguity stops
the queue and never triggers an automatic retry.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import benchmark_new_york_budget_anchors as benchmark
from scripts.benchmark_kansas_blocks import sha256
from scripts.correct_state_block_parts import write_json
from scripts.state_block_execution_lock import state_execution_lock

OUTPUT = benchmark.SUITE / 'corrections/new-york-inner-budget-anchors-v1'
COUNTS = (35, 42, 61)
PRESERVATION_FLAGS = (
    'all_original_strict_files_byte_identical',
    'all_original_diagnostic_files_byte_identical',
    'national_suite_byte_identical', 'source_archive_byte_identical',
    'prior_policy_and_correction_evidence_byte_identical',
    'original_failed_policy_tree_byte_identical', 'completed_k26_tree_byte_identical',
    'baseline_configuration_only_inner_budget_changed',
    'recorded_connections_byte_identical', 'run_code_unchanged',
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def verify_hashes(inventory: dict[str, str], *, root: Path = ROOT) -> None:
    for name, digest in inventory.items():
        if sha256(root / name) != digest:
            raise ValueError(f'Protected evidence or frozen source changed: {name}')


def artifact_path(directory: Path, name: str) -> Path:
    path = (directory / name).resolve()
    if path == directory.resolve() or not path.is_relative_to(directory.resolve()):
        raise ValueError(f'Artifact path escapes the run directory: {name}')
    return path


def validate_terminal_job(
    count: int, output: Path, exit_code: int, *, baseline: dict[str, Any],
    code: dict[str, str], inventory: dict[str, str],
) -> dict[str, Any]:
    """Require consistent terminal process, progress, report and artifact evidence."""
    report_path, progress_path = output / 'benchmark.json', output / 'progress.json'
    report, progress = read_json(report_path), read_json(progress_path)
    if (report['district_count'] != count or report['state_fips'] != '36'
            or report['run_kind'] != 'new_york_inner_budget_anchors_experiment_v1'
            or report['policy'] != benchmark.POLICY
            or report['status'] not in ('complete_under_recorded_mixed_policy', 'failed')
            or not report.get('finished_at') or report.get('active_phase') is not None
            or progress.get('active_phase') is not None
            or progress['status'] != report['status'] or progress['district_count'] != count
            or progress['solver_progress'] != report['solver_progress']):
        raise ValueError('Child report and progress do not describe the same terminal attempt.')
    if report['configuration'] != benchmark.configuration_for_experiment(baseline):
        raise ValueError('Child changed settings beyond its authorized inner iteration budget.')
    if (report['comparison_baseline']['failed_policy_report_sha256'] != benchmark.BASELINE_REPORT_SHA256[count]
            or report['completed_k26_reference']['report_sha256'] != benchmark.K26_REPORT_SHA256
            or report['completed_k26_reference']['reused_without_rerun'] is not True):
        raise ValueError('Child baseline or completed K26 reference differs from the preserved evidence.')
    if (report['source']['archive_sha256'] != baseline['source']['archive_sha256']
            or report['recorded_connections'] != baseline['recorded_connections']
            or report['environment']['python'] != baseline['environment']['python']
            or report['environment']['packages'] != baseline['environment']['packages']):
        raise ValueError('Child source, connection records or runtime environment changed.')
    if report['code_sha256'] != code:
        raise ValueError('Child ran a different source snapshot than its parent.')
    verify_hashes(code, root=ROOT)
    if (read_json(output / 'preserved-file-inventory.json') != inventory
            or report['preservation_audit']['protected_file_count'] != len(inventory)
            or any(report['preservation_audit'].get(key) is not True for key in PRESERVATION_FLAGS)
            or report.get('preservation_error')):
        raise ValueError('Child historical-preservation audit is incomplete or inconsistent.')
    verify_hashes(inventory, root=ROOT)
    if benchmark.protected_inventory() != inventory:
        raise ValueError('Historical evidence tree changed during the child attempt.')
    required = {'recorded-connections.json', 'optimizer-trace.jsonl'}
    hashes = report['artifact_sha256']
    if not required.issubset(hashes):
        raise ValueError('Child lacks hashed connection or optimizer-trace evidence.')
    for name, digest in hashes.items():
        if sha256(artifact_path(output, name)) != digest:
            raise ValueError(f'Child artifact hash mismatch: {name}')
    if hashes['recorded-connections.json'] != baseline['artifact_sha256']['recorded-connections.json']:
        raise ValueError('Child connection artifact differs from its own failed baseline.')
    trace = report['optimizer_trace']
    passes = report['solver_progress']
    if (trace.get('observation_ok') is not True or trace.get('telemetry_errors')
            or trace.get('passes') != passes or not passes
            or any(row.get('inner_optimizer', {}).get('actual_maxiter') != 1000 for row in passes)):
        raise ValueError('Child optimizer trace is incomplete or uses a different inner budget.')
    duration = report['timed_pipeline_wall_seconds']
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
        raise ValueError('Child timing is not a finite nonnegative duration.')
    if report['status'] == 'complete_under_recorded_mixed_policy':
        if exit_code != 0 or not all(row['inner_optimizer']['success'] is True for row in passes):
            raise ValueError('Completed child has a failing process or optimizer pass.')
        required |= {'initial-solver-result.json', 'after-repair-result.json', 'solver-result.json',
                     'move-audit.json', 'maps/map-manifest.json', 'index.html'}
        if not required.issubset(hashes):
            raise ValueError('Completed child lacks required hashed plan/map artifacts.')
        manifest = read_json(output / 'maps/map-manifest.json')
        final = report['final_plan']
        validation = manifest['connectivity_validation']
        if (manifest != report['maps'] or validation['policy'] != benchmark.POLICY
                or validation['passed'] is not True
                or validation['source_coverage_preserved_exactly'] is not True
                or validation['source_geometry_modified'] is not False
                or final['all_districts_policy_connected'] is not True
                or final['policy_part_components'] != [1] * count
                or final['all_blocks_assigned_once'] is not True
                or final['population_sum_matches_source'] is not True
                or final['total_population'] != 20201249):
            raise ValueError('Completed child lacks its independent population/connectivity acceptance audit.')
        classification = 'validated_complete_plan'
    else:
        failure = report.get('optimizer_failure', {})
        last = passes[-1]['inner_optimizer']
        if (exit_code == 0 or report.get('failed_phase') != 'solve'
                or not str(report.get('error', '')).startswith('DistrictingOptimizationError:')
                or failure.get('plan_returned') is not False
                or failure.get('balance_pass') != len(passes)
                or last['success'] is not False
                or failure.get('iterations') != last['iterations']
                or failure.get('function_evaluations') != last['function_evaluations']
                or failure.get('status') != last['status']
                or failure.get('message') != last['message']
                or not all(row['inner_optimizer']['success'] is True for row in passes[:-1])
                or 'final_plan' in report or 'maps' in report):
            raise ValueError('Child failure is operational or ambiguous; serial queue must stop.')
        classification = 'verified_numerical_failure'
    return {
        'status': report['status'], 'classification': classification, 'passed': True,
        'benchmark_sha256': sha256(report_path), 'progress_sha256': sha256(progress_path),
        'artifact_count': len(hashes), 'protected_file_count': len(inventory),
        'timed_pipeline_wall_seconds': duration,
        'scope': 'Terminal orchestration, fixed configuration, provenance, saved artifact hashes and acceptance audit checks; the final comparison additionally reconciles source populations and map payloads.',
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    record = OUTPUT / 'run.json'
    started_at = now()
    with state_execution_lock('36'):
        for count in COUNTS:
            benchmark.validate_output(OUTPUT / f'states/36/districts-{count}', count)
            if (OUTPUT / f'districts-{count}.log').exists():
                raise ValueError('A prior child log exists; this suite never retries ambiguous attempts.')
        with record.open('x', encoding='utf-8') as stream:
            json.dump({'status': 'admitted', 'pid': os.getpid(), 'started_at': started_at}, stream)
    data: dict[str, Any] = {
        'status': 'running', 'pid': os.getpid(), 'started_at': started_at,
        'execution': 'serial_fresh_processes', 'district_counts': list(COUNTS),
        'jobs': [{'district_count': count, 'status': 'pending'} for count in COUNTS],
    }
    start = time.perf_counter()
    child: Any = None
    job: dict[str, Any] | None = None
    child_start = 0.0
    try:
        baselines = {count: benchmark.load_baseline(count) for count in COUNTS}
        reference = benchmark.load_reference()
        code = {**reference['code_sha256'], **{name: sha256(ROOT / name) for name in benchmark.EXTRA_CODE}}
        inventory = benchmark.protected_inventory()
        write_json(OUTPUT / 'preserved-file-inventory.json', inventory)
        data.update(code_sha256=code, baseline_report_sha256=benchmark.BASELINE_REPORT_SHA256,
                    preserved_file_inventory_sha256=sha256(OUTPUT / 'preserved-file-inventory.json'),
                    protected_file_count=len(inventory), completed_k26_reference={
                        'report_path': str(benchmark.reference_directory() / 'benchmark.json'),
                        'report_sha256': benchmark.K26_REPORT_SHA256, 'reused_without_rerun': True,
                        'original_pipeline_wall_seconds': reference['timed_pipeline_wall_seconds']})
        write_json(record, data)
        for job in data['jobs']:
            verify_hashes(code, root=ROOT)
            if benchmark.protected_inventory() != inventory:
                raise ValueError('Historical evidence changed before the next child.')
            count = job['district_count']
            output = OUTPUT / f'states/36/districts-{count}'
            with state_execution_lock('36'):
                benchmark.validate_output(output, count)
            log = OUTPUT / f'districts-{count}.log'
            command = [sys.executable, '-X', 'utf8', '-u',
                       str(ROOT / 'scripts/benchmark_new_york_budget_anchors.py'),
                       '--district-count', str(count), '--output', str(output)]
            job.update(status='starting', started_at=now(), command=command,
                       output=str(output), log=str(log))
            write_json(record, data)
            child_start = time.perf_counter()
            with log.open('xb') as stream:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                job.update(status='running', pid=child.pid)
                write_json(record, data)
                print(f'New York K{count} started; PID {child.pid}; {log}', flush=True)
                exit_code = child.wait()
            child = None
            job.update(exit_code=exit_code, finished_at=now(),
                       process_wall_seconds=time.perf_counter() - child_start)
            with state_execution_lock('36'):
                validation = validate_terminal_job(count, output, exit_code,
                    baseline=baselines[count], code=code, inventory=inventory)
            if job['process_wall_seconds'] < validation['timed_pipeline_wall_seconds']:
                raise ValueError('External child runtime is shorter than its measured pipeline.')
            job.update(status=validation['status'], terminal_validation=validation,
                       benchmark_sha256=validation['benchmark_sha256'], progress_sha256=validation['progress_sha256'])
            write_json(record, data)
            print(f'New York K{count}: {job["status"]}; exit {exit_code}; terminal evidence verified.', flush=True)
        data['status'] = ('complete_with_numerical_failures'
                          if any(job['status'] == 'failed' for job in data['jobs']) else 'complete')
    except BaseException as error:
        # A failed metadata write never abandons an active child or starts another.
        if child is not None and job is not None:
            exit_code = child.wait()
            job.update(exit_code=exit_code, finished_at=now(),
                       process_wall_seconds=time.perf_counter() - child_start)
        if job is not None and 'terminal_validation' not in job:
            job['status'] = 'needs_inspection'
            report_path = Path(job['output']) / 'benchmark.json' if job.get('output') else None
            if report_path is not None and report_path.is_file():
                job['benchmark_sha256'] = sha256(report_path)
        data.update(status='stopped', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        data.update(finished_at=now(), elapsed_wall_seconds=time.perf_counter() - start)
        try:
            write_json(record, data)
        except Exception as error:
            # Keep a separately named terminal record if Windows sharing prevents
            # replacing the manifest even after the normal bounded write retries.
            emergency = OUTPUT / f'emergency-{os.getpid()}.json'
            data['manifest_write_error'] = f'{type(error).__name__}: {error}'
            with emergency.open('x', encoding='utf-8') as stream:
                json.dump(data, stream, indent=2, allow_nan=False)
            raise


if __name__ == '__main__':
    main()
