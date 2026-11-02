"""Audit and catalog saved block plans at four House anchors without rerunning them.

The explicit baseline and replacement inventories are reviewed inputs. Historical
benchmarks, maps and national manifests are read-only; only this audit's namespace
and its durable report are written. Final-plan validity, population quality and
optimizer convergence are separate findings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apportionment import apportion_us_2020
from apportionment.data.apportionment_2020 import US_2020_APPORTIONMENT_POPULATIONS
from scripts.district_block_sources import EXPECTED_BLOCK_COUNTS, EXPECTED_RESIDENT_POPULATIONS
from scripts.precompute_state_districts import STATE_NAMES

CAPS = (435, 574, 692, 1000)
SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
DEFAULT_OUTPUT = SUITE / 'final-anchors-v1'
WORK = ROOT / '.cache/state-block-benchmark/final-audit-work'


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.partial')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def exact_apportionment(cap: int) -> dict[str, int]:
    """Independent rational squared priorities, avoiding the production heap."""
    seats = {fips: 1 for fips in US_2020_APPORTIONMENT_POPULATIONS}
    for _ in range(cap - len(seats)):
        winner = min(seats, key=lambda f: (
            -Fraction(US_2020_APPORTIONMENT_POPULATIONS[f] ** 2, seats[f] * (seats[f] + 1)), f))
        seats[winner] += 1
    return seats


def expected_grid() -> dict[tuple[str, int], list[int]]:
    result: dict[tuple[str, int], list[int]] = {}
    for cap in CAPS:
        seats = exact_apportionment(cap)
        if seats != apportion_us_2020(cap) or set(seats) != set(STATE_NAMES) or sum(seats.values()) != cap:
            raise ValueError(f'Independent apportionment mismatch at House {cap}.')
        for fips, count in seats.items():
            result.setdefault((fips, count), []).append(cap)
    return result


def resolve_local(path: str) -> Path:
    result = (ROOT / path).resolve()
    if not result.is_relative_to(ROOT):
        raise ValueError(f'Evidence path escapes repository: {path}')
    return result


def collect_evidence(selection: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in selection:
        for item in entry.get('evidence', []):
            path, digest = item['path'], item['sha256']
            if path in result and result[path] != digest:
                raise ValueError(f'Conflicting selection evidence hashes: {path}')
            result[path] = digest
    return result


def assemble_selection(baseline: list[dict[str, Any]], overrides: list[dict[str, Any]],
                       grid: dict[tuple[str, int], list[int]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, int], dict[str, Any]] = {}
    for entries, replacement in ((baseline, False), (overrides, True)):
        seen = set()
        for entry in entries:
            if (not isinstance(entry['state_fips'], str) or entry['state_fips'] not in STATE_NAMES
                    or type(entry['district_count']) is not int or entry['district_count'] < 1):
                raise ValueError('Selected state and district count must be an exact valid identity.')
            key = (entry['state_fips'], entry['district_count'])
            if key not in grid:
                raise ValueError(f'Out-of-scope selected plan: {key}')
            if key in seen:
                raise ValueError(f'Duplicate selected identity: {key}')
            seen.add(key)
            row = dict(entry)
            if replacement and key in selected:
                row['supersedes_report_path'] = selected[key]['report_path']
            row['house_sizes'] = grid[key]
            row['plan_id'] = f'{key[0]}-{key[1]}'
            row['state'] = STATE_NAMES[key[0]]
            selected[key] = row
    missing = set(grid) - set(selected)
    if missing:
        raise ValueError(f'Missing accepted plan candidates: {sorted(missing)}')
    paths = [row['report_path'] for row in selected.values()]
    if len(paths) != len(set(paths)):
        raise ValueError('One report was selected for multiple state/count identities.')
    return [selected[key] for key in sorted(selected)]


def optimizer_metrics(report: dict[str, Any]) -> dict[str, Any]:
    passes = report.get('solver_progress', [])
    observations = [p['inner_optimizer'] for p in passes if 'inner_optimizer' in p]
    # New traced adapters also retain the conventional solver_progress record.
    solver = report.get('solver', {})
    failures = [dict(pass_number=i + 1, **p) for i, p in enumerate(observations) if p.get('success') is False]
    return {
        'inner_pass_count': len(observations), 'unsuccessful_inner_pass_count': len(failures),
        'unsuccessful_inner_passes': failures,
        'inner_iteration_caps': sum(bool(p.get('iteration_limit_reached')) for p in observations),
        'maximum_inner_iterations': max((p.get('iterations', 0) for p in observations), default=None),
        'centers_converged': solver.get('centers_converged'),
        'outer_iteration_limit_reached': solver.get('outer_iteration_limit_reached'),
        'outer_iterations': solver.get('outer_iterations'),
        'kind': solver.get('kind'),
    }


def map_url(report_path: Path) -> str:
    if report_path.is_relative_to(SUITE):
        return 'http://127.0.0.1:8770/' + report_path.parent.relative_to(SUITE).as_posix() + '/'
    # Kansas retains its original, separately served anchor namespace.
    return 'http://127.0.0.1:8769/' + report_path.parent.name + '/'


def normalized_metrics(entry: dict[str, Any], report: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    fips, k = entry['state_fips'], entry['district_count']
    final = report.get('final_plan', {})
    pops = final.get('district_populations')
    if pops is None:
        raise ValueError(f'{entry["plan_id"]}: no final district populations in selected report')
    if len(pops) != k or sum(pops) != EXPECTED_RESIDENT_POPULATIONS[fips]:
        raise ValueError('Selected report population identity mismatch.')
    total = sum(pops)
    deviations = [abs(k * p - total) for p in pops]
    maps = report.get('maps', {})
    physical = maps.get('strict_validation', {})
    policy = maps.get('connectivity_validation', {})
    outlines = maps.get('district_outlines', {})
    load = maps.get('load_scenarios', {})
    phases = report.get('phases', {})
    optimizer = optimizer_metrics(report)
    upstream = entry.get('numerical_convergence', {})
    if upstream.get('upstream_solver_reused'):
        optimizer = {
            'inner_pass_count': upstream['inner_pass_count'],
            'unsuccessful_inner_pass_count': len(upstream['unsuccessful_inner_passes']),
            'unsuccessful_inner_passes': upstream['unsuccessful_inner_passes'],
            'inner_iteration_caps': len(upstream['capped_inner_passes']),
            'maximum_inner_iterations': upstream['max_inner_iterations'],
            'centers_converged': upstream['centers_converged'],
            'outer_iteration_limit_reached': upstream['outer_iteration_limit_reached'],
            'outer_iterations': upstream['outer_iterations'], 'kind': upstream['optimizer_kind'],
            'scope': 'preserved original solve reused by the correction',
        }
    alaska = fips == '02'
    if alaska:
        physical = {'passed': maps['physical_validation']['all_districts_physically_connected'],
                    **maps['physical_validation']}
    elif fips == '20':
        quality = maps['quality']
        physical = {'passed': quality['dissolved_geometries_valid'] and
                    all(x['polygon_components'] == 1 for x in quality['districts'].values()),
                    'basis': 'legacy full-polygon quality audit', 'districts': quality['districts']}
    row = dict(entry)
    row.update({
        'status': 'validated', 'saved_status': report['status'],
        'resident_population': total, 'block_count': EXPECTED_BLOCK_COUNTS[fips],
        'district_populations': pops,
        'max_deviation_people': max(deviations) / k,
        'max_deviation_percent': max(deviations) / total * 100,
        'population_range_people': max(pops) - min(pops),
        'connectivity_policy': 'shared_edges_plus_recorded_water_connections' if alaska else report.get('policy', 'strict_shared_edge'),
        'coordinate_handling': maps.get('coordinate_frames', 'original source coordinate frame'),
        'strict_polygon_validation_passed': physical.get('passed'),
        'policy_polygon_validation_passed': policy.get('passed'),
        'physical_polygon_audit': physical, 'recorded_connection_audit': policy,
        'optimizer': optimizer,
        'runtime_scope': 'correction_only_original_solve_reused' if upstream.get('upstream_solver_reused') else 'full_plan_pipeline',
        'configuration': report.get('configuration', {}),
        'postprocessing': report.get('postprocessing', {}),
        'pipeline_seconds': report.get('timed_pipeline_wall_seconds'),
        'peak_process_working_set_bytes': report.get('peak_process_working_set_bytes'),
        'phases': phases, 'load_scenarios': load,
        'national_outline_gzip_bytes': maps['map_payload_summary']['national_gzip_bytes'] if alaska else outlines.get('national', {}).get('gzip_bytes'),
        'state_outline_gzip_bytes': maps['map_payload_summary']['state_gzip_bytes'] if alaska else outlines.get('state', {}).get('gzip_bytes'),
        'map_url': map_url(resolve_local(entry['report_path'])),
        'map_directory': (resolve_local(entry['report_path']).parent / 'maps').relative_to(ROOT).as_posix(),
        'source': report.get('source', {}), 'code_sha256': report.get('code_sha256', {}),
        'validation': audit,
    })
    return row


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_cap = []
    for cap in CAPS:
        plans = [r for r in rows if cap in r['house_sizes']]
        worst = max(plans, key=lambda r: r['max_deviation_percent']) if plans else None
        by_cap.append({
            'house_size': cap, 'states_validated': len(plans),
            'district_count': sum(r['district_count'] for r in plans),
            'resident_population': sum(r['resident_population'] for r in plans),
            'block_count': sum(r['block_count'] for r in plans),
            'max_deviation_percent': worst['max_deviation_percent'] if worst else None,
            'worst_plan_id': worst['plan_id'] if worst else None,
            'max_deviation_people': max((r['max_deviation_people'] for r in plans), default=None),
            'national_outline_gzip_bytes': sum(r['national_outline_gzip_bytes'] or 0 for r in plans),
            'plan_ids': [r['plan_id'] for r in plans],
        })
    times = [r['pipeline_seconds'] for r in rows if isinstance(r['pipeline_seconds'], (int, float))]
    memories = [r['peak_process_working_set_bytes'] for r in rows if r['peak_process_working_set_bytes'] is not None]
    full_runs = [r for r in rows if r.get('runtime_scope') == 'full_plan_pipeline' and r['pipeline_seconds'] is not None]
    return {
        'anchors': by_cap, 'unique_plans': len(rows),
        'state_anchor_combinations': sum(len(r['house_sizes']) for r in rows),
        'strict_shared_edge_plans': sum(r['connectivity_policy'] == 'strict_shared_edge' for r in rows),
        'recorded_connection_plans': sum(r['connectivity_policy'] != 'strict_shared_edge' for r in rows),
        'plans_with_legacy_unsuccessful_inner_passes': sum(r['optimizer']['unsuccessful_inner_pass_count'] > 0 for r in rows),
        'plans_at_outer_iteration_cap': sum(r['optimizer']['outer_iteration_limit_reached'] is True for r in rows),
        'median_pipeline_seconds': statistics.median(times) if times else None,
        'maximum_pipeline_seconds': max(times, default=None),
        'maximum_peak_process_working_set_bytes': max(memories, default=None),
        'full_pipeline_plan_count': len(full_runs),
        'correction_only_plan_count': sum(r.get('runtime_scope') == 'correction_only_original_solve_reused' for r in rows),
        'median_full_pipeline_seconds': statistics.median(r['pipeline_seconds'] for r in full_runs) if full_runs else None,
        'compressed_payload_count': sum(r.get('validation', {}).get('checks', {}).get('compressed_payload_count', 0) for r in rows),
        'verified_compressed_bytes': sum(p['gzip_bytes'] for r in rows for p in r.get('validation', {}).get('payloads', {}).values()),
    }


def markdown(data: dict[str, Any]) -> str:
    a = data['aggregate']
    ready = data['status'] == 'complete'
    rows = data['plans']
    lines = [
        '# Final 50-state census-block plan catalog', '',
        f'**{"All four anchors are covered" if ready else "Final verification is incomplete"}: '
        f'{a["state_anchor_combinations"]}/200 state–House combinations; {a["unique_plans"]}/181 distinct plans.**', '',
        'Scope: 50 states, 2020 Census blocks, House sizes **435 / 574 / 692 / 1,000**. '
        'District counts are independently reconciled with exact rational Huntington–Hill priorities. '
        'Apportionment uses apportionment population; district balance uses resident population.', '',
        f'[Interactive inventory]({data.get("url", "http://127.0.0.1:8770/final-anchors-v1/")}) · '
        '[Machine-readable catalog](state-block-final-catalog.json)', '',
        '| House | States | Districts | Worst deviation | Largest deviation (people) | National outlines gzip |',
        '|---:|---:|---:|---:|---:|---:|',
    ]
    for cap in a['anchors']:
        percent = 'unavailable' if cap['max_deviation_percent'] is None else f'{cap["max_deviation_percent"]:.6f}%'
        people = 'unavailable' if cap['max_deviation_people'] is None else f'{cap["max_deviation_people"]:.3f}'
        lines.append(f'| {cap["house_size"]} | {cap["states_validated"]}/50 | {cap["district_count"]} | '
                     f'{percent} | {people} | '
                     f'{cap["national_outline_gzip_bytes"]/2**20:.2f} MiB |')
    lines += ['', '## What validation establishes', '',
        'Accepted final assignments cover every source block exactly once, with reconciled resident totals and '
        'nonempty districts. Full map polygons and connectivity are checked separately from simplified display outlines. '
        'Recorded water/exclave connections remain explicit; they do not turn separate polygons into physical shared edges. '
        'See each plan’s validation record for independent checks and retained historical audit evidence.', '',
        f'{a["strict_shared_edge_plans"]} plans use strict shared-edge connectivity; '
        f'{a["recorded_connection_plans"]} use recorded geographic connections. '
        'Alaska retains its documented longitude normalization and display seam handling.', '',
        'Population balance is measured, not inferred from solver status. No new tolerance or global-optimality '
        'claim is imposed by this catalog. Whole blocks, zero-population blocks and water blocks remain included.', '',
        f'{a["plans_with_legacy_unsuccessful_inner_passes"]} selected historical plans contain at least one '
        f'unsuccessful legacy inner pass; {a["plans_at_outer_iteration_cap"]} report an outer iteration cap. '
        'These flags remain in the catalog. They do not replace the independent final-map acceptance checks, '
        'and these runs must not be described as uniformly converged.', '',
        '## State inventory', '',
        'Each cell gives district count / maximum absolute population deviation in people. '
        'Equal state seat counts reuse the same accepted plan.', '',
        '| State | House 435 | House 574 | House 692 | House 1,000 | Connectivity |',
        '|---|---|---|---|---|---|']
    for fips in sorted(STATE_NAMES, key=lambda f: STATE_NAMES[f]):
        state_rows = [r for r in rows if r['state_fips'] == fips]
        cells = []
        for cap in CAPS:
            r = next((r for r in state_rows if cap in r['house_sizes']), None)
            cells.append(f'[{r["district_count"]} / {r["max_deviation_people"]:.3f}]({r["map_url"]})' if r else '**MISSING**')
        kind = 'Recorded connections' if any(r['connectivity_policy'] != 'strict_shared_edge' for r in state_rows) else 'Shared edges'
        lines.append(f'| {STATE_NAMES[fips]} | ' + ' | '.join(cells) + f' | {kind} |')
    lines += ['', '## Runtime, memory and verification cost', '']
    if a.get('full_pipeline_plan_count'):
        slowest = max((r for r in rows if r.get('runtime_scope') == 'full_plan_pipeline'), key=lambda r: r['pipeline_seconds'])
        largest = max(rows, key=lambda r: r['peak_process_working_set_bytes'] or 0)
        lines += [f'The {a["full_pipeline_plan_count"]} full-pipeline records have a median of '
                  f'{a["median_full_pipeline_seconds"]/60:.2f} minutes. The slowest is '
                  f'{slowest["state"]} K{slowest["district_count"]} at {slowest["pipeline_seconds"]/60:.2f} minutes. '
                  f'The largest recorded process peak is {largest["peak_process_working_set_bytes"]/2**30:.3f} GiB '
                  f'for {largest["state"]} K{largest["district_count"]}. '
                  f'{a["correction_only_plan_count"]} selected corrections have separately scoped timings that exclude their original solve. '
                  'These historical measurements span concurrent and serial execution and different code versions; they are not controlled speed comparisons.', '']
    lines += [f'This read-only audit verified {a.get("compressed_payload_count", 0):,} compressed payloads '
              f'({a.get("verified_compressed_bytes", 0)/2**30:.2f} GiB across distinct saved plans, including repeated geography). '
              'It did not generate or repair any districts. Its runtime is separate from the benchmark measurements.', '',
              '## Integration boundary', '',
        '- This catalog selects existing immutable results; it does not modify the demo or overwrite historical failures.',
        '- The four anchors are ready only when all validation records pass. Intermediate slider values and House 11,037 are outside this catalog.',
        '- Integration must preserve recorded links, Alaska seam handling, population/solver status, source provenance and the selected correction versions.',
        '- The current app uses tract summary/topology files and its state page selects the 435-seat plan. It needs a deliberate block-plan adapter, anchor selection and truthful convergence labels; this catalog is not a drop-in replacement for that schema.',
        '- Load national district outlines first, state outlines on selection, and county block detail on demand. Outline totals exclude links, manifests, application code and other request overhead.',
        '- Runtime measurements span older two-worker runs and later serial runs, several numerical versions, and correction-only pipelines. They are observations, not controlled comparisons or a new nationwide runtime.',
        '- No new solve, repair, export or connectivity-policy change was performed for this audit.', '',
        '## Verification provenance', '',
        f'Audit generated {data["generated_at"]}; elapsed {data["audit_wall_seconds"]:.1f} seconds. '
        'The JSON records explicit selection reasons, original report hashes, apportionment, accepted audit checks and any failures. '
        'The detailed validation checkpoints are in `.cache/state-block-benchmark/suite-through-1000/final-anchors-v1/validation/`.', '']
    if data['errors']:
        lines += ['## Unresolved validation failures', ''] + [f'- {e["plan_id"]}: {e["error"]}' for e in data['errors']] + ['']
    if data.get('final_review'):
        review = data['final_review']
        lines += [f'Final review: **{review["tests"]["passed"]} regression tests passed** '
                  f'in {review["tests"]["seconds"]:.2f} seconds. '
                  f'All {review["map_links"]["checked"]} selected map URLs returned HTML successfully. '
                  'The browser checks cover all four anchors, policy filters, corrected-map selection, solver warnings, '
                  'search, sorting and the overview layout. Browser evidence is saved beside the catalog in `qa/`.', '']
    return '\n'.join(lines)


def write_page(output: Path) -> None:
    template = (ROOT / 'scripts/assets/final-state-catalog.html').read_text(encoding='utf-8')
    (output / 'index.html').write_text(template, encoding='utf-8')


def validate_output_path(output: Path) -> None:
    if output.parent != SUITE.resolve() or not re.fullmatch(r'final-anchors-v[1-9][0-9]*', output.name):
        raise ValueError('Audit output must be a new top-level final-anchors-vN namespace.')
    if output.exists():
        raise ValueError('Audit namespace already exists; preserve it and choose a new version.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=WORK / 'baseline-selection.json')
    parser.add_argument('--policies', type=Path, default=WORK / 'policy-selection.json')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    validate_output_path(output)
    start = time.perf_counter()
    inputs = {p.relative_to(ROOT).as_posix(): sha(p) for p in (args.baseline.resolve(), args.policies.resolve())}
    grid = expected_grid()
    selection = assemble_selection(read(args.baseline)['entries'], read(args.policies)['entries'], grid)
    evidence = collect_evidence(selection)
    for path, digest in evidence.items():
        if sha(resolve_local(path)) != digest:
            raise ValueError(f'Selection evidence hash mismatch: {path}')
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'selection.json', {'inputs': inputs, 'plans': selection})
    from scripts.final_state_plan_validation import ValidationContext, validate_plan
    context = ValidationContext()
    rows, errors = [], []
    for index, entry in enumerate(selection, 1):
        path = resolve_local(entry['report_path'])
        print(f'Validating {index}/{len(selection)}: {entry["state"]} K{entry["district_count"]}', flush=True)
        try:
            if sha(path) != entry['report_sha256']:
                raise ValueError('Selected report hash changed before validation.')
            audit = validate_plan(path, expected_report_sha256=entry['report_sha256'],
                                  expected_state_fips=entry['state_fips'],
                                  expected_district_count=entry['district_count'], context=context)
            row = normalized_metrics(entry, read(path), audit)
            if sha(path) != entry['report_sha256']:
                raise ValueError('Selected report changed during validation.')
            write(output / 'validation' / f'{entry["plan_id"]}.json', row)
            rows.append(row)
        except Exception as error:
            item = {'plan_id': entry['plan_id'], 'report_path': entry['report_path'],
                    'error': f'{type(error).__name__}: {error}'}
            errors.append(item)
            write(output / 'validation' / f'{entry["plan_id"]}.failed.json', item)
            print(f'VALIDATION FAILURE {item}', flush=True)
        write(output / 'progress.json', {'status': 'auditing', 'completed': len(rows), 'failed': len(errors),
                                        'processed': index, 'total': len(selection), 'errors': errors})
    for path, digest in inputs.items():
        if sha(ROOT / path) != digest:
            raise ValueError('Reviewed selection inventory changed during audit.')
    for path, digest in evidence.items():
        if sha(resolve_local(path)) != digest:
            raise ValueError(f'Selection evidence changed during audit: {path}')
    data = {'schema_version': 1, 'status': 'complete' if not errors else 'validation_failed',
            'url': 'http://127.0.0.1:8770/' + output.name + '/',
            'generated_at': datetime.now(timezone.utc).isoformat(), 'house_sizes': list(CAPS),
            'selection_inputs': inputs, 'selection_evidence_hashes': evidence, 'expected_unique_plans': len(grid),
            'audit_wall_seconds': time.perf_counter() - start, 'aggregate': aggregate(rows),
            'plans': rows, 'errors': errors}
    write(output / 'catalog.json', data)
    write(output / 'progress.json', {'status': data['status'], 'completed': len(rows), 'failed': len(errors), 'total': len(selection)})
    write(ROOT / 'prompts/state-block-final-catalog.json', data)
    report = markdown(data)
    (output / 'report.md').write_text(report.replace('(state-block-final-catalog.json)', '(catalog.json)'), encoding='utf-8')
    (ROOT / 'prompts/state-block-final-catalog.md').write_text(report, encoding='utf-8')
    write_page(output)
    print(json.dumps({'status': data['status'], 'aggregate': data['aggregate'], 'errors': errors}), flush=True)


if __name__ == '__main__':
    main()
