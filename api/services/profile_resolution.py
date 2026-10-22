"""
Resolve a profile under every method its ballots allow.

Orchestration only: the voting package builds profiles and ballots, the
ballot model turns utilities into ballots, the methods resolve, and the
criteria and decisiveness checks judge. This module wires one request
through it and records every tie the tiebreak settles.

- A ranked profile is resolved by the four ranked methods.
- A utility profile is cast into every ballot format by the sincere ballot
  model, then resolved by all seven methods.
"""

from voting.ballot_models import (
    SINCERE_V1,
    BallotModel,
    UtilityProfile,
    cast_profile,
    create_utility_profile,
    rankings_of,
    rated_ballots,
)
from voting.ballots.approval import ApprovalBallot
from voting.ballots.quadratic import QuadraticBallot
from voting.ballots.ranked_choice import RankedChoiceBallot
from voting.ballots.ranked_profile import RankedProfile, create_ranked_profile, profile_ballots
from voting.ballots.score import MAX_SCORE, ScoreBallot
from voting.ballots.single_choice import create_single_choice_ballot
from voting.criteria import condorcet_loser, condorcet_winner, majority_winner, pairwise_counts
from voting.methods.approval import resolve_approval
from voting.methods.borda import resolve_borda
from voting.methods.irv import resolve_irv
from voting.methods.plurality import resolve_plurality
from voting.methods.quadratic import resolve_quadratic
from voting.methods.ranked_pairs import resolve_ranked_pairs
from voting.methods.score import resolve_score
from voting.search.outcomes import RANKED_METHODS, RankedMethod, is_decisive
from voting.types import Candidate, CandidateId, ElectionResult, TiebreakFunction, random_tiebreak

from ..schemas.voting import (
    ApprovalTraceSchema,
    BordaTraceSchema,
    IRVRoundSchema,
    IRVTraceSchema,
    MethodResultSchema,
    PluralityTraceSchema,
    ProfileResolveRequest,
    ProfileResolveResponse,
    QuadraticTraceSchema,
    RankedPairsTraceSchema,
    RankedProfileSchema,
    RankedRowSchema,
    ScoreTraceSchema,
    SingleProfileCriteriaSchema,
    TiebreakEventSchema,
    TraceSchema,
    UtilityProfileSchema,
    UtilityRowSchema,
    VictorySchema,
    VoterBallotsSchema,
)


def resolve_profile_request(request: ProfileResolveRequest) -> ProfileResolveResponse:
    """
    Resolve a ranked or utility profile.

    Raises:
        InvalidProfileError, InvalidRankingError: If the profile is invalid
    """
    schema = request.profile
    seed = request.tiebreak_seed

    if isinstance(schema, RankedProfileSchema):
        rankings = create_ranked_profile(
            schema.candidates, [(row.count, row.ranking) for row in schema.rows]
        )
        return _response(
            echo=_ranked_schema(rankings),
            rankings=rankings,
            seed=seed,
            model=None,
            utility_profile=None,
        )

    utility_profile = create_utility_profile(
        schema.candidates, [(row.count, row.utilities) for row in schema.rows]
    )
    return _response(
        echo=_utility_schema(utility_profile),
        rankings=rankings_of(utility_profile, SINCERE_V1),
        seed=seed,
        model=SINCERE_V1,
        utility_profile=utility_profile,
    )


