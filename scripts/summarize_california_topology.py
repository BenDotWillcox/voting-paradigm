"""Validate and summarize the California source-connectivity diagnosis.

No solver runs, source geometry changes, or historical result edits.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.district_block_sources import sha256

OUTPUT = ROOT / '.cache/state-block-benchmark/suite-through-1000/diagnostics/california'


def run() -> dict:
    diagnosis = json.loads((OUTPUT / 'diagnosis.json').read_text(encoding='utf-8'))
    geography = json.loads((OUTPUT / 'geography-context.json').read_text(encoding='utf-8'))
    optimizer = json.loads((OUTPUT / 'optimizer-starting-point.json').read_text(encoding='utf-8'))
    inventory = json.loads((OUTPUT / 'preserved-file-inventory.json').read_text(encoding='utf-8'))
    for path, digest in inventory.items():
        if sha256(ROOT / path) != digest:
            raise ValueError(f'Historical file changed: {path}')
    for path, digest in diagnosis['artifact_sha256'].items():
        if sha256(OUTPUT / path) != digest:
            raise ValueError(f'Diagnostic artifact changed: {path}')
    for path, digest in diagnosis['code_sha256'].items():
        if sha256(ROOT / path) != digest:
            raise ValueError(f'Diagnostic source changed: {path}')
    if sha256(ROOT / optimizer['evidence_path']) != optimizer['evidence_sha256']:
        raise ValueError('New York evidence changed.')
    components = diagnosis['components']
    if diagnosis['blocks_spanning_components']:
        raise ValueError('Summary requires unambiguous whole-block component ownership.')
    for field, total in [('population', diagnosis['total_population']),
                         ('block_count', diagnosis['block_count']),
                         ('part_count', diagnosis['part_count'])]:
        if sum(row[field] for row in components) != total:
            raise ValueError(f'Component {field} does not reconcile.')
    labels = {row['id']: row['label'] for row in geography['components']}
    selected_ids = diagnosis['plans'][0]['selected_link_ids']
    for plan in diagnosis['plans']:
        if plan['selected_link_ids'] != selected_ids:
            raise ValueError('Expected the same single-root forest at every anchor.')
        audit = plan['augmented_graph_validation']
        if not audit['all_source_parts_reached'] or audit['component_sizes'] != [diagnosis['part_count']]:
            raise ValueError('Full augmented-graph coverage did not pass.')
        if plan['actual_district_plan_generated']:
            raise ValueError('This summary is only for a source diagnosis.')
    selected = [link for link in diagnosis['links'] if link['id'] in selected_ids]
    if len(selected) != len(components) - 1:
        raise ValueError('Selected edges do not have tree cardinality.')
    # Recompute component-level connectivity independently of the saved part traversal.
    adjacency = {row['id']: set() for row in components}
    for link in selected:
        if not link['eligible_positive_gap'] or link['source_boundaries_intersect']:
            raise ValueError('Selected candidate violates geometry eligibility.')
        if any(end['source_boundary_error_degrees'] > 1e-9 for end in link['endpoints']):
            raise ValueError('Endpoint is not on its source boundary.')
        a, b = link['component_ids']
        adjacency[a].add(b)
        adjacency[b].add(a)
    pending, seen = [0], {0}
    while pending:
        for neighbor in adjacency[pending.pop()]:
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    if len(seen) != len(components):
        raise ValueError('Selected source-component tree is disconnected.')
    report = {
        'schema_version': 1,
        'scope': 'California exact source topology and proposed population-aware water forest; no district plans generated.',
        'map_url': 'http://127.0.0.1:8770/diagnostics/california/',
        'total_population': diagnosis['total_population'],
        'block_count': diagnosis['block_count'],
        'part_count': diagnosis['part_count'],
        'physical_component_count': len(components),
        'detached_population': sum(row['population'] for row in components if row['id'] != 0),
        'components': [{**row, 'label': labels[row['id']]} for row in components],
        'selected_links': [{**link, 'component_labels': [labels[c] for c in link['component_ids']]} for link in selected],
        'plans': diagnosis['plans'],
        'strict_baseline': diagnosis['original_runs'],
        'diagnostic_runtime_seconds': diagnosis['elapsed_seconds'],
        'diagnostic_peak_rss_bytes': diagnosis['diagnostic_peak_rss_bytes'],
        'measurement_scope': 'Fresh part-graph diagnosis including geometry loading/dissolve; not solver or plan runtime. Original strict preflight is separately reported.',
        'geography': geography,
        'optimizer_starting_point': optimizer,
        'limits': diagnosis['limitations'],
        'validation': {'historical_file_hashes_verified': len(inventory),
                       'diagnostic_artifact_and_code_hashes_verified': True,
                       'component_totals_reconciled': True,
                       'independent_component_tree_check': True,
                       'full_part_graph_traversal': diagnosis['plans'][0]['augmented_graph_validation'],
                       'source_dissolves_are_valid_single_polygons': diagnosis['independent_dissolved_polygon_check_passed']},
        'source_artifacts': {name: sha256(OUTPUT / name) for name in
                             ['diagnosis.json', 'geography-context.json', 'optimizer-starting-point.json']},
    }
    path = ROOT / 'prompts/california-topology-diagnosis.json'
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(path), 'components': len(components), 'selected_links': len(selected),
                      'part_count': diagnosis['part_count'], 'validation': 'passed'}))
    return report


if __name__ == '__main__':
    run()
