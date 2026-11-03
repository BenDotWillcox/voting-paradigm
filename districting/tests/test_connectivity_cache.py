"""Exact cached donor checks, including mutable membership and multipart guards."""
from collections import Counter
import random

import pytest

from districting import connectivity as c
from districting.part_connectivity import PartConnectivityResult, PartGraph, part_component_counts


def graph(n, edges):
    rows = [set() for _ in range(n)]
    for left, right in edges:
        rows[left].add(right)
        rows[right].add(left)
    return tuple(tuple(sorted(row)) for row in rows)


def grid(width, height):
    return graph(width * height, [
        (i, j) for i in range(width * height) for j in (i + 1, i + width)
        if j < width * height and (j == i + width or i // width == j // width)
    ])


def removal_oracle(adjacency, labels, unit):
    remaining = {i for i, label in enumerate(labels) if label == labels[unit] and i != unit}
    if not remaining:
        return True  # The balancing caller separately prevents an empty donor.
    pending = [min(remaining)]
    seen = {pending[0]}
    while pending:
        for neighbor in adjacency[pending.pop()]:
            if neighbor in remaining and neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return seen == remaining


@pytest.mark.parametrize('seed', range(15))
def test_cached_removals_match_independent_oracle_on_random_connected_partitions(seed):
    rng = random.Random(seed)
    adjacency = grid(8, 6)
    labels = [-1] * len(adjacency)
    for district, unit in enumerate((0, 7, 47)):
        labels[unit] = district
    while -1 in labels:
        candidates = [(unit, labels[neighbor]) for unit, label in enumerate(labels) if label == -1
                      for neighbor in adjacency[unit] if labels[neighbor] >= 0]
        unit, district = rng.choice(candidates)
        labels[unit] = district
    cache = c._DistrictArticulationCache(adjacency, labels)
    for unit in rng.sample(range(len(labels)), len(labels)):
        expected = removal_oracle(adjacency, labels, unit)
        assert cache.preserves_removal(unit) == expected
        assert c._removal_preserves_connectivity(adjacency, labels, unit) == expected


def test_path_and_cycle_articulation_sets_are_independent_of_dfs_root():
    path = graph(5, [(i, i + 1) for i in range(4)])
    cycle = graph(5, [(i, (i + 1) % 5) for i in range(5)])
    for start in range(5):
        assert c._district_articulation_points(path, [0] * 5, start) == {1, 2, 3}
        assert c._district_articulation_points(cycle, [0] * 5, start) == set()
    assert c._district_articulation_points(((),), [0], 0) == set()


def test_long_corridor_uses_no_python_recursion():
    n = 5000
    adjacency = graph(n, [(i, i + 1) for i in range(n - 1)])
    assert c._district_articulation_points(adjacency, [0] * n, n // 2) == set(range(1, n - 1))


def test_cache_is_lazy_and_invalidates_both_entire_affected_districts(monkeypatch):
    # Moving 0 opens the donor cycle and closes a recipient cycle: a donor
    # articulation appears while a recipient articulation disappears.
    adjacency = graph(8, [(0, 1), (1, 2), (2, 3), (3, 0),
                          (4, 5), (5, 6), (0, 4), (0, 6)])
    labels = [0, 0, 0, 0, 1, 1, 1, 2]
    calls = Counter()
    original = c._district_articulation_points

    def observed(graph_arg, labels_arg, start):
        calls[labels_arg[start]] += 1
        return original(graph_arg, labels_arg, start)

    monkeypatch.setattr(c, '_district_articulation_points', observed)
    cache = c._DistrictArticulationCache(adjacency, labels)
    assert not calls
    assert cache.preserves_removal(2)
    assert cache.preserves_removal(3)
    assert not cache.preserves_removal(5)
    assert cache.preserves_removal(7)
    assert calls == {0: 1, 1: 1, 2: 1}
    labels[0] = 1
    cache.invalidate(0, 1)
    assert not cache.preserves_removal(2)
    assert cache.preserves_removal(5)
    assert cache.preserves_removal(7)
    assert calls == {0: 2, 1: 2, 2: 1}
    for unit in range(8):
        assert cache.preserves_removal(unit) == removal_oracle(adjacency, labels, unit)


@pytest.mark.parametrize('seed', range(12))
@pytest.mark.parametrize('budget', [0, 1, 7, 100])
def test_full_repair_move_trace_and_stop_reason_match_traversal(seed, budget):
    rng = random.Random(seed)
    adjacency = grid(6, 6)
    labels = [0, 1, 2] + [rng.randrange(3) for _ in range(33)]
    populations = [rng.randrange(30) for _ in labels]
    saved = labels.copy()
    reference = c.repair_and_rebalance(
        adjacency, labels, populations, n_districts=3, max_moves=budget, cache_connectivity=False,
    )
    cached = c.repair_and_rebalance(
        adjacency, labels, populations, n_districts=3, max_moves=budget,
    )
    assert cached == reference  # Includes repair stages, every move and termination.
    assert labels == saved


def test_zero_population_articulation_vertices_and_final_unit_remain_protected():
    adjacency = graph(4, [(0, 1), (1, 2), (1, 3)])
    labels = [0, 0, 0, 1]
    pops = [30, 0, 30, 40]
    assert not c._DistrictArticulationCache(adjacency, labels).preserves_removal(1)
    for cached in (False, True):
        result = c.repair_and_rebalance(adjacency, labels, pops, n_districts=2, cache_connectivity=cached)
        assert result.assignments == tuple(labels)
        assert not result.rebalance_moves
        singleton = c.repair_and_rebalance(((1,), (0,)), [0, 1], [100, 0],
                                           n_districts=2, cache_connectivity=cached)
        assert singleton.assignments == (0, 1)


def test_hundred_move_split_continuation_matches_reference_uninterrupted_run():
    n = 240
    adjacency = graph(n, [(i, i + 1) for i in range(n - 1)])
    labels = [0] * 220 + [1] * 20
    populations = [1] * n
    reference = c.repair_and_rebalance(adjacency, labels, populations, n_districts=2,
                                       max_moves=100, cache_connectivity=False)
    first = c.repair_and_rebalance(adjacency, labels, populations, n_districts=2, max_moves=37)
    continuation = c.repair_and_rebalance(adjacency, first.assignments, populations,
                                          n_districts=2, max_moves=63)
    assert first.stop_reason == 'max_moves'
    assert continuation.stop_reason == reference.stop_reason == 'local_optimum'
    assert continuation.repair_moves == ()
    assert continuation.assignments == reference.assignments
    assert first.rebalance_moves + continuation.rebalance_moves == reference.rebalance_moves


def parts_and_unit_graph(owners, edges):
    parts = PartGraph(graph(len(owners), edges), tuple(owners))
    adjacency = graph(len(parts.unit_to_parts), {
        (owners[left], owners[right]) for left, neighbors in enumerate(parts.adjacency)
        for right in neighbors if owners[left] != owners[right]
    })
    return parts, adjacency


@pytest.mark.parametrize('kind', ['repair', 'recipient', 'donor', 'safe'])
def test_multipart_repairs_and_exact_donor_recipient_guards_match_reference(kind):
    if kind == 'repair':
        parts, adjacency = parts_and_unit_graph([0, 0, 0, 1, 2], [(0, 3), (0, 4), (1, 4), (2, 4)])
        labels, pops = [0, 0, 1], [0, 100, 100]
    elif kind == 'recipient':
        parts, adjacency = parts_and_unit_graph([0, 0, 1, 2], [(0, 2), (1, 2), (0, 3)])
        labels, pops = [0, 0, 1], [10, 50, 40]
    elif kind == 'donor':
        parts, adjacency = parts_and_unit_graph([0, 1, 1, 2, 3, 4],
                                               [(0, 1), (0, 2), (1, 3), (2, 4), (0, 5)])
        labels, pops = [0, 0, 0, 0, 1], [10, 25, 12, 13, 40]
    else:
        parts, adjacency = parts_and_unit_graph([0, 0, 1, 2], [(0, 2), (1, 2), (0, 3), (1, 3)])
        labels, pops = [0, 0, 1], [10, 50, 40]
    reference = c.repair_and_rebalance(adjacency, labels, pops, n_districts=2,
                                       part_graph=parts, cache_connectivity=False)
    cached = c.repair_and_rebalance(adjacency, labels, pops, n_districts=2, part_graph=parts)
    assert cached == reference
    assert part_component_counts(parts, cached.assignments, n_districts=2) == (1, 1)
    if kind in ('donor', 'recipient'):
        assert not cached.rebalance_moves


def test_incompatible_part_repair_falls_back_to_reference_traversal(monkeypatch):
    # An arbitrary caller's part graph can disagree with unit edges. Simulate
    # the post-part-repair condition directly; the legacy final audit must
    # still fail, rather than applying a connected-donor-only cache.
    from districting import part_connectivity

    adjacency = graph(4, [(0, 1), (1, 2), (2, 3)])
    parts = PartGraph(adjacency, (0, 1, 2, 3))
    monkeypatch.setattr(part_connectivity, 'repair_part_connectivity',
                        lambda *args, **kwargs: PartConnectivityResult((0, 1, 0, 1), ()))
    monkeypatch.setattr(c, '_DistrictArticulationCache',
                        lambda *args: pytest.fail('Disconnected districts must use traversal.'))
    calls = []
    original = c._removal_preserves_connectivity

    def observed(*args):
        calls.append(args[2])
        return original(*args)

    monkeypatch.setattr(c, '_removal_preserves_connectivity', observed)
    for cached in (False, True):
        with pytest.raises(RuntimeError, match='produced a disconnected district'):
            c.repair_and_rebalance(adjacency, [0, 0, 1, 1], [30, 10, 30, 10],
                                   n_districts=2, max_moves=0, part_graph=parts,
                                   cache_connectivity=cached)
    assert calls


@pytest.mark.parametrize('value', [0, 1, None, 'false', [], object()])
def test_cache_option_requires_an_actual_bool(value):
    with pytest.raises(ValueError, match='cache_connectivity must be a bool'):
        c.repair_and_rebalance([[]], [0], [1], n_districts=1, cache_connectivity=value)

