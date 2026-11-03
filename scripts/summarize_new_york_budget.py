"""Verify and summarize the isolated New York K26 inner-budget experiment.

This reader never edits measured code or prior benchmark evidence. The only
outputs are a new comparison, its viewer, and the durable experiment report.
Objective values have meaning within one balancing pass, not across passes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
from typing import Any

try:
    from scripts import summarize_new_york_links as checks
except ModuleNotFoundError:  # direct script execution
    import summarize_new_york_links as checks

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / '.cache/state-block-benchmark/suite-through-1000'
OUTPUT = SUITE / 'corrections/new-york-inner-budget-v1'
RUN = OUTPUT / 'states/36/districts-26'
BASELINE = SUITE / 'policies/new-york-links-v1/states/36/districts-26'
REPORT = ROOT / 'prompts/new-york-inner-budget-benchmark'
URL = 'http://127.0.0.1:8770/corrections/new-york-inner-budget-v1/'
K = 26


def finite(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'Nonfinite or nonnumeric {label}.')
    return float(value)


def close(actual: Any, expected: float, label: str, *, tolerance: float = 1e-8) -> None:
    if not math.isclose(finite(actual, label), expected, abs_tol=tolerance, rel_tol=1e-11):
        raise ValueError(f'Inconsistent {label}: {actual} != {expected}.')


def verify_fixed_experiment(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Only the inner iteration budget may change among numerical settings."""
    for report in (baseline, current):
        if (report['state_fips'] != '36' or report['district_count'] != K
                or report['house_sizes'] != [435] or report['policy'] != checks.POLICY):
            raise ValueError('Unexpected experiment state, district count, anchor or policy.')
    before, after = baseline['configuration'], current['configuration']
    differences = {
        key: {'before': before.get(key), 'after': after.get(key)}
        for key in set(before) | set(after) if before.get(key) != after.get(key)
    }
    if differences != {'inner_max_iterations': {'before': 300, 'after': 1000}}:
        raise ValueError('The experiment changed more than the authorized inner iteration budget.')
    if (baseline['status'] != 'failed' or baseline.get('failed_phase') != 'solve'
            or baseline.get('optimizer_failure', {}).get('iterations') != 300):
        raise ValueError('The baseline is not the preserved 300-iteration numerical failure.')
    if baseline['source']['archive_sha256'] != current['source']['archive_sha256']:
        raise ValueError('Source archive changed between attempts.')
    if baseline['recorded_connections'] != current['recorded_connections']:
        raise ValueError('Recorded connection identities or geometry changed between attempts.')
    for name, digest in baseline['code_sha256'].items():
        if current['code_sha256'].get(name) != digest:
            raise ValueError(f'Original numerical/source code changed: {name}')
    if baseline['environment']['packages'] != current['environment']['packages']:
        raise ValueError('Package versions changed between the controlled attempts.')
    if baseline['environment']['python'] != current['environment']['python']:
        raise ValueError('Python version changed between the controlled attempts.')
    return {
        'only_numerical_setting_changed': differences,
        'same_original_code_snapshot': True, 'same_source_archive': True,
        'same_recorded_connections': True, 'same_package_versions': True, 'same_python_version': True,
        'original_code_file_count': len(baseline['code_sha256']),
        'instrumentation_note': 'The new observer records existing objective evaluations and accepted iterates without adding objective evaluations or changing optimizer decisions. Logging introduces measured overhead.',
    }


