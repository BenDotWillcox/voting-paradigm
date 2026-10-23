"""
Ballot models: from voters' utilities to the ballots they cast.

Ballots express; methods resolve; ballot models say how preferences become
ballots, so a comparison across ballot formats states its assumption.
"""

from collections.abc import Sequence

from ..ballots.approval import ApprovalBallot, create_approval_ballot
from ..ballots.quadratic import QuadraticBallot, create_quadratic_ballot
from ..ballots.ranked_profile import RankedProfile, create_ranked_profile
from ..ballots.score import ScoreBallot, create_score_ballot
from .models import SINCERE_V1, BallotModel, SincereModelV1, VoterBallots
from .utility_profile import (
    UTILITY_SCALE,
    UtilityProfile,
    UtilityRow,
    create_utility_profile,
)


def cast_profile(profile: UtilityProfile, model: BallotModel) -> list[VoterBallots]:
    """The ballots each voter type casts, one entry per row, in row order."""
    return [model.cast(profile.candidates, utilities) for _, utilities in profile.rows]


def rankings_of(profile: UtilityProfile, model: BallotModel) -> RankedProfile:
    """The ranked profile the voter types' ranked ballots make, canonical."""
    cast = cast_profile(profile, model)
    return create_ranked_profile(
        profile.candidates,
        [(count, list(ballots.ranking)) for (count, _), ballots in zip(profile.rows, cast)],
    )


def rated_ballots(
    profile: UtilityProfile,
    model: BallotModel,
) -> tuple[list[ApprovalBallot], list[ScoreBallot], list[QuadraticBallot]]:
    """One approval, score and quadratic ballot per voter, row by row."""
    approval: list[ApprovalBallot] = []
    score: list[ScoreBallot] = []
    quadratic: list[QuadraticBallot] = []
    voter = 0
    for (count, _), ballots in zip(profile.rows, cast_profile(profile, model)):
        for _ in range(count):
            voter += 1
            voter_id = f"v{voter}"
            approval.append(create_approval_ballot(voter_id, list(ballots.approvals)))
            score.append(create_score_ballot(voter_id, dict(ballots.scores)))
            quadratic.append(
                create_quadratic_ballot(
                    voter_id, dict(ballots.allocations), credit_budget=ballots.credit_budget
                )
            )
    return approval, score, quadratic


def evenly_spaced(candidates: Sequence[str], ranking: Sequence[str]) -> dict[str, int]:
    """Utilities that space a ranking evenly from UTILITY_SCALE down to 0."""
    steps = max(len(ranking) - 1, 1)
    return {c: round(UTILITY_SCALE * (steps - i) / steps) for i, c in enumerate(ranking)}


__all__ = [
    "BallotModel",
    "SINCERE_V1",
    "SincereModelV1",
    "UTILITY_SCALE",
    "UtilityProfile",
    "UtilityRow",
    "VoterBallots",
    "cast_profile",
    "create_utility_profile",
    "evenly_spaced",
    "rankings_of",
    "rated_ballots",
]
