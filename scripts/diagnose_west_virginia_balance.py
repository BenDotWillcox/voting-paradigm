"""Preserved-evidence diagnosis and bounded continuation of West Virginia K3.

The existing optimizer and connectivity implementation are never edited. The
100-move probe is diagnostic, not a claim that a larger budget solves balance.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import shapefile
import shapely
from shapely.geometry import mapping, shape
from districting import connectivity
from scripts.benchmark_kansas_anchors import population_metrics
from scripts.benchmark_kansas_blocks import Measurements, process_memory, sha256
from scripts.correct_state_block_parts import write_json
from scripts.district_block_graph_cache import _identity, _read_cache
from scripts.district_block_sources import _safe_members
from scripts.state_block_execution_lock import state_execution_lock

SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'diagnostics/west-virginia'
ORIGINAL = SUITE / 'states/54/districts-3'
ARCHIVE = ROOT / '.cache/state-block-benchmark/source/54/tl_2020_54_tabblock20.zip'
SOURCE_SHA = '04e931a5d288ed62da3b947239f3f23f8b6a8d8b4a749ec749eb90158b50f863'
BLOCKS, TOTAL, K, ADDITIONAL_MOVES = 72558, 1793716, 3, 100


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def preservation_paths():
    paths = {ARCHIVE, ARCHIVE.with_suffix('.manifest.json'), SUITE / 'suite.json'}
    paths.update(p for p in (SUITE / 'states/54').rglob('*') if p.is_file())
    paths.add(Path(read(ORIGINAL / 'benchmark.json')['graph_cache']['path']))
    return sorted(paths)


def inventory(paths):
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}


def components(graph, labels, k):
    """Independent traversal of induced districts, without calling repair code."""
    seen = set(); counts = [0] * k
    for start in range(len(labels)):
        if start in seen:
            continue
        counts[labels[start]] += 1; seen.add(start); stack = [start]
        while stack:
            node = stack.pop()
            for neighbor in graph[node]:
                if neighbor not in seen and labels[neighbor] == labels[start]:
                    seen.add(neighbor); stack.append(neighbor)
    return counts


def stage(labels, pops, graph, accepted=False):
    totals = [0] * K
    for label, pop in zip(labels, pops, strict=True):
        if type(label) is not int or not 0 <= label < K:
            raise ValueError('Invalid saved district label.')
        totals[label] += pop
    metrics = population_metrics(totals)
    return {**metrics, 'populations': totals, 'components': components(graph, labels, K),
        'max_deviation_people': metrics['max_absolute_deviation_people'],
        'max_deviation_percent': metrics['max_absolute_deviation_percent'], 'accepted_map': accepted}


def replay(labels, totals, moves, pops, geoids, trace, start, *, improving):
    labels = list(labels); totals = list(totals)
    for index, move in enumerate(moves, start + 1):
        units = move['units']; source, target = move['source_district'], move['target_district']
        amount = move['population']
        if (not isinstance(units, (list, tuple)) or not units
                or any(type(u) is not int or not 0 <= u < len(labels) for u in units)
                or type(source) is not int or type(target) is not int
                or not 0 <= source < len(totals) or not 0 <= target < len(totals) or source == target
                or type(amount) is not int or amount < 0
                or improving and (len(units) != 1 or amount == 0)):
            raise ValueError('Move audit has invalid units, district IDs, or population.')
        if (len(set(units)) != len(units)
                or any(labels[u] != source for u in units)
                or move['geoids'] != [geoids[u] for u in units]
                or sum(pops[u] for u in units) != move['population']):
            raise ValueError('Move audit does not replay against original source and labels.')
        previous = connectivity._objective(totals, TOTAL)
        for unit in units:
            labels[unit] = target
        totals[source] -= move['population']; totals[target] += move['population']
        current = connectivity._objective(totals, TOTAL)
        if improving and not current < previous:
            raise ValueError('A balancing move failed to strictly improve the exact objective.')
        m = population_metrics(totals)
        if trace is not None:
            trace.append({'moves': index, 'populations': list(totals),
                'max_deviation_people': m['max_absolute_deviation_people'],
                'max_deviation_percent': m['max_absolute_deviation_percent'],
                'squared_deviation_numerator': m['squared_deviation_numerator']})
    return tuple(labels), totals


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if any((OUTPUT / name).exists() for name in ('diagnosis.json', 'probe-assignments.json', 'admitted.json')):
        raise FileExistsError('An earlier diagnosis/probe exists; preserve it instead of overwriting.')
    with state_execution_lock('54'):
        write_json(OUTPUT / 'admitted.json', {'started_at': datetime.now(timezone.utc).isoformat(), 'additional_move_limit': ADDITIONAL_MOVES})
        measure = Measurements(); began = time.perf_counter()
        report = {'status': 'running', 'state': 'West Virginia', 'district_count': K,
            'diagnostic_only': True, 'started_at': datetime.now(timezone.utc).isoformat()}
        try:
            paths = preservation_paths(); before = inventory(paths)
            code_paths = [Path(__file__), Path(connectivity.__file__), ROOT / 'districting/part_connectivity.py',
                ROOT / 'scripts/district_block_graph_cache.py', ROOT / 'scripts/district_block_adjacency.py']
            code_before = inventory(code_paths)
            write_json(OUTPUT / 'preserved-file-inventory.json', before)
            prior = read(ORIGINAL / 'benchmark.json'); audits = read(ORIGINAL / 'move-audit.json')
            if sha256(ARCHIVE) != SOURCE_SHA or prior['source']['archive_sha256'] != SOURCE_SHA:
                raise ValueError('Original source archive identity changed.')
            for name, digest in prior['artifact_sha256'].items():
                if sha256(ORIGINAL / name) != digest:
                    raise ValueError(f'Historical artifact changed: {name}')
            with measure.phase('source_records_and_verified_original_graph'):
                with zipfile.ZipFile(ARCHIVE) as zipped:
                    _safe_members(zipped, ARCHIVE.stem)
                    with shapefile.Reader(dbf=io.BytesIO(zipped.read(ARCHIVE.stem + '.dbf'))) as reader:
                        records = list(reader.iterRecords())
                geoids = [str(r['GEOID20']) for r in records]; pops = [int(r['POP20']) for r in records]
                if len(geoids) != BLOCKS or len(set(geoids)) != BLOCKS or sum(pops) != TOTAL or min(pops) < 0:
                    raise ValueError('Source population/block coverage failed.')
                identity = _identity(geoids, SOURCE_SHA)
                if identity != prior['graph_cache']['identity']:
                    raise ValueError('Source order or original graph cache identity changed.')
                graph, graph_info = _read_cache(Path(prior['graph_cache']['path']), identity)
                if graph_info != prior['graph'] or graph_info['multipart_block_count'] != 0:
                    raise ValueError('Expected the original single-part shared-edge graph.')
                labels = {}
                for key, name in (('initial', 'initial-solver-result.json'), ('repaired', 'after-repair-result.json'), ('original', 'solver-result.json')):
                    saved = read(ORIGINAL / name)['assignments']
                    if set(saved) != set(geoids): raise ValueError('Saved block universe differs from source.')
                    labels[key] = tuple(saved[g] for g in geoids)
                stages = {name: stage(value, pops, graph, name == 'original') for name, value in labels.items()}
                repaired, _ = replay(labels['initial'], stages['initial']['populations'], audits['repair_moves'], pops, geoids, None, 0, improving=False)
                if repaired != labels['repaired']: raise ValueError('Original repair trace does not reconcile.')
                trace = [{'moves': 0, 'populations': stages['repaired']['populations'],
                    'max_deviation_people': stages['repaired']['max_deviation_people'],
                    'max_deviation_percent': stages['repaired']['max_deviation_percent']}]
                original, _ = replay(repaired, stages['repaired']['populations'], audits['rebalance_moves'], pops, geoids, trace, 0, improving=True)
                if original != labels['original'] or stages['original']['components'] != [1] * K:
                    raise ValueError('Original final assignments/connectedness do not reconcile.')
            profile = {'guard_calls': 0, 'guard_failed_calls': 0, 'guard_wall_seconds': 0.0}
            original_guard = connectivity._removal_preserves_connectivity
            def observed_guard(*args):
                start = time.perf_counter()
                answer = original_guard(*args)
                profile['guard_wall_seconds'] += time.perf_counter() - start
                profile['guard_calls'] += 1; profile['guard_failed_calls'] += int(not answer)
                return answer
            with measure.phase('bounded_100_move_continuation'):
                start = time.perf_counter(); connectivity._removal_preserves_connectivity = observed_guard
                try:
                    result = connectivity.repair_and_rebalance(graph, labels['original'], pops, n_districts=K, max_moves=ADDITIONAL_MOVES)
                finally:
                    connectivity._removal_preserves_connectivity = original_guard
                elapsed = time.perf_counter() - start
            if result.repair_moves or result.repaired_assignments != labels['original']:
                raise ValueError('Continuation unexpectedly changed the already repaired starting plan.')
            new_moves = [{**asdict(m), 'geoids': [geoids[u] for u in m.units]} for m in result.rebalance_moves]
            endpoint, _ = replay(labels['original'], stages['original']['populations'], new_moves, pops, geoids, trace, len(audits['rebalance_moves']), improving=True)
            if endpoint != result.assignments: raise ValueError('Probe moves do not reconcile.')
            labels['probe'] = endpoint; stages['probe'] = stage(endpoint, pops, graph)
            if stages['probe']['components'] != [1] * K: raise ValueError('Probe graph connectivity failed.')
            write_json(OUTPUT / 'probe-assignments.json', {'assignments': dict(zip(geoids, endpoint, strict=True)), 'diagnostic_only': True, 'source_sha256': SOURCE_SHA, 'code_sha256': code_before})
            write_json(OUTPUT / 'probe-moves.json', {'moves': new_moves, 'stop_reason': result.stop_reason, 'profile': profile})
            component = max(audits['repair_moves'], key=lambda m: m['population'])
            with measure.phase('independent_unsimplified_polygon_audit_and_diagnostic_geometry'):
                with zipfile.ZipFile(ARCHIVE) as zipped:
                    with shapefile.Reader(shp=io.BytesIO(zipped.read(ARCHIVE.stem + '.shp')),
                            shx=io.BytesIO(zipped.read(ARCHIVE.stem + '.shx')),
                            dbf=io.BytesIO(zipped.read(ARCHIVE.stem + '.dbf'))) as reader:
                        geometries = []
                        for index, row in enumerate(reader.iterShapeRecords()):
                            if row.record['GEOID20'] != geoids[index]: raise ValueError('Source geometry order changed.')
                            geometry = shape(row.shape.__geo_interface__)
                            if geometry.geom_type != 'Polygon' or not geometry.is_valid: raise ValueError('Expected valid single-part source polygons.')
                            geometries.append(geometry)
                if len(geometries) != BLOCKS or not bool(shapely.coverage_is_valid(geometries)):
                    raise ValueError('Source full polygon coverage is invalid.')
                source_union = shapely.coverage_union_all(geometries)
                for name, values in labels.items():
                    full = [shapely.coverage_union_all([g for g, d in zip(geometries, values, strict=True) if d == district]) for district in range(K)]
                    counts = [1 if g.geom_type == 'Polygon' else len(g.geoms) for g in full]
                    if any(not g.is_valid for g in full) or counts != stages[name]['components']:
                        raise ValueError(f'Independent polygon/graph connectivity mismatch: {name}')
                    if not source_union.symmetric_difference(shapely.coverage_union_all(full)).is_empty:
                        raise ValueError('District polygons changed full source coverage.')
                    stages[name]['strict_polygon_validation_passed'] = counts == [1] * K
                    features = [{'type': 'Feature', 'geometry': mapping(g.simplify(.0005, preserve_topology=True)),
                        'properties': {'district_id': d, 'population': stages[name]['populations'][d],
                            'deviation_percent': 100 * stages[name]['deviations_people'][d] / (TOTAL / K)}} for d, g in enumerate(full)]
                    write_json(OUTPUT / f'stage-{name}.geojson', {'type': 'FeatureCollection', 'features': features})
                moved_geometry = shapely.coverage_union_all([geometries[i] for i in component['units']])
                write_json(OUTPUT / 'repair-component.geojson', {'type': 'FeatureCollection', 'features': [{'type': 'Feature',
                    'geometry': mapping(moved_geometry.simplify(.0005, preserve_topology=True)),
                    'properties': {'block_count': len(component['units']), 'population': component['population']}}]})
            original_plans = []
            for k in (2, 3, 4, 5):
                old = read(SUITE / f'states/54/districts-{k}/benchmark.json'); p = old['final_plan']
                original_plans.append({'district_count': k, 'house_sizes': old['house_sizes'],
                    'final_populations': p['district_populations'], 'max_deviation_people': p['max_absolute_deviation_people'],
                    'max_deviation_percent': p['max_absolute_deviation_percent'], 'pipeline_seconds': old['timed_pipeline_wall_seconds'],
                    'peak_working_set_bytes': old['peak_process_working_set_bytes'], 'rebalance_moves': old['rebalance_move_count'],
                    'stop_reason': old['stop_reason'], 'strict_polygon_validation_passed': old['maps']['strict_validation']['passed'],
                    'unsuccessful_inner_passes': old['solver']['unsuccessful_inner_passes']})
            if inventory(paths) != before or inventory(code_paths) != code_before:
                raise ValueError('Historical files or diagnostic code changed.')
            report.update(status='diagnosis_complete', source={'block_count': BLOCKS, 'resident_population': TOTAL, 'archive_sha256': SOURCE_SHA,
                'multipart_block_count': 0, 'graph': graph_info}, original_plans=original_plans, stages=stages, trace=trace,
                repair_component={'block_count': len(component['units']), 'population': component['population'],
                    'source_district': component['source_district'], 'target_district': component['target_district'],
                    'counties': dict(Counter(geoids[i][2:5] for i in component['units']))},
                probe={'additional_moves': len(new_moves), 'additional_move_limit': ADDITIONAL_MOVES,
                    'cumulative_moves': len(audits['rebalance_moves']) + len(new_moves), 'elapsed_seconds': elapsed,
                    'stop_reason': result.stop_reason, 'strict_polygon_validation_passed': stages['probe']['strict_polygon_validation_passed'],
                    'solver_rerun': False, 'repair_move_count': 0, 'accepted_map': False, **profile},
                historical_preservation={'unchanged': True, 'file_count': len(before), 'inventory': 'preserved-file-inventory.json'},
                code_comparison={'current': code_before, 'historical': prior['code_sha256'],
                    'interpretation': 'Current unchanged legacy block-graph continuation branch; historical source bytes unavailable, so byte-identical historical implementation is not certified.'},
                caveats=['This is a bounded diagnostic continuation, not a completed correction or guarantee of final balance.',
                    'Probe timing includes observational guard profiling; original timing involved two-worker contention.',
                    'Display geometries are simplified; strict connectivity validation uses unsimplified source polygons.',
                    'No artificial water links, new optimizer run, or changes to core numerical/source code.'])
        except BaseException as error:
            report.update(status='failed_diagnosis', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            measure.close()
            report.update(phases=measure.phases, elapsed_seconds=time.perf_counter() - began,
                peak_working_set_bytes=process_memory()[1], finished_at=datetime.now(timezone.utc).isoformat())
            write_json(OUTPUT / 'diagnosis.json', report)
    print(json.dumps({'status': report['status'], 'probe': report['probe'], 'final_probe': report['stages']['probe']}), flush=True)


if __name__ == '__main__':
    main()
