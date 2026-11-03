"""New York suite admission, serial ownership, and stop-without-retry rules."""
from contextlib import nullcontext
import json
from pathlib import Path

import pytest

from scripts import benchmark_new_york_links as benchmark
from scripts import run_new_york_link_suite as suite


def setup_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output = tmp_path / 'policies/new-york-links-v1'
    monkeypatch.setattr(suite, 'ROOT', tmp_path)
    monkeypatch.setattr(suite, 'OUTPUT', output)
    monkeypatch.setattr(benchmark, 'CODE_PATHS', ())
    monkeypatch.setattr(benchmark, 'EXTRA_CODE', ())
    locks = []
    monkeypatch.setattr(suite, 'state_execution_lock', lambda state: locks.append(state) or nullcontext())
    for relative in ('scripts/run_new_york_link_suite.py', 'districting/__init__.py'):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('frozen code')
    return output, locks


def fake_children(monkeypatch: pytest.MonkeyPatch, *, first_exit: int = 0):
    active = [False]
    commands = []
    waits = []
    def launch(command, *, cwd, stdout, stderr):
        assert not active[0], 'A second child cannot begin before the first exits'
        active[0] = True
        commands.append(command)
        count = int(command[command.index('--district-count') + 1])
        output = Path(command[command.index('--output') + 1])
        stdout.write(f'child K{count}\n'.encode())
        class Child:
            pid = 1000 + count
            def wait(self):
                assert active[0]
                active[0] = False
                waits.append(count)
                output.mkdir(parents=True, exist_ok=True)
                code = first_exit if len(commands) == 1 else 0
                report = {'status': 'failed' if code else 'complete_under_recorded_mixed_policy'}
                (output / 'benchmark.json').write_text(json.dumps(report))
                return code
        return Child()
    monkeypatch.setattr(suite.subprocess, 'Popen', launch)
    return commands, waits, active


def test_serial_suite_uses_all_four_counts_and_preserves_direct_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, locks = setup_suite(tmp_path, monkeypatch)
    commands, waits, active = fake_children(monkeypatch)
    suite.main()
    assert waits == [26, 35, 42, 61]
    assert not active[0]
    assert locks == ['36']
    report = json.loads((output / 'run.json').read_text())
    assert report['status'] == 'complete'
    assert report['execution'] == 'serial_fresh_processes'
    assert all(job['exit_code'] == 0 for job in report['jobs'])
    assert all(job['benchmark_sha256'] and job['process_wall_seconds'] >= 0 for job in report['jobs'])
    for count, command in zip(waits, commands, strict=True):
        assert command[1:4] == ['-X', 'utf8', '-u']
        assert command[-1] == str(output / f'states/36/districts-{count}')
        assert (output / f'districts-{count}.log').read_text() == f'child K{count}\n'


def test_duplicate_admission_never_starts_a_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _ = setup_suite(tmp_path, monkeypatch)
    output.mkdir(parents=True)
    original = b'{"status":"admitted","pid":123}'
    (output / 'run.json').write_bytes(original)
    monkeypatch.setattr(suite.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('No duplicate launch'))
    with pytest.raises(FileExistsError):
        suite.main()
    assert (output / 'run.json').read_bytes() == original


def test_failed_child_stops_queue_without_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _ = setup_suite(tmp_path, monkeypatch)
    commands, waits, active = fake_children(monkeypatch, first_exit=1)
    with pytest.raises(RuntimeError, match='prior attempt retained, queue stopped'):
        suite.main()
    assert len(commands) == 1 and waits == [26] and not active[0]
    report = json.loads((output / 'run.json').read_text())
    assert report['status'] == 'stopped'
    assert report['jobs'][0]['status'] == 'failed'
    assert report['jobs'][0]['exit_code'] == 1
    assert all(job['status'] == 'pending' for job in report['jobs'][1:])


def test_parent_metadata_failure_waits_for_child_and_records_its_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output, _ = setup_suite(tmp_path, monkeypatch)
    commands, waits, active = fake_children(monkeypatch)
    original_write = suite.write_json
    denied = []
    def transient_denial(path, data):
        if data['jobs'][0]['status'] == 'running' and not denied:
            denied.append(True)
            raise PermissionError('injected metadata replacement error')
        original_write(path, data)
    monkeypatch.setattr(suite, 'write_json', transient_denial)
    with pytest.raises(PermissionError, match='injected metadata replacement error'):
        suite.main()
    assert len(commands) == 1 and waits == [26] and not active[0]
    report = json.loads((output / 'run.json').read_text())
    assert report['status'] == 'stopped'
    assert report['jobs'][0]['status'] == 'complete_under_recorded_mixed_policy'
    assert report['jobs'][0]['exit_code'] == 0
    assert all(job['status'] == 'pending' for job in report['jobs'][1:])