def verify_population_sample(sample: dict[str, Any], *, k: int, total: int) -> None:
    pop = sample['population']
    assigned, targets, gradient = pop['assigned_populations'], pop['target_populations'], sample['normalized_gradient']
    if any(len(values) != k for values in (assigned, targets, gradient)):
        raise ValueError('A trace sample does not contain one population/gradient per district.')
    tolerance = finite(pop['population_reconstruction_tolerance_people'], 'population reconstruction tolerance')
    if not 0 <= tolerance <= 0.01:
        raise ValueError('Population reconstruction tolerance is unexpectedly broad.')
    tolerance = max(1e-7, tolerance)
    if pop['total_population'] != total:
        raise ValueError('Trace population universe differs from the source resident count.')
    base, remainder = divmod(total, k)
    if targets != [base + int(i < remainder) for i in range(k)]:
        raise ValueError('Trace target populations differ from the unchanged solver integer targets.')
    for i in range(k):
        value = finite(assigned[i], 'assigned population')
        if value < -tolerance or abs(value - round(value)) > tolerance:
            raise ValueError('Trace population is not compatible with whole-block integer populations.')
        close(gradient[i], (value - targets[i]) / total, 'population/gradient relation', tolerance=tolerance / total)
    close(sum(assigned), total, 'trace total population', tolerance=tolerance * k)
    ideal = total / k
    deviations = [abs(value - ideal) for value in assigned]
    close(pop['fractional_ideal_population'], ideal, 'fractional ideal')
    close(pop['max_absolute_deviation_people'], max(deviations), 'trace maximum deviation', tolerance=tolerance)
    close(pop['max_absolute_deviation_percent'], max(deviations) * 100 / ideal, 'trace maximum percentage deviation', tolerance=tolerance)
    close(pop['mean_absolute_deviation_people'], sum(deviations) / k, 'trace mean deviation', tolerance=tolerance)
    close(pop['max_absolute_target_deviation_people'], max(abs(a - b) for a, b in zip(assigned, targets)), 'integer-target deviation', tolerance=tolerance)
    close(pop['max_normalized_gradient'], max(map(abs, gradient)), 'gradient maximum', tolerance=tolerance / total)


