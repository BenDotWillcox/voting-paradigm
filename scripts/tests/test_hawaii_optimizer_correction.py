"""Correction runs preserve earlier evidence and persist optimizer failures."""
from contextlib import nullcontext
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from districting import DistrictingOptimizationError, Unit
from districting import algorithm
from districting.part_connectivity import PartGraph
from scripts import benchmark_hawaii_water as benchmark


@pytest.mark.parametrize('relative', [
    'states/15/districts-2', 'policies/hawaii-water-v1/states/15/districts-2',
    'corrections/hawaii-optimizer-v1/states/15',
    'corrections/hawaii-optimizer-v1/states/15/../../../../policies/hawaii-water-v1',
])
def test_correction_cannot_target_original_evidence(relative: str) -> None:
    with pytest.raises(ValueError, match='new run below'):
        benchmark.validate_output((benchmark.SUITE / relative).resolve(), optimizer_correction=True)


def test_correction_attempt_is_never_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    output = tmp_path / 'corrections/hawaii-optimizer-v1/states/15/districts-2'
    output.mkdir(parents=True)
    original = b'{"status":"failed","error":"original evidence"}'
    (output / 'benchmark.json').write_bytes(original)
    with pytest.raises(ValueError, match='earlier attempts are preserved'):
        benchmark.run(2, output, optimizer_correction=True)
    assert (output / 'benchmark.json').read_bytes() == original


