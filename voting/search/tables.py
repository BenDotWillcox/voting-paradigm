"""
Winner tables: every profile up to a size, resolved once by the reference
method, so searches over pairs of profiles become array lookups.

Nothing here re-implements a voting method. Each table row is a profile's
count vector (voters per ranking, rankings in canonical order) and the index
of its decisive winner, or -1 when a tiebreak was needed. A profile is found
again from its count vector through an integer key.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ..types import CandidateId
from .enumeration import profiles, rankings
from .outcomes import RankedMethod, is_decisive, resolve_profile

IntArray = npt.NDArray[np.int64]
WinnerArray = npt.NDArray[np.int8]

NOT_DECISIVE = -1


@dataclass(frozen=True)
class SizeTable:
    """All profiles of one size, in canonical enumeration order."""
    # counts[i] = voters per ranking in profile i
    counts: IntArray
    # winners[i] = candidate index of profile i's decisive winner, or -1
    winners: WinnerArray
    # Keys sorted ascending, and the profile index each sorted key belongs to
    sorted_keys: IntArray
    sorted_index: IntArray


@dataclass(frozen=True)
class WinnerTable:
    """Decisive winners of every profile up to `max_voters` voters."""
    method: RankedMethod
    candidates: tuple[CandidateId, ...]
    max_voters: int
    sizes: dict[int, SizeTable]

    @property
    def key_weights(self) -> IntArray:
        types = len(rankings(self.candidates))
        return (self.max_voters + 1) ** np.arange(types, dtype=np.int64)

    def lookup(self, voters: int, counts: IntArray) -> WinnerArray:
        """Winner indices for count vectors (last axis) that sum to `voters`."""
        table = self.sizes[voters]
        keys = counts @ self.key_weights
        positions = np.searchsorted(table.sorted_keys, keys)
        return table.winners[table.sorted_index[positions]]


def build_winner_table(
    method: RankedMethod,
    candidates: Sequence[CandidateId],
    max_voters: int,
) -> WinnerTable:
    """Resolve every profile of 1 to `max_voters` voters with the reference method."""
    candidate_tuple = tuple(candidates)
    types = rankings(candidate_tuple)
    index_of = {candidate: i for i, candidate in enumerate(candidate_tuple)}
    weights = (max_voters + 1) ** np.arange(len(types), dtype=np.int64)
    sizes: dict[int, SizeTable] = {}

    for voters in range(1, max_voters + 1):
        count_rows: list[list[int]] = []
        winner_rows: list[int] = []
        for profile in profiles(candidate_tuple, voters):
            by_ranking = dict((ranking, count) for count, ranking in profile.rows)
            count_rows.append([by_ranking.get(ranking, 0) for ranking in types])
            # Resolved directly, not through the outcome cache, which would
            # hold every profile in memory
            result = resolve_profile(method, profile)
            winner_rows.append(
                index_of[result.winners[0]] if is_decisive(result) else NOT_DECISIVE
            )
        counts = np.array(count_rows, dtype=np.int64)
        keys = counts @ weights
        order = np.argsort(keys, kind="stable")
        sizes[voters] = SizeTable(
            counts=counts,
            winners=np.array(winner_rows, dtype=np.int8),
            sorted_keys=keys[order],
            sorted_index=order.astype(np.int64),
        )

    return WinnerTable(
        method=method,
        candidates=candidate_tuple,
        max_voters=max_voters,
        sizes=sizes,
    )
