"""Audit the saved WV probe without repeating any balancing work.

Preserves the first diagnostic's failed geometry-audit record. Robust unary
union follows the established map exporter; no source geometry is repaired.
"""
from __future__ import annotations
from collections import Counter
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
from scripts import diagnose_west_virginia_balance as d
from scripts.state_block_execution_lock import state_execution_lock


def audit_stage(geometries, labels, graph_components, source_union, *, initial):
    full = []
    fast_diagnostics = []
    for district in range(3):
        members = [g for g, label in zip(geometries, labels, strict=True) if label == district]
        try:
            fast = shapely.coverage_union_all(members)
            fast_diagnostics.append({'type': fast.geom_type, 'valid': bool(fast.is_valid),
                'validity_reason': shapely.is_valid_reason(fast),
                'polygon_components': 1 if fast.geom_type == 'Polygon' else len(fast.geoms)})
        except shapely.errors.GEOSException as error:
            fast_diagnostics.append({'valid': False, 'error': str(error)})
        # Use the established exporter's robust dissolve for the audit itself.
        full.append(shapely.union_all(members))
    counts = [1 if g.geom_type == 'Polygon' else len(g.geoms) for g in full]
    if any(g.is_empty or not g.is_valid or g.geom_type not in ('Polygon', 'MultiPolygon') for g in full):
        raise ValueError('Robust union failed full unsimplified geometry validity.')
    if not bool(shapely.coverage_is_valid(full)):
        raise ValueError('Full district coverage is invalid.')
    if not source_union.symmetric_difference(shapely.union_all(full)).is_empty:
        raise ValueError('Full district polygons do not exactly preserve source coverage.')
    if not initial and (counts != [1, 1, 1] or graph_components != [1, 1, 1]):
        raise ValueError('A repaired/original/probe stage failed strict connectivity.')
    return full, {'polygon_components': counts, 'polygons_valid': True,
        'source_coverage_preserved_exactly': True, 'district_coverage_valid': True,
        'strict_polygon_validation_passed': counts == [1, 1, 1],
        'graph_polygon_component_counts_agree': counts == graph_components,
        'union_method': 'unary_union / union_all; unchanged source coordinates',
        'coverage_union_diagnostic': fast_diagnostics}


