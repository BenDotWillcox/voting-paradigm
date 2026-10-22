"""
Who a ranked method elects from a profile, and whether the ballots alone
decided it.

The paradox search only accepts decisive outcomes, so a specimen never rests
on a tiebreak. An outcome is decisive when the method applied no tiebreak
and, for IRV, no round eliminated several candidates tied for last at once
(the package does that without consulting the tiebreak).

Every outcome comes from the reference methods in voting.methods. Plurality
counts each voter's first choice.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from ..ballots.ranked_choice import RankedChoiceBallot, create_ranked_choice_ballot
from ..ballots.ranked_profile import RankedProfile
from ..ballots.single_choice import SingleChoiceBallot, create_single_choice_ballot
from ..methods.borda import resolve_borda
from ..methods.irv import IRVResult, resolve_irv
from ..methods.plurality import resolve_plurality
from ..methods.ranked_pairs import resolve_ranked_pairs
from ..types import Candidate, CandidateId, ElectionResult

RankedMethod = Literal["plurality", "irv", "borda", "ranked_pairs"]

RANKED_METHODS: tuple[RankedMethod, ...] = ("plurality", "irv", "borda", "ranked_pairs")


@dataclass(frozen=True)
class Outcome:
    """A method's winner and whether a tie had to be broken to reach it."""
    winner: CandidateId
    decisive: bool


def is_decisive(result: ElectionResult) -> bool:
    """Whether the ballots alone decided this result."""
    if result.tiebreak_applied:
        return False
    if isinstance(result, IRVResult):
        return all(len(round_.eliminated) <= 1 for round_ in result.rounds)
    return True


def resolve_profile(
    method: RankedMethod,
    profile: RankedProfile,
    ballots: list[RankedChoiceBallot] | None = None,
) -> ElectionResult:
    """
    Resolve a profile with the reference method.

    Ties go to the smallest candidate ID, but the search discards any result
    that needed a tiebreak.

    Args:
        method: Which ranked method to apply
        profile: The electorate
        ballots: Ballots to resolve instead of the search's shared ones, for
            example fresh ones from profile_ballots when certifying
    """
    candidates = _candidates(profile.candidates)
    if method == "plurality":
        first_choices = (
            _first_choice_ballots(profile)
            if ballots is None
            else [create_single_choice_ballot(b.voter_id, b.ranking[0]) for b in ballots]
        )
        return resolve_plurality(candidates, first_choices, tiebreak=min)
    ranked = _ranked_ballots(profile) if ballots is None else ballots
    if method == "irv":
        return resolve_irv(candidates, ranked, tiebreak=min)
    if method == "borda":
        return resolve_borda(candidates, ranked, tiebreak=min)
    return resolve_ranked_pairs(
        candidates, ranked, tiebreak=min, include_pairwise_matrix=False
    )


# Bounded so long searches keep memory flat; profiles revisited soon after
# (a profile and its raised or reduced neighbors) still hit
@lru_cache(maxsize=1 << 17)
def outcome(method: RankedMethod, profile: RankedProfile) -> Outcome:
    """The method's winner on this profile, cached for the search."""
    result = resolve_profile(method, profile)
    return Outcome(winner=result.winners[0], decisive=is_decisive(result))


@lru_cache(maxsize=None)
def _candidates(ids: tuple[CandidateId, ...]) -> list[Candidate]:
    return [Candidate(id=cid, name=cid) for cid in ids]


@lru_cache(maxsize=None)
def _ranked_ballot(
    candidates: tuple[CandidateId, ...],
    ranking: tuple[CandidateId, ...],
) -> RankedChoiceBallot:
    return create_ranked_choice_ballot("-".join(ranking), list(ranking), list(candidates))


@lru_cache(maxsize=None)
def _first_choice_ballot(choice: CandidateId) -> SingleChoiceBallot:
    return create_single_choice_ballot(choice, choice)


def _ranked_ballots(profile: RankedProfile) -> list[RankedChoiceBallot]:
    """One shared, read-only ballot object per ranking, repeated per voter."""
    ballots: list[RankedChoiceBallot] = []
    for count, ranking in profile.rows:
        ballots.extend([_ranked_ballot(profile.candidates, ranking)] * count)
    return ballots


def _first_choice_ballots(profile: RankedProfile) -> list[SingleChoiceBallot]:
    ballots: list[SingleChoiceBallot] = []
    for count, ranking in profile.rows:
        ballots.extend([_first_choice_ballot(ranking[0])] * count)
    return ballots