@pytest.mark.parametrize('district_count', [3, 4])
def test_additional_anchor_dispatches_as_a_correction(
    district_count: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    calls = []

    def record_run(count, output, max_moves, *, optimizer_correction):
        calls.append((count, output, max_moves, optimizer_correction))
        return {'district_count': count}

    monkeypatch.setattr(benchmark, '_run_locked', record_run)
    output = tmp_path / f'corrections/hawaii-optimizer-v1/states/15/districts-{district_count}'
    assert benchmark.run(district_count, output, optimizer_correction=True) == {
        'district_count': district_count,
    }
    assert calls == [(district_count, output.resolve(), 1000, True)]


@pytest.mark.parametrize('district_count', [3, 4])
def test_correction_preserves_originals_and_prior_k2_without_tracking_new_outputs(
    district_count: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    required = [
        suite / 'suite.json', suite / 'diagnostics/hawaii/diagnosis.json',
        suite / 'diagnostics/hawaii/components.geojson', suite / 'diagnostics/hawaii/links.geojson',
        tmp_path / '.cache/state-block-benchmark/source/15/tl_2020_15_tabblock20.zip',
        suite / 'states/15/districts-2/benchmark.json',
        *(suite / f'policies/hawaii-water-v1/states/15/districts-{k}/benchmark.json' for k in (2, 3, 4)),
        *(tmp_path / f'prompts/hawaii-water-benchmark.{suffix}' for suffix in ('md', 'json')),
        suite / 'corrections/hawaii-optimizer-v1/states/15/districts-2/benchmark.json',
        suite / 'corrections/hawaii-optimizer-v1/states/15/districts-2/maps/final.geojson.gz',
        suite / 'corrections/hawaii-optimizer-v1/baseline-code/districting/algorithm.py',
        *(suite / f'corrections/hawaii-optimizer-v1/{name}' for name in (
            'index.html', 'comparison.json', 'districts-2.log', 'hawaii-corrected-map.png')),
        *(tmp_path / f'prompts/hawaii-optimizer-fix.{suffix}' for suffix in ('md', 'json')),
    ]
    for index, path in enumerate(required):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'preserved evidence {index}', encoding='utf-8')
    original_bytes = {path: path.read_bytes() for path in required}
    active = suite / f'corrections/hawaii-optimizer-v1/states/15/districts-{district_count}/progress.json'
    active.parent.mkdir(parents=True)
    active.write_text('running', encoding='utf-8')
    before = benchmark.protected_inventory(optimizer_correction=True, district_count=district_count)
    assert set(before) == {path.relative_to(tmp_path).as_posix() for path in required}
    active.write_text('complete', encoding='utf-8')
    assert benchmark.protected_inventory(optimizer_correction=True, district_count=district_count) == before
    assert all(path.read_bytes() == content for path, content in original_bytes.items())
    prior_map = suite / 'corrections/hawaii-optimizer-v1/states/15/districts-2/maps/final.geojson.gz'
    prior_map.write_text('changed prior map', encoding='utf-8')
    assert benchmark.protected_inventory(optimizer_correction=True, district_count=district_count) != before


@pytest.mark.parametrize('district_count', [3, 4])
def test_additional_anchor_records_its_own_original_baseline(
    district_count: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark, 'ROOT', tmp_path)
    suite = tmp_path / '.cache/state-block-benchmark/suite-through-1000'
    monkeypatch.setattr(benchmark, 'SUITE', suite)
    monkeypatch.setattr(benchmark, 'CODE_PATHS', ())
    monkeypatch.setattr(benchmark, 'EXTRA_CODE', ())
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda **kwargs: {})
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    baseline_hashes = {}
    for name in ('districting/algorithm.py', 'scripts/benchmark_hawaii_water.py'):
        snapshot = suite / 'corrections/hawaii-optimizer-v1/baseline-code' / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text('preserved source: ' + name, encoding='utf-8')
        baseline_hashes[name] = benchmark.sha256(snapshot)
    for name in ('scripts/benchmark_hawaii_optimizer.py', 'districting/__init__.py'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('current source: ' + name, encoding='utf-8')
    for k in (2, 3, 4):
        original = suite / f'policies/hawaii-water-v1/states/15/districts-{k}/benchmark.json'
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_text(json.dumps({
            'state_fips': '15', 'district_count': k,
            'artifact_sha256': {'water-connections.json': f'water-policy-{k}'},
            'code_sha256': baseline_hashes,
        }), encoding='utf-8')

    def stop_before_loading(*args):
        raise RuntimeError('stop before loading source data')

    monkeypatch.setattr(benchmark, 'prepare_source', stop_before_loading)
    output = suite / f'corrections/hawaii-optimizer-v1/states/15/districts-{district_count}'
    with pytest.raises(RuntimeError, match='stop before loading source data'):
        benchmark.run(district_count, output, optimizer_correction=True)
    report = json.loads((output / 'benchmark.json').read_text())
    original = suite / f'policies/hawaii-water-v1/states/15/districts-{district_count}/benchmark.json'
    assert report['comparison_baseline'] == {
        'benchmark_path': original.relative_to(tmp_path).as_posix(),
        'benchmark_sha256': benchmark.sha256(original),
        'water_connections_sha256': f'water-policy-{district_count}',
    }
    assert {name: data['sha256'] for name, data in report['preserved_baseline_code'].items()} == baseline_hashes
    assert report['status'] == 'failed'
    assert 'final_plan' not in report


@pytest.mark.parametrize('district_count', [2, 3, 4])
def test_correction_viewer_links_matching_original_and_comparison(
    district_count: int, tmp_path: Path,
) -> None:
    benchmark.write_viewer(tmp_path, {
        'district_count': district_count,
        'run_kind': 'hawaii_optimizer_scaling_correction_v1',
        'input': {'projection': {'lon0': -157, 'lat0': 21}},
        'final_plan': {'max_absolute_deviation_percent': 0.001},
    })
    page = (tmp_path / 'index.html').read_text(encoding='utf-8')
    assert f'policies/hawaii-water-v1/states/15/districts-{district_count}/' in page
    assert f'Original {district_count}-district map' in page
    comparison = '../../../' if district_count == 2 else '../../../anchors-3-4/'
    assert f'href="{comparison}">Before / after comparison' in page


def test_optimizer_failure_is_saved_without_a_completed_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A forced SciPy failure travels through observation, domain, and runner."""
    monkeypatch.setattr(benchmark, 'SUITE', tmp_path)
    source_hash = 'unchanged-source'
    monkeypatch.setattr(benchmark, 'protected_inventory', lambda **kwargs: {
        '.cache/state-block-benchmark/source/15/tl_2020_15_tabblock20.zip': source_hash,
    })
    monkeypatch.setattr(benchmark, 'state_execution_lock', lambda state: nullcontext())
    monkeypatch.setattr(benchmark, 'prepare_source', lambda *args: (
        tmp_path / 'source.shp', {'archive_sha256': source_hash}))
    units = [Unit('a', (0., 0.), 10), Unit('b', (1000., 0.), 10)]
    monkeypatch.setattr(benchmark, 'load_units', lambda *args: (units, {'a': 10, 'b': 10}, {}))
    graph = PartGraph(((1,), (0,)), (0, 1))
    monkeypatch.setattr(benchmark, 'load_or_build_shared_edge_part_graph', lambda *args, **kwargs: (graph, {}, {}))
    monkeypatch.setattr(benchmark, 'build_hawaii_connections', lambda *args, **kwargs: (graph, (), {}))
    monkeypatch.setattr(algorithm, 'minimize', lambda *args, **kwargs: OptimizeResult(
        x=np.zeros(2), fun=0., jac=np.zeros(2), success=False, status=2,
        message='forced line-search failure', nit=0, nfev=21))
    output = tmp_path / 'policies/hawaii-water-v1/states/15/failure-witness'
    with pytest.raises(DistrictingOptimizationError, match='forced line-search failure'):
        benchmark.run(2, output)
    report = json.loads((output / 'benchmark.json').read_text())
    assert report['status'] == 'failed'
    assert report['failed_phase'] == 'solve'
    assert report['optimizer_failure'] == {
        'reason': 'unsuccessful termination', 'status': 2, 'message': 'forced line-search failure',
        'iterations': 0, 'function_evaluations': 21, 'balance_pass': 1, 'plan_returned': False,
    }
    assert report['solver_progress'][0]['inner_optimizer']['success'] is False
    assert report['finished_at'] and report['timed_pipeline_wall_seconds'] > 0
    assert 'final_plan' not in report
    assert not (output / 'solver-result.json').exists()
    assert not (output / 'index.html').exists()
    assert json.loads((output / 'progress.json').read_text())['status'] == 'failed'
