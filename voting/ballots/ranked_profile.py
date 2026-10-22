"""
Anonymous ranked profile: how many voters cast each complete ranking.

Used by: criteria checks, and anywhere an electorate is easier to state as
counts than as individual ballots

Voting theory writes electorates this way ("35: A>C>B"). A profile is
anonymous: it records how many voters cast each ranking, not who cast them,
and it has no abstentions.

Profiles are stored in canonical form so that equal electorates compare and
hash equal: one row per distinct ranking, positive counts only, and rows
sorted by their ranking read in candidate order.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..types import CandidateId
from .ranked_choice import RankedChoiceBallot, create_ranked_choice_ballot

# A profile row: (number of voters, their ranking from most to least preferred)
ProfileRow = tuple[int, tuple[CandidateId, ...]]


class InvalidProfileError(ValueError):
    """Raised when a profile's candidates or counts are invalid."""
    pass


@dataclass(frozen=True)
class RankedProfile:
    """
    A canonical anonymous profile of complete rankings.

    Build one with create_ranked_profile, which validates and canonicalizes
    the rows; constructing the dataclass directly skips both.
    """
    # Candidate IDs in their reference order
    candidates: tuple[CandidateId, ...]
    # Canonical rows: distinct rankings, positive counts, sorted
    rows: tuple[ProfileRow, ...]

    @property
    def total_voters(self) -> int:
        return sum(count for count, _ in self.rows)


def create_ranked_profile(
    candidates: Sequence[CandidateId],
    rows: Iterable[tuple[int, Sequence[CandidateId]]],
    validate: bool = True,
) -> RankedProfile:
    """
    Create a ranked profile in canonical form.

    Rows with the same ranking are merged and rows with a zero count are
    dropped.

    Args:
        candidates: Candidate IDs in their reference order
        rows: (count, ranking) pairs
        validate: If False, skip checking that each ranking is a complete
            strict ranking. Only for rows built from an already valid profile.

    Raises:
        InvalidProfileError: If there are no candidates, candidates repeat,
            or a count is negative
        InvalidRankingError: If a ranking is not a complete strict ranking
            of the candidates (when validate=True)
    """
    candidate_tuple = tuple(candidates)
    if not candidate_tuple:
        raise InvalidProfileError("Profile needs at least one candidate")
    if len(set(candidate_tuple)) != len(candidate_tuple):
        raise InvalidProfileError("Profile candidates contain duplicates")

    position = {candidate: index for index, candidate in enumerate(candidate_tuple)}
    counts: dict[tuple[CandidateId, ...], int] = {}

    for count, ranking in rows:
        if count < 0:
            raise InvalidProfileError(f"Row count must not be negative, got {count}")
        ranking_tuple = tuple(ranking)
        if validate:
            # Reuse the ballot validator so every row is a complete strict ranking
            create_ranked_choice_ballot(
                "profile-row", list(ranking_tuple), list(candidate_tuple)
            )
        if count:
            counts[ranking_tuple] = counts.get(ranking_tuple, 0) + count

    canonical = tuple(
        sorted(
            counts.items(),
            key=lambda item: tuple(position[candidate] for candidate in item[0]),
        )
    )

    return RankedProfile(
        candidates=candidate_tuple,
        rows=tuple((count, ranking) for ranking, count in canonical),
    )


def profile_ballots(profile: RankedProfile) -> list[RankedChoiceBallot]:
    """
    Expand a profile into one ranked ballot per voter.

    Voter IDs are "v1", "v2", ... in row order, so the same profile always
    expands to the same ballots.
    """
    candidates = list(profile.candidates)
    ballots: list[RankedChoiceBallot] = []
    for count, ranking in profile.rows:
        for _ in range(count):
            ballots.append(
                create_ranked_choice_ballot(f"v{len(ballots) + 1}", list(ranking), candidates)
            )
    return ballots
