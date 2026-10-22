"""
Utility profile: voter types, each a count of voters sharing one set of
utilities over the candidates.

Used by: ballot models, which turn a voter type's utilities into the ballot
it casts under each ballot format

Utilities are integers from 0 (worst) to UTILITY_SCALE (best). Unlike a
RankedProfile, rows keep the order they were given in and are never merged:
each row is a voter type a reader built and can refer back to.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ..ballots.ranked_profile import InvalidProfileError
from ..types import CandidateId

UTILITY_SCALE = 100

# A row: (number of voters, utilities aligned with the profile's candidates)
UtilityRow = tuple[int, tuple[int, ...]]


@dataclass(frozen=True)
class UtilityProfile:
    """Voter types with integer utilities, rows in the order given."""
    candidates: tuple[CandidateId, ...]
    rows: tuple[UtilityRow, ...]

    @property
    def total_voters(self) -> int:
        return sum(count for count, _ in self.rows)


def create_utility_profile(
    candidates: Sequence[CandidateId],
    rows: Iterable[tuple[int, Mapping[CandidateId, int]]],
) -> UtilityProfile:
    """
    Create a utility profile.

    Raises:
        InvalidProfileError: If candidates are missing or repeat, a count is
            negative, or a row does not give every candidate exactly one
            utility between 0 and UTILITY_SCALE
    """
    candidate_tuple = tuple(candidates)
    if not candidate_tuple:
        raise InvalidProfileError("Profile needs at least one candidate")
    if len(set(candidate_tuple)) != len(candidate_tuple):
        raise InvalidProfileError("Profile candidates contain duplicates")

    validated: list[UtilityRow] = []
    for index, (count, utilities) in enumerate(rows):
        if count < 0:
            raise InvalidProfileError(f"Row {index + 1}: count must not be negative")
        if set(utilities) != set(candidate_tuple):
            raise InvalidProfileError(
                f"Row {index + 1}: give exactly one utility for each candidate"
            )
        values = tuple(utilities[c] for c in candidate_tuple)
        if any(not 0 <= value <= UTILITY_SCALE for value in values):
            raise InvalidProfileError(
                f"Row {index + 1}: utilities must be between 0 and {UTILITY_SCALE}"
            )
        validated.append((count, values))

    return UtilityProfile(candidates=candidate_tuple, rows=tuple(validated))