def verify_trace(rows: list[dict[str, Any]], reported: dict[str, Any], *, k: int, total: int) -> dict[str, Any]:
    """Check the trace sequence, objective arithmetic, populations and endings."""
    if not rows or reported.get('observation_ok') is not True or reported.get('telemetry_errors'):
        raise ValueError('A complete trustworthy optimizer trace was not recorded.')
    if finite(reported['observed_overhead_seconds'], 'observed overhead') < 0:
        raise ValueError('Observed overhead cannot be negative.')
    if finite(reported['recorded_elapsed_seconds'], 'recorded trace runtime') < 0:
        raise ValueError('Recorded trace runtime cannot be negative.')
    passes: dict[int, list[dict[str, Any]]] = {}
    previous_time = -1.0
    previous_pass = 0
    for row in rows:
        if row.get('schema_version') != 1:
            raise ValueError('Unsupported optimizer trace schema.')
        event = row.get('event')
        if event in ('telemetry_error', 'pass_exception'):
            # A normal DistrictingOptimizationError after a terminal optimizer
            # result is allowed and checked below; telemetry errors never are.
            if event == 'telemetry_error':
                raise ValueError('The observer recorded a telemetry error.')
            continue
        if event not in ('baseline', 'iteration', 'terminal', 'pass_complete'):
            raise ValueError(f'Unknown optimizer trace event: {event}')
        if event == 'pass_complete':
            continue
        index = row['balance_pass']
        if type(index) is not int or index < 1:
            raise ValueError('Invalid balancing-pass label.')
        if index < previous_pass or index > previous_pass + 1:
            raise ValueError('Balancing-pass observations are out of order.')
        previous_pass = index
        elapsed = finite(row['elapsed_seconds'], 'elapsed seconds')
        if elapsed < previous_time or finite(row['pass_elapsed_seconds'], 'pass seconds') < 0:
            raise ValueError('Trace wall time runs backwards.')
        previous_time = elapsed
        finite(row['objective'], 'objective')
        verify_population_sample(row, k=k, total=total)
        passes.setdefault(index, []).append(row)
    if not passes or sorted(passes) != list(range(1, len(passes) + 1)):
        raise ValueError('Balancing-pass sequence has missing or repeated labels.')
    summaries = reported['passes']
    if len(summaries) != len(passes):
        raise ValueError('Trace summary and JSONL disagree about the number of passes.')
    result = []
    for index, samples in passes.items():
        first, last = samples[0], samples[-1]
        if first['event'] != 'baseline' or first['iteration'] != 0 or last['event'] != 'terminal':
            raise ValueError('Each balancing pass needs a baseline and terminal observation.')
        iterations = samples[1:-1]
        if ([row['event'] for row in iterations] != ['iteration'] * len(iterations)
                or [row['iteration'] for row in iterations] != list(range(1, len(iterations) + 1))):
            raise ValueError('Accepted-iteration sequence is incomplete.')
        previous = first['objective']
        previous_evaluations = 0
        for row in samples:
            if type(row['objective_evaluations']) is not int or row['objective_evaluations'] < previous_evaluations:
                raise ValueError('Objective evaluation count runs backwards.')
            previous_evaluations = row['objective_evaluations']
            close(row['improvement_from_initial'], first['objective'] - row['objective'], 'objective improvement from baseline', tolerance=1e-13)
            close(row['improvement_from_previous'], previous - row['objective'], 'objective improvement from previous observation', tolerance=1e-13)
            previous = row['objective']
        optimizer = last['optimizer']
        if (optimizer['actual_maxiter'] != 1000 or optimizer['iterations'] != last['iteration']
                or optimizer['iterations'] != len(iterations)
                or optimizer['function_evaluations'] != last['objective_evaluations']):
            raise ValueError('Optimizer counters, accepted observations or iteration budget disagree.')
        entry = summaries[index - 1]
        first_payload = {key: value for key, value in first.items() if key != 'schema_version'}
        last_payload = {key: value for key, value in last.items() if key != 'schema_version'}
        if entry['balance_pass'] != index or entry['initial_sample'] != first_payload or entry['terminal_sample'] != last_payload:
            raise ValueError('Trace summary endpoints differ from the JSONL.')
        if entry.get('errors') or entry['accepted_iterations'] != len(iterations):
            raise ValueError('The trace summary contains missing observations or observer errors.')
        if entry['inner_optimizer'] != optimizer or entry['objective_evaluations'] != last['objective_evaluations']:
            raise ValueError('Trace summary optimizer termination differs from its JSONL terminal record.')
        at300 = next((row for row in iterations if row['iteration'] == 300), None)
        visual_samples = [{
            'event': row['event'], 'iteration': row['iteration'],
            'objective': row['objective'], 'improvement_from_initial': row['improvement_from_initial'],
            'pass_elapsed_seconds': row['pass_elapsed_seconds'],
            'population': {key: row['population'][key] for key in (
                'max_absolute_deviation_people', 'max_absolute_deviation_percent')},
        } for row in samples]
        result.append({
            'balance_pass': index, 'optimizer': optimizer,
            'initial_objective': first['objective'], 'terminal_objective': last['objective'],
            'objective_improvement': first['objective'] - last['objective'],
            'initial_max_deviation_people': first['population']['max_absolute_deviation_people'],
            'terminal_max_deviation_people': last['population']['max_absolute_deviation_people'],
            'terminal_max_deviation_percent': last['population']['max_absolute_deviation_percent'],
            'at_original_budget': at300,
            'objective_improvement_after_original_budget': at300['objective'] - last['objective'] if at300 else None,
            'max_deviation_people_at_original_budget': at300['population']['max_absolute_deviation_people'] if at300 else None,
            'trace_wall_seconds': last['pass_elapsed_seconds'],
            'wrapper_wall_seconds': entry['wall_seconds'],
            'samples': visual_samples,
        })
    return {
        'passed': True, 'pass_count': len(result), 'passes': result,
        'accepted_iteration_count': sum(row['optimizer']['iterations'] for row in result),
        'all_inner_passes_succeeded': all(row['optimizer']['success'] is True for row in result),
        'recorded_elapsed_seconds': reported['recorded_elapsed_seconds'],
        'observed_overhead_seconds': reported['observed_overhead_seconds'],
        'scope': 'Observer consistency and population reconstruction from existing optimizer gradients; these are intermediate point assignments, not accepted connected districts.',
    }


