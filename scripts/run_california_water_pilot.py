"""Launch exactly one California K52 water-policy attempt with direct logs.

The fixed run record refuses duplicate launches. Failed attempts are retained;
this launcher never resumes, retries, or edits historical suite manifests.
"""
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
from scripts.correct_state_block_parts import write_json
from scripts.state_block_execution_lock import state_execution_lock

OUTPUT = ROOT / '.cache/state-block-benchmark/suite-through-1000/policies/california-water-v1'


def main() -> int:
    # Check ownership before creating a durable launch record; the child takes
    # the same state lock for its entire computation.
    with state_execution_lock('06'):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        record_path = OUTPUT / 'run.json'
        command = [str(ROOT / 'venv/Scripts/python.exe'), '-X', 'utf8', '-u',
                   str(ROOT / 'scripts/benchmark_california_water.py'),
                   '--district-count', '52', '--output',
                   str(OUTPUT / 'states/06/districts-52')]
        record = {'run_kind': 'california_water_k52_pilot_v1', 'status': 'launching',
                  'state_fips': '06', 'district_count': 52, 'inner_max_iterations': 1000,
                  'started_at': datetime.now(timezone.utc).isoformat(),
                  'launcher_pid': os.getpid(), 'command': command,
                  'stdout_log': 'benchmark.stdout.log', 'stderr_log': 'benchmark.stderr.log',
                  'retries': 0, 'original_suite_modified': False}
        with record_path.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2)
            stream.write('\n')
    started = time.perf_counter()
    try:
        with (OUTPUT / 'benchmark.stdout.log').open('xb') as stdout, (OUTPUT / 'benchmark.stderr.log').open('xb') as stderr:
            child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            record.update(status='running', child_pid=child.pid)
            print(json.dumps({'status': 'running', 'child_pid': child.pid, 'output': str(OUTPUT)}), flush=True)
            try:
                write_json(record_path, record)
            except OSError as error:
                # A display metadata conflict must not orphan an active child
                # or lead a caller to launch a duplicate attempt.
                record['metadata_write_errors'] = [f'{type(error).__name__}: {error}']
                print(json.dumps({'metadata_write_error': str(error), 'child_pid': child.pid,
                                  'action': 'continue waiting for the existing child'}), flush=True)
            returncode = child.wait()
        record['returncode'] = returncode
        report_path = OUTPUT / 'states/06/districts-52/benchmark.json'
        report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
        record['benchmark_status'] = report.get('status', 'missing')
        record['benchmark_path'] = 'states/06/districts-52/benchmark.json'
        record['status'] = 'complete' if returncode == 0 and str(report.get('status', '')).startswith('complete_') else 'failed'
        return returncode if returncode else (0 if record['status'] == 'complete' else 1)
    except Exception as error:
        record.update(status='launcher_failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        record['elapsed_seconds'] = time.perf_counter() - started
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(record_path, record)
        print(json.dumps({key: record[key] for key in ('status', 'elapsed_seconds', 'finished_at')}), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
