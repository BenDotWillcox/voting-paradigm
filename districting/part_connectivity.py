"""Connectivity of polygon parts with indivisible census-unit assignments.

Each graph vertex is one polygon part. Multiple parts can belong to the same
unit, but ownership never creates an edge between them. Moving a unit moves all
its parts together and counts its population exactly once. Geometry and true
shared-edge construction belong to the caller.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from numbers import Integral


def _integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer.")
    return int(value)


@dataclass(frozen=True)
class PartGraph:
    """Immutable shared-edge graph; ``part_to_unit`` couples assignments only."""

    adjacency: tuple[tuple[int, ...], ...]
    part_to_unit: tuple[int, ...]
    unit_to_parts: tuple[tuple[int, ...], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        owners = tuple(_integer(unit, "unit index") for unit in self.part_to_unit)
        if not owners or len(self.adjacency) != len(owners):
            raise ValueError("Part adjacency and ownership must have equal, nonzero lengths.")
        if any(unit < 0 for unit in owners) or set(owners) != set(range(max(owners) + 1)):
            raise ValueError("Unit indices must be contiguous from zero; every unit needs a part.")
        graph = tuple(
            tuple(sorted({_integer(neighbor, "part neighbor index") for neighbor in neighbors}))
            for neighbors in self.adjacency
        )
        for part, neighbors in enumerate(graph):
            for neighbor in neighbors:
                if neighbor < 0 or neighbor >= len(graph):
                    raise ValueError("Part neighbors must refer to existing parts.")
                if neighbor == part:
                    raise ValueError("Part adjacency must not contain self edges.")
                if part not in graph[neighbor]:
                    raise ValueError("Part adjacency must be undirected (symmetric).")
        by_unit: list[list[int]] = [[] for _ in range(max(owners) + 1)]
        for part, unit in enumerate(owners):
            by_unit[unit].append(part)
        object.__setattr__(self, "adjacency", graph)
        object.__setattr__(self, "part_to_unit", owners)
        object.__setattr__(self, "unit_to_parts", tuple(tuple(parts) for parts in by_unit))


@dataclass(frozen=True)
class PartMoveAudit:
    """A whole-unit transfer; fields match connectivity.MoveAudit."""

    units: tuple[int, ...]
    source_district: int
    target_district: int
    population: int


@dataclass(frozen=True)
class PartConnectivityResult:
    assignments: tuple[int, ...]
    moves: tuple[PartMoveAudit, ...]


class PartConnectivityRepairError(ValueError):
    """Local single-unit repair stalled; this is not a proof of infeasibility."""

    def __init__(
        self,
        assignments: Sequence[int],
        moves: Sequence[PartMoveAudit],
        component_counts: Sequence[int],
    ) -> None:
        self.assignments = tuple(assignments)
        self.moves = tuple(moves)
        self.component_counts = tuple(component_counts)
        super().__init__(
            "Polygon-part repair stalled: no whole-unit move reduces disconnected "
            "components without worsening or emptying an affected district. "
            "This local-search limitation does not establish infeasibility. "
            f"Component counts: {self.component_counts}."
        )


def _validate_labels(
    graph: PartGraph, assignments: Sequence[int], n_districts: int
) -> list[int]:
    n_districts = _integer(n_districts, "n_districts")
    if n_districts < 1 or n_districts > len(graph.unit_to_parts):
        raise ValueError("n_districts must be between one and the number of units.")
    if len(assignments) != len(graph.unit_to_parts):
        raise ValueError("Assignments must contain one label per unit, not per part.")
    labels = [_integer(label, "district label") for label in assignments]
    if any(label < 0 or label >= n_districts for label in labels):
        raise ValueError("District labels must be in [0, n_districts).")
    if set(labels) != set(range(n_districts)):
        raise ValueError("Every district must contain at least one unit.")
    return labels


def _components(
    graph: PartGraph, labels: Sequence[int], n_districts: int
) -> tuple[list[list[tuple[int, ...]]], list[int]]:
    components: list[list[tuple[int, ...]]] = [[] for _ in range(n_districts)]
    memberships = [-1] * len(graph.adjacency)
    for start, owner in enumerate(graph.part_to_unit):
        if memberships[start] >= 0:
            continue
        district = labels[owner]
        component_id = len(components[district])
        memberships[start] = component_id
        stack = [start]
        members = []
        while stack:
            part = stack.pop()
            members.append(part)
            for neighbor in graph.adjacency[part]:
                if memberships[neighbor] < 0 and labels[graph.part_to_unit[neighbor]] == district:
                    memberships[neighbor] = component_id
                    stack.append(neighbor)
        components[district].append(tuple(members))
    return components, memberships


def part_component_counts(
    graph: PartGraph, assignments: Sequence[int], *, n_districts: int
) -> tuple[int, ...]:
    """Count physical components without connecting parts by common ownership."""
    labels = _validate_labels(graph, assignments, n_districts)
    components, _ = _components(graph, labels, n_districts)
    return tuple(len(parts) for parts in components)


def _affected_component_counts(
    graph: PartGraph, labels: Sequence[int], source: int, target: int
) -> tuple[int, int]:
    counts = {source: 0, target: 0}
    seen: set[int] = set()
    for start, unit in enumerate(graph.part_to_unit):
        district = labels[unit]
        if district not in counts or start in seen:
            continue
        counts[district] += 1
        seen.add(start)
        stack = [start]
        while stack:
            part = stack.pop()
            for neighbor in graph.adjacency[part]:
                if neighbor not in seen and labels[graph.part_to_unit[neighbor]] == district:
                    seen.add(neighbor)
                    stack.append(neighbor)
    return counts[source], counts[target]


def repair_part_connectivity(
    graph: PartGraph,
    assignments: Sequence[int],
    populations: Sequence[int],
    *,
    n_districts: int,
) -> PartConnectivityResult:
    """Deterministically repair geometry by monotone single-whole-unit moves.

    Zero-population units are eligible. Every accepted move reduces the total
    number of district components and cannot increase either affected district's
    count or empty one. This finite local search can stall even when a repair
    involving several units or temporary worsening exists; it then raises
    ``PartConnectivityRepairError`` with the partial audit. Inputs are unchanged.
    """
    labels = _validate_labels(graph, assignments, n_districts)
    pops = tuple(_integer(population, "population") for population in populations)
    if len(pops) != len(labels) or any(population < 0 for population in pops):
        raise ValueError("Populations must be nonnegative, with one value per unit.")
    district_pops = [0] * n_districts
    for district, population in zip(labels, pops):
        district_pops[district] += population
    total = sum(pops)
    moves: list[PartMoveAudit] = []
    while True:
        components, memberships = _components(graph, labels, n_districts)
        counts = [len(parts) for parts in components]
        if all(count == 1 for count in counts):
            return PartConnectivityResult(tuple(labels), tuple(moves))
        best: tuple[int, int, int, int, int, int] | None = None
        for unit, parts in enumerate(graph.unit_to_parts):
            source = labels[unit]
            removed = Counter(memberships[part] for part in parts)
            removes_component = any(
                amount == len(components[source][component])
                for component, amount in removed.items()
            )
            targets = {
                labels[graph.part_to_unit[neighbor]]
                for part in parts
                for neighbor in graph.adjacency[part]
            } - {source}
            for target in sorted(targets):
                # A necessary condition avoids expensive trials for ordinary
                # boundary blocks: remove a donor component or join recipient
                # components. The exact test below still decides acceptance.
                target_components = {
                    memberships[neighbor]
                    for part in parts
                    for neighbor in graph.adjacency[part]
                    if labels[graph.part_to_unit[neighbor]] == target
                }
                if not removes_component and len(target_components) < 2:
                    continue
                labels[unit] = target
                after_source, after_target = _affected_component_counts(graph, labels, source, target)
                labels[unit] = source
                if (
                    after_source < 1 or after_target < 1
                    or after_source > counts[source] or after_target > counts[target]
                    or after_source + after_target >= counts[source] + counts[target]
                ):
                    continue
                proposed_pops = list(district_pops)
                proposed_pops[source] -= pops[unit]
                proposed_pops[target] += pops[unit]
                deviations = [n_districts * population - total for population in proposed_pops]
                score = (
                    after_source + after_target - counts[source] - counts[target],
                    max(abs(deviation) for deviation in deviations),
                    sum(deviation * deviation for deviation in deviations),
                    pops[unit], unit, target,
                )
                if best is None or score < best:
                    best = score
        if best is None:
            raise PartConnectivityRepairError(labels, moves, counts)
        _, _, _, _, unit, target = best
        source = labels[unit]
        labels[unit] = target
        district_pops[source] -= pops[unit]
        district_pops[target] += pops[unit]
        moves.append(PartMoveAudit((unit,), source, target, pops[unit]))


def _move_preserves_connected_districts(
    graph: PartGraph, labels: Sequence[int], unit: int, target: int
) -> bool:
    """Fast donor/recipient check; inputs and initial connectivity are validated.

    The balancing caller separately prevents emptying the donor district. Each
    connected component of the transferred parts must touch the recipient; the
    donor's neighboring parts must remain mutually reachable after removal.
    """
    source = labels[unit]
    moving = set(graph.unit_to_parts[unit])
    unseen = set(moving)
    while unseen:
        stack = [unseen.pop()]
        touches_target = False
        while stack:
            part = stack.pop()
            for neighbor in graph.adjacency[part]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
                elif neighbor not in moving and labels[graph.part_to_unit[neighbor]] == target:
                    touches_target = True
        if not touches_target:
            return False
    neighbors = {
        neighbor
        for part in moving
        for neighbor in graph.adjacency[part]
        if neighbor not in moving and labels[graph.part_to_unit[neighbor]] == source
    }
    if len(neighbors) < 2:
        return True
    start = min(neighbors)
    remaining = neighbors - {start}
    seen = moving | {start}
    stack = [start]
    while stack:
        part = stack.pop()
        for neighbor in graph.adjacency[part]:
            if neighbor not in seen and labels[graph.part_to_unit[neighbor]] == source:
                remaining.discard(neighbor)
                if not remaining:
                    return True
                seen.add(neighbor)
                stack.append(neighbor)
    return False
