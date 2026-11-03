"""Deterministic contiguity repair and population balancing on a unit graph.

An edge must mean that two units share a boundary of positive length. Geometry
construction is deliberately outside this module. Every unit, including units
with zero residents, participates in connectivity.

Repair keeps each district's largest-population component as its anchor and
absorbs detached components into touching anchored territories. Balancing then
moves individual populated boundary units, minimizing maximum population
deviation and then squared deviations without disconnecting either district.
This is a local search, not a guarantee of globally optimal balance. In
particular, it does not explore swaps or moves of zero-population units.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from districting.part_connectivity import PartGraph


@dataclass(frozen=True)
class MoveAudit:
    """One connected component transfer or one subsequent boundary-unit move."""

    units: tuple[int, ...]
    source_district: int
    target_district: int
    population: int


@dataclass(frozen=True)
class ConnectivityResult:
    """Assignments and a reproducible audit of connectivity repair and balancing.

    ``repair_moves`` contains all repair moves in order. ``part_repair_moves``
    identifies the optional polygon-part repair suffix separately.
    """

    assignments: tuple[int, ...]
    repaired_assignments: tuple[int, ...]
    repair_moves: tuple[MoveAudit, ...]
    rebalance_moves: tuple[MoveAudit, ...]
    stop_reason: Literal["local_optimum", "max_moves"]
    part_repair_moves: tuple[MoveAudit, ...] = ()


def _integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer.")
    return int(value)


def _validate(
    adjacency: Sequence[Sequence[int]],
    assignments: Sequence[int],
    populations: Sequence[int],
    n_districts: int,
    max_moves: int,
) -> tuple[tuple[tuple[int, ...], ...], list[int], tuple[int, ...]]:
    n_districts = _integer(n_districts, "n_districts")
    max_moves = _integer(max_moves, "max_moves")
    n_units = len(adjacency)
    if n_districts < 1 or n_districts > n_units:
        raise ValueError("n_districts must be between one and the number of units.")
    if max_moves < 0:
        raise ValueError("max_moves must be nonnegative.")
    if len(assignments) != n_units or len(populations) != n_units:
        raise ValueError("adjacency, assignments, and populations must have equal lengths.")
    labels = [_integer(label, "district label") for label in assignments]
    if any(label < 0 or label >= n_districts for label in labels):
        raise ValueError("District labels must be in [0, n_districts).")
    if set(labels) != set(range(n_districts)):
        raise ValueError("Every district must initially contain at least one unit.")
    pops = tuple(_integer(population, "population") for population in populations)
    if any(population < 0 for population in pops):
        raise ValueError("Populations must be nonnegative.")
    graph = tuple(
        tuple(sorted({_integer(neighbor, "neighbor index") for neighbor in neighbors}))
        for neighbors in adjacency
    )
    for unit, neighbors in enumerate(graph):
        for neighbor in neighbors:
            if neighbor < 0 or neighbor >= n_units:
                raise ValueError("Neighbor indices must refer to existing units.")
            if neighbor == unit:
                raise ValueError("Adjacency must not contain self edges.")
            if unit not in graph[neighbor]:
                raise ValueError("Adjacency must be undirected (symmetric).")
    return graph, labels, pops


def _components(
    graph: tuple[tuple[int, ...], ...], labels: Sequence[int], n_districts: int
) -> list[list[tuple[int, ...]]]:
    components: list[list[tuple[int, ...]]] = [[] for _ in range(n_districts)]
    visited = bytearray(len(graph))
    for start, label in enumerate(labels):
        if visited[start]:
            continue
        visited[start] = 1
        stack = [start]
        members = []
        while stack:
            unit = stack.pop()
            members.append(unit)
            for neighbor in graph[unit]:
                if not visited[neighbor] and labels[neighbor] == label:
                    visited[neighbor] = 1
                    stack.append(neighbor)
        components[label].append(tuple(sorted(members)))
    return components


def _objective(populations: Sequence[int], total: int) -> tuple[int, int]:
    """Exact integer version of max deviation, then sum of squared deviations."""
    n_districts = len(populations)
    deviations = [n_districts * population - total for population in populations]
    return max(abs(deviation) for deviation in deviations), sum(
        deviation * deviation for deviation in deviations
    )


def _transfer_objective(
    populations: Sequence[int], total: int, source: int, target: int, amount: int
) -> tuple[int, int]:
    updated = list(populations)
    updated[source] -= amount
    updated[target] += amount
    return _objective(updated, total)


def _repair(
    graph: tuple[tuple[int, ...], ...],
    labels: list[int],
    populations: tuple[int, ...],
    district_populations: list[int],
    total: int,
) -> tuple[MoveAudit, ...]:
    components = _components(graph, labels, len(district_populations))
    anchored = bytearray(len(graph))
    pending: list[tuple[int, ...]] = []
    for district_components in components:
        anchor = max(
            district_components,
            key=lambda members: (
                sum(populations[unit] for unit in members), len(members), -members[0]
            ),
        )
        for unit in anchor:
            anchored[unit] = 1
        pending.extend(members for members in district_components if members != anchor)
    moves = []
    while pending:
        # Components can become reachable after another detached component is
        # absorbed. Each choice minimizes current balance damage, with stable ties.
        options: list[tuple[int, int, int, int, int, int]] = []
        for pending_index, members in enumerate(pending):
            source = labels[members[0]]
            amount = sum(populations[unit] for unit in members)
            targets = {
                labels[neighbor]
                for unit in members
                for neighbor in graph[unit]
                if anchored[neighbor]
            }
            for target in targets:
                objective = _transfer_objective(
                    district_populations, total, source, target, amount
                )
                options.append(
                    (*objective, len(members), members[0], target, pending_index)
                )
        if not options:
            raise ValueError(
                "Shared-edge repair cannot reach all units from the chosen district "
                "anchors: the unit graph contains an unanchored disconnected component."
            )
        _, _, _, _, target, pending_index = min(options)
        members = pending.pop(pending_index)
        source = labels[members[0]]
        amount = sum(populations[unit] for unit in members)
        for unit in members:
            labels[unit] = target
            anchored[unit] = 1
        district_populations[source] -= amount
        district_populations[target] += amount
        if source != target:
            moves.append(MoveAudit(members, source, target, amount))
    return tuple(moves)


def _removal_preserves_connectivity(
    graph: tuple[tuple[int, ...], ...], labels: Sequence[int], unit: int
) -> bool:
    """All same-district neighbors must connect without passing through unit.

    Given a connected donor district, this is equivalent to checking that its
    remaining units are connected. Usually only a small neighborhood needs to
    be traversed; an articulation point may require exploring the whole donor.
    The caller separately prevents removal of a district's last unit.
    """
    source = labels[unit]
    neighbors = [neighbor for neighbor in graph[unit] if labels[neighbor] == source]
    if len(neighbors) < 2:
        return True
    remaining = set(neighbors[1:])
    seen = {unit, neighbors[0]}
    stack = [neighbors[0]]
    while stack:
        current = stack.pop()
        for neighbor in graph[current]:
            if neighbor not in seen and labels[neighbor] == source:
                remaining.discard(neighbor)
                if not remaining:
                    return True
                seen.add(neighbor)
                stack.append(neighbor)
    return False


def _district_articulation_points(
    graph: tuple[tuple[int, ...], ...], labels: Sequence[int], start: int
) -> frozenset[int]:
    """Find articulation vertices in a connected induced district iteratively.

    The caller guarantees the district is connected. Zero-population vertices
    participate exactly like every other vertex. An explicit DFS stack avoids
    recursion limits on long geographic corridors.
    """
    district = labels[start]
    discovered = {start: 0}
    low = {start: 0}
    parent = {start: -1}
    children = {start: 0}
    articulation: set[int] = set()
    stack = [(start, iter(graph[start]))]
    while stack:
        unit, neighbors = stack[-1]
        neighbor = next(neighbors, None)
        if neighbor is None:
            stack.pop()
            ancestor = parent[unit]
            if ancestor == -1:
                if children[unit] > 1:
                    articulation.add(unit)
            else:
                low[ancestor] = min(low[ancestor], low[unit])
                if parent[ancestor] != -1 and low[unit] >= discovered[ancestor]:
                    articulation.add(ancestor)
            continue
        if labels[neighbor] != district:
            continue
        if neighbor not in discovered:
            parent[neighbor] = unit
            children[unit] += 1
            children[neighbor] = 0
            discovered[neighbor] = len(discovered)
            low[neighbor] = discovered[neighbor]
            stack.append((neighbor, iter(graph[neighbor])))
        elif neighbor != parent[unit]:
            low[unit] = min(low[unit], discovered[neighbor])
    return frozenset(articulation)


class _DistrictArticulationCache:
    """Lazy removal decisions for connected districts with mutable labels.

    Every accepted transfer must invalidate both affected districts. A local
    boundary change can alter articulation status anywhere in either district.
    The caller separately prevents removal of a district's final vertex.
    """

    def __init__(self, graph: tuple[tuple[int, ...], ...], labels: Sequence[int]) -> None:
        self.graph = graph
        self.labels = labels
        self._points: dict[int, frozenset[int]] = {}

    def preserves_removal(self, unit: int) -> bool:
        district = self.labels[unit]
        if district not in self._points:
            self._points[district] = _district_articulation_points(self.graph, self.labels, unit)
        return unit not in self._points[district]

    def invalidate(self, source: int, target: int) -> None:
        self._points.pop(source, None)
        self._points.pop(target, None)


def repair_and_rebalance(
    adjacency: Sequence[Sequence[int]],
    assignments: Sequence[int],
    populations: Sequence[int],
    *,
    n_districts: int,
    max_moves: int = 1000,
    part_graph: PartGraph | None = None,
    cache_connectivity: bool = True,
) -> ConnectivityResult:
    """Return contiguous assignments with deterministic, connectivity-safe balance.

    ``max_moves`` caps the balancing stage, not the repair stage. A
    ``local_optimum`` means no strictly improving, connectivity-preserving
    single populated-unit transfer exists. It does not rule out improvements
    requiring simultaneous swaps, neutral moves, or initially worse balance.

    Invalid inputs and disconnected graph components unreachable from the
    selected anchors raise ``ValueError``. Inputs are never modified.

    When ``part_graph`` is supplied, connectivity is additionally repaired and
    preserved at polygon-part resolution while assignments remain whole units.
    This repair can move zero-population units. A stalled single-unit part
    repair raises ``PartConnectivityRepairError`` rather than claiming that no
    connected partition exists. Without it, legacy unit-graph behavior is kept.

    ``cache_connectivity`` replaces repeated donor traversals with exact cached
    articulation points. False retains the reference traversal. Both paths use
    the same candidates, tie-breaking, part checks, and stopping rules.
    """
    from districting.part_connectivity import (
        _move_preserves_connected_districts,
        part_component_counts,
        repair_part_connectivity,
    )

    if type(cache_connectivity) is not bool:
        raise ValueError("cache_connectivity must be a bool.")
    graph, labels, pops = _validate(
        adjacency, assignments, populations, n_districts, max_moves
    )
    if part_graph is not None:
        # Validate ownership and label dimensions before either repair stage.
        part_component_counts(part_graph, labels, n_districts=n_districts)
    district_populations = [0] * n_districts
    for label, population in zip(labels, pops):
        district_populations[label] += population
    total = sum(pops)
    repair_moves = _repair(graph, labels, pops, district_populations, total)
    part_repair_moves: tuple[MoveAudit, ...] = ()
    if part_graph is not None:
        part_result = repair_part_connectivity(
            part_graph, labels, pops, n_districts=n_districts
        )
        labels = list(part_result.assignments)
        part_repair_moves = tuple(
            MoveAudit(move.units, move.source_district, move.target_district, move.population)
            for move in part_result.moves
        )
        repair_moves += part_repair_moves
        district_populations = [0] * n_districts
        for label, population in zip(labels, pops):
            district_populations[label] += population
    repaired_assignments = tuple(labels)
    # Unit repair guarantees connected districts. A separately supplied part
    # graph need not agree with unit adjacency, so its later repair can break
    # that precondition. Preserve the reference behavior in that case instead
    # of applying a connected-district shortcut to a disconnected donor.
    cache = None
    if cache_connectivity and (
        part_graph is None
        or all(len(parts) == 1 for parts in _components(graph, labels, n_districts))
    ):
        cache = _DistrictArticulationCache(graph, labels)
    counts = [labels.count(label) for label in range(n_districts)]
    boundary = {
        unit
        for unit, neighbors in enumerate(graph)
        if any(labels[neighbor] != labels[unit] for neighbor in neighbors)
    }
    rebalance_moves: list[MoveAudit] = []
    stop_reason: Literal["local_optimum", "max_moves"] = "local_optimum"
    while True:
        current_objective = _objective(district_populations, total)
        candidates: list[tuple[int, int, int, int]] = []
        for unit in boundary:
            amount = pops[unit]
            source = labels[unit]
            if amount == 0 or counts[source] <= 1:
                continue
            targets = {labels[neighbor] for neighbor in graph[unit]} - {source}
            for target in targets:
                objective = _transfer_objective(
                    district_populations, total, source, target, amount
                )
                if objective < current_objective:
                    candidates.append((*objective, unit, target))
        chosen: tuple[int, int] | None = None
        blocked: set[int] = set()
        for _, _, unit, target in sorted(candidates):
            if unit in blocked:
                continue
            removal_is_safe = (
                cache.preserves_removal(unit) if cache is not None
                else _removal_preserves_connectivity(graph, labels, unit)
            )
            if not removal_is_safe:
                blocked.add(unit)
                continue
            if part_graph is not None and not _move_preserves_connected_districts(
                part_graph, labels, unit, target
            ):
                # Recipient safety depends on target, so another target for the
                # same unit must remain eligible.
                continue
            chosen = unit, target
            break
        if chosen is None:
            break
        if len(rebalance_moves) >= max_moves:
            stop_reason = "max_moves"
            break
        unit, target = chosen
        source = labels[unit]
        amount = pops[unit]
        labels[unit] = target
        if cache is not None:
            cache.invalidate(source, target)
        counts[source] -= 1
        counts[target] += 1
        district_populations[source] -= amount
        district_populations[target] += amount
        rebalance_moves.append(MoveAudit((unit,), source, target, amount))
        for affected in (unit, *graph[unit]):
            if any(labels[neighbor] != labels[affected] for neighbor in graph[affected]):
                boundary.add(affected)
            else:
                boundary.discard(affected)
    if any(len(parts) != 1 for parts in _components(graph, labels, n_districts)):
        raise RuntimeError("Connectivity postprocessing produced a disconnected district.")
    if part_graph is not None and any(
        count != 1
        for count in part_component_counts(part_graph, labels, n_districts=n_districts)
    ):
        raise RuntimeError("Connectivity postprocessing produced disconnected polygon parts.")
    return ConnectivityResult(
        assignments=tuple(labels),
        repaired_assignments=repaired_assignments,
        repair_moves=repair_moves,
        rebalance_moves=tuple(rebalance_moves),
        stop_reason=stop_reason,
        part_repair_moves=part_repair_moves,
    )
