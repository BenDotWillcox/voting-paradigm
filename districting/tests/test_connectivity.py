"""Graph-only tests of repair and population balancing; no geometry fixtures."""

from collections.abc import Sequence
import random

import pytest

from districting.connectivity import ConnectivityResult, repair_and_rebalance


def graph(n_units: int, edges: Sequence[tuple[int, int]]) -> list[list[int]]:
    result: list[list[int]] = [[] for _ in range(n_units)]
    for left, right in edges:
        result[left].append(right)
        result[right].append(left)
    return result


def district_populations(labels: Sequence[int], populations: Sequence[int]) -> tuple[int, ...]:
    return tuple(
        sum(population for label, population in zip(labels, populations) if label == district)
        for district in range(max(labels) + 1)
    )


def assert_connected(adjacency: Sequence[Sequence[int]], labels: Sequence[int]) -> None:
    for district in set(labels):
        members = {unit for unit, label in enumerate(labels) if label == district}
        seen = {min(members)}
        stack = list(seen)
        while stack:
            for neighbor in adjacency[stack.pop()]:
                if neighbor in members and neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        assert seen == members


def test_repair_includes_positive_and_zero_population_pieces() -> None:
    adjacency = graph(6, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)])
    labels = [0, 0, 1, 1, 0, 0]
    populations = [60, 40, 60, 40, 0, 1]
    result = repair_and_rebalance(adjacency, labels, populations, n_districts=2, max_moves=0)
    assert result.repaired_assignments == (0, 0, 1, 1, 1, 1)
    assert len(result.repair_moves) == 1
    assert result.repair_moves[0].units == (4, 5)
    assert result.repair_moves[0].population == 1
    assert sum(district_populations(result.assignments, populations)) == sum(populations)
    assert_connected(adjacency, result.assignments)
    assert labels == [0, 0, 1, 1, 0, 0]


def test_repair_reaches_pieces_through_other_detached_components() -> None:
    adjacency = graph(7, [(index, index + 1) for index in range(6)])
    # The last three components can only reach an anchor after prior repairs.
    labels = [0, 0, 1, 1, 0, 1, 0]
    result = repair_and_rebalance(
        adjacency, labels, [50, 50, 50, 50, 1, 1, 1], n_districts=2, max_moves=0
    )
    assert result.repaired_assignments == (0, 0, 1, 1, 1, 1, 1)
    assert_connected(adjacency, result.assignments)


def test_rebalance_improves_balance_with_shared_edge_and_keeps_donor_connected() -> None:
    adjacency = graph(5, [(0, 1), (1, 2), (2, 3), (3, 4)])
    populations = [30, 20, 10, 20, 20]
    result = repair_and_rebalance(adjacency, [0, 0, 0, 1, 1], populations, n_districts=2)
    assert district_populations(result.repaired_assignments, populations) == (60, 40)
    assert district_populations(result.assignments, populations) == (50, 50)
    assert result.assignments == (0, 0, 1, 1, 1)
    assert len(result.rebalance_moves) == 1
    assert result.rebalance_moves[0].units == (2,)
    assert result.stop_reason == "local_optimum"
    assert_connected(adjacency, result.assignments)


def test_rebalance_rejects_donor_articulation_even_when_balance_would_improve() -> None:
    adjacency = graph(4, [(0, 1), (1, 2), (1, 3)])
    result = repair_and_rebalance(adjacency, [0, 0, 0, 1], [30, 20, 30, 20], n_districts=2)
    assert result.assignments == (0, 0, 0, 1)
    assert not result.rebalance_moves
    assert result.stop_reason == "local_optimum"


def test_rebalance_cannot_transfer_to_nonadjacent_district() -> None:
    adjacency = graph(3, [(0, 1), (1, 2)])
    result = repair_and_rebalance(adjacency, [0, 0, 1], [20, 80, 0], n_districts=2)
    # Moving unit 0 would help the objective but it has no receiver edge.
    assert result.assignments == (0, 1, 1)
    assert [move.units for move in result.rebalance_moves] == [(1,)]
    assert_connected(adjacency, result.assignments)


def test_move_limit_is_explicit() -> None:
    adjacency = graph(5, [(0, 1), (1, 2), (2, 3), (3, 4)])
    result = repair_and_rebalance(
        adjacency, [0, 0, 0, 1, 1], [30, 20, 10, 20, 20], n_districts=2, max_moves=0
    )
    assert result.assignments == result.repaired_assignments
    assert result.stop_reason == "max_moves"


def test_squared_error_improves_when_worst_district_cannot_yet_improve() -> None:
    adjacency = graph(6, [(2, 3), (3, 4), (4, 5)])
    populations = [120, 80, 105, 5, 45, 45]
    result = repair_and_rebalance(adjacency, [0, 1, 2, 2, 3, 3], populations, n_districts=4)
    assert district_populations(result.assignments, populations) == (120, 80, 105, 95)
    assert result.rebalance_moves[0].units == (3,)


