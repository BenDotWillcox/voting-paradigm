"""Regression topologies for multipart blocks hidden by a whole-block graph.

The Maryland and Virginia fixtures preserve the diagnosed source/receiver
relationships without shipping their large census geometry archives in tests.
"""

from collections.abc import Sequence
from dataclasses import FrozenInstanceError

import pytest

from districting.connectivity import repair_and_rebalance
from districting.part_connectivity import (
    PartConnectivityRepairError,
    PartGraph,
    part_component_counts,
    repair_part_connectivity,
)


def part_graph(owners: Sequence[int], edges: Sequence[tuple[int, int]]) -> PartGraph:
    adjacency: list[list[int]] = [[] for _ in owners]
    for left, right in edges:
        adjacency[left].append(right)
        adjacency[right].append(left)
    return PartGraph(tuple(tuple(neighbors) for neighbors in adjacency), tuple(owners))


def unit_graph(parts: PartGraph) -> tuple[tuple[int, ...], ...]:
    adjacency: list[set[int]] = [set() for _ in parts.unit_to_parts]
    for part, neighbors in enumerate(parts.adjacency):
        unit = parts.part_to_unit[part]
        for neighbor in neighbors:
            other = parts.part_to_unit[neighbor]
            if unit != other:
                adjacency[unit].add(other)
    return tuple(tuple(sorted(neighbors)) for neighbors in adjacency)


def district_populations(labels: Sequence[int], populations: Sequence[int]) -> tuple[int, ...]:
    return tuple(
        sum(population for label, population in zip(labels, populations) if label == district)
        for district in range(max(labels) + 1)
    )


@pytest.mark.parametrize("parts_count", [3, 2], ids=["maryland-three-parts", "virginia-two-parts"])
def test_whole_zero_population_block_repairs_the_confirmed_failure(parts_count: int) -> None:
    # Maryland block 240419608001043: D17 -> D16, three parts.
    # Virginia block 510010906001010: D19 -> D15, two parts.
    # Part 0 meets the donor mainland. Every part meets the receiver mainland;
    # the remaining parts have no same-district path to the donor mainland.
    parts = part_graph(
        [0] * parts_count + [1, 2],
        [(0, parts_count)] + [(part, parts_count + 1) for part in range(parts_count)],
    )
    original = [0, 0, 1]
    populations = [0, 100, 100]
    assert part_component_counts(parts, original, n_districts=2) == (parts_count, 1)
    legacy = repair_and_rebalance(unit_graph(parts), original, populations, n_districts=2)
    assert legacy.assignments == tuple(original)  # The old graph misses the failure.

    result = repair_and_rebalance(
        unit_graph(parts), original, populations, n_districts=2, part_graph=parts
    )
    assert result.assignments == (1, 0, 1)
    assert part_component_counts(parts, result.assignments, n_districts=2) == (1, 1)
    assert result.repaired_assignments == result.assignments
    assert len(result.part_repair_moves) == 1
    assert result.repair_moves == result.part_repair_moves
    move = result.part_repair_moves[0]
    assert (move.units, move.source_district, move.target_district, move.population) == ((0,), 0, 1, 0)
    assert district_populations(result.assignments, populations) == (100, 100)
    assert not result.rebalance_moves
    assert original == [0, 0, 1]


def test_part_ownership_does_not_create_synthetic_connectivity() -> None:
    parts = part_graph([0, 0], [])
    assert part_component_counts(parts, [0], n_districts=1) == (2,)
    with pytest.raises(PartConnectivityRepairError, match="does not establish infeasibility"):
        repair_part_connectivity(parts, [0], [0], n_districts=1)


def test_repair_rejects_receiver_that_touches_only_one_of_two_parts() -> None:
    parts = part_graph([0, 0, 1, 2], [(0, 2), (1, 3)])
    with pytest.raises(PartConnectivityRepairError, match="local-search limitation") as error:
        repair_part_connectivity(parts, [0, 0, 1], [0, 100, 100], n_districts=2)
    assert error.value.assignments == (0, 0, 1)
    assert error.value.moves == ()
    assert error.value.component_counts == (2, 1)


def test_repair_cannot_disconnect_donor_to_fix_detached_parts() -> None:
    # Part 0 is also the donor mainland's articulation point. Removing its
    # whole unit would replace two donor components with three.
    parts = part_graph([0, 0, 1, 2, 3, 4], [(0, 2), (0, 3), (0, 4), (0, 5), (1, 5)])
    labels = [0, 0, 0, 0, 1]
    with pytest.raises(PartConnectivityRepairError):
        repair_part_connectivity(parts, labels, [0, 30, 30, 40, 100], n_districts=2)
    assert part_component_counts(parts, labels, n_districts=2) == (2, 1)


def test_balancing_rejects_move_with_a_detached_part_in_recipient() -> None:
    parts = part_graph([0, 0, 1, 2], [(0, 2), (1, 2), (0, 3)])
    labels = [0, 0, 1]
    populations = [10, 50, 40]
    legacy = repair_and_rebalance(unit_graph(parts), labels, populations, n_districts=2)
    assert legacy.assignments == (1, 0, 1)
    assert part_component_counts(parts, legacy.assignments, n_districts=2) == (1, 2)
    guarded = repair_and_rebalance(
        unit_graph(parts), labels, populations, n_districts=2, part_graph=parts
    )
    assert guarded.assignments == tuple(labels)
    assert not guarded.rebalance_moves
    assert part_component_counts(parts, guarded.assignments, n_districts=2) == (1, 1)


