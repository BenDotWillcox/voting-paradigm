"""
Method of Equal Proportions (Huntington-Hill) apportionment.

This is the rule the United States has used since 1941 to apportion seats
in the House of Representatives among the 50 states. Given each state's
population and a total number of seats, it produces a seat count per state
satisfying:

  * Each state receives at least one seat (constitutional minimum).
  * The sum of seats equals the requested total.
  * Among the methods avoiding the Alabama paradox, the population paradox,
    and the new-states paradox, this method minimizes pairwise relative
    differences in district size (this is the theorem that motivated its
    adoption).

Algorithm

  Each state starts with `min_per_state` seats (default: 1). The remaining
  seats are assigned one at a time. At each step, every state has a
  *priority value*

      P(n) = population / sqrt(n * (n + 1))

  where `n` is the state's current seat count. The next seat goes to the
  state with the highest priority value. After receiving the seat, the
  state's `n` increments by one and its priority is recomputed.

  This is implemented with a max-heap keyed on -P(n) (Python's heapq is a
  min-heap), giving O(C log S) total time for C remaining seats and S states.

Determinism

  Priority ties are extraordinarily unlikely with realistic populations but
  possible in principle. Python's tuple comparison naturally tiebreaks by
  the second element of the heap entry — the state's FIPS code (a string).
  This makes the algorithm fully deterministic given the input mapping.
  The actual US procedure has its own statutory tiebreak, but it has never
  been invoked, and reproducing it is not part of this demo's value.
"""

from __future__ import annotations

import heapq
import math
from typing import Mapping

from .data.apportionment_2020 import US_2020_APPORTIONMENT_POPULATIONS


class InvalidApportionmentError(ValueError):
    """Raised when apportionment inputs are inconsistent."""


def priority_value(population: int, current_seats: int) -> float:
    """
    Compute the Huntington-Hill priority value for a state.

    A state with `population` people currently holding `current_seats`
    seats has priority `population / sqrt(n * (n + 1))` for receiving its
    next (n+1-th) seat, where `n = current_seats`.

    Exposed as a public helper for telemetry and UI affordances such as
    "the next marginal seat would go to state X".
    """
    if population <= 0:
        raise InvalidApportionmentError(
            f"Population must be positive, got {population}"
        )
    if current_seats < 0:
        raise InvalidApportionmentError(
            f"current_seats must be non-negative, got {current_seats}"
        )
    n = current_seats
    return population / math.sqrt(n * (n + 1)) if n > 0 else float("inf")


def apportion(
    state_populations: Mapping[str, int],
    total_seats: int,
    *,
    min_per_state: int = 1,
) -> dict[str, int]:
    """
    Apportion `total_seats` seats among the states.

    Args:
        state_populations: Mapping of state identifier (typically FIPS code)
            to apportionment population. All values must be positive.
        total_seats: Total number of seats to distribute. Must be at least
            len(state_populations) * min_per_state.
        min_per_state: Floor on each state's seat count. Default 1 matches
            the US constitutional minimum. Set to 0 only for testing the
            "no floor" variant of the algorithm.

    Returns:
        A new dict mapping each state identifier to its assigned seat count.
        The sum of values equals `total_seats`.

    Raises:
        InvalidApportionmentError: If total_seats is too small to satisfy
            the floor, or if any population is non-positive.
    """
    n_states = len(state_populations)

    if n_states == 0:
        if total_seats == 0:
            return {}
        raise InvalidApportionmentError(
            f"Cannot apportion {total_seats} seats among 0 states"
        )

    if min_per_state < 0:
        raise InvalidApportionmentError(
            f"min_per_state must be non-negative, got {min_per_state}"
        )

    floor_total = n_states * min_per_state
    if total_seats < floor_total:
        raise InvalidApportionmentError(
            f"total_seats ({total_seats}) is less than the floor "
            f"({n_states} states * {min_per_state} = {floor_total})"
        )

    for fips, pop in state_populations.items():
        if pop <= 0:
            raise InvalidApportionmentError(
                f"Population for state {fips!r} must be positive, got {pop}"
            )

    seats: dict[str, int] = {fips: min_per_state for fips in state_populations}
    remaining = total_seats - floor_total

    if remaining == 0:
        return seats

    # Max-heap keyed on (-priority, fips). Tuple comparison breaks priority
    # ties deterministically by FIPS code.
    heap: list[tuple[float, str]] = []
    for fips, pop in state_populations.items():
        heap.append((-priority_value(pop, seats[fips]), fips))
    heapq.heapify(heap)

    for _ in range(remaining):
        _neg_priority, fips = heapq.heappop(heap)
        seats[fips] += 1
        new_priority = priority_value(state_populations[fips], seats[fips])
        heapq.heappush(heap, (-new_priority, fips))

    return seats


def apportion_us_2020(total_seats: int) -> dict[str, int]:
    """
    Apportion `total_seats` among the 50 states using 2020 census
    apportionment populations.

    Convenience wrapper around `apportion` for the demo's primary use case.
    """
    return apportion(US_2020_APPORTIONMENT_POPULATIONS, total_seats)
