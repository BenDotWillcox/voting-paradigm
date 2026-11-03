"""Synthetic checks for preserved-evidence replay and bounded continuation."""
from copy import deepcopy

import pytest

from districting.connectivity import repair_and_rebalance
from scripts import diagnose_west_virginia_balance as diagnosis


@pytest.fixture
def replay_fixture(monkeypatch):
    monkeypatch.setattr(diagnosis, 'TOTAL', 100)
    labels = [0, 0, 0, 1, 1]
    pops = [30, 20, 10, 20, 20]
    geoids = ['a', 'b', 'c', 'd', 'e']
    move = {'units': [2], 'source_district': 0, 'target_district': 1,
            'population': 10, 'geoids': ['c']}
    return labels, pops, geoids, move


def test_replay_reconciles_population_and_trace_without_mutating_inputs(replay_fixture):
    labels, pops, geoids, move = replay_fixture
    original = deepcopy((labels, pops, geoids, move))
    trace = []
    final, totals = diagnosis.replay(
        labels, [60, 40], [move], pops, geoids, trace, 1000, improving=True,
    )
    assert final == (0, 0, 1, 1, 1)
    assert totals == [50, 50]
    assert trace[0]['moves'] == 1001
    assert trace[0]['max_deviation_people'] == 0
    assert trace[0]['squared_deviation_numerator'] == 0
    assert (labels, pops, geoids, move) == original


@pytest.mark.parametrize('change', [
    {'geoids': ['wrong-geoid']},
    {'population': 11},
    {'source_district': 1},
    {'units': [2, 2], 'geoids': ['c', 'c'], 'population': 20},
    {'units': [], 'geoids': [], 'population': 0},
    {'units': [-1], 'geoids': ['e'], 'source_district': 1,
     'target_district': 0, 'population': 20},
    {'units': [True], 'geoids': ['b'], 'population': 20},
    {'target_district': -1},
    {'target_district': True},
    {'source_district': False},
    {'target_district': 0},
])
def test_replay_rejects_corrupted_move_identity(replay_fixture, change):
    labels, pops, geoids, move = replay_fixture
    move.update(change)
    with pytest.raises(ValueError):
        diagnosis.replay(labels, [60, 40], [move], pops, geoids, None, 0, improving=False)


def test_replay_rejects_a_valid_transfer_that_worsens_balance(replay_fixture):
    labels, pops, geoids, move = replay_fixture
    move.update(units=[3], source_district=1, target_district=0,
                population=20, geoids=['d'])
    with pytest.raises(ValueError, match='strictly improve'):
        diagnosis.replay(labels, [60, 40], [move], pops, geoids, None, 0, improving=True)


def test_component_audit_counts_fragmentation_isolated_nodes_and_empty_districts():
    graph = ((1,), (0, 2), (1, 3), (2,), (), ())
    labels = [0, 1, 0, 1, 2, 2]
    assert diagnosis.components(graph, labels, 4) == [2, 2, 2, 0]
    # Intervening other-district vertices must never create an induced path.
    assert diagnosis.components(graph, [0, 0, 0, 1, 2, 2], 4) == [1, 1, 2, 0]


def test_stage_keeps_zero_population_vertices_in_connectivity_audit(monkeypatch):
    monkeypatch.setattr(diagnosis, 'K', 2)
    stage = diagnosis.stage([0, 1, 0], [10, 0, 10], ((1,), (0, 2), (1,)))
    assert stage['populations'] == [20, 0]
    assert stage['components'] == [2, 1]
    assert stage['accepted_map'] is False


def test_hundred_move_budget_split_matches_uninterrupted_trace():
    # Both districts stay nonempty and connected along a path. Exactly 100
    # transfers are needed; the split preserves the original candidate ties.
    n = 240
    graph = [tuple(j for j in (i - 1, i + 1) if 0 <= j < n) for i in range(n)]
    labels = [0] * 220 + [1] * 20
    populations = [1] * n
    first = repair_and_rebalance(graph, labels, populations, n_districts=2, max_moves=37)
    assert first.stop_reason == 'max_moves'
    assert len(first.rebalance_moves) == 37
    continuation = repair_and_rebalance(
        graph, first.assignments, populations, n_districts=2, max_moves=63,
    )
    uninterrupted = repair_and_rebalance(
        graph, labels, populations, n_districts=2, max_moves=100,
    )
    assert continuation.repair_moves == ()
    assert continuation.repaired_assignments == first.assignments
    assert first.rebalance_moves + continuation.rebalance_moves == uninterrupted.rebalance_moves
    assert continuation.assignments == uninterrupted.assignments
    # Reaching the count limit exactly is not itself proof of truncation:
    # no eligible improving move remains, so the result is a local optimum.
    assert continuation.stop_reason == uninterrupted.stop_reason == 'local_optimum'
    assert diagnosis.components(graph, continuation.assignments, 2) == [1, 1]
    assert labels == [0] * 220 + [1] * 20


@pytest.mark.parametrize('artifact', ['diagnosis.json', 'probe-assignments.json', 'admitted.json'])
def test_existing_or_partial_attempt_is_refused_without_touching_evidence(
    tmp_path, monkeypatch, artifact,
):
    monkeypatch.setattr(diagnosis, 'OUTPUT', tmp_path)
    saved = b'{"previous": "retain original attempt"}'
    (tmp_path / artifact).write_bytes(saved)
    monkeypatch.setattr(diagnosis, 'state_execution_lock',
                        lambda *args: pytest.fail('Duplicate must be refused before locking/running.'))
    with pytest.raises(FileExistsError, match='earlier diagnosis/probe'):
        diagnosis.main()
    assert (tmp_path / artifact).read_bytes() == saved

