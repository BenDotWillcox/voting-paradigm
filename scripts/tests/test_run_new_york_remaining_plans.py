"""Supplemental New York first attempts never retry or rewrite K26 history."""
from contextlib import nullcontext
import json
from pathlib import Path

import pytest

from scripts import run_new_york_remaining_plans as runner


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    output = tmp_path / 'policies/new-york-links-v1'
    monkeypatch.setattr(runner, 'OUTPUT', output)
    monkeypatch.setattr(runner, 'state_execution_lock', lambda state: nullcontext())
    monkeypatch.setattr(runner, 'process_is_running', lambda pid: False)
    for name in ('frozen.py', runner.RUNNER, 'historical-source.zip'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('original evidence')
    code = {'frozen.py': runner.sha256(tmp_path / 'frozen.py')}
    inventory = {'historical-source.zip': runner.sha256(tmp_path / 'historical-source.zip')}
    baseline = {'configuration': {'seed': 20200955, 'inner_max_iterations': 300},
                'source': {'archive_sha256': 'source-hash'}}
    def save_report(count, *, numerical=True, success=False):
        path = output / f'states/36/districts-{count}'
        path.mkdir(parents=True, exist_ok=True)
        report = {**baseline, 'state_fips': '36', 'district_count': count, 'policy': runner.POLICY,
                  'active_phase': None, 'finished_at': 'finished', 'code_sha256': code,
                  'preservation_audit': {**dict.fromkeys(runner.PRESERVATION_FLAGS, True), 'protected_file_count': 1},
                  'status': runner.COMPLETE if success else 'failed'}
        if success:
            report.update(final_plan={'policy_part_components': [1] * count},
                          solver={'all_inner_optimizer_passes_succeeded': True},
                          maps={'connectivity_validation': {'passed': True, 'policy': runner.POLICY}})
        else:
            report.update(failed_phase='solve' if numerical else 'independent_polygon_validation_and_map_export',
                          optimizer_failure={'plan_returned': False},
                          error='DistrictingOptimizationError: test iteration limit' if numerical else 'ValueError: bad geometry')
        for name, value in [('benchmark.json', report), ('progress.json', {'status': report['status']}),
                            ('preserved-file-inventory.json', inventory)]:
            (path / name).write_text(json.dumps(value))
        return path, report
    old_output, old_report = save_report(26)
    (output / 'districts-26.log').write_text('preserved failure log')
    original = {'status': 'stopped', 'finished_at': 'finished', 'pid': 123, 'code_sha256': code,
                'jobs': [{'district_count': 26, 'status': 'failed', 'exit_code': 1, 'pid': 456,
                          'benchmark_sha256': runner.sha256(old_output / 'benchmark.json')},
                         *[{'district_count': k, 'status': 'pending'} for k in runner.COUNTS]]}
    (output / 'run.json').write_text(json.dumps(original))
    return output, old_report, code, save_report


def test_admission_preserves_original_and_refuses_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output, *_ = fixture(tmp_path, monkeypatch)
    original = (output / 'run.json').read_bytes()
    data, _ = runner.admit()
    assert [job['district_count'] for job in data['jobs']] == [35, 42, 61]
    assert data['original_run_manifest']['sha256'] == runner.sha256(output / 'run.json')
    assert (output / 'run.json').read_bytes() == original
    with pytest.raises(FileExistsError):
        runner.admit()


@pytest.mark.parametrize('obstacle', ['active_pid', 'old_output', 'old_log', 'changed_code'])
def test_ambiguous_admission_is_rejected(obstacle, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output, *_ = fixture(tmp_path, monkeypatch)
    if obstacle == 'active_pid':
        monkeypatch.setattr(runner, 'process_is_running', lambda pid: True)
    elif obstacle == 'old_output':
        (output / 'states/36/districts-35').mkdir()
    elif obstacle == 'old_log':
        (output / 'districts-35.log').write_text('earlier attempt')
    else:
        (tmp_path / 'frozen.py').write_text('changed')
    with pytest.raises(ValueError):
        runner.admit()
    assert not (output / 'supplemental-first-attempts.json').exists()


@pytest.mark.parametrize('defect', ['wrong_exit', 'nonnumerical_failure', 'preservation_failure', 'unfinished_progress'])
def test_child_validation_blocks_ambiguity(defect, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output, baseline, code, save = fixture(tmp_path, monkeypatch)
    path, report = save(35, numerical=defect != 'nonnumerical_failure')
    exit_code = 0 if defect == 'wrong_exit' else 1
    if defect == 'preservation_failure':
        report['preservation_audit']['source_archive_byte_identical'] = False
        (path / 'benchmark.json').write_text(json.dumps(report))
    if defect == 'unfinished_progress':
        (path / 'progress.json').write_text('{"status":"running"}')
    with pytest.raises(ValueError):
        runner.validate_terminal_report(path, 35, exit_code, code, baseline)


def test_verified_numerical_failure_continues_serial_unstarted_anchors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    output, _, _, save = fixture(tmp_path, monkeypatch)
    original = (output / 'run.json').read_bytes()
    launches, waits = [], []
    active = [False]
    def launch(command, *, cwd, stdout, stderr):
        assert not active[0]
        active[0] = True
        count = int(command[command.index('--district-count') + 1])
        launches.append(count)
        stdout.write(f'K{count}'.encode())
        class Child:
            pid = count + 1000
            def wait(self):
                active[0] = False
                waits.append(count)
                save(count, success=count != 35)
                return 1 if count == 35 else 0
        return Child()
    monkeypatch.setattr(runner.subprocess, 'Popen', launch)
    runner.main()
    assert launches == waits == [35, 42, 61]
    assert (output / 'run.json').read_bytes() == original
    data = json.loads((output / 'supplemental-first-attempts.json').read_text())
    assert data['status'] == 'complete'
    assert data['outcome_counts'] == {'complete': 2, 'numerical_failure': 1}
    assert data['original_attempt_preserved_byte_identically']
    assert all(job['terminal_validation']['passed'] for job in data['jobs'])
