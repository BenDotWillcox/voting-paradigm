"""Run Florida K28/K37/K45/K65 once in serial fresh processes.

Preserve original Florida strict and diagnostic evidence. Verified numerical failures are outcomes;
operational ambiguity stops the queue. Never duplicate, retry, or abandon a child.
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
from scripts import benchmark_florida_water as benchmark
from scripts.benchmark_kansas_blocks import sha256
from scripts.florida_recorded_links import AUTHORIZED_CANDIDATE_IDS, PINNED_EVIDENCE_SHA256
from scripts.correct_state_block_parts import write_json
from scripts.state_block_execution_lock import state_execution_lock

OUTPUT = benchmark.SUITE / 'policies/florida-water-v1'
COUNTS = (28, 37, 45, 65)
COMPLETE = 'complete_under_island_water_policy'


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    # Bounded sharing-conflict retries never retry a numerical computation.
    for attempt in range(6):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(.1 * (attempt + 1))
    raise AssertionError('unreachable')


def verify_hashes(inventory: dict[str, str], *, root: Path = ROOT) -> None:
    for name, digest in inventory.items():
        if sha256(root / name) != digest:
            raise ValueError(f'Protected evidence or frozen source changed: {name}')


def artifact_path(directory: Path, name: str) -> Path:
    path = (directory / name).resolve()
    if path == directory.resolve() or not path.is_relative_to(directory.resolve()):
        raise ValueError(f'Artifact path escapes the run directory: {name}')
    return path


def validate_policy_audit(report: dict[str, Any], count: int) -> None:
    audit = report['island_policy_audit']
    selection = audit['population_selection']
    groups = selection['groups']
    if (audit['district_count'] != count or selection['district_count'] != count
            or not math.isclose(selection['ideal_population'], benchmark.TOTAL/count, rel_tol=1e-12)
            or not math.isclose(selection['minimum_root_population'],
                report['configuration']['minimum_district_population_for_root_classification'], rel_tol=1e-12)
            or selection['eligible_root_component_ids'] != [0]
            or selection['selected_link_ids'] != list(AUTHORIZED_CANDIDATE_IDS)
            or len(groups) != 1 or groups[0]['district_count'] != count
            or groups[0]['population'] != benchmark.TOTAL
            or groups[0]['component_ids'] != list(range(audit['physical_component_count']))
            or audit['source_population'] != benchmark.TOTAL or audit['block_count'] != benchmark.BLOCKS
            or audit['physical_component_count'] != 2 or audit['part_count'] != 390182
            or audit['augmented_component_count'] != 1
            or audit['target_selection_verified_against_diagnosis'] is not True
            or audit['source_geometry_modified'] is not False
            or audit['augmented_graph_connected'] is not True or audit['all_source_parts_reached'] is not True
            or audit['synthetic_edge_count'] != len(AUTHORIZED_CANDIDATE_IDS)
            or len(report['water_connections']) != len(AUTHORIZED_CANDIDATE_IDS)
            or any(link.get('kind') != 'recorded-water-connection' for link in report['water_connections'])):
        raise ValueError('Target-count population/link audit differs from the authorized Florida policy.')
    for index, (candidate, link) in enumerate(zip(AUTHORIZED_CANDIDATE_IDS, report['water_connections'], strict=True), 1):
        if (link.get('candidate_id') != candidate or link.get('id') != f'fl-water-{index:03d}'
                or link.get('state_fips') != '12'
                or link.get('provenance', {}).get('diagnostic_evidence_sha256') != PINNED_EVIDENCE_SHA256):
            raise ValueError('Saved Florida connection identity or diagnostic provenance changed.')


def validate_terminal_job(count: int, output: Path, exit_code: int, *,
                          code: dict[str, str], inventory: dict[str, str],
                          environment: dict[str, Any], baselines: dict[int, dict[str, Any]]) -> dict[str, Any]:
    report_path = output / 'terminal-report.json'
    if not report_path.exists():
        report_path = output / 'benchmark.json'
    report, progress = read_json(report_path), read_json(output / 'progress.json')
    if (report['district_count'] != count or report['state_fips'] != '12'
            or report['run_kind'] != 'florida_population_aware_water_v1'
            or report['policy'] != benchmark.POLICY
            or report['status'] not in (COMPLETE, 'failed')
            or not report.get('finished_at') or report.get('active_phase') is not None
            or progress.get('active_phase') is not None
            or progress['status'] != report['status'] or progress['district_count'] != count
            or progress['solver_progress'] != report['solver_progress']):
        raise ValueError('Child report/progress do not describe the same terminal attempt.')
    if report['comparison_baseline'] != baselines[count] or report['house_sizes'] != benchmark.house_links('12', count, (435, 574, 692, 1000)):
        raise ValueError('Child preflight reference or House anchor identity changed.')
    if report_path.name == 'terminal-report.json' and (report.get('authoritative_terminal_report') != 'terminal-report.json'
            or not report.get('terminal_report_write_error')):
        raise ValueError('Emergency terminal report lacks its explicit write-failure provenance.')
    if report['configuration'] != benchmark.configuration_for_run(count):
        raise ValueError('Child changed settings beyond district count and its derived population threshold.')
    if report['configuration_sha256'] != benchmark._digest(report['configuration']):
        raise ValueError('Child configuration fingerprint is invalid.')
    validate_policy_audit(report, count)
    if (report['source']['archive_sha256'] != baselines[count]['source_archive_sha256']
            or report['environment'] != environment
            or report.get('final_progress_snapshot_written') is not True):
        raise ValueError('Child source, environment or final progress status changed.')
    if report['code_sha256'] != code:
        raise ValueError('Child source snapshot differs from its parent.')
    verify_hashes(code, root=ROOT)
    preserved = report['preservation_audit']
    flags = ('all_original_strict_files_byte_identical',
             'all_original_diagnostic_files_byte_identical', 'national_suite_byte_identical',
             'source_archive_byte_identical', 'run_code_unchanged')
    if (read_json(output / 'preserved-file-inventory.json') != inventory
            or preserved['protected_file_count'] != len(inventory)
            or any(preserved.get(key) is not True for key in flags)
            or report.get('preservation_error')):
        raise ValueError('Child historical-preservation audit is incomplete.')
    verify_hashes(inventory, root=ROOT)
    if benchmark.protected_inventory() != inventory:
        raise ValueError('Historical evidence tree changed during the attempt.')
    hashes = report['artifact_sha256']
    required = {'water-connections.json', 'optimizer-trace.jsonl'}
    if not required.issubset(hashes):
        raise ValueError('Child lacks hashed link or optimizer trace evidence.')
    for name, digest in hashes.items():
        if sha256(artifact_path(output, name)) != digest:
            raise ValueError(f'Child artifact hash mismatch: {name}')
    connection_file = read_json(output / 'water-connections.json')
    if connection_file != {'policy': benchmark.POLICY, 'connections': report['water_connections'],
                           'source_sha256': report['source']['archive_sha256']}:
        raise ValueError('Saved water connection artifact differs from the report.')
    trace, passes = report['optimizer_trace'], report['solver_progress']
    if (trace.get('observation_ok') is not True or trace.get('telemetry_errors')
            or trace.get('passes') != passes or not passes
            or any(row.get('inner_optimizer', {}).get('actual_maxiter') != 1000 for row in passes)):
        raise ValueError('Optimizer trace is incomplete or has another iteration budget.')
    duration, peak = report['timed_pipeline_wall_seconds'], report['peak_process_working_set_bytes']
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0 or type(peak) is not int or peak <= 0:
        raise ValueError('Child runtime or memory measurement is invalid.')
    if report['status'] == COMPLETE:
        if exit_code != 0 or not all(row['inner_optimizer']['success'] is True for row in passes):
            raise ValueError('Completed child has a failing process or optimizer pass.')
        required |= {'initial-solver-result.json', 'after-repair-result.json', 'solver-result.json',
                     'move-audit.json', 'maps/map-manifest.json', 'index.html'}
        if not required.issubset(hashes):
            raise ValueError('Completed child lacks hashed plan/map artifacts.')
        manifest, final = read_json(output / 'maps/map-manifest.json'), report['final_plan']
        validation = manifest['connectivity_validation']
        if (manifest != report['maps'] or validation['policy'] != benchmark.POLICY
                or validation['passed'] is not True
                or validation['source_coverage_preserved_exactly'] is not True
                or validation['source_geometry_modified'] is not False
                or [row['district_id'] for row in validation['districts']] != list(range(count))
                or any(row['connected_components_after_links'] != 1 for row in validation['districts'])
                or final['all_districts_policy_connected'] is not True
                or final['policy_part_components'] != [1] * count
                or final['all_blocks_assigned_once'] is not True
                or final['population_sum_matches_source'] is not True
                or final['total_population'] != 21_538_187):
            raise ValueError('Completed child lacks independent population/connectivity acceptance.')
        classification = 'validated_complete_plan'
    else:
        failure, last = report.get('optimizer_failure', {}), passes[-1]['inner_optimizer']
        if (exit_code == 0 or report.get('failed_phase') != 'solve'
                or not str(report.get('error', '')).startswith('DistrictingOptimizationError:')
                or failure.get('plan_returned') is not False
                or failure.get('balance_pass') != len(passes) or last['success'] is not False
                or any(failure.get(key) != last[key] for key in ('iterations', 'function_evaluations', 'status', 'message'))
                or not all(row['inner_optimizer']['success'] is True for row in passes[:-1])
                or 'final_plan' in report or 'maps' in report):
            raise ValueError('Child failure is operational or ambiguous; stop the queue.')
        classification = 'verified_numerical_failure'
    return {'status': report['status'], 'classification': classification, 'passed': True,
            'report_path': report_path.relative_to(output).as_posix(),
            'benchmark_sha256': sha256(report_path), 'progress_sha256': sha256(output / 'progress.json'),
            'artifact_count': len(hashes), 'protected_file_count': len(inventory),
            'timed_pipeline_wall_seconds': duration,
            'scope': 'Terminal process, settings, provenance, artifact hashes and acceptance audits; final comparison also reconciles source populations and compressed maps.'}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    record, started_at = OUTPUT / 'run.json', now()
    with state_execution_lock('12'):
        for count in COUNTS:
            benchmark.validate_output(OUTPUT / f'states/12/districts-{count}', count)
            if (OUTPUT / f'districts-{count}.log').exists():
                raise ValueError('A prior log exists; no automatic retries.')
        with record.open('x', encoding='utf-8') as stream:
            json.dump({'status': 'admitted', 'pid': os.getpid(), 'started_at': started_at}, stream)
    data: dict[str, Any] = {'status': 'running', 'pid': os.getpid(), 'started_at': started_at,
        'execution': 'serial_fresh_processes', 'district_counts': list(COUNTS),
        'jobs': [{'district_count': count, 'status': 'pending'} for count in COUNTS]}
    started, child_start = time.perf_counter(), 0.
    child: Any = None
    job: dict[str, Any] | None = None
    try:
        code = benchmark.runtime_code()
        environment = benchmark.environment_snapshot()
        baselines = {count: benchmark.load_strict_baseline(count) for count in COUNTS}
        inventory = benchmark.protected_inventory()
        write_json(OUTPUT / 'preserved-file-inventory.json', inventory)
        data.update(code_sha256=code, environment=environment,
                    preserved_file_inventory_sha256=sha256(OUTPUT / 'preserved-file-inventory.json'),
                    protected_file_count=len(inventory),
                    strict_preflight_baselines={str(count): baseline for count, baseline in baselines.items()})
        data['preparation_wall_seconds'] = time.perf_counter() - started
        write_json(record, data)
        for job in data['jobs']:
            verify_hashes(code, root=ROOT)
            if benchmark.protected_inventory() != inventory:
                raise ValueError('Historical evidence changed before the next child.')
            count = job['district_count']
            output, log = OUTPUT / f'states/12/districts-{count}', OUTPUT / f'districts-{count}.log'
            with state_execution_lock('12'):
                benchmark.validate_output(output, count)
            command = [sys.executable, '-X', 'utf8', '-u', str(ROOT / 'scripts/benchmark_florida_water.py'),
                       '--district-count', str(count), '--output', str(output)]
            job.update(status='starting', started_at=now(), command=command, output=str(output), log=str(log))
            write_json(record, data)
            child_start = time.perf_counter()
            with log.open('xb') as stream:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                job.update(status='running', pid=child.pid)
                write_json(record, data)
                print(f'Florida K{count} started; PID {child.pid}; {log}', flush=True)
                exit_code = child.wait()
            child = None
            job.update(exit_code=exit_code, finished_at=now(), process_wall_seconds=time.perf_counter() - child_start)
            with state_execution_lock('12'):
                validation = validate_terminal_job(count, output, exit_code, code=code, inventory=inventory, environment=environment, baselines=baselines)
            if job['process_wall_seconds'] < validation['timed_pipeline_wall_seconds']:
                raise ValueError('Child process duration is shorter than its measured pipeline.')
            job.update(status=validation['status'], terminal_validation=validation,
                       benchmark_sha256=validation['benchmark_sha256'], progress_sha256=validation['progress_sha256'])
            write_json(record, data)
            print(f'Florida K{count}: {job["status"]}; exit {exit_code}; terminal evidence verified.', flush=True)
        data['status'] = 'complete_with_numerical_failures' if any(job['status'] == 'failed' for job in data['jobs']) else 'complete'
    except BaseException as error:
        if child is not None and job is not None:
            exit_code = child.wait()
            job.update(exit_code=exit_code, finished_at=now(), process_wall_seconds=time.perf_counter() - child_start)
        if job is not None and 'terminal_validation' not in job:
            job['status'] = 'needs_inspection'
        data.update(status='stopped', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        data.update(finished_at=now(), elapsed_wall_seconds=time.perf_counter() - started)
        data['serial_child_process_wall_seconds'] = sum(row.get('process_wall_seconds', 0) for row in data['jobs'])
        try:
            write_json(record, data)
        except Exception as error:
            data['manifest_write_error'] = f'{type(error).__name__}: {error}'
            with (OUTPUT / f'emergency-{os.getpid()}.json').open('x', encoding='utf-8') as stream:
                json.dump(data, stream, indent=2, allow_nan=False)
            raise


if __name__ == '__main__':
    main()