def _response(
    echo: RankedProfileSchema | UtilityProfileSchema,
    rankings: RankedProfile,
    seed: int,
    model: BallotModel | None,
    utility_profile: UtilityProfile | None,
) -> ProfileResolveResponse:
    candidates = [Candidate(id=cid, name=cid) for cid in rankings.candidates]
    ranked_ballots = profile_ballots(rankings)
    results = [_resolve_ranked(method, candidates, ranked_ballots, seed) for method in RANKED_METHODS]
    voter_ballots: list[VoterBallotsSchema] = []

    if model is not None and utility_profile is not None:
        approval, score, quadratic = rated_ballots(utility_profile, model)
        results += [
            _resolve_approval(candidates, approval, seed),
            _resolve_score(candidates, score, seed),
            _resolve_quadratic(candidates, quadratic, seed),
        ]
        voter_ballots = [
            VoterBallotsSchema(
                row=index,
                count=count,
                choice=ballots.choice,
                ranking=list(ballots.ranking),
                approvals=list(ballots.approvals),
                scores=ballots.scores,
                allocations=ballots.allocations,
                credits_used=ballots.credits_used,
                credit_budget=ballots.credit_budget,
            )
            for index, ((count, _), ballots) in enumerate(
                zip(utility_profile.rows, cast_profile(utility_profile, model))
            )
        ]

    return ProfileResolveResponse(
        profile=echo,
        rankings=_ranked_schema(rankings),
        ballot_model=model.model_id if model is not None else None,
        voter_ballots=voter_ballots,
        total_voters=rankings.total_voters,
        tiebreak_seed=seed,
        pairwise=pairwise_counts(rankings),
        criteria=SingleProfileCriteriaSchema(
            majority_winner=majority_winner(rankings),
            condorcet_winner=condorcet_winner(rankings),
            condorcet_loser=condorcet_loser(rankings),
        ),
        results=results,
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


def _tiebreak(seed: int) -> _RecordingTiebreak:
    # A fresh tiebreaker per method, so no method's ties shift another's draws
    return _RecordingTiebreak(random_tiebreak(seed))


def _result(
    method: str,
    result: ElectionResult,
    tiebreak: _RecordingTiebreak,
    trace: TraceSchema,
) -> MethodResultSchema:
    return MethodResultSchema.model_validate(
        {
            "method": method,
            "winner": result.winners[0],
            "decisive": is_decisive(result),
            "tiebreaks": tiebreak.events,
            "trace": trace,
        }
    )


def _resolve_ranked(
    method: RankedMethod,
    candidates: list[Candidate],
    ballots: list[RankedChoiceBallot],
    seed: int,
) -> MethodResultSchema:
    tiebreak = _tiebreak(seed)
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

    return _result(method, result, tiebreak, trace)


def _resolve_approval(
    candidates: list[Candidate], ballots: list[ApprovalBallot], seed: int
) -> MethodResultSchema:
    tiebreak = _tiebreak(seed)
    result = resolve_approval(candidates, ballots, tiebreak)
    trace = ApprovalTraceSchema(approvals=result.vote_counts, abstentions=result.abstentions)
    return _result("approval", result, tiebreak, trace)


def _resolve_score(
    candidates: list[Candidate], ballots: list[ScoreBallot], seed: int
) -> MethodResultSchema:
    tiebreak = _tiebreak(seed)
    result = resolve_score(candidates, ballots, tiebreak)
    trace = ScoreTraceSchema(totals=result.score_totals, max_score=MAX_SCORE)
    return _result("score", result, tiebreak, trace)


def _resolve_quadratic(
    candidates: list[Candidate], ballots: list[QuadraticBallot], seed: int
) -> MethodResultSchema:
    tiebreak = _tiebreak(seed)
    result = resolve_quadratic(candidates, ballots, tiebreak)
    trace = QuadraticTraceSchema(
        net_votes=result.vote_totals,
        credits_spent=result.total_credits_spent,
        credits_available=result.total_credits_available,
    )
    return _result("quadratic", result, tiebreak, trace)


def _victory(victory: tuple[CandidateId, CandidateId, int]) -> VictorySchema:
    winner, loser, margin = victory
    return VictorySchema(winner=winner, loser=loser, margin=margin)


def _ranked_schema(profile: RankedProfile) -> RankedProfileSchema:
    return RankedProfileSchema(
        ballot_type="ranked",
        candidates=list(profile.candidates),
        rows=[
            RankedRowSchema(count=count, ranking=list(ranking))
            for count, ranking in profile.rows
        ],
    )


def _utility_schema(profile: UtilityProfile) -> UtilityProfileSchema:
    return UtilityProfileSchema(
        ballot_type="utility",
        candidates=list(profile.candidates),
        rows=[
            UtilityRowSchema(count=count, utilities=dict(zip(profile.candidates, utilities)))
            for count, utilities in profile.rows
        ],
    )
