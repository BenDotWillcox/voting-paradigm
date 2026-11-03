"""Run the four new New York mixed-link plans serially without replacing history."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_kansas_blocks import sha256
from scripts.correct_state_block_parts import write_json
from scripts.state_block_execution_lock import state_execution_lock

OUTPUT = ROOT / '.cache/state-block-benchmark/suite-through-1000/policies/new-york-links-v1'
COUNTS = (26, 35, 42, 61)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    from scripts.benchmark_new_york_links import CODE_PATHS, EXTRA_CODE

    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Exclusive creation is a one-attempt admission guard, not an automatic
    # resume mechanism. An ambiguous prior launch must be inspected manually.
    record = OUTPUT / 'run.json'
    with state_execution_lock('36'):
        for count in COUNTS:
            path = OUTPUT / f'states/36/districts-{count}'
            if path.exists() and any(path.iterdir()):
                raise ValueError(f'An earlier attempt exists: {path}')
        with record.open('x', encoding='utf-8') as stream:
            json.dump({'status': 'admitted', 'pid': os.getpid(), 'started_at': now()}, stream)
    code = {name: sha256(ROOT / name) for name in set((*CODE_PATHS, *EXTRA_CODE,
            'scripts/run_new_york_link_suite.py', 'districting/__init__.py'))}
    data = {'status': 'running', 'pid': os.getpid(), 'started_at': now(),
            'execution': 'serial_fresh_processes', 'code_sha256': code,
            'jobs': [{'district_count': k, 'status': 'pending'} for k in COUNTS]}
    start = time.perf_counter()
    child = None
    try:
        for job in data['jobs']:
            if any(sha256(ROOT / name) != digest for name, digest in code.items()):
                raise ValueError('Benchmark code changed during the serial suite.')
            count = job['district_count']
            output = OUTPUT / f'states/36/districts-{count}'
            log = OUTPUT / f'districts-{count}.log'
            command = [sys.executable, '-X', 'utf8', '-u',
                       str(ROOT / 'scripts/benchmark_new_york_links.py'),
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
            report_path = output / 'benchmark.json'
            report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else {}
            job.update(status=report.get('status', 'failed_without_report'),
                       benchmark_sha256=sha256(report_path) if report_path.is_file() else None)
            write_json(record, data)
            print(f'New York K{count}: {job["status"]}; exit {exit_code}', flush=True)
            if exit_code != 0 or not str(job['status']).startswith('complete_under_'):
                raise RuntimeError(f'K{count} did not complete; prior attempt retained, queue stopped.')
        data['status'] = 'complete'
    except BaseException as error:
        # Retain ownership of any live child through a metadata-write failure.
        # Never launch a second attempt or abandon an ambiguous child.
        if child is not None:
            exit_code = child.wait()
            job.update(exit_code=exit_code, finished_at=now(),
                       process_wall_seconds=time.perf_counter() - child_start)
            report_path = output / 'benchmark.json'
            try:
                report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else {}
                job.update(status=report.get('status', 'failed_without_report'),
                           benchmark_sha256=sha256(report_path) if report_path.is_file() else None)
            except Exception as reconciliation_error:
                job.update(status='needs_inspection',
                           reconciliation_error=f'{type(reconciliation_error).__name__}: {reconciliation_error}')
        data['status'] = 'stopped'
        data['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        data.update(finished_at=now(), elapsed_wall_seconds=time.perf_counter() - start)
        write_json(record, data)


if __name__ == '__main__':
    main()