def test_balancing_rejects_donor_split_hidden_by_another_multipart_unit() -> None:
    # Unit 1 has parts on opposite sides of the bridge unit 0. On a whole-unit
    # graph it looks as if unit 1 still joins both sides after the bridge moves.
    parts = part_graph([0, 1, 1, 2, 3, 4], [(0, 1), (0, 2), (1, 3), (2, 4), (0, 5)])
    labels = [0, 0, 0, 0, 1]
    populations = [10, 25, 12, 13, 40]
    legacy = repair_and_rebalance(unit_graph(parts), labels, populations, n_districts=2)
    assert legacy.assignments == (1, 0, 0, 0, 1)
    assert part_component_counts(parts, legacy.assignments, n_districts=2) == (2, 1)
    guarded = repair_and_rebalance(
        unit_graph(parts), labels, populations, n_districts=2, part_graph=parts
    )
    assert guarded.assignments == tuple(labels)
    assert not guarded.rebalance_moves


def test_balancing_accepts_safe_multipart_move_and_counts_population_once() -> None:
    parts = part_graph([0, 0, 1, 2], [(0, 2), (1, 2), (0, 3), (1, 3)])
    populations = [10, 50, 40]
    result = repair_and_rebalance(
        unit_graph(parts), [0, 0, 1], populations, n_districts=2, part_graph=parts
    )
    assert result.assignments == (1, 0, 1)
    assert district_populations(result.assignments, populations) == (50, 50)
    assert len(result.rebalance_moves) == 1
    assert result.rebalance_moves[0].population == 10
    assert part_component_counts(parts, result.assignments, n_districts=2) == (1, 1)


def test_repair_is_deterministic_and_every_move_monotonically_reduces_components() -> None:
    # Two independent zero-population multipart units can be repaired in either
    # order; stable unit ordering makes the audit reproducible.
    parts = part_graph([0, 0, 1, 1, 2, 3], [(0, 4), (2, 4), (0, 5), (1, 5), (2, 5), (3, 5)])
    labels = [0, 0, 0, 1]
    populations = [0, 0, 100, 100]
    result = repair_part_connectivity(parts, labels, populations, n_districts=2)
    reverse_neighbors = PartGraph(tuple(tuple(reversed(row)) for row in parts.adjacency), parts.part_to_unit)
    assert repair_part_connectivity(reverse_neighbors, labels, populations, n_districts=2) == result
    assert [move.units for move in result.moves] == [(0,), (1,)]
    replay = list(labels)
    before = part_component_counts(parts, replay, n_districts=2)
    for move in result.moves:
        replay[move.units[0]] = move.target_district
        after = part_component_counts(parts, replay, n_districts=2)
        assert all(0 < new <= old for old, new in zip(before, after))
        assert sum(after) < sum(before)
        before = after
    assert tuple(replay) == result.assignments
    assert before == (1, 1)


def test_part_graph_is_immutable() -> None:
    parts = part_graph([0, 1], [(0, 1)])
    with pytest.raises(FrozenInstanceError):
        parts.part_to_unit = (0, 0)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("adjacency", "owners", "message"),
    [
        ((), (), "nonzero"),
        (((),), (0, 1), "equal"),
        (((),), (-1,), "contiguous"),
        (((), ()), (0, 2), "contiguous"),
        (((1,), ()), (0, 1), "undirected"),
        (((0,),), (0,), "self edges"),
        (((2,), ()), (0, 1), "existing parts"),
        (((),), (True,), "integer"),
        (((False,),), (0,), "integer"),
    ],
)
def test_invalid_part_graph(
    adjacency: tuple[tuple[int, ...], ...], owners: tuple[int, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PartGraph(adjacency, owners)


@pytest.mark.parametrize(
    ("labels", "populations", "n_districts", "message"),
    [
        ([0, 1, 0], [1, 1, 1], 2, "one label per unit"),
        ([0, 0], [1, 1], 2, "Every district"),
        ([0, 2], [1, 1], 2, "District labels"),
        ([0, 1], [1, 1], 0, "n_districts"),
        ([0, 1], [1, 1], True, "integer"),
        ([False, 1], [1, 1], 2, "integer"),
        ([0, 1], [-1, 1], 2, "nonnegative"),
        ([0, 1], [1], 2, "one value per unit"),
        ([0, 1], [0.5, 1], 2, "integer"),
    ],
)
def test_invalid_repair_inputs(
    labels: list[int], populations: list[int], n_districts: int, message: str
) -> None:
    parts = part_graph([0, 1], [(0, 1)])
    with pytest.raises(ValueError, match=message):
        repair_part_connectivity(parts, labels, populations, n_districts=n_districts)


def test_integrated_repair_rejects_mismatched_unit_ownership() -> None:
    with pytest.raises(ValueError, match="one label per unit"):
        repair_and_rebalance(
            [[1], [0]], [0, 0], [1, 1], n_districts=1,
            part_graph=part_graph([0], []),
        )
