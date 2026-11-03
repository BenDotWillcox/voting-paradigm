"""Attempt unstarted New York anchors without changing or retrying K26.

The original serial suite stopped on an explicit optimizer failure. This one
supplemental invocation owns only the three previously unstarted plans. It
keeps original code/settings and records first attempts separately from the
unchanged original manifest. Only verified numerical failures permit the next
first attempt; orchestration ambiguity stops the queue.
"""
from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_kansas_blocks import sha256
from scripts.correct_state_block_parts import write_json
from scripts.state_block_execution_lock import state_execution_lock

OUTPUT = ROOT / '.cache/state-block-benchmark/suite-through-1000/policies/new-york-links-v1'
COUNTS = (35, 42, 61)
COMPLETE = 'complete_under_recorded_mixed_policy'
POLICY = 'shared_edges_plus_recorded_mixed_connections'
RUNNER = 'scripts/run_new_york_remaining_plans.py'
PRESERVATION_FLAGS = (
    'all_original_strict_files_byte_identical', 'all_original_diagnostic_files_byte_identical',
    'national_suite_byte_identical', 'source_archive_byte_identical',
    'prior_policy_and_correction_evidence_byte_identical', 'run_code_unchanged',
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def process_is_running(pid: int) -> bool:
    """Fail closed on inaccessible/reused PIDs; the state lock catches children."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError('Saved process ID is not a positive integer.')
    if sys.platform != 'win32':
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error in (87, 1168):
            return False
        raise OSError(error, f'Cannot establish whether saved PID {pid} exited.')
    try:
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return exit_code.value == 259
    finally:
        kernel.CloseHandle(handle)


def verify_hashes(inventory: dict[str, str]) -> None:
    if not inventory:
        raise ValueError('An empty preservation/code inventory cannot authorize execution.')
    for relative, expected in inventory.items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or sha256(path) != expected:
            raise ValueError(f'Preserved file/code changed or disappeared: {relative}')


def configuration_without_count_values(report: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in report['configuration'].items() if name not in (
        'minimum_district_population_for_root_classification', 'minimum_district_population_exact')}


def validate_terminal_report(
    output: Path, count: int, exit_code: int, code: dict[str, str], baseline: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconcile after exit/lock release, before permitting any next child."""
    report = read_json(output / 'benchmark.json')
    progress = read_json(output / 'progress.json')
    if (report.get('state_fips') != '36' or report.get('district_count') != count
            or report.get('policy') != POLICY or report.get('active_phase') is not None
            or not report.get('finished_at') or progress.get('status') != report.get('status')):
        raise ValueError(f'K{count} has an ambiguous or mismatched terminal report/progress.')
    if report.get('code_sha256') != code:
        raise ValueError(f'K{count} code differs from the frozen original suite.')
    verify_hashes(code)
    if configuration_without_count_values(report) != configuration_without_count_values(baseline):
        raise ValueError(f'K{count} numerical/policy settings differ from K26.')
    if report.get('source', {}).get('archive_sha256') != baseline['source']['archive_sha256']:
        raise ValueError(f'K{count} source archive differs from K26.')
    preservation = report.get('preservation_audit', {})
    if report.get('preservation_error') or any(preservation.get(name) is not True for name in PRESERVATION_FLAGS):
        raise ValueError(f'K{count} lacks a successful preservation audit.')
    inventory = read_json(output / 'preserved-file-inventory.json')
    if preservation.get('protected_file_count') != len(inventory):
        raise ValueError(f'K{count} protected-file count is inconsistent.')
    verify_hashes(inventory)
    for relative, expected in report.get('artifact_sha256', {}).items():
        artifact = (output / relative).resolve()
        if not artifact.is_relative_to(output.resolve()) or not artifact.is_file() or sha256(artifact) != expected:
            raise ValueError(f'K{count} saved artifact changed: {relative}')
    status = report['status']
    if status == COMPLETE and exit_code == 0:
        if (report.get('final_plan', {}).get('policy_part_components') != [1] * count
                or report.get('solver', {}).get('all_inner_optimizer_passes_succeeded') is not True
                or report.get('maps', {}).get('connectivity_validation', {}).get('passed') is not True
                or report['maps']['connectivity_validation'].get('policy') != POLICY):
            raise ValueError(f'K{count} completion lacks graph, optimizer, or polygon validation.')
        classification = 'complete'
    elif (status == 'failed' and exit_code != 0 and report.get('failed_phase') == 'solve'
          and report.get('optimizer_failure', {}).get('plan_returned') is False
          and str(report.get('error', '')).startswith('DistrictingOptimizationError:')
          and 'final_plan' not in report and 'maps' not in report):
        classification = 'numerical_failure'
    else:
        raise ValueError(f'K{count} has a nonnumerical failure or inconsistent exit/report; inspect before continuing.')
    return report, {'passed': True, 'classification': classification,
                    'preservation_verified': True, 'code_unchanged': True,
                    'protected_file_count': len(inventory)}


def admit() -> tuple[dict[str, Any], dict[str, Any]]:
    original_path = OUTPUT / 'run.json'
    original = read_json(original_path)
    if original.get('status') != 'stopped' or not original.get('finished_at'):
        raise ValueError('The original serial suite is not terminal/stopped.')
    jobs = original.get('jobs', [])
    if [job.get('district_count') for job in jobs] != [26, *COUNTS]:
        raise ValueError('The original suite is not the expected New York four-anchor attempt.')
    if jobs[0].get('status') != 'failed' or jobs[0].get('exit_code') != 1 or any(job != {'district_count': k, 'status': 'pending'} for job, k in zip(jobs[1:], COUNTS, strict=True)):
        raise ValueError('Supplemental execution requires exactly K26 failed and K35/K42/K61 never started.')
    for pid in (original['pid'], jobs[0]['pid']):
        if process_is_running(pid):
            raise ValueError(f'Original PID {pid} still exists; do not duplicate ambiguous work.')
    code = original['code_sha256']
    verify_hashes(code)
    old_output = OUTPUT / 'states/36/districts-26'
    if sha256(old_output / 'benchmark.json') != jobs[0]['benchmark_sha256']:
        raise ValueError('Original K26 report differs from its terminal suite manifest.')
    baseline = read_json(old_output / 'benchmark.json')
    _, validation = validate_terminal_report(old_output, 26, 1, code, baseline)
    if validation['classification'] != 'numerical_failure':
        raise ValueError('K26 is not the known terminal numerical failure.')
    old_files = [original_path, OUTPUT / 'districts-26.log', *[p for p in old_output.rglob('*') if p.is_file()]]
    history = {p.relative_to(ROOT).as_posix(): sha256(p) for p in old_files}
    data = {'status': 'admitted', 'pid': os.getpid(), 'started_at': now(),
            'attempt_kind': 'deferred_first_attempts', 'execution': 'serial_fresh_processes',
            'original_run_manifest': {'path': original_path.relative_to(ROOT).as_posix(),
                                      'sha256': sha256(original_path), 'status': original['status']},
            'original_code_sha256': code, 'supplemental_runner_sha256': sha256(ROOT / RUNNER),
            'preserved_original_attempt_inventory': history,
            'jobs': [{'district_count': k, 'attempt_kind': 'deferred_first_attempt', 'status': 'pending'} for k in COUNTS],
            'notes': ['K26 is not retried and original run.json is never edited.',
                      'Only an exited, verified numerical failure permits the next first attempt.',
                      'All source, optimizer, population policy, and postprocessing settings remain unchanged.']}
    record = OUTPUT / 'supplemental-first-attempts.json'
    with state_execution_lock('36'):
        for count in COUNTS:
            for path in (OUTPUT / f'states/36/districts-{count}', OUTPUT / f'districts-{count}.log'):
                if path.exists():
                    raise ValueError(f'An earlier attempt or ambiguous output exists: {path}')
        with record.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
    return data, baseline


def main() -> None:
    data, baseline = admit()
    record = OUTPUT / 'supplemental-first-attempts.json'
    start = time.perf_counter()
    child = None
    job: dict[str, Any] | None = None
    try:
        data['status'] = 'running'
        for job in data['jobs']:
            verify_hashes(data['original_code_sha256'])
            verify_hashes(data['preserved_original_attempt_inventory'])
            if sha256(ROOT / RUNNER) != data['supplemental_runner_sha256']:
                raise ValueError('Supplemental orchestration code changed during execution.')
            count = job['district_count']
            output = OUTPUT / f'states/36/districts-{count}'
            log = OUTPUT / f'districts-{count}.log'
            with state_execution_lock('36'):
                if output.exists() or log.exists():
                    raise ValueError('A pending first attempt acquired existing output; stop for inspection.')
            command = [sys.executable, '-X', 'utf8', '-u', str(ROOT / 'scripts/benchmark_new_york_links.py'),
                       '--district-count', str(count), '--output', str(output)]
            job.update(status='starting', started_at=now(), command=command, output=str(output), log=str(log))
            write_json(record, data)
            child_start = time.perf_counter()
            with log.open('xb') as stream:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                job.update(status='running', pid=child.pid)
                write_json(record, data)
                print(f'New York K{count} first attempt started; PID {child.pid}; {log}', flush=True)
                exit_code = child.wait()
            child = None
            job.update(exit_code=exit_code, finished_at=now(), process_wall_seconds=time.perf_counter() - child_start)
            with state_execution_lock('36'):
                report, validation = validate_terminal_report(output, count, exit_code, data['original_code_sha256'], baseline)
                verify_hashes(data['preserved_original_attempt_inventory'])
            job.update(status=report['status'], benchmark_sha256=sha256(output / 'benchmark.json'), terminal_validation=validation)
            write_json(record, data)
            print(f'New York K{count}: {job["status"]}; {validation["classification"]}; exit {exit_code}', flush=True)
        data['status'] = 'complete'
        data['outcome_counts'] = {name: sum(job['terminal_validation']['classification'] == name for job in data['jobs'])
                                  for name in ('complete', 'numerical_failure')}
    except BaseException as error:
        if child is not None:
            # Keep ownership and the direct log open until this child exits;
            # metadata errors never authorize another launch or a retry.
            exit_code = child.wait()
            assert job is not None
            job.update(exit_code=exit_code, finished_at=now(), process_wall_seconds=time.perf_counter() - child_start,
                       status='needs_inspection')
            try:
                with state_execution_lock('36'):
                    report, validation = validate_terminal_report(output, count, exit_code, data['original_code_sha256'], baseline)
                job.update(status=report['status'], terminal_validation=validation,
                           benchmark_sha256=sha256(output / 'benchmark.json'))
            except Exception as reconciliation_error:
                job['reconciliation_error'] = f'{type(reconciliation_error).__name__}: {reconciliation_error}'
        data.update(status='stopped', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        data.update(finished_at=now(), elapsed_wall_seconds=time.perf_counter() - start)
        try:
            verify_hashes(data['preserved_original_attempt_inventory'])
            data['original_attempt_preserved_byte_identically'] = True
        except Exception as preservation_error:
            data.update(status='stopped', original_attempt_preserved_byte_identically=False,
                        preservation_error=f'{type(preservation_error).__name__}: {preservation_error}')
        write_json(record, data)


if __name__ == '__main__':
    main()
