"""
Analyses behind the apportionment essay.

Everything here derives from the same Method of Equal Proportions priority
queue as `apportionment.methods.apportion` (same priority values, same FIPS
tiebreak), so every figure the essay shows agrees with the seat counts the
rest of the project computes.
"""

from __future__ import annotations

import heapq
import statistics
from dataclasses import dataclass
from typing import Mapping

from .methods import InvalidApportionmentError, priority_value


# ----------------------------------------------------------------------
# House sizes defined by a rule, computed rather than hard-coded
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class HouseSizeRule:
    key: str
    label: str
    formula: str
    seats: int


def wyoming_rule_size(populations: Mapping[str, int]) -> int:
    """District size set by the smallest state: round(total / smallest)."""
    return round(sum(populations.values()) / min(populations.values()))


def cube_root_size(populations: Mapping[str, int]) -> int:
    """Taagepera's cube-root law: round(total ** (1/3))."""
    return round(sum(populations.values()) ** (1 / 3))


def article_one_max_size(populations: Mapping[str, int]) -> int:
    """
    Article I, section 2: "The Number of Representatives shall not exceed one
    for every thirty Thousand." The largest House that satisfies it nationally
    is floor(total / 30,000); rounding up would exceed the ratio.
    """
    return sum(populations.values()) // 30_000


def house_size_rules(populations: Mapping[str, int], current: int = 435) -> list[HouseSizeRule]:
    return [
        HouseSizeRule("current", "Current House", "Fixed by the 1929 Act", current),
        HouseSizeRule(
            "wyoming", "Wyoming Rule", "total ÷ smallest state", wyoming_rule_size(populations)
        ),
        HouseSizeRule("cube_root", "Cube Root Rule", "∛ total", cube_root_size(populations)),
        HouseSizeRule("thousand", "A thousand seats", "Round number", 1_000),
        HouseSizeRule(
            "article_one",
            "Article I limit",
            "⌊total ÷ 30,000⌋",
            article_one_max_size(populations),
        ),
    ]


# ----------------------------------------------------------------------
# The priority queue, exposed step by step
# ----------------------------------------------------------------------


def award_order(populations: Mapping[str, int], max_seats: int) -> list[str]:
    """
    The state receiving each seat after every state's guaranteed first seat,
    in order: element i is the recipient of seat len(populations) + 1 + i.
    Seat counts for any House size N are a prefix count of this list.
    """
    floor_total = len(populations)
    if max_seats < floor_total:
        raise InvalidApportionmentError(
            f"max_seats ({max_seats}) is below the one-seat floor ({floor_total})"
        )
    seats = {fips: 1 for fips in populations}
    heap = [(-priority_value(pop, 1), fips) for fips, pop in populations.items()]
    heapq.heapify(heap)
    order: list[str] = []
    for _ in range(max_seats - floor_total):
        _, fips = heapq.heappop(heap)
        seats[fips] += 1
        order.append(fips)
        heapq.heappush(heap, (-priority_value(populations[fips], seats[fips]), fips))
    return order


@dataclass(frozen=True)
class Candidate:
    fips: str
    current_seats: int
    priority: float


@dataclass(frozen=True)
class RaceStep:
    seat_number: int
    winner: str
    winner_new_seats: int
    winner_priority: float
    #: The highest-priority states just before this seat is awarded.
    leaders: tuple[Candidate, ...]


def allocation_race(
    populations: Mapping[str, int], total_seats: int, top_k: int = 8
) -> list[RaceStep]:
    """Each award from the first unguaranteed seat to `total_seats`."""
    seats = {fips: 1 for fips in populations}
    steps: list[RaceStep] = []
    for seat_number in range(len(populations) + 1, total_seats + 1):
        ranked = sorted(
            (
                Candidate(fips, seats[fips], priority_value(pop, seats[fips]))
                for fips, pop in populations.items()
            ),
            key=lambda c: (-c.priority, c.fips),
        )
        winner = ranked[0]
        seats[winner.fips] += 1
        steps.append(
            RaceStep(
                seat_number=seat_number,
                winner=winner.fips,
                winner_new_seats=seats[winner.fips],
                winner_priority=winner.priority,
                leaders=tuple(ranked[:top_k]),
            )
        )
    return steps


# ----------------------------------------------------------------------
# District-size inequality at every House size
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SizeStats:
    house_size: int
    #: Largest people-per-seat divided by smallest.
    ratio: float
    largest: str
    smallest: str
    #: Median over states of |people per seat / national average - 1|.
    median_abs_deviation: float


def house_size_sweep(
    populations: Mapping[str, int], start: int, stop: int
) -> list[SizeStats]:
    """Inequality statistics for every House size in [start, stop]."""
    if start < len(populations) or stop < start:
        raise InvalidApportionmentError(f"Invalid sweep range [{start}, {stop}]")
    total = sum(populations.values())
    order = award_order(populations, stop)
    seats = {fips: 1 for fips in populations}
    for fips in order[: start - len(populations)]:
        seats[fips] += 1

    results: list[SizeStats] = []
    next_award = start - len(populations)
    for size in range(start, stop + 1):
        if size > start:
            seats[order[next_award]] += 1
            next_award += 1
        per_seat = {fips: populations[fips] / seats[fips] for fips in populations}
        largest = max(per_seat, key=lambda f: (per_seat[f], f))
        smallest = min(per_seat, key=lambda f: (per_seat[f], f))
        average = total / size
        results.append(
            SizeStats(
                house_size=size,
                ratio=per_seat[largest] / per_seat[smallest],
                largest=largest,
                smallest=smallest,
                median_abs_deviation=statistics.median(
                    abs(value / average - 1) for value in per_seat.values()
                ),
            )
        )
    return results


def seats_at(order: list[str], populations: Mapping[str, int], house_size: int) -> dict[str, int]:
    """Seat counts at `house_size` from an `award_order` prefix."""
    seats = {fips: 1 for fips in populations}
    for fips in order[: house_size - len(populations)]:
        seats[fips] += 1
    return seats
