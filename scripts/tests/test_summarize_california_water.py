"""Protect the pilot report from accepting incomplete or misattributed results."""
from copy import deepcopy

import pytest

from scripts.summarize_california_water import POLICY, verify_configuration, verify_execution, verify_links


def terminal_evidence():
    report = {'status': 'complete_under_island_water_policy', 'state_fips': '06',
              'district_count': 52, 'policy': POLICY, 'active_phase': None, 'finished_at': 'saved'}
    process = {'status': 'complete', 'benchmark_status': report['status'], 'returncode': 0, 'finished_at': 'saved'}
    progress = {'status': report['status'], 'active_phase': None}
    return process, report, progress


def test_accepts_terminal_consistent_evidence():
    verify_execution(*terminal_evidence())


@pytest.mark.parametrize('target,key,value', [
    (0, 'status', 'running'), (0, 'returncode', 1), (0, 'returncode', False),
    (0, 'benchmark_status', 'failed'), (1, 'district_count', 69),
    (1, 'active_phase', 'solve'), (2, 'active_phase', 'map_export'), (2, 'status', 'running'),
])
def test_rejects_incomplete_or_mismatched_execution(target, key, value):
    evidence = list(terminal_evidence())
    evidence[target][key] = value
    with pytest.raises(ValueError):
        verify_execution(*evidence)


def test_failure_is_an_honest_terminal_outcome():
    process, report, progress = terminal_evidence()
    process.update(status='failed', benchmark_status='failed', returncode=1)
    report['status'] = progress['status'] = 'failed'
    verify_execution(process, report, progress)


def test_rejects_wrong_inner_budget():
    settings = {'seed': 20200955, 'max_outer_iterations': 80, 'inner_max_iterations': 300,
                'center_tolerance_m': 1e-4, 'max_rebalance_moves': 1000,
                'root_eligibility_relative_band': .01, 'group_population_preflight_tolerance': .01,
                'inner_optimization': {'max_line_search_steps': 100}}
    with pytest.raises(ValueError):
        verify_configuration(settings)
    settings['inner_max_iterations'] = 1000
    verify_configuration(settings)


def connections():
    records, features, assignments = [], [], {}
    for i in range(6):
        endpoints = [{'geoid': f'06{i:013}', 'part_node': i, 'part_index': 0, 'coordinate': [-120 + i, 34]},
                     {'geoid': f'06{i+10:013}', 'part_node': i+10, 'part_index': 0, 'coordinate': [-119 + i, 34]}]
        assignments[endpoints[0]['geoid']] = assignments[endpoints[1]['geoid']] = i
        record = {'id': f'ca-{i}', 'component_ids': [0, i+1], 'distance_m': 1200., 'endpoints': endpoints}
        records.append(record)
        features.append({'geometry': {'type': 'LineString', 'coordinates': [x['coordinate'] for x in endpoints]},
                         'properties': {**deepcopy(record), 'endpoint_districts': [i, i], 'used_by_district': i}})
    return features, records, assignments


def test_validates_connection_ownership_against_assignments():
    assert len(verify_links(*connections())) == 6


@pytest.mark.parametrize('field,value', [('used_by_district', None), ('endpoint_districts', [0, 5]),
                                        ('distance_m', 1300.), ('id', 'foreign-link')])
def test_rejects_changed_link_or_claimed_ownership(field, value):
    features, records, assignments = connections()
    features[0]['properties'][field] = value
    with pytest.raises(ValueError):
        verify_links(features, records, assignments)


def test_link_whose_endpoints_differ_is_retained_as_unused():
    features, records, assignments = connections()
    assignments[records[0]['endpoints'][1]['geoid']] = 20
    features[0]['properties'].update(endpoint_districts=[0, 20], used_by_district=None)
    result = verify_links(features, records, assignments)
    assert result[0]['used_by_district'] is None


def test_rejects_removed_connection():
    features, records, assignments = connections()
    with pytest.raises(ValueError):
        verify_links(features[:-1], records, assignments)