def test_anchor_ties_use_component_size_then_smallest_unit() -> None:
    adjacency = graph(5, [(0, 1), (1, 2), (2, 3), (3, 4)])
    result = repair_and_rebalance(
        adjacency, [0, 1, 1, 0, 0], [5, 5, 5, 5, 0], n_districts=2, max_moves=0
    )
    assert result.repaired_assignments == (1, 1, 1, 0, 0)


def test_deterministic_even_when_neighbors_are_reordered() -> None:
    adjacency = graph(6, [(0, 1), (0, 2), (1, 3), (2, 3), (3, 4), (4, 5)])
    labels = [0, 0, 1, 1, 1, 0]
    populations = [20, 20, 15, 15, 10, 2]
    first = repair_and_rebalance(adjacency, labels, populations, n_districts=2)
    second = repair_and_rebalance(
        [list(reversed(neighbors)) for neighbors in adjacency], labels, populations, n_districts=2
    )
    assert first == second
    assert_connected(adjacency, first.assignments)


def test_unreachable_detached_piece_raises_clearly() -> None:
    adjacency = graph(5, [(0, 1), (2, 3)])
    with pytest.raises(ValueError, match="unanchored disconnected component"):
        repair_and_rebalance(adjacency, [0, 0, 1, 1, 0], [20, 20, 20, 20, 0], n_districts=2)


def test_disconnected_graph_can_have_contiguous_districts() -> None:
    adjacency = graph(4, [(0, 1), (2, 3)])
    result = repair_and_rebalance(adjacency, [0, 0, 1, 1], [20, 20, 20, 20], n_districts=2)
    assert result.assignments == (0, 0, 1, 1)
    assert result.stop_reason == "local_optimum"


def test_single_district_zero_population_and_singleton_are_valid() -> None:
    result = repair_and_rebalance([[]], [0], [0], n_districts=1)
    assert result == ConnectivityResult((0,), (0,), (), (), "local_optimum")


@pytest.mark.parametrize("seed", range(12))
def test_repair_and_every_balance_move_preserve_invariants_on_fragmented_grids(seed: int) -> None:
    rng = random.Random(seed)
    width = 6
    edges = [
        (unit, neighbor)
        for unit in range(width * width)
        for neighbor in (unit + 1, unit + width)
        if neighbor < width * width
        and (neighbor == unit + width or unit // width == neighbor // width)
    ]
    adjacency = graph(width * width, edges)
    labels = [0, 1, 2] + [rng.randrange(3) for _ in range(width * width - 3)]
    populations = [rng.randrange(30) for _ in labels]
    result = repair_and_rebalance(adjacency, labels, populations, n_districts=3)
    replay = list(labels)
    for move in result.repair_moves:
        assert all(replay[unit] == move.source_district for unit in move.units)
        assert sum(populations[unit] for unit in move.units) == move.population
        for unit in move.units:
            replay[unit] = move.target_district
    assert tuple(replay) == result.repaired_assignments
    assert_connected(adjacency, replay)

    def objective(assignments: Sequence[int]) -> tuple[int, int]:
        totals = district_populations(assignments, populations)
        deviations = [3 * population - sum(populations) for population in totals]
        return max(abs(value) for value in deviations), sum(value * value for value in deviations)

    for move in result.rebalance_moves:
        previous = objective(replay)
        assert len(move.units) == 1
        unit = move.units[0]
        assert replay[unit] == move.source_district
        assert any(replay[neighbor] == move.target_district for neighbor in adjacency[unit])
        replay[unit] = move.target_district
        assert_connected(adjacency, replay)
        assert objective(replay) < previous
    assert tuple(replay) == result.assignments
    assert sum(district_populations(replay, populations)) == sum(populations)


@pytest.mark.parametrize(
    ("adjacency", "labels", "populations", "n_districts", "max_moves", "message"),
    [
        ([[1], []], [0, 1], [1, 1], 2, 10, "undirected"),
        ([[0]], [0], [1], 1, 10, "self edges"),
        ([[1]], [0], [1], 1, 10, "existing units"),
        ([[]], [], [1], 1, 10, "equal lengths"),
        ([[], []], [0, 2], [1, 1], 2, 10, "District labels"),
        ([[], []], [0, 0], [1, 1], 2, 10, "initially contain"),
        ([[]], [0], [-1], 1, 10, "nonnegative"),
        ([[]], [0], [1], 0, 10, "n_districts"),
        ([[]], [0], [1], 1, -1, "nonnegative"),
        ([[]], [0], [1.5], 1, 10, "integer"),
        ([[]], [False], [1], 1, 10, "integer"),
    ],
)
def test_invalid_input(
    adjacency: list[list[int]],
    labels: list[int],
    populations: list[int],
    n_districts: int,
    max_moves: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        repair_and_rebalance(
            adjacency, labels, populations, n_districts=n_districts, max_moves=max_moves
        )
