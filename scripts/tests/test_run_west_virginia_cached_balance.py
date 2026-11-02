"""Synthetic admission, equivalence, and acceptance checks; no real state jobs."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import io
import json
from types import SimpleNamespace
import zipfile

import pytest
import shapefile

from scripts import run_west_virginia_cached_balance as runner


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def suite_fixture(tmp_path, monkeypatch):
    output, diag = tmp_path / 'suite', tmp_path / 'diagnostic'
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'OUTPUT', output)
    monkeypatch.setattr(runner, 'DIAG', diag)
    monkeypatch.setattr(runner, 'RUNTIME', ())
    monkeypatch.setattr(runner, 'protected_paths', lambda: set())
    monkeypatch.setattr(runner, 'state_execution_lock', lambda state: nullcontext())
    save(output / 'baseline-code.json', {})
    save(output / 'prelaunch-validation.json', {'status': 'passed'})
    save(diag / 'probe-assignments.json', {'code_sha256': {}})
    events = []

    def popen(command, **kwargs):
        stage = command[command.index('--stage') + 1]
        events.append(('start', stage))
        assert kwargs['stdout'] is not None
        assert kwargs['stderr'] == runner.subprocess.STDOUT
        return SimpleNamespace(pid=100 + len(events), wait=lambda: events.append(('wait', stage)) or 0)

    def terminal(job, run):
        assert events[-1] == ('wait', job['id'])
        events.append(('validate', job['id']))
        job['report_sha256'] = 'selected-terminal-report'
        return {'status': 'complete'}

    def compare():
        assert events[-1] == ('validate', 'cached-100')
        events.append(('equivalence', 'passed'))
        return {'passed': True}

    monkeypatch.setattr(runner.subprocess, 'Popen', popen)
    monkeypatch.setattr(runner, 'validate_terminal', terminal)
    monkeypatch.setattr(runner, 'compare_verification', compare)
    return output, events


def test_parent_waits_for_both_verified_children_and_equivalence_before_continuation(tmp_path, monkeypatch):
    output, events = suite_fixture(tmp_path, monkeypatch)
    runner.run_suite()
    assert events == [
        ('start', 'traversal-100'), ('wait', 'traversal-100'), ('validate', 'traversal-100'),
        ('start', 'cached-100'), ('wait', 'cached-100'), ('validate', 'cached-100'),
        ('equivalence', 'passed'),
        ('start', 'continuation'), ('wait', 'continuation'), ('validate', 'continuation'),
    ]
    manifest = runner.read(output / 'run.json')
    assert manifest['status'] == 'complete' and manifest['preservation_unchanged'] is True
    assert all(job['status'] == 'complete' and job['returncode'] == 0 for job in manifest['jobs'])


def test_equivalence_failure_never_starts_larger_attempt(tmp_path, monkeypatch):
    output, events = suite_fixture(tmp_path, monkeypatch)
    def mismatch():
        raise ValueError('ordered move disagreement')
    monkeypatch.setattr(runner, 'compare_verification', mismatch)
    with pytest.raises(ValueError, match='move disagreement'):
        runner.run_suite()
    assert ('start', 'continuation') not in events
    manifest = runner.read(output / 'run.json')
    assert manifest['status'] == 'failed'
    assert manifest['jobs'][2]['status'] == 'pending'


def test_uncertain_terminal_child_stops_queue_after_wait(tmp_path, monkeypatch):
    output, events = suite_fixture(tmp_path, monkeypatch)
    def ambiguous(*args):
        raise ValueError('terminal geometry unavailable')
    monkeypatch.setattr(runner, 'validate_terminal', ambiguous)
    with pytest.raises(ValueError, match='geometry unavailable'):
        runner.run_suite()
    assert events == [('start', 'traversal-100'), ('wait', 'traversal-100')]
    manifest = runner.read(output / 'run.json')
    assert manifest['status'] == 'failed'
    assert manifest['jobs'][0]['status'] == 'failed_or_ambiguous'
    assert manifest['jobs'][1]['status'] == 'pending'


@pytest.mark.parametrize('prior', ['run.json', 'traversal-100.log', 'verification/cached-100'])
def test_existing_attempt_or_log_is_preserved_before_launch(prior, tmp_path, monkeypatch):
    output, events = suite_fixture(tmp_path, monkeypatch)
    path = output / prior
    if '.' in path.name:
        path.write_bytes(b'preserved evidence')
    else:
        path.mkdir(parents=True)
        (path / 'evidence').write_bytes(b'preserved evidence')
    with pytest.raises(FileExistsError):
        runner.run_suite()
    assert events == []
    assert (path if path.is_file() else path / 'evidence').read_bytes() == b'preserved evidence'


def test_admission_rechecks_after_acquiring_state_lock(tmp_path, monkeypatch):
    output, events = suite_fixture(tmp_path, monkeypatch)
    @contextmanager
    def lock(state):
        (output / 'run.json').write_bytes(b'another admitted owner')
        yield
    monkeypatch.setattr(runner, 'state_execution_lock', lock)
    with pytest.raises(FileExistsError):
        runner.run_suite()
    assert not events
    assert (output / 'run.json').read_bytes() == b'another admitted owner'


def test_metadata_failure_still_waits_for_launched_child(tmp_path, monkeypatch):
    output, events = suite_fixture(tmp_path, monkeypatch)
    original = runner.write_json
    def write(path, value):
        if path.name == 'run.json' and value['jobs'][0].get('pid') and not value.get('finished_at'):
            raise PermissionError('simulated sharing conflict')
        original(path, value)
    monkeypatch.setattr(runner, 'write_json', write)
    with pytest.raises(PermissionError):
        runner.run_suite()
    assert events == [('start', 'traversal-100'), ('wait', 'traversal-100')]
    manifest = runner.read(output / 'run.json')
    assert manifest['status'] == 'failed' and manifest['jobs'][0]['returncode'] == 0


def test_terminal_manifest_failure_preserves_emergency_record(tmp_path, monkeypatch):
    output, events = suite_fixture(tmp_path, monkeypatch)
    original = runner.write_json
    def write(path, value):
        if path.name == 'run.json' and value.get('finished_at'):
            raise PermissionError('simulated final metadata conflict')
        original(path, value)
    monkeypatch.setattr(runner, 'write_json', write)
    with pytest.raises(PermissionError):
        runner.run_suite()
    emergency, = output.glob('emergency-*.json')
    manifest = runner.read(emergency)
    assert manifest['status'] == 'complete'
    assert all(job['returncode'] == 0 for job in manifest['jobs'])
    assert events[-1] == ('validate', 'continuation')


def terminal_fixture(tmp_path, monkeypatch, stage='cached-100'):
    output, original = tmp_path / 'suite', tmp_path / 'original'
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'OUTPUT', output)
    monkeypatch.setattr(runner, 'ORIGINAL', original)
    save(original / 'solver-result.json', {'assignments': {'a': 0, 'b': 1, 'c': 2}})
    save(original / 'benchmark.json', {'status': 'complete'})
    relative, cached, limit, chunk = runner.STAGES[stage]
    directory = output / relative
    for name in ('solver-result.json', 'move-audit.json', 'trace.json'):
        save(directory / name, {'saved': name})
    accepted = stage == 'continuation'
    report = {
        'status': 'complete', 'stage': stage, 'state_fips': '54', 'district_count': 3,
        'house_sizes': [574], 'pid': 123, 'finished_at': 'finished',
        'config': {'cache_connectivity': cached, 'max_additional_moves': limit, 'chunk_size': chunk},
        'code_sha256': {}, 'preservation_unchanged': True,
        'source': {'archive_sha256': runner.diagnostic.SOURCE_SHA},
        'original_run': {'assignments_sha256': runner.sha256(original / 'solver-result.json'),
            'benchmark_sha256': runner.sha256(original / 'benchmark.json')},
        'rebalance_seconds': 1.0, 'timed_pipeline_wall_seconds': 2.0,
        'peak_process_working_set_bytes': 1000000, 'rebalance_move_count': 100,
        'repair_move_count': 0, 'accepted_map': accepted,
        'final_plan': {'shared_edge_components': [1, 1, 1], 'total_population': runner.diagnostic.TOTAL},
    }
    if accepted:
        report.update(maps={'strict_validation': {'passed': True}},
            coverage_validation={'exact_original_union_preserved': True}, matched_verified_prefix=True)
        save(directory / 'maps/map-manifest.json', report['maps'])
        (directory / 'maps/districts-full.geojson.gz').write_bytes(b'hashed synthetic map payload')
        (directory / 'index.html').write_text('synthetic viewer')
    report['artifact_sha256'] = {p.relative_to(directory).as_posix(): runner.sha256(p)
        for p in directory.rglob('*') if p.is_file()}
    progress = {'status': 'complete', 'finished_at': 'finished',
        'rebalance_move_count': 100, 'accepted_map': accepted}
    job = {'id': stage, 'report': relative + '/benchmark.json', 'returncode': 0}
    return directory, job, {'code_sha256': {}}, report, progress


def validate_fixture(directory, job, run, report, progress):
    save(directory / 'benchmark.json', report)
    save(directory / 'progress.json', progress)
    return runner.validate_terminal(job, run)


@pytest.mark.parametrize('stage', ['cached-100', 'continuation'])
def test_terminal_selection_requires_valid_complete_artifacts(stage, tmp_path, monkeypatch):
    args = terminal_fixture(tmp_path, monkeypatch, stage)
    report = validate_fixture(*args)
    assert report['accepted_map'] is (stage == 'continuation')
    assert args[1]['report_sha256'] == runner.sha256(args[0] / 'benchmark.json')
    assert args[1]['child_pid'] == 123


@pytest.mark.parametrize('mutation', [
    'exit_code', 'status', 'stage', 'path', 'settings', 'code', 'preservation',
    'state', 'district_count', 'house', 'source', 'checkpoint', 'baseline_report',
    'runtime_nan', 'memory_zero', 'runtime_bool', 'finished', 'progress',
    'progress_count', 'progress_acceptance', 'artifact_hash', 'missing_artifact',
    'artifact_escape', 'repair', 'graph', 'population', 'verification_published',
])
def test_terminal_validator_rejects_ambiguous_or_changed_evidence(mutation, tmp_path, monkeypatch):
    directory, job, run, report, progress = terminal_fixture(tmp_path, monkeypatch)
    if mutation == 'exit_code': job['returncode'] = 1
    elif mutation == 'status': report['status'] = 'running'
    elif mutation == 'stage': report['stage'] = 'traversal-100'
    elif mutation == 'path': job['report'] = 'unselected/benchmark.json'
    elif mutation == 'settings': report['config']['max_additional_moves'] = 1000
    elif mutation == 'code': report['code_sha256'] = {'unexpected.py': 'hash'}
    elif mutation == 'preservation': report['preservation_unchanged'] = False
    elif mutation == 'state': report['state_fips'] = '12'
    elif mutation == 'district_count': report['district_count'] = 4
    elif mutation == 'house': report['house_sizes'] = [435]
    elif mutation == 'source': report['source']['archive_sha256'] = 'changed'
    elif mutation == 'checkpoint': report['original_run']['assignments_sha256'] = 'changed'
    elif mutation == 'baseline_report': report['original_run']['benchmark_sha256'] = 'changed'
    elif mutation == 'runtime_nan': report['rebalance_seconds'] = float('nan')
    elif mutation == 'memory_zero': report['peak_process_working_set_bytes'] = 0
    elif mutation == 'runtime_bool': report['timed_pipeline_wall_seconds'] = True
    elif mutation == 'finished': report['finished_at'] = ''
    elif mutation == 'progress': progress['status'] = 'running'
    elif mutation == 'progress_count': progress['rebalance_move_count'] = 99
    elif mutation == 'progress_acceptance': progress['accepted_map'] = True
    elif mutation == 'artifact_hash': (directory / 'trace.json').write_text('changed')
    elif mutation == 'missing_artifact': report['artifact_sha256'].pop('trace.json')
    elif mutation == 'artifact_escape': report['artifact_sha256']['../outside.json'] = 'wrong'
    elif mutation == 'repair': report['repair_move_count'] = 1
    elif mutation == 'graph': report['final_plan']['shared_edge_components'] = [1, 1, 2]
    elif mutation == 'population': report['final_plan']['total_population'] += 1
    elif mutation == 'verification_published': report['accepted_map'] = progress['accepted_map'] = True
    with pytest.raises(ValueError):
        validate_fixture(directory, job, run, report, progress)


@pytest.mark.parametrize('mutation', ['accepted', 'geometry', 'coverage', 'prefix', 'map_artifact'])
def test_correction_cannot_be_accepted_without_geometry_and_provenance(mutation, tmp_path, monkeypatch):
    directory, job, run, report, progress = terminal_fixture(tmp_path, monkeypatch, 'continuation')
    if mutation == 'accepted': report['accepted_map'] = progress['accepted_map'] = False
    elif mutation == 'geometry': report['maps']['strict_validation']['passed'] = False
    elif mutation == 'coverage': report['coverage_validation']['exact_original_union_preserved'] = False
    elif mutation == 'prefix': report['matched_verified_prefix'] = False
    elif mutation == 'map_artifact': report['artifact_sha256'].pop('maps/districts-full.geojson.gz')
    with pytest.raises(ValueError):
        validate_fixture(directory, job, run, report, progress)


def verification_fixture(tmp_path, monkeypatch):
    output, diag = tmp_path / 'suite', tmp_path / 'diag'
    monkeypatch.setattr(runner, 'OUTPUT', output)
    monkeypatch.setattr(runner, 'DIAG', diag)
    moves = [{'units': [index], 'source_district': 0, 'target_district': 1,
              'population': 1, 'geoids': [f'unit-{index}']} for index in range(100)]
    assignments = {f'unit-{i}': 1 for i in range(100)}
    for stage in ('traversal-100', 'cached-100'):
        path = output / runner.STAGES[stage][0]
        save(path / 'benchmark.json', {'rebalance_seconds': 20. if stage == 'traversal-100' else 2., 'stop_reason': 'max_moves'})
        save(path / 'move-audit.json', {'rebalance_moves': moves})
        save(path / 'solver-result.json', {'assignments': assignments})
    save(diag / 'probe-moves.json', {'moves': moves})
    save(diag / 'probe-assignments.json', {'assignments': assignments})
    return output, diag, moves, assignments


def test_matched_comparison_preserves_sequence_endpoint_and_stop(tmp_path, monkeypatch):
    output, _, _, _ = verification_fixture(tmp_path, monkeypatch)
    result = runner.compare_verification()
    assert result['passed'] and result['matches_preserved_probe']
    assert result['ordered_moves_equal'] and result['assignments_equal'] and result['stop_reasons_equal']
    assert result['measured_speedup'] == 10.
    assert runner.read(output / 'verification/equivalence.json') == result


@pytest.mark.parametrize('change', ['order', 'population', 'preserved_move', 'count', 'endpoint', 'preserved_endpoint', 'stop'])
def test_equivalence_requires_exact_ordered_moves_and_original_probe(change, tmp_path, monkeypatch):
    output, diag, moves, assignments = verification_fixture(tmp_path, monkeypatch)
    cached = output / runner.STAGES['cached-100'][0]
    if change == 'order':
        moves[0], moves[1] = moves[1], moves[0]
        save(cached / 'move-audit.json', {'rebalance_moves': moves})
    elif change == 'population':
        moves[0]['population'] = 2
        save(cached / 'move-audit.json', {'rebalance_moves': moves})
    elif change == 'preserved_move':
        moves[0]['geoids'] = ['changed']
        save(diag / 'probe-moves.json', {'moves': moves})
    elif change == 'count': save(cached / 'move-audit.json', {'rebalance_moves': moves[:-1]})
    elif change in ('endpoint', 'preserved_endpoint'):
        assignments['unit-0'] = 0
        target = cached / 'solver-result.json' if change == 'endpoint' else diag / 'probe-assignments.json'
        save(target, {'assignments': assignments})
    elif change == 'stop': save(cached / 'benchmark.json', {'rebalance_seconds': 2., 'stop_reason': 'local_optimum'})
    with pytest.raises(ValueError):
        runner.compare_verification()
    assert not (output / 'verification/equivalence.json').exists()


def original_fixture(tmp_path, monkeypatch):
    original = tmp_path / 'original'; original.mkdir()
    archive = tmp_path / 'tl_2020_54_tabblock20.zip'
    dbf = io.BytesIO()
    with shapefile.Writer(dbf=dbf) as writer:
        writer.field('GEOID20', 'C', size=15)
        writer.field('POP20', 'N', size=10)
        for geoid, pop in [('540010001001001', 50), ('540010001001002', 30), ('540010001001003', 20)]:
            writer.record(geoid, pop)
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr(archive.stem + '.dbf', dbf.getvalue())
        for ext in ('.shp', '.shx', '.prj'): zipped.writestr(archive.stem + ext, b'only DBF is read here')
    source_hash = runner.sha256(archive)
    monkeypatch.setattr(runner, 'ORIGINAL', original)
    monkeypatch.setattr(runner, 'ARCHIVE', archive)
    monkeypatch.setattr(runner.diagnostic, 'SOURCE_SHA', source_hash)
    monkeypatch.setattr(runner.diagnostic, 'BLOCKS', 3)
    monkeypatch.setattr(runner.diagnostic, 'TOTAL', 100)
    graph, info, identity = ((1,), (0, 2), (1,)), {'multipart_block_count': 0}, {'source': source_hash}
    monkeypatch.setattr(runner, '_identity', lambda geoids, source: identity)
    monkeypatch.setattr(runner, '_read_cache', lambda path, supplied: (graph, info))
    assignments = {'540010001001001': 0, '540010001001002': 1, '540010001001003': 2}
    save(original / 'solver-result.json', {'assignments': assignments})
    report = {'status': 'complete', 'maps': {'strict_validation': {'passed': True}},
        'source': {'archive_sha256': source_hash}, 'graph': info,
        'graph_cache': {'identity': identity, 'path': 'synthetic-cache.npz'},
        'artifact_sha256': {'solver-result.json': runner.sha256(original / 'solver-result.json')}}
    save(original / 'benchmark.json', report)
    return original, report


def test_original_loader_checks_independent_dbf_populations_and_saved_source_order(tmp_path, monkeypatch):
    original_fixture(tmp_path, monkeypatch)
    _, geoids, pops, graph, labels = runner.load_original()
    assert len(geoids) == 3 and pops == [50, 30, 20] and labels == (0, 1, 2)
    assert graph == ((1,), (0, 2), (1,))


@pytest.mark.parametrize('change', ['source', 'checkpoint', 'graph_identity', 'multipart', 'universe'])
def test_original_loader_refuses_drift_before_any_balancing(change, tmp_path, monkeypatch):
    original, report = original_fixture(tmp_path, monkeypatch)
    if change == 'source': report['source']['archive_sha256'] = 'changed'
    elif change == 'checkpoint': (original / 'solver-result.json').write_text('changed')
    elif change == 'graph_identity': report['graph_cache']['identity'] = {'changed': True}
    elif change == 'multipart':
        report['graph']['multipart_block_count'] = 1
        monkeypatch.setattr(runner, '_read_cache', lambda *args: (((1,), (0, 2), (1,)), {'multipart_block_count': 1}))
    elif change == 'universe':
        save(original / 'solver-result.json', {'assignments': {'unexpected': 0}})
        report['artifact_sha256']['solver-result.json'] = runner.sha256(original / 'solver-result.json')
    save(original / 'benchmark.json', report)
    with pytest.raises(ValueError):
        runner.load_original()


def test_child_refuses_wrong_parent_token_without_creating_attempt(tmp_path, monkeypatch):
    output = tmp_path / 'suite'
    monkeypatch.setattr(runner, 'OUTPUT', output)
    save(output / 'run.json', {'status': 'running', 'jobs': [
        {'id': 'cached-100', 'status': 'running', 'token': 'owned-token'}]})
    with pytest.raises(ValueError, match='owned'):
        runner.run_child('cached-100', 'different-token')
    assert not (output / runner.STAGES['cached-100'][0]).exists()


@pytest.mark.parametrize('name', ['../escaped.json', '/absolute/escaped.json'])
def test_artifact_escape_rejected(name, tmp_path):
    with pytest.raises(ValueError, match='escapes'):
        runner.confined(tmp_path / 'child', name)