def verify_first_pass(baseline: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    """The formerly successful pass should retain its exact numerical counters."""
    old = next(row['inner_optimizer'] for row in baseline['solver_progress'] if row['balance_pass'] == 1)
    new = trace['passes'][0]['optimizer']
    keys = ('success', 'status', 'message', 'iterations', 'function_evaluations', 'iteration_limit_reached')
    if any(old[key] != new[key] for key in keys):
        raise ValueError('The first-pass numerical prefix differs from the preserved baseline.')
    return {'matched': True, **{key: old[key] for key in keys},
            'scope': 'Matching first-pass termination and counters corroborate the fixed numerical setup; the original run has no per-iteration objective trace to compare.'}


def verify_execution(report: dict[str, Any], benchmark_path: Path) -> dict[str, Any]:
    process_path = OUTPUT / 'process.json'
    process = checks.read_json(process_path)
    if (process['status'] != 'finished' or not process.get('finished_at')
            or type(process.get('exit_code')) is not int
            or (process['exit_code'] == 0) != (report['status'] == 'complete_under_recorded_mixed_policy')
            or process['benchmark_sha256'] != checks.sha256(benchmark_path)):
        raise ValueError('The terminal process record does not match the saved benchmark.')
    if finite(process['process_wall_seconds'], 'process runtime') < report['timed_pipeline_wall_seconds']:
        raise ValueError('Recorded process runtime is shorter than its measured pipeline.')
    return process


def terminal_plan(directory: Path, report: dict[str, Any], populations: dict[str, int]) -> dict[str, Any]:
    """Independently verify final assignments and delivered maps if they exist."""
    if report['status'] == 'failed':
        return {'accepted_plan': False, 'failure': checks.failure_details(report)}
    if report['status'] != 'complete_under_recorded_mixed_policy':
        raise ValueError('The budget attempt is not terminal; no final comparison was written.')
    manifest = checks.read_json(directory / 'maps/map-manifest.json')
    if manifest != report['maps']:
        raise ValueError('Delivered map manifest differs from the benchmark report.')
    audit = manifest['connectivity_validation']
    if (audit['policy'] != checks.POLICY or audit['passed'] is not True
            or audit['source_coverage_preserved_exactly'] is not True or audit['source_geometry_modified'] is not False
            or report['final_plan']['all_districts_policy_connected'] is not True
            or report['final_plan']['policy_part_components'] != [1] * K
            or [row['district_id'] for row in audit['districts']] != list(range(K))
            or any(row['connected_components_after_links'] != 1 for row in audit['districts'])):
        raise ValueError('The completed plan lacks independent polygon-plus-link connectivity.')
    final = checks.read_json(directory / 'solver-result.json')
    independent = checks.verify_assignments(final['assignments'], populations, K, report['final_plan'])
    artifact_count = checks.verify_compressed_maps(directory, manifest)
    links = json.loads(gzip.decompress((directory / 'maps/recorded-connections.geojson.gz').read_bytes()))
    source_record = checks.read_json(directory / 'recorded-connections.json')
    checks.verify_connections(links, source_record, report, final['assignments'])
    outlines = json.loads(gzip.decompress((directory / 'maps/districts-national.geojson.gz').read_bytes()))
    properties = sorted((feature['properties'] for feature in outlines['features']), key=lambda row: row['district_id'])
    if ([row['district_id'] for row in properties] != list(range(K))
            or [row['population'] for row in properties] != independent['district_populations']
            or [row['block_count'] for row in properties] != independent['district_block_counts']):
        raise ValueError('Delivered outlines disagree with independent final-assignment populations.')
    if report['solver']['all_inner_optimizer_passes_succeeded'] is not True:
        raise ValueError('A completed plan contains an unsuccessful inner optimizer pass.')
    return {
        'accepted_plan': True, 'initial_plan': report['initial_plan'], 'after_repair_plan': report['after_repair_plan'],
        'final_plan': report['final_plan'], 'postprocessing': report['postprocessing'],
        'independent_population_audit': independent, 'verified_compressed_map_artifact_count': artifact_count,
        'physical_polygon_components': [row['physical_polygon_components'] for row in audit['districts']],
        'policy_polygon_components': [row['connected_components_after_links'] for row in audit['districts']],
        'strict_polygon_validation': manifest['strict_validation'], 'policy_polygon_validation': audit,
        'outer_termination': checks.outer_termination(report['solver'], report['configuration']),
        'payloads': {key: manifest[key] for key in ('district_outlines', 'recorded_connections', 'load_scenarios')},
        'map_url': URL + 'states/36/districts-26/',
    }


def summary(validation_note: str) -> dict[str, Any]:
    baseline_path, current_path = BASELINE / 'benchmark.json', RUN / 'benchmark.json'
    baseline, current = checks.read_json(baseline_path), checks.read_json(current_path)
    if current['status'] not in ('complete_under_recorded_mixed_policy', 'failed'):
        raise ValueError('The measured run is active; terminal comparison must wait.')
    controlled = verify_fixed_experiment(baseline, current)
    baseline_reference = current['comparison_baseline']
    if baseline_reference['failed_policy_report_sha256'] != checks.sha256(baseline_path):
        raise ValueError('The prior failed report changed after experiment setup.')
    inventory = checks.read_json(RUN / 'preserved-file-inventory.json')
    for name, expected in inventory.items():
        if checks.sha256(ROOT / name) != expected:
            raise ValueError(f'Protected historical evidence changed: {name}')
    flags = current['preservation_audit']
    for key in ('all_original_strict_files_byte_identical', 'all_original_diagnostic_files_byte_identical',
                'national_suite_byte_identical', 'source_archive_byte_identical',
                'prior_policy_and_correction_evidence_byte_identical', 'run_code_unchanged',
                'original_failed_policy_tree_byte_identical', 'baseline_configuration_only_inner_budget_changed',
                'recorded_connections_byte_identical'):
        if flags.get(key) is not True:
            raise ValueError(f'The measured run did not verify preservation: {key}')
    for name, expected in current['artifact_sha256'].items():
        if checks.sha256(RUN / name) != expected:
            raise ValueError(f'Measured run artifact changed: {name}')
    for name, expected in current['code_sha256'].items():
        if checks.sha256(ROOT / name) != expected:
            raise ValueError(f'Measured code changed after the run: {name}')
    if checks.sha256(BASELINE / 'recorded-connections.json') != checks.sha256(RUN / 'recorded-connections.json'):
        raise ValueError('Recorded connection file is not byte-identical to the failed attempt.')
    populations = checks.source_populations(current['source']['archive_sha256'])
    source_policy = checks.verify_source_policy(checks.read_json(RUN / 'recorded-connections.json'), current, populations)
    rows = [json.loads(line, object_pairs_hook=checks.unique_pairs) for line in (RUN / 'optimizer-trace.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    trace = verify_trace(rows, current['optimizer_trace'], k=K, total=sum(populations.values()))
    controlled['first_pass_numerical_prefix'] = verify_first_pass(baseline, trace)
    original_failure_pass = baseline['optimizer_failure']['balance_pass']
    followup = next((row for row in trace['passes'] if row['balance_pass'] == original_failure_pass), None)
    if followup is not None and followup['at_original_budget'] is not None:
        checkpoint = followup['at_original_budget']
        controlled['original_failing_pass_checkpoint'] = {
            'balance_pass': original_failure_pass, 'source': 'new_run_at_iteration_300',
            'additional_iterations': followup['optimizer']['iterations'] - 300,
            'additional_function_evaluations': followup['optimizer']['function_evaluations'] - checkpoint['objective_evaluations'],
            'additional_trace_wall_seconds': followup['trace_wall_seconds'] - checkpoint['pass_elapsed_seconds'],
            'additional_objective_improvement': followup['objective_improvement_after_original_budget'],
            'max_deviation_people_at_300': followup['max_deviation_people_at_original_budget'],
            'terminal_max_deviation_people': followup['terminal_max_deviation_people'],
            'terminal_inner_success': followup['optimizer']['success'],
        }
    plan = terminal_plan(RUN, current, populations)
    if plan['accepted_plan'] and not trace['all_inner_passes_succeeded']:
        raise ValueError('A completed plan has a failed optimizer trace.')
    return {
        'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'New York 26 districts (House 435), 300 versus 1,000 inner iterations; all other numerical settings, source and recorded links fixed.',
        'controlled_comparison': controlled, 'source_policy_verification': source_policy,
        'total_population': checks.TOTAL, 'block_count': checks.BLOCKS, 'district_count': K,
        'fractional_ideal_population': checks.TOTAL / K,
        'baseline': {
            'status': baseline['status'], 'inner_max_iterations': 300,
            'benchmark_path': baseline_path.relative_to(ROOT).as_posix(), 'benchmark_sha256': checks.sha256(baseline_path),
            'timed_pipeline_wall_seconds': baseline['timed_pipeline_wall_seconds'],
            'solve_wall_seconds': baseline['phases']['solve']['wall_seconds'],
            'peak_process_working_set_bytes': baseline['peak_process_working_set_bytes'],
            'optimizer_failure': baseline['optimizer_failure'], 'solver_progress': baseline['solver_progress'],
            'accepted_plan': False, 'iteration_trace_available': False,
            'note': 'The original failed attempt remains unchanged. It saved pass-level counters but no objective/population trajectory or accepted district plan.',
        },
        'rerun': {
            'status': current['status'], 'inner_max_iterations': 1000,
            'benchmark_path': current_path.relative_to(ROOT).as_posix(), 'benchmark_sha256': checks.sha256(current_path),
            'timed_pipeline_wall_seconds': current['timed_pipeline_wall_seconds'],
            'solve_wall_seconds': current['phases']['solve']['wall_seconds'],
            'peak_process_working_set_bytes': current['peak_process_working_set_bytes'],
            'started_at': current['started_at'], 'finished_at': current['finished_at'],
            'configuration': current['configuration'], 'phases': current['phases'],
            'solver': current.get('solver'), **plan,
        },
        'trace': trace, 'execution': verify_execution(current, current_path),
        'preservation_audit': flags, 'preserved_historical_file_count': len(inventory),
        'trace_path': (RUN / 'optimizer-trace.jsonl').relative_to(ROOT).as_posix(),
        'trace_sha256': checks.sha256(RUN / 'optimizer-trace.jsonl'), 'validation_note': validation_note,
        'notes': [
            'Normalized objective is the negative dual: lower is better. Positive gain is start objective minus current objective. Center updates change the objective; compare gains only within a balancing pass.',
            'The 300-iteration marker is a checkpoint in the new run, not a retroactively recorded baseline trajectory. Only pass 2 directly addresses the original failing pass; later passes have no prior-attempt counterpart.',
            'Population deviations use the fractional statewide ideal. Intermediate populations are reconstructed from already evaluated optimizer gradients; they are not a connected or accepted district plan.',
            'Whole blocks switch assignment in discrete jumps. Improving the dual objective does not require population imbalance to improve at every accepted step.',
            'Successful inner optimization, outer center convergence, final postprocessed population balance, and polygon-plus-link connectivity are separate outcomes.',
            'Both attempts ran serially on a shared desktop; timings include source preparation and, when reached, repair/export/validation. Instrumentation adds recorded overhead, so these are observational timings rather than isolated hardware benchmarks.',
        ],
    }


def report_markdown(data: dict[str, Any]) -> str:
    before, after, trace = data['baseline'], data['rerun'], data['trace']
    complete_passes = [row for row in trace['passes'] if row['optimizer']['success']]
    above_original = [row['balance_pass'] for row in trace['passes'] if row['optimizer']['iterations'] > 300]
    if after['accepted_plan']:
        top_finding = (
            f"The larger inner budget produced a validated 26-district plan. All {len(complete_passes)} inner passes succeeded; "
            f"only passes {', '.join(map(str, above_original))} exceeded 300 iterations. "
            f"The largest pass used {max(row['optimizer']['iterations'] for row in trace['passes'])} of the allowed 1,000 iterations. "
            f"After repair/rebalancing, maximum population deviation is {after['final_plan']['max_absolute_deviation_people']:.6f} people "
            f"({after['final_plan']['max_absolute_deviation_percent']:.9f}%). "
            + after['outer_termination']['disclosure']
        )
    else:
        top_finding = after['failure']['disclosure']
    lines = [
        '# New York: 1,000-iteration inner-budget experiment', '', data['scope'], '',
        top_finding, '',
        f"Result: **{after['status']}**. Original failed evidence and {data['preserved_historical_file_count']:,} protected files remain byte-identical.", '',
        '| Measure | Original: 300 | Rerun: 1,000 |', '|---|---:|---:|',
        f"| Timed pipeline | {before['timed_pipeline_wall_seconds']:.3f} s | {after['timed_pipeline_wall_seconds']:.3f} s |",
        f"| Solve | {before['solve_wall_seconds']:.3f} s | {after['solve_wall_seconds']:.3f} s |",
        f"| Peak process working set | {before['peak_process_working_set_bytes'] / 2**30:.3f} GiB | {after['peak_process_working_set_bytes'] / 2**30:.3f} GiB |",
        '| Accepted district plan | No | ' + ('Yes' if after['accepted_plan'] else 'No') + ' |', '',
        f"The original failed on inner pass {before['optimizer_failure']['balance_pass']} at 300 iterations. The rerun recorded {trace['pass_count']} inner passes and {trace['accepted_iteration_count']:,} accepted optimizer iterations. Observer overhead: {trace['observed_overhead_seconds']:.3f} s.", '',
        '| Pass | Inner iterations | Success | Objective gain | Max deviation at 300 (people) | Terminal max deviation (people) | Pass trace time |',
        '|---:|---:|:---:|---:|---:|---:|---:|',
    ]
    for row in trace['passes']:
        at300 = row['max_deviation_people_at_original_budget']
        lines.append(f"| {row['balance_pass']} | {row['optimizer']['iterations']} | {'Yes' if row['optimizer']['success'] else 'No'} | {row['objective_improvement']:.9g} | {at300:,.3f} | {row['terminal_max_deviation_people']:,.3f} | {row['trace_wall_seconds']:.3f} s |" if at300 is not None else f"| {row['balance_pass']} | {row['optimizer']['iterations']} | {'Yes' if row['optimizer']['success'] else 'No'} | {row['objective_improvement']:.9g} | Not reached | {row['terminal_max_deviation_people']:,.3f} | {row['trace_wall_seconds']:.3f} s |")
    lines += ['', 'The pass table shows intermediate point assignments, before connectivity repair and whole-block rebalancing.', '']
    checkpoint = data['controlled_comparison'].get('original_failing_pass_checkpoint')
    if checkpoint is not None:
        lines += [
            f"On the originally failing pass {checkpoint['balance_pass']}, the new run continued for {checkpoint['additional_iterations']} iterations and {checkpoint['additional_trace_wall_seconds']:.3f} seconds beyond its own 300-iteration checkpoint. The normalized negative-dual objective decreased by {checkpoint['additional_objective_improvement']:.12g}; maximum population deviation changed from {checkpoint['max_deviation_people_at_300']:,.6f} to {checkpoint['terminal_max_deviation_people']:,.6f} people. These checkpoint values were observed in the new run; the preserved original attempt did not record that trajectory.", '',
        ]
    if after['accepted_plan']:
        final = after['final_plan']
        lines += [f"Final postprocessed maximum population deviation: **{final['max_absolute_deviation_people']:.6f} people ({final['max_absolute_deviation_percent']:.9f}%)**. All 26 districts pass polygon-plus-recorded-link connectivity. Physical polygon components per district: `{after['physical_polygon_components']}`.", '', after['outer_termination']['disclosure'], '', f"[Corrected district map]({after['map_url']})", '']
    else:
        lines += [after['failure']['disclosure'], '']
    lines += [f"[Interactive comparison and pass traces]({URL})", '', 'Validation: ' + data['validation_note'], '']
    lines.extend('- ' + note for note in data['notes'])
    return '\n'.join(lines) + '\n'


def viewer(data: dict[str, Any]) -> str:
    template = (ROOT / 'scripts/assets/new-york-budget-viewer.html').read_text(encoding='utf-8')
    payload = json.dumps(data, separators=(',', ':'), ensure_ascii=False).replace('<', '\\u003c')
    return template.replace('__EXPERIMENT_DATA__', payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-note', default='Saved trace, original source DBF, hashes, fixed settings and terminal artifacts independently checked.')
    args = parser.parse_args()
    data = summary(args.validation_note)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'comparison.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (OUTPUT / 'index.html').write_text(viewer(data), encoding='utf-8')
    REPORT.with_suffix('.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    REPORT.with_suffix('.md').write_text(report_markdown(data), encoding='utf-8')
    print(json.dumps({'status': data['rerun']['status'], 'accepted_plan': data['rerun']['accepted_plan'],
                      'inner_passes': data['trace']['pass_count'], 'url': URL, 'report': str(REPORT.with_suffix('.md'))}))


if __name__ == '__main__':
    main()
