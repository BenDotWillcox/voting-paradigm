"""Preserved WV K3 cache equivalence benchmark and larger-budget continuation.

Three serial fresh processes share the same original connected assignment.
Only the third exports a corrected map, after exact trace equivalence succeeds.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import html
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import shapefile
from districting.connectivity import repair_and_rebalance
from scripts.benchmark_kansas_anchors import stage_metrics
from scripts.benchmark_kansas_blocks import Measurements, process_memory, sha256
from scripts.benchmark_state_blocks import CODE_PATHS
from scripts.correct_state_block_parts import write_json, verify_unchanged_coverage
from scripts import diagnose_west_virginia_balance as diagnostic
from scripts.district_block_graph_cache import _identity, _read_cache
from scripts.district_block_sources import _safe_members
from scripts.state_block_execution_lock import state_execution_lock
from scripts.state_block_map_export import export_state_block_maps

SUITE = diagnostic.SUITE
OUTPUT = SUITE / 'corrections/west-virginia-cached-balance-v1'
ORIGINAL = diagnostic.ORIGINAL
DIAG = diagnostic.OUTPUT
ARCHIVE = diagnostic.ARCHIVE
RUNTIME = tuple(sorted(set(CODE_PATHS) | {
    'scripts/run_west_virginia_cached_balance.py', 'scripts/diagnose_west_virginia_balance.py',
    'scripts/correct_state_block_parts.py', 'scripts/assets/state-block-viewer.html',
}))
STAGES = {
    'traversal-100': ('verification/traversal-100', False, 100, 100),
    'cached-100': ('verification/cached-100', True, 100, 100),
    'continuation': ('states/54/districts-3', True, 10_000, 500),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def inventory(paths):
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(paths)}


def protected_paths():
    paths = set(diagnostic.preservation_paths())
    paths.update(p for p in DIAG.rglob('*') if p.is_file())
    paths.update(p for p in (OUTPUT / 'baseline-code').rglob('*') if p.is_file())
    paths.add(OUTPUT / 'baseline-code.json')
    return paths


def verify_inventory(saved):
    for name, digest in saved.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha256(path) != digest:
            raise ValueError(f'Protected file changed or escaped repository: {name}')


def confined(root, name):
    path = (root / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError('Artifact path escapes its run directory.')
    return path


def load_original():
    prior = read(ORIGINAL / 'benchmark.json')
    if prior['status'] != 'complete' or not prior['maps']['strict_validation']['passed']:
        raise ValueError('Original is not a validated connected plan.')
    if sha256(ARCHIVE) != diagnostic.SOURCE_SHA or prior['source']['archive_sha256'] != diagnostic.SOURCE_SHA:
        raise ValueError('Original source archive identity changed.')
    for name, digest in prior['artifact_sha256'].items():
        if sha256(confined(ORIGINAL, name)) != digest:
            raise ValueError(f'Original checkpoint identity failed: {name}')
    with zipfile.ZipFile(ARCHIVE) as zipped:
        _safe_members(zipped, ARCHIVE.stem)
        with shapefile.Reader(dbf=io.BytesIO(zipped.read(ARCHIVE.stem + '.dbf'))) as reader:
            records = list(reader.iterRecords())
    geoids = [str(row['GEOID20']) for row in records]
    pops = [int(row['POP20']) for row in records]
    if len(geoids) != diagnostic.BLOCKS or len(set(geoids)) != len(geoids) or sum(pops) != diagnostic.TOTAL or min(pops) < 0:
        raise ValueError('Source universe or population differs.')
    identity = _identity(geoids, diagnostic.SOURCE_SHA)
    if identity != prior['graph_cache']['identity']:
        raise ValueError('Source graph identity changed.')
    graph, info = _read_cache(Path(prior['graph_cache']['path']), identity)
    if info != prior['graph'] or info['multipart_block_count'] != 0:
        raise ValueError('Expected unchanged single-part WV graph.')
    saved = read(ORIGINAL / 'solver-result.json')['assignments']
    if set(saved) != set(geoids): raise ValueError('Original block universe differs.')
    labels = tuple(saved[g] for g in geoids)
    return prior, geoids, pops, graph, labels


def audit(labels, pops, graph, geoids):
    result = stage_metrics(labels, pops, graph, geoids, n_districts=3,
        expected_population=diagnostic.TOTAL, expected_blocks=diagnostic.BLOCKS)
    if not result['all_districts_shared_edge_connected']:
        raise ValueError('Continuation lost strict shared-edge connectivity.')
    return result


def write_viewer(output, report):
    projection = report['input']['projection']
    summary = (f"CORRECTED · 3 strictly connected districts; worst population deviation "
        f"{report['final_plan']['max_absolute_deviation_people']:.3f} people. "
        f"{report['rebalance_move_count']:,} additional balancing moves; original preserved.")
    template = (ROOT / 'scripts/assets/state-block-viewer.html').read_text(encoding='utf-8')
    for key, value in {'__STATE_NAME__': 'West Virginia', '__DISTRICT_COUNT__': '3',
        '__RESULT_SUMMARY__': html.escape(summary),
        '__ANCHOR_NAVIGATION__': '<a href="../../../">Correction comparison</a> <a href="../../../../../states/54/districts-3/">Original plan</a>',
        '__LON0__': str(projection['lon0']), '__LAT0__': str(projection['lat0'])}.items():
        template = template.replace(key, value)
    (output / 'index.html').write_text(template, encoding='utf-8')


def run_child(stage, token):
    run = read(OUTPUT / 'run.json')
    job = next(j for j in run['jobs'] if j['id'] == stage)
    if run['status'] != 'running' or job['status'] != 'running' or token != job['token']:
        raise ValueError('Child is not owned by the active parent.')
    relative, cached, limit, chunk = STAGES[stage]
    output = OUTPUT / relative
    if output.exists(): raise FileExistsError('Attempt directory already exists; do not overwrite.')
    output.mkdir(parents=True)
    started = time.perf_counter(); measure = Measurements()
    report = {'status': 'running', 'stage': stage, 'pid': os.getpid(), 'started_at': now(),
        'state': 'West Virginia', 'state_fips': '54', 'district_count': 3, 'house_sizes': [574],
        'config': {'cache_connectivity': cached, 'max_additional_moves': limit, 'chunk_size': chunk},
        'accepted_map': False, 'numerical_solver_rerun': False, 'full_end_to_end_run': False,
        'code_sha256': run['code_sha256'], 'artifact_sha256': {},
        'measurement_notes': ['Fresh serial process; no guard profiling.',
            'Balancing starts from the original 1000-move connected endpoint.',
            'Correction time includes source verification, checkpoints, strict audits and map export; no new power solve.',
            '500-move continuation checkpoints restart bookkeeping without changing the deterministic move sequence.']}
    write_json(output / 'benchmark.json', report)
    try:
        verify_inventory(run['code_sha256'])
        verify_inventory(read(OUTPUT / 'preserved-file-inventory.json'))
        with measure.phase('load_and_verify_source_graph'):
            prior, geoids, pops, graph, labels = load_original()
            report.update(source=prior['source'], input=prior['input'], graph_cache=prior['graph_cache'],
                original_run={'path': str(ORIGINAL), 'benchmark_sha256': sha256(ORIGINAL / 'benchmark.json'),
                    'assignments_sha256': sha256(ORIGINAL / 'solver-result.json')})
            report['initial_plan'] = audit(labels, pops, graph, geoids)
            if report['initial_plan']['district_populations'] != prior['final_plan']['district_populations']:
                raise ValueError('Original population reconciliation failed.')
        initial = labels; moves = []; trace = [{'moves': 0, 'populations': report['initial_plan']['district_populations'],
            'max_deviation_people': report['initial_plan']['max_absolute_deviation_people'],
            'max_deviation_percent': report['initial_plan']['max_absolute_deviation_percent']}]
        rebalance_seconds = 0.; chunks = []; stop_reason = 'max_moves'
        while len(moves) < limit:
            count = min(chunk, limit - len(moves))
            with measure.phase(f'balance_chunk_{len(chunks) + 1}'):
                before = time.perf_counter()
                result = repair_and_rebalance(graph, labels, pops, n_districts=3,
                    max_moves=count, cache_connectivity=cached)
                elapsed = time.perf_counter() - before
            rebalance_seconds += elapsed
            if result.repair_moves or result.repaired_assignments != labels:
                raise ValueError('Already connected input unexpectedly needed repair.')
            new = [{**asdict(m), 'units': list(m.units), 'geoids': [geoids[u] for u in m.units]} for m in result.rebalance_moves]
            totals = audit(labels, pops, graph, geoids)['district_populations']
            replayed, _ = diagnostic.replay(labels, totals, new, pops, geoids, trace, len(moves), improving=True)
            if replayed != result.assignments: raise ValueError('Saved move replay failed.')
            labels = result.assignments; moves.extend(new); stop_reason = result.stop_reason
            current = audit(labels, pops, graph, geoids)
            chunks.append({'moves': len(new), 'cumulative_additional_moves': len(moves), 'wall_seconds': elapsed,
                'stop_reason': stop_reason, 'max_absolute_deviation_people': current['max_absolute_deviation_people']})
            checkpoint = {'assignments': dict(zip(geoids, labels, strict=True)), 'additional_moves': len(moves),
                'status': 'checkpoint_not_accepted', 'source_sha256': diagnostic.SOURCE_SHA}
            write_json(output / f'checkpoint-{len(moves):05d}.json', checkpoint)
            write_json(output / 'progress.json', {'status': 'running', 'stage': stage, 'chunks': chunks,
                'additional_moves': len(moves), 'population_metrics': current})
            print(json.dumps(chunks[-1]), flush=True)
            if stop_reason == 'local_optimum': break
            if not new: raise ValueError('No moves despite nonterminal balancing result.')
        report.update(final_plan=current, rebalance_move_count=len(moves), repair_move_count=0,
            stop_reason=stop_reason, rebalance_seconds=rebalance_seconds, chunks=chunks)
        write_json(output / 'solver-result.json', {'plan_kind': 'cached_connectivity_continuation',
            'assignments': dict(zip(geoids, labels, strict=True)), 'source_sha256': diagnostic.SOURCE_SHA,
            'original_assignments_sha256': report['original_run']['assignments_sha256']})
        write_json(output / 'move-audit.json', {'repair_moves': [], 'rebalance_moves': moves,
            'original_cumulative_moves': 1000, 'total_cumulative_moves': 1000 + len(moves)})
        write_json(output / 'trace.json', trace)
        if stage == 'continuation':
            prefix = read(OUTPUT / STAGES['cached-100'][0] / 'move-audit.json')['rebalance_moves']
            if moves[:100] != prefix: raise ValueError('Larger run did not reproduce verified 100-move prefix.')
            report['matched_verified_prefix'] = True
            with measure.phase('independent_polygon_validation_and_map_export'):
                extract = output / 'source-extracted'; extract.mkdir()
                with zipfile.ZipFile(ARCHIVE) as zipped:
                    for member in _safe_members(zipped, ARCHIVE.stem):
                        # Whitelisted flat names, confined to this new attempt.
                        with zipped.open(member) as source, confined(extract, member.filename).open('wb') as target:
                            while data := source.read(1_048_576): target.write(data)
                report['maps'] = export_state_block_maps(extract / (ARCHIVE.stem + '.shp'),
                    dict(zip(geoids, labels, strict=True)), dict(zip(geoids, pops, strict=True)), output / 'maps',
                    state_fips='54', state_name='West Virginia', n_districts=3)
            with measure.phase('verify_exact_original_coverage'):
                report['coverage_validation'] = verify_unchanged_coverage(ORIGINAL / 'maps', output / 'maps')
            report['accepted_map'] = True
            write_viewer(output, report)
        verify_inventory(run['code_sha256'])
        verify_inventory(read(OUTPUT / 'preserved-file-inventory.json'))
        report['preservation_unchanged'] = True
        report['artifact_sha256'] = {p.relative_to(output).as_posix(): sha256(p) for p in output.rglob('*')
            if p.is_file() and p.name not in ('benchmark.json', 'progress.json') and 'source-extracted' not in p.parts}
        report['status'] = 'complete'
    except BaseException as error:
        report.update(status='failed', accepted_map=False, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        measure.close()
        report.update(phases=measure.phases, timed_pipeline_wall_seconds=time.perf_counter() - started,
            peak_process_working_set_bytes=process_memory()[1], finished_at=now())
        write_json(output / 'benchmark.json', report)
        write_json(output / 'progress.json', {'status': report['status'], 'accepted_map': report['accepted_map'],
            'rebalance_move_count': report.get('rebalance_move_count'), 'finished_at': report['finished_at']})


def validate_terminal(job, run):
    canonical = STAGES[job['id']][0] + '/benchmark.json'
    if job['report'] != canonical: raise ValueError('Terminal report path differs from admitted stage.')
    report_path = confined(OUTPUT, job['report'])
    report = read(report_path)
    if job['returncode'] != 0 or report['status'] != 'complete' or report['stage'] != job['id']:
        raise ValueError('Child did not exit with a matching complete terminal report.')
    _, cached, count, chunk = STAGES[job['id']]
    if report['config'] != {'cache_connectivity': cached, 'max_additional_moves': count, 'chunk_size': chunk}:
        raise ValueError('Child settings differ from admitted configuration.')
    if report['code_sha256'] != run['code_sha256'] or report.get('preservation_unchanged') is not True:
        raise ValueError('Child code/preservation validation failed.')
    if (report.get('state_fips'), report.get('district_count'), report.get('house_sizes')) != ('54', 3, [574]):
        raise ValueError('Child state/anchor identity differs.')
    if report['source']['archive_sha256'] != diagnostic.SOURCE_SHA or report['original_run']['assignments_sha256'] != sha256(ORIGINAL / 'solver-result.json'):
        raise ValueError('Child source/checkpoint provenance differs.')
    if report['original_run']['benchmark_sha256'] != sha256(ORIGINAL / 'benchmark.json'):
        raise ValueError('Original benchmark provenance differs.')
    for key in ('rebalance_seconds', 'timed_pipeline_wall_seconds', 'peak_process_working_set_bytes'):
        value = report.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'Invalid terminal measurement: {key}')
    progress = read(report_path.parent / 'progress.json')
    if (not report.get('finished_at') or progress.get('status') != 'complete'
            or progress.get('finished_at') != report['finished_at']
            or progress.get('rebalance_move_count') != report['rebalance_move_count']
            or progress.get('accepted_map') is not report['accepted_map']):
        raise ValueError('Final progress and report do not agree.')
    for name, digest in report['artifact_sha256'].items():
        if sha256(confined(report_path.parent, name)) != digest: raise ValueError('Child artifact hash changed.')
    required = {'solver-result.json', 'move-audit.json', 'trace.json'}
    if not required.issubset(report['artifact_sha256']): raise ValueError('Required final artifacts missing.')
    if report['repair_move_count'] != 0 or report['final_plan']['shared_edge_components'] != [1, 1, 1]:
        raise ValueError('Child graph/repair invariant failed.')
    if report['final_plan']['total_population'] != diagnostic.TOTAL:
        raise ValueError('Child population differs from source.')
    if job['id'] == 'continuation' and (not report.get('accepted_map') or not report['maps']['strict_validation']['passed']
            or not report['coverage_validation']['exact_original_union_preserved'] or not report['matched_verified_prefix']):
        raise ValueError('Correction lacks strict geometry/prefix/coverage acceptance.')
    if job['id'] == 'continuation' and not {'maps/map-manifest.json', 'maps/districts-full.geojson.gz', 'index.html'}.issubset(report['artifact_sha256']):
        raise ValueError('Correction lacks hashed map artifacts.')
    if job['id'] != 'continuation' and report.get('accepted_map') is not False:
        raise ValueError('Verification-only child cannot publish an accepted map.')
    job['report_sha256'] = sha256(report_path)
    job['child_pid'] = report['pid']
    return report


def compare_verification():
    paths = [OUTPUT / STAGES[name][0] for name in ('traversal-100', 'cached-100')]
    reports = [read(p / 'benchmark.json') for p in paths]
    moves = [read(p / 'move-audit.json')['rebalance_moves'] for p in paths]
    assignments = [read(p / 'solver-result.json')['assignments'] for p in paths]
    preserved = read(DIAG / 'probe-moves.json')['moves']
    old_assignments = read(DIAG / 'probe-assignments.json')['assignments']
    if moves[0] != moves[1] or moves[0] != preserved or len(moves[0]) != 100:
        raise ValueError('Cached/traversal/preserved ordered moves differ.')
    if assignments[0] != assignments[1] or assignments[0] != old_assignments:
        raise ValueError('Cached/traversal/preserved endpoints differ.')
    if reports[0]['stop_reason'] != reports[1]['stop_reason'] or reports[0]['stop_reason'] != 'max_moves':
        raise ValueError('Matched run stopping conditions differ.')
    result = {'passed': True, 'ordered_moves_equal': True, 'assignments_equal': True,
        'stop_reasons_equal': True, 'matches_preserved_probe': True, 'move_count': 100,
        'fresh_processes': True, 'profiling_enabled': False,
        'traversal_seconds': reports[0]['rebalance_seconds'], 'cached_seconds': reports[1]['rebalance_seconds'],
        'measured_speedup': reports[0]['rebalance_seconds'] / reports[1]['rebalance_seconds'],
        'notes': 'Single serial matched-input timing per mode; not a repeated statistical benchmark.'}
    write_json(OUTPUT / 'verification/equivalence.json', result)
    return result


def refuse_prior_attempt():
    if (OUTPUT / 'run.json').exists(): raise FileExistsError('An admitted suite already exists; never duplicate it.')
    if any((OUTPUT / spec[0]).exists() for spec in STAGES.values()):
        raise FileExistsError('An earlier child attempt exists.')
    if any((OUTPUT / f'{name}.log').exists() for name in STAGES):
        raise FileExistsError('An earlier child log exists; preserve the partial attempt.')


def run_suite():
    refuse_prior_attempt()
    with state_execution_lock('54'):
        refuse_prior_attempt()
        before = inventory(protected_paths())
        baseline = read(OUTPUT / 'baseline-code.json')
        probe_code = read(DIAG / 'probe-assignments.json')['code_sha256']
        for name, entry in baseline.items():
            if sha256(ROOT / entry['snapshot']) != entry['sha256'] or entry['sha256'] != probe_code[name]:
                raise ValueError('Preserved implementation differs from diagnostic baseline.')
        validation = read(OUTPUT / 'prelaunch-validation.json')
        if validation['status'] != 'passed': raise ValueError('Prelaunch validation not passed.')
        write_json(OUTPUT / 'preserved-file-inventory.json', before)
        run = {'status': 'running', 'pid': os.getpid(), 'started_at': now(),
            'preservation_inventory': 'preserved-file-inventory.json', 'code_sha256': inventory([ROOT / name for name in RUNTIME]),
            'prelaunch_validation_sha256': sha256(OUTPUT / 'prelaunch-validation.json'),
            'jobs': [{'id': key, 'status': 'pending', 'report': value[0] + '/benchmark.json'} for key, value in STAGES.items()]}
        start = time.perf_counter(); write_json(OUTPUT / 'run.json', run)
        try:
            for job in run['jobs']:
                verify_inventory(before); verify_inventory(run['code_sha256'])
                job.update(status='running', token=uuid.uuid4().hex, started_at=now())
                write_json(OUTPUT / 'run.json', run)
                child_start = time.perf_counter()
                with (OUTPUT / f"{job['id']}.log").open('xb') as log:
                    process = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__)),
                        '--stage', job['id'], '--token', job['token']], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                    try:
                        job['pid'] = process.pid
                        write_json(OUTPUT / 'run.json', run)
                    finally:
                        # A metadata write cannot orphan/duplicate an already launched child.
                        job['returncode'] = process.wait()
                        job['elapsed_seconds'] = time.perf_counter() - child_start
                        job['finished_at'] = now()
                validate_terminal(job, run)
                job['status'] = 'complete'
                if job['id'] == 'cached-100': run['equivalence'] = compare_verification()
                write_json(OUTPUT / 'run.json', run)
            verify_inventory(before); verify_inventory(run['code_sha256'])
            run.update(status='complete', preservation_unchanged=True)
        except BaseException as error:
            run.update(status='failed', error=f'{type(error).__name__}: {error}')
            for job in run['jobs']:
                if job['status'] == 'running': job['status'] = 'failed_or_ambiguous'
            raise
        finally:
            run.update(finished_at=now(), elapsed_seconds=time.perf_counter() - start)
            try:
                write_json(OUTPUT / 'run.json', run)
            except BaseException:
                (OUTPUT / f'emergency-{os.getpid()}.json').write_text(json.dumps(run, indent=2), encoding='utf-8')
                raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=list(STAGES))
    parser.add_argument('--token')
    args = parser.parse_args()
    if args.stage:
        run_child(args.stage, args.token)
    else:
        run_suite()
