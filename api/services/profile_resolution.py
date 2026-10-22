"""
Resolve an anonymous ranked profile under every ranked method.

Orchestration only: the voting package builds the profile and ballots,
resolves each method, judges the single-profile criteria, and decides
whether a result was decisive. This module wires one request through it and
records every tie the tiebreak settles.
"""

from voting.ballots.ranked_choice import RankedChoiceBallot
from voting.ballots.ranked_profile import (
    RankedProfile,
    create_ranked_profile,
    profile_ballots,
)
from voting.ballots.single_choice import create_single_choice_ballot
from voting.criteria import condorcet_loser, condorcet_winner, majority_winner, pairwise_counts
from voting.methods.borda import resolve_borda
from voting.methods.irv import resolve_irv
from voting.methods.plurality import resolve_plurality
from voting.methods.ranked_pairs import resolve_ranked_pairs
from voting.search.outcomes import RANKED_METHODS, RankedMethod, is_decisive
from voting.types import Candidate, CandidateId, ElectionResult, TiebreakFunction, random_tiebreak

from ..schemas.voting import (
    BordaTraceSchema,
    IRVRoundSchema,
    IRVTraceSchema,
    MethodResultSchema,
    PluralityTraceSchema,
    ProfileResolveRequest,
    ProfileResolveResponse,
    RankedPairsTraceSchema,
    RankedProfileSchema,
    RankedRowSchema,
    SingleProfileCriteriaSchema,
    TiebreakEventSchema,
    TraceSchema,
    VictorySchema,
)


def resolve_profile_request(request: ProfileResolveRequest) -> ProfileResolveResponse:
    """
    Resolve a ranked profile under plurality, IRV, Borda and Ranked Pairs.

    Raises:
        InvalidProfileError, InvalidRankingError: If the profile is invalid
    """
    profile = create_ranked_profile(
        request.profile.candidates,
        [(row.count, row.ranking) for row in request.profile.rows],
    )
    candidates = [Candidate(id=cid, name=cid) for cid in profile.candidates]
    ballots = profile_ballots(profile)

    return ProfileResolveResponse(
        profile=_canonical_schema(profile),
        total_voters=profile.total_voters,
        tiebreak_seed=request.tiebreak_seed,
        pairwise=pairwise_counts(profile),
        criteria=SingleProfileCriteriaSchema(
            majority_winner=majority_winner(profile),
            condorcet_winner=condorcet_winner(profile),
            condorcet_loser=condorcet_loser(profile),
        ),
        results=[
            _resolve(method, candidates, ballots, request.tiebreak_seed)
            for method in RANKED_METHODS
        ],
    )


class _RecordingTiebreak:
    """Wraps a tiebreak and records each tie it settles."""

    def __init__(self, inner: TiebreakFunction) -> None:
        self._inner = inner
        self.events: list[TiebreakEventSchema] = []

    def __call__(self, tied: list[CandidateId]) -> CandidateId:
        choice = self._inner(tied)
        self.events.append(TiebreakEventSchema(tied=sorted(tied), chose=choice))
        return choice


def _resolve(
    method: RankedMethod,
    candidates: list[Candidate],
    ballots: list[RankedChoiceBallot],
    seed: int,
) -> MethodResultSchema:
    # A fresh tiebreaker per method, so no method's ties shift another's draws
    tiebreak = _RecordingTiebreak(random_tiebreak(seed))
    result: ElectionResult
    trace: TraceSchema

    if method == "plurality":
        first_choices = [
            create_single_choice_ballot(ballot.voter_id, ballot.ranking[0])
            for ballot in ballots
        ]
        result = resolve_plurality(candidates, first_choices, tiebreak)
        trace = PluralityTraceSchema(first_choices=result.vote_counts)
    elif method == "irv":
        irv = resolve_irv(candidates, ballots, tiebreak)
        result = irv
        trace = IRVTraceSchema(
            rounds=[
                IRVRoundSchema(
                    round_number=round_.round_number,
                    counts=round_.vote_counts,
                    exhausted_ballots=round_.exhausted_ballots,
                    eliminated=round_.eliminated,
                    elimination_was_tiebreak=round_.elimination_was_tiebreak,
                )
                for round_ in irv.rounds
            ],
            winning_round=irv.winning_round,
        )
    elif method == "borda":
        borda = resolve_borda(candidates, ballots, tiebreak)
        result = borda
        trace = BordaTraceSchema(
            points=borda.point_totals,
            max_points_per_ballot=borda.max_points_per_ballot,
        )
    else:
        ranked_pairs = resolve_ranked_pairs(
            candidates, ballots, tiebreak, include_pairwise_matrix=False
        )
        result = ranked_pairs
        trace = RankedPairsTraceSchema(
            had_condorcet_winner=ranked_pairs.had_condorcet_winner,
            locked=[_victory(v) for v in ranked_pairs.locked_victories],
            skipped=[_victory(v) for v in ranked_pairs.skipped_victories],
            tiebreak_priority=ranked_pairs.tiebreak_priority,
        )

    return MethodResultSchema(
        method=method,
        winner=result.winners[0],
        decisive=is_decisive(result),
        tiebreaks=tiebreak.events,
        trace=trace,
    )


def _victory(victory: tuple[CandidateId, CandidateId, int]) -> VictorySchema:
    winner, loser, margin = victory
    return VictorySchema(winner=winner, loser=loser, margin=margin)


def _canonical_schema(profile: RankedProfile) -> RankedProfileSchema:
    return RankedProfileSchema(
        ballot_type="ranked",
        candidates=list(profile.candidates),
        rows=[
            RankedRowSchema(count=count, ranking=list(ranking))
            for count, ranking in profile.rows
        ],
    )