def main():
    output = d.OUTPUT
    history_path = output / 'diagnosis-attempt-1.json'
    if history_path.exists() or (output / 'finalization-admitted.json').exists():
        raise FileExistsError('A finalization attempt already exists; preserve it.')
    failed = d.read(output / 'diagnosis.json')
    if failed.get('status') != 'failed_diagnosis' or failed.get('error') != 'ValueError: Independent polygon/graph connectivity mismatch: initial':
        raise ValueError('Only the known initial-stage audit failure can be finalized.')
    began = time.perf_counter()
    with state_execution_lock('54'):
        history_path.write_bytes((output / 'diagnosis.json').read_bytes())
        d.write_json(output / 'finalization-admitted.json', {'started_at': datetime.now(timezone.utc).isoformat(),
            'purpose': 'Independent audit of saved probe; no solver or balancing rerun', 'code_sha256': d.sha256(Path(__file__))})
        original_files = d.read(output / 'preserved-file-inventory.json')
        probe_assignment = d.read(output / 'probe-assignments.json')
        probe_moves = d.read(output / 'probe-moves.json')
        code_files = probe_assignment['code_sha256']
        for group in (original_files, code_files):
            if d.inventory([ROOT / name for name in group]) != group:
                raise ValueError('Original evidence or probe runtime code changed.')
        protected = d.inventory([output / name for name in ('diagnosis-attempt-1.json', 'diagnosis.log',
            'probe-assignments.json', 'probe-moves.json', 'preserved-file-inventory.json')])
        prior = d.read(d.ORIGINAL / 'benchmark.json')
        moves = d.read(d.ORIGINAL / 'move-audit.json')
        with zipfile.ZipFile(d.ARCHIVE) as archive:
            d._safe_members(archive, d.ARCHIVE.stem)
            with shapefile.Reader(shp=io.BytesIO(archive.read(d.ARCHIVE.stem + '.shp')),
                    shx=io.BytesIO(archive.read(d.ARCHIVE.stem + '.shx')),
                    dbf=io.BytesIO(archive.read(d.ARCHIVE.stem + '.dbf'))) as reader:
                geoids, pops, geometries = [], [], []
                for row in reader.iterShapeRecords():
                    geoids.append(str(row.record['GEOID20'])); pops.append(int(row.record['POP20']))
                    geometries.append(shape(row.shape.__geo_interface__))
        if len(geoids) != d.BLOCKS or len(set(geoids)) != d.BLOCKS or sum(pops) != d.TOTAL or min(pops) < 0:
            raise ValueError('Source population/block coverage failed.')
        if d.sha256(d.ARCHIVE) != d.SOURCE_SHA or probe_assignment['source_sha256'] != d.SOURCE_SHA:
            raise ValueError('Source hash changed.')
        if any(g.is_empty or not g.is_valid or g.geom_type != 'Polygon' for g in geometries) or not bool(shapely.coverage_is_valid(geometries)):
            raise ValueError('Source single-part polygon coverage invalid.')
        identity = d._identity(geoids, d.SOURCE_SHA)
        if identity != prior['graph_cache']['identity']:
            raise ValueError('Original graph identity changed.')
        graph, graph_info = d._read_cache(Path(prior['graph_cache']['path']), identity)
        labels = {}
        for key, name in (('initial', 'initial-solver-result.json'), ('repaired', 'after-repair-result.json'), ('original', 'solver-result.json')):
            assignments = d.read(d.ORIGINAL / name)['assignments']
            if set(assignments) != set(geoids): raise ValueError('Saved source universe differs.')
            labels[key] = tuple(assignments[g] for g in geoids)
        if set(probe_assignment['assignments']) != set(geoids): raise ValueError('Probe source universe differs.')
        labels['probe'] = tuple(probe_assignment['assignments'][g] for g in geoids)
        stages = {key: d.stage(value, pops, graph, key == 'original') for key, value in labels.items()}
        replayed, _ = d.replay(labels['initial'], stages['initial']['populations'], moves['repair_moves'], pops, geoids, None, 0, improving=False)
        if replayed != labels['repaired']: raise ValueError('Repair audit differs.')
        trace = [{key: stages['repaired'][key] for key in ('populations', 'max_deviation_people', 'max_deviation_percent')}]
        trace[0]['moves'] = 0
        for key, audit, start in (('original', moves['rebalance_moves'], 0), ('probe', probe_moves['moves'], 1000)):
            prior_key = 'repaired' if key == 'original' else 'original'
            replayed, _ = d.replay(labels[prior_key], stages[prior_key]['populations'], audit, pops, geoids, trace, start, improving=True)
            if replayed != labels[key]: raise ValueError('Balancing replay differs.')
        if len(moves['rebalance_moves']) != 1000 or len(probe_moves['moves']) != 100 or probe_moves['stop_reason'] != 'max_moves':
            raise ValueError('Unexpected saved probe budget or termination.')
        print('Source and saved move replay verified; dissolving source.', flush=True)
        source_union = shapely.union_all(geometries)
        if not source_union.is_valid: raise ValueError('Robust source union invalid.')
        for key, values in labels.items():
            print(f'Auditing {key} full geometry.', flush=True)
            full, audit = audit_stage(geometries, values, stages[key]['components'], source_union, initial=key == 'initial')
            stages[key].update(audit)
            print(json.dumps({'stage': key, **audit}), flush=True)
            features = [{'type': 'Feature', 'geometry': mapping(g.simplify(.0005, preserve_topology=True)),
                'properties': {'district_id': i, 'population': stages[key]['populations'][i],
                    'deviation_percent': 100 * stages[key]['deviations_people'][i] / (d.TOTAL / 3)}} for i, g in enumerate(full)]
            d.write_json(output / f'stage-{key}.geojson', {'type': 'FeatureCollection', 'features': features})
        component = max(moves['repair_moves'], key=lambda m: m['population'])
        moved = shapely.union_all([geometries[i] for i in component['units']])
        d.write_json(output / 'repair-component.geojson', {'type': 'FeatureCollection', 'features': [{'type': 'Feature',
            'geometry': mapping(moved.simplify(.0005, preserve_topology=True)),
            'properties': {'block_count': len(component['units']), 'population': component['population']}}]})
        plans = []
        for k in (2, 3, 4, 5):
            old = d.read(d.SUITE / f'states/54/districts-{k}/benchmark.json'); p = old['final_plan']
            plans.append({'district_count': k, 'house_sizes': old['house_sizes'], 'final_populations': p['district_populations'],
                'max_deviation_people': p['max_absolute_deviation_people'], 'max_deviation_percent': p['max_absolute_deviation_percent'],
                'pipeline_seconds': old['timed_pipeline_wall_seconds'], 'peak_working_set_bytes': old['peak_process_working_set_bytes'],
                'rebalance_moves': old['rebalance_move_count'], 'stop_reason': old['stop_reason'],
                'strict_polygon_validation_passed': old['maps']['strict_validation']['passed'],
                'unsuccessful_inner_passes': old['solver']['unsuccessful_inner_passes']})
        for group in (original_files, code_files, protected):
            if d.inventory([ROOT / name for name in group]) != group: raise ValueError('Preserved evidence changed during audit.')
        result = {'status': 'diagnosis_complete', 'diagnostic_only': True, 'state': 'West Virginia', 'district_count': 3,
            'source': {'block_count': d.BLOCKS, 'resident_population': d.TOTAL, 'archive_sha256': d.SOURCE_SHA,
                'multipart_block_count': 0, 'graph': graph_info}, 'original_plans': plans, 'stages': stages, 'trace': trace,
            'repair_component': {'block_count': len(component['units']), 'population': component['population'],
                'source_district': component['source_district'], 'target_district': component['target_district'],
                'counties': dict(Counter(geoids[i][2:5] for i in component['units']))},
            'probe': {'additional_moves': 100, 'additional_move_limit': 100, 'cumulative_moves': 1100,
                'elapsed_seconds': failed['phases']['bounded_100_move_continuation']['wall_seconds'],
                'stop_reason': 'max_moves', 'strict_polygon_validation_passed': True, 'solver_rerun': False,
                'repair_move_count': 0, 'accepted_map': False, **probe_moves['profile']},
            'historical_preservation': {'unchanged': True, 'file_count': len(original_files), 'inventory': 'preserved-file-inventory.json'},
            'code_comparison': {'current': code_files, 'historical': prior['code_sha256'],
                'interpretation': 'Current unchanged legacy block-graph continuation branch; historical source bytes unavailable, so byte-identical historical implementation is not certified.'},
            'audit_history': {'initial_attempt': 'diagnosis-attempt-1.json', 'initial_log': 'diagnosis.log',
                'finalization_elapsed_seconds': time.perf_counter() - began, 'balancing_repeated': False,
                'finalization_script_sha256': d.sha256(Path(__file__)), 'preserved_probe_sha256': protected},
            'caveats': ['Bounded diagnostic continuation, not a completed correction or guarantee of final balance.',
                'Probe timing includes guard profiling; original batch timing includes two-worker contention.',
                'Display geometry simplified; strict audit uses unchanged full source polygons and robust unary union.',
                'No new optimizer run, water links, or core numerical code changes.'],
            'finished_at': datetime.now(timezone.utc).isoformat()}
        d.write_json(output / 'diagnosis.json', result)
        print(json.dumps({'status': result['status'], 'probe': result['probe']}), flush=True)


if __name__ == '__main__':
    main()
