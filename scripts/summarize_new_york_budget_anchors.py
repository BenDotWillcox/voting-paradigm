"""Independently verify the three new New York inner-budget anchor reruns.

The successful K26 experiment is a read-only reference, never a new suite job.
Only new comparison/report outputs are written; original evidence is immutable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
from typing import Any

try:
    from scripts import summarize_new_york_links as checks
    from scripts import summarize_new_york_budget as trace_checks
except ModuleNotFoundError:
    import summarize_new_york_links as checks
    import summarize_new_york_budget as trace_checks

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'corrections/new-york-inner-budget-anchors-v1'
REFERENCE = SUITE / 'corrections/new-york-inner-budget-v1/states/36/districts-26'
REPORT = ROOT / 'prompts/new-york-inner-budget-anchors'
URL = 'http://127.0.0.1:8770/corrections/new-york-inner-budget-anchors-v1/'
ANCHORS = {26: 435, 35: 574, 42: 692, 61: 1000}
COUNTS = (35, 42, 61)
ACCEPTED = 'complete_under_recorded_mixed_policy'


def verify_comparison(old: dict[str, Any], new: dict[str, Any], k: int) -> dict[str, Any]:
    if k not in ANCHORS:
        raise ValueError('Unrequested district count.')
    for report in (old, new):
        if (report['state_fips'] != '36' or report['district_count'] != k
                or report['house_sizes'] != [ANCHORS[k]] or report['policy'] != checks.POLICY):
            raise ValueError('Experiment identity or connectivity policy differs.')
    changes = {key: [old['configuration'].get(key), new['configuration'].get(key)]
               for key in old['configuration'].keys() | new['configuration'].keys()
               if old['configuration'].get(key) != new['configuration'].get(key)}
    if changes != {'inner_max_iterations': [300, 1000]}:
        raise ValueError('Only the inner iteration limit may differ from this anchor baseline.')
    if (old['status'] != 'failed' or old['failed_phase'] != 'solve'
            or old['optimizer_failure']['iterations'] != 300 or old['optimizer_failure']['plan_returned'] is not False):
        raise ValueError('Expected this anchor\'s original 300-iteration numerical failure.')
    if old['source']['archive_sha256'] != new['source']['archive_sha256']:
        raise ValueError('Source archive changed.')
    if old['recorded_connections'] != new['recorded_connections']:
        raise ValueError('Recorded links changed.')
    for key in ('python', 'packages'):
        if old['environment'][key] != new['environment'][key]:
            raise ValueError(f'Runtime environment changed: {key}')
    if any(new['code_sha256'].get(path) != digest for path, digest in old['code_sha256'].items()):
        raise ValueError('Original numerical/source code changed.')
    return {'only_setting_changed': changes, 'same_source_code_environment_and_links': True}


def verify_prefix(old: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    successful = [row for row in old['solver_progress'] if row['inner_optimizer']['success']]
    keys = ('success', 'status', 'message', 'iterations', 'function_evaluations', 'iteration_limit_reached')
    for row in successful:
        index = row['balance_pass'] - 1
        if index >= len(trace['passes']) or any(row['inner_optimizer'][key] != trace['passes'][index]['optimizer'][key] for key in keys):
            raise ValueError('Previously successful inner-pass termination/counters changed.')
    index = old['optimizer_failure']['balance_pass'] - 1
    if index >= len(trace['passes']):
        raise ValueError('The rerun did not reach the original failing pass.')
    followup = trace['passes'][index]
    checkpoint = followup['at_original_budget']
    if checkpoint is not None and checkpoint['objective_evaluations'] != old['optimizer_failure']['function_evaluations']:
        raise ValueError('Objective evaluation count at the original budget differs from the baseline.')
    return {'matched_successful_pass_count': len(successful), 'original_failing_pass': index + 1,
            'new_run_checkpoint_available': checkpoint is not None,
            'new_run_at_300': checkpoint,
            'additional_iterations': followup['optimizer']['iterations'] - 300,
            'additional_objective_improvement': followup['objective_improvement_after_original_budget'],
            'terminal_max_deviation_people': followup['terminal_max_deviation_people'],
            'terminal_inner_success': followup['optimizer']['success'],
            'note': 'Only original termination/counters can be compared. Objective/population trajectory at iteration 300 was recorded in the rerun, not the historical failure.'}


def verify_plan(directory: Path, report: dict[str, Any], populations: dict[str, int], k: int) -> dict[str, Any]:
    if report['status'] == 'failed':
        return {'accepted_plan': False, 'failure': checks.failure_details(report)}
    if report['status'] != ACCEPTED:
        raise ValueError('A requested attempt is not terminal.')
    manifest = checks.read_json(directory / 'maps/map-manifest.json')
    if manifest != report['maps']:
        raise ValueError('Saved map manifest differs from the measured report.')
    audit, final = manifest['connectivity_validation'], report['final_plan']
    if (audit['policy'] != checks.POLICY or audit['passed'] is not True
            or audit['source_coverage_preserved_exactly'] is not True or audit['source_geometry_modified'] is not False
            or final['all_districts_policy_connected'] is not True or final['policy_part_components'] != [1] * k
            or [row['district_id'] for row in audit['districts']] != list(range(k))
            or any(row['connected_components_after_links'] != 1 for row in audit['districts'])):
        raise ValueError('Accepted plan lacks independent polygon-plus-recorded-link connectivity.')
    assignments = checks.read_json(directory / 'solver-result.json')['assignments']
    population_audit = checks.verify_assignments(assignments, populations, k, final)
    artifact_count = checks.verify_compressed_maps(directory, manifest)
    links = json.loads(gzip.decompress((directory / 'maps/recorded-connections.geojson.gz').read_bytes()))
    checks.verify_connections(links, checks.read_json(directory / 'recorded-connections.json'), report, assignments)
    outlines = json.loads(gzip.decompress((directory / 'maps/districts-national.geojson.gz').read_bytes()))
    props = sorted((feature['properties'] for feature in outlines['features']), key=lambda row: row['district_id'])
    if ([row['district_id'] for row in props] != list(range(k))
            or [row['population'] for row in props] != population_audit['district_populations']
            or [row['block_count'] for row in props] != population_audit['district_block_counts']):
        raise ValueError('Delivered map properties disagree with independently recomputed populations.')
    if report['solver']['all_inner_optimizer_passes_succeeded'] is not True:
        raise ValueError('An accepted plan contains a failed inner optimizer pass.')
    return {'accepted_plan': True, 'final_plan': final, 'initial_plan': report['initial_plan'],
            'after_repair_plan': report['after_repair_plan'], 'postprocessing': report['postprocessing'],
            'independent_population_audit': population_audit, 'verified_compressed_map_artifact_count': artifact_count,
            'physical_polygon_components': [row['physical_polygon_components'] for row in audit['districts']],
            'policy_polygon_components': [row['connected_components_after_links'] for row in audit['districts']],
            'strict_polygon_validation': manifest['strict_validation'], 'policy_polygon_validation': audit,
            'outer_termination': checks.outer_termination(report['solver'], report['configuration']),
            'payloads': {key: manifest[key] for key in ('district_outlines', 'recorded_connections', 'load_scenarios')},
            'connection_districts': [feature['properties']['used_by_district'] for feature in links['features']]}


def load_run(k: int, populations: dict[str, int], *, reference: bool = False) -> tuple[dict[str, Any], dict[str, str]]:
    directory = REFERENCE if reference else OUTPUT / f'states/36/districts-{k}'
    path = directory / 'benchmark.json'
    current = checks.read_json(path)
    baseline_directory = SUITE / f'policies/new-york-links-v1/states/36/districts-{k}'
    baseline_path = baseline_directory / 'benchmark.json'
    old = checks.read_json(baseline_path)
    if current['status'] not in ('failed', ACCEPTED):
        raise ValueError(f'K{k} has not reached a terminal state.')
    if reference and current['status'] != ACCEPTED:
        raise ValueError('The K26 reference must remain an accepted prior plan.')
    if not reference and current['run_kind'] != 'new_york_inner_budget_anchors_experiment_v1':
        raise ValueError('Unexpected new experiment run kind.')
    comparison = verify_comparison(old, current, k)
    if current['comparison_baseline']['failed_policy_report_sha256'] != checks.sha256(baseline_path):
        raise ValueError('Historical failed report hash mismatch.')
    flags = ('all_original_strict_files_byte_identical', 'all_original_diagnostic_files_byte_identical',
             'national_suite_byte_identical', 'source_archive_byte_identical',
             'prior_policy_and_correction_evidence_byte_identical', 'run_code_unchanged',
             'original_failed_policy_tree_byte_identical', 'baseline_configuration_only_inner_budget_changed',
             'recorded_connections_byte_identical')
    if not reference:
        flags += ('completed_k26_tree_byte_identical',)
        linked = current['completed_k26_reference']
        if linked['report_sha256'] != checks.sha256(REFERENCE / 'benchmark.json') or linked['reused_without_rerun'] is not True:
            raise ValueError('The completed K26 reference was not preserved.')
    if not all(current['preservation_audit'].get(key) is True for key in flags):
        raise ValueError('Historical evidence preservation was not verified by the runner.')
    for name, expected in current['artifact_sha256'].items():
        if checks.sha256(directory / name) != expected:
            raise ValueError(f'Measured artifact changed: K{k}/{name}')
    for name, expected in current['code_sha256'].items():
        if checks.sha256(ROOT / name) != expected:
            raise ValueError(f'Measured code changed: {name}')
    if checks.sha256(directory / 'recorded-connections.json') != checks.sha256(baseline_directory / 'recorded-connections.json'):
        raise ValueError('Recorded connection file is not byte-identical to this baseline.')
    source_audit = checks.verify_source_policy(checks.read_json(directory / 'recorded-connections.json'), current, populations)
    rows = [json.loads(line, object_pairs_hook=checks.unique_pairs) for line in (directory / 'optimizer-trace.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    trace = trace_checks.verify_trace(rows, current['optimizer_trace'], k=k, total=checks.TOTAL)
    prefix = verify_prefix(old, trace)
    plan = verify_plan(directory, current, populations, k)
    if plan['accepted_plan'] and not trace['all_inner_passes_succeeded']:
        raise ValueError('Accepted plan has a failed inner trace.')
    return {
        'district_count': k, 'house_size': ANCHORS[k], 'read_only_reference': reference,
        'benchmark_path': path.relative_to(ROOT).as_posix(), 'benchmark_sha256': checks.sha256(path),
        'code_sha256': current['code_sha256'], 'source_sha256': current['source']['archive_sha256'],
        'baseline': {'status': old['status'], 'accepted_plan': False,
                     'benchmark_sha256': checks.sha256(baseline_path), 'benchmark_path': baseline_path.relative_to(ROOT).as_posix(),
                     'timed_pipeline_wall_seconds': old['timed_pipeline_wall_seconds'], 'solve_wall_seconds': old['phases']['solve']['wall_seconds'],
                     'peak_process_working_set_bytes': old['peak_process_working_set_bytes'], 'optimizer_failure': old['optimizer_failure'],
                     'iteration_trace_available': False},
        'status': current['status'], 'timed_pipeline_wall_seconds': current['timed_pipeline_wall_seconds'],
        'solve_wall_seconds': current['phases']['solve']['wall_seconds'], 'phases': current['phases'],
        'peak_process_working_set_bytes': current['peak_process_working_set_bytes'],
        'configuration': current['configuration'], 'comparison': comparison, 'prefix_comparison': prefix,
        'source_connection_verification': source_audit, 'preservation_audit': current['preservation_audit'],
        'trace': trace, 'started_at': current['started_at'], 'finished_at': current['finished_at'],
        'map_url': ('http://127.0.0.1:8770/corrections/new-york-inner-budget-v1/' if reference else URL) + f'states/36/districts-{k}/',
        **plan,
    }, checks.read_json(directory / 'preserved-file-inventory.json')


def verify_execution(manifest: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    if manifest['status'] not in ('complete', 'complete_with_numerical_failures', 'stopped') or not manifest.get('finished_at'):
        raise ValueError('The new anchor suite is still active.')
    if len(runs) != 3 or {row['district_count'] for row in runs} != set(COUNTS):
        raise ValueError('The suite comparison must contain precisely the three new anchors.')
    jobs = manifest['jobs']
    if len(jobs) != 3 or {job['district_count'] for job in jobs} != set(COUNTS):
        raise ValueError('The launcher job universe differs from the requested three anchors.')
    indexed = {row['district_count']: row for row in runs}
    for job in jobs:
        row = indexed[job['district_count']]
        if (job['status'] != row['status'] or not job.get('finished_at')
                or type(job.get('exit_code')) is not int
                or (job['exit_code'] == 0) != row['accepted_plan']
                or job['benchmark_sha256'] != row['benchmark_sha256']):
            raise ValueError('Terminal child metadata differs from its saved benchmark.')
        if trace_checks.finite(job['process_wall_seconds'], 'child process runtime') < row['timed_pipeline_wall_seconds']:
            raise ValueError('Child process runtime is shorter than its measured pipeline.')
        progress = ROOT / row['benchmark_path']
        progress = progress.parent / 'progress.json'
        if checks.sha256(progress) != job['progress_sha256']:
            raise ValueError('Terminal child progress changed.')
        validation = job.get('terminal_validation', {})
        if (validation.get('passed') is not True
                or validation.get('classification') != ('validated_complete_plan' if row['accepted_plan'] else 'verified_numerical_failure')
                or validation.get('benchmark_sha256') != job['benchmark_sha256']
                or validation.get('progress_sha256') != job['progress_sha256']):
            raise ValueError('Launcher did not verify a terminal child result.')
        if row['code_sha256'] != manifest['code_sha256']:
            raise ValueError('A child used code outside the launcher snapshot.')
        if manifest['baseline_report_sha256'][str(row['district_count'])] != row['baseline']['benchmark_sha256']:
            raise ValueError('A child baseline differs from the launcher snapshot.')
    if manifest['status'] == 'complete' and not all(row['accepted_plan'] for row in runs):
        raise ValueError('A complete suite contains failed district plans.')
    if manifest['status'] == 'complete_with_numerical_failures' and all(row['accepted_plan'] for row in runs):
        raise ValueError('The suite failure classification contradicts its children.')
    return manifest


def summary(validation_note: str) -> dict[str, Any]:
    first = checks.read_json(OUTPUT / 'states/36/districts-35/benchmark.json')
    populations = checks.source_populations(first['source']['archive_sha256'])
    runs, inventories = zip(*(load_run(k, populations) for k in COUNTS), strict=True)
    reference, reference_inventory = load_run(26, populations, reference=True)
    reference_process = checks.read_json(REFERENCE.parents[2] / 'process.json')
    if (reference_process['status'] != 'finished' or reference_process['exit_code'] != 0
            or reference_process['benchmark_sha256'] != reference['benchmark_sha256']):
        raise ValueError('K26 reference process record no longer matches its completed benchmark.')
    merged: dict[str, str] = {}
    for inventory in (*inventories, reference_inventory):
        for path, digest in inventory.items():
            if path in merged and merged[path] != digest:
                raise ValueError('Attempts disagree about protected history identity.')
            merged[path] = digest
    for path, digest in merged.items():
        if checks.sha256(ROOT / path) != digest:
            raise ValueError(f'Protected history changed: {path}')
    if any(row['code_sha256'] != runs[0]['code_sha256'] for row in runs[1:]):
        raise ValueError('The three new plans used different frozen pipeline code.')
    if any(row['source_sha256'] != runs[0]['source_sha256'] for row in (*runs[1:], reference)):
        raise ValueError('Source archive differs across anchors.')
    manifest = checks.read_json(OUTPUT / 'run.json')
    inventory_path = OUTPUT / 'preserved-file-inventory.json'
    parent_inventory = checks.read_json(inventory_path)
    if (checks.sha256(inventory_path) != manifest['preserved_file_inventory_sha256']
            or len(parent_inventory) != manifest['protected_file_count']
            or any(inventory != parent_inventory for inventory in inventories)):
        raise ValueError('New children and launcher disagree about the preserved historical inventory.')
    if (manifest['completed_k26_reference']['report_sha256'] != reference['benchmark_sha256']
            or manifest['completed_k26_reference']['reused_without_rerun'] is not True):
        raise ValueError('Launcher does not identify the preserved K26 reference.')
    execution = verify_execution(manifest, list(runs))
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'New York K35/K42/K61 for House 574/692/1000 with 1,000 inner iterations; K26 is a preserved prior reference.',
            'runs': list(runs), 'reference_k26': reference, 'execution': execution,
            'accepted_plan_count': sum(row['accepted_plan'] for row in runs),
            'failed_plan_count': sum(not row['accepted_plan'] for row in runs),
            'preserved_historical_file_count': len(merged), 'total_population': checks.TOTAL, 'block_count': checks.BLOCKS,
            'validation_note': validation_note,
            'notes': [
                'Each new plan is compared with its own original failed 300-iteration attempt. Only inner_max_iterations changes to 1,000; original code, source, seed, other settings and recorded links are retained.',
                'K26 was not rerun. Its timing and results are a read-only reference from the earlier completed experiment, excluded from new-suite elapsed time and counts.',
                'An original failed runtime stops in optimization; it is not the runtime of a complete district plan. New completed runtimes include repair, independent polygon validation and map export. Runs are serial on a shared desktop, with measured observer overhead.',
                'Normalized negative dual is minimized. Objective gain is initial minus current objective within one balancing pass only; center changes alter the objective between passes. Whole-block population imbalance can worsen while objective improves.',
                'Iteration-300 checkpoints are observations in the new runs. Historical failed attempts did not save objective or population trajectories. Diagnostic point assignments are not accepted connected plans.',
                'Successful inner optimization, outer center convergence, postprocessed population balance and polygon-plus-recorded-link connectivity are separate outcomes. Physical connectivity remains distinct from recorded-link policy connectivity.',
                'Map payloads are compressed bytes on disk, not browser memory or transfer latency. Full block geometry remains split into county files loaded on demand.',
            ]}


def markdown(data: dict[str, Any]) -> str:
    lines = ['# New York: remaining 1,000-iteration anchors', '', data['scope'], '',
             f"{data['accepted_plan_count']} accepted new plans; {data['failed_plan_count']} failed new attempts. {data['preserved_historical_file_count']:,} historical files remain byte-identical.", '',
             '| Districts / House | Outcome | Maximum final deviation | Pipeline | Solve | Peak memory | Outer centers |',
             '|---|---|---:|---:|---:|---:|---|']
    for row in [data['reference_k26'], *data['runs']]:
        final = row.get('final_plan')
        deviation = f"{final['max_absolute_deviation_people']:.6f} people ({final['max_absolute_deviation_percent']:.9f}%)" if final else 'No accepted plan'
        outer = row.get('outer_termination', {}).get('status', 'Unavailable')
        lines.append(f"| {row['district_count']} / {row['house_size']}{' (prior reference)' if row['read_only_reference'] else ''} | {row['status']} | {deviation} | {row['timed_pipeline_wall_seconds']:.3f} s | {row['solve_wall_seconds']:.3f} s | {row['peak_process_working_set_bytes']/2**30:.3f} GiB | {outer} |")
    for row in data['runs']:
        maximum_inner = max(item['optimizer']['iterations'] for item in row['trace']['passes'])
        above_original = sum(item['optimizer']['iterations'] > 300 for item in row['trace']['passes'])
        lines += ['', f"## {row['district_count']} districts / House {row['house_size']}", '',
                  f"Original failure: {row['baseline']['timed_pipeline_wall_seconds']:.3f} s through solver failure on pass {row['baseline']['optimizer_failure']['balance_pass']} at 300 iterations. New trace: {row['trace']['pass_count']} passes, {row['trace']['accepted_iteration_count']:,} accepted iterations, {row['trace']['observed_overhead_seconds']:.3f} s observed overhead.", '',
                  f"The largest inner pass used **{maximum_inner} of 1,000 allowed iterations**; {above_original} passes exceeded the original 300-iteration budget."]
        if row['accepted_plan']:
            lines += ['', row['outer_termination']['disclosure'], '',
                      f"All {row['district_count']} districts pass graph and independent polygon-plus-link connectivity. Physical polygon components per district: `{row['physical_polygon_components']}`. Recorded links belong to display district(s): `{[value+1 for value in row['connection_districts']]}`.", '',
                      f"[Validated district map]({row['map_url']})"]
        else:
            lines += ['', row['failure']['disclosure']]
        prefix = row['prefix_comparison']
        if prefix['new_run_at_300']:
            pop = prefix['new_run_at_300']['population']['max_absolute_deviation_people']
            direction = 'increased' if prefix['terminal_max_deviation_people'] > pop else 'decreased'
            lines += ['', f"At the new run's checkpoint corresponding to the original failing pass {prefix['original_failing_pass']}, maximum population deviation **{direction}** from {pop:.6f} people at iteration 300 to {prefix['terminal_max_deviation_people']:.6f} at termination; additional objective improvement {prefix['additional_objective_improvement']:.12g}. These are intermediate optimizer assignments, before repair/rebalancing."]
    lines += ['', f'[Interactive comparison and optimizer traces]({URL})', '', 'Validation: ' + data['validation_note'], '']
    lines.extend('- ' + note for note in data['notes'])
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-note', default='Terminal reports, hashes, original source DBF, traces and final artifacts independently verified.')
    args = parser.parse_args()
    data = summary(args.validation_note)
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    template = (ROOT / 'scripts/assets/new-york-budget-anchors-viewer.html').read_text(encoding='utf-8')
    (OUTPUT / 'comparison.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    (OUTPUT / 'index.html').write_text(template.replace('__ANCHOR_DATA__', payload), encoding='utf-8')
    REPORT.with_suffix('.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    REPORT.with_suffix('.md').write_text(markdown(data), encoding='utf-8')
    print(json.dumps({'accepted': data['accepted_plan_count'], 'failed': data['failed_plan_count'], 'url': URL}))


if __name__ == '__main__':
    main()
