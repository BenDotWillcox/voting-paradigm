"""Compare two ballot formats using one reproducible, fictional electorate.

The binary question uses Colorado's 2022 Proposition 121 rates. The 99 prepared
curves are an illustrative seeded fixture, not a model of Colorado voters. The
submitted user completes the same 100 voters used in every tally. Equal 0--1
score weight is a voting-rule convention, not measured interpersonal welfare.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from expressive.scalar import SCALAR_DOMAIN_MAX, ScalarBallot, evaluate_scalar

BinaryVote = Literal["yes", "no", "abstain"]
STATUS_QUO: Literal[4.55] = 4.55
PROPOSAL: Literal[4.4] = 4.4
CANDIDATE_STEP: Literal[0.05] = 0.05
SCORE_TIE_TOLERANCE = 1e-12
ELECTORATE_SEED = 20221108
CANDIDATES = tuple(index / 20 for index in range(int(SCALAR_DOMAIN_MAX * 20) + 1))


def compare_scores(first: float, second: float) -> int:
    """Compare scores with one explicit absolute numerical tie convention."""
    if math.isclose(first, second, rel_tol=0.0, abs_tol=SCORE_TIE_TOLERANCE):
        return 0
    return 1 if first > second else -1


def curve_vote(ballot: ScalarBallot) -> BinaryVote:
    """Prefer the higher-scoring offered rate; a numerical tie abstains."""
    comparison = compare_scores(
        evaluate_scalar(ballot, PROPOSAL).score,
        evaluate_scalar(ballot, STATUS_QUO).score,
    )
    return "yes" if comparison > 0 else "no" if comparison < 0 else "abstain"


@dataclass(frozen=True)
class ComparisonVoter:
    id: str
    label: str
    ballot: ScalarBallot
    binary_vote: BinaryVote
    curve_vote: BinaryVote = field(init=False)
    status_quo_score: float = field(init=False)
    proposal_score: float = field(init=False)

    def __post_init__(self) -> None:
        if self.binary_vote not in ("yes", "no", "abstain"):
            raise ValueError("A binary vote must be yes, no, or abstain.")
        object.__setattr__(self, "curve_vote", curve_vote(self.ballot))
        object.__setattr__(self, "status_quo_score", evaluate_scalar(self.ballot, STATUS_QUO).score)
        object.__setattr__(self, "proposal_score", evaluate_scalar(self.ballot, PROPOSAL).score)


@dataclass(frozen=True)
class ComparisonElectorate:
    id: str
    label: str
    description: str
    seed: int
    voters: tuple[ComparisonVoter, ...]


@dataclass(frozen=True)
class BinaryResult:
    yes: int
    no: int
    abstain: int
    passed: bool
    outcome_rate: float


@dataclass(frozen=True)
class PairResult:
    status_quo_mean: float
    proposal_mean: float
    winner_rates: tuple[float, ...]


@dataclass(frozen=True)
class ComparisonPoint:
    rate: float
    mean_score: float
    approval_count: int
    user_score: float
    user_approved: bool
    prefer_this: int
    prefer_binary: int
    indifferent: int


@dataclass(frozen=True)
class ComparisonResult:
    electorate: ComparisonElectorate
    binary: BinaryResult
    pair: PairResult
    winner_rates: tuple[float, ...]
    max_mean_score: float
    points: tuple[ComparisonPoint, ...]


@lru_cache(maxsize=1)
def prepared_voters() -> tuple[ComparisonVoter, ...]:
    """A fixed fixture with varied ideals, asymmetric tapers, and approval bands.

    The triangular ideal distribution and independent widths are authored demo
    choices, not estimated preferences. Nothing conditions generation on a
    desired yes/no tally or aggregate winner. Local RNG state makes submissions
    unable to change the other voters; the fixture version and seed travel with
    the result. Every fifth voter leaves approval at the full domain.
    """
    rng = random.Random(ELECTORATE_SEED)
    voters = []
    for index in range(99):
        ideal = round(rng.triangular(0, 12, 4.5), 3)
        lower_width = round(rng.uniform(0.35, 3.5), 3)
        upper_width = round(rng.uniform(0.35, 3.5), 3)
        lower_span = rng.uniform(1, 5)
        upper_span = rng.uniform(1, 6)
        ballot = ScalarBallot(
            ideal=ideal,
            lower_half_width=lower_width,
            upper_half_width=upper_width,
            approval_min=0 if index % 5 == 0 else round(max(0, ideal - lower_span), 3),
            approval_max=100 if index % 5 == 0 else round(min(100, ideal + upper_span), 3),
        )
        voters.append(ComparisonVoter(
            id=f"voter-{index + 1:03d}", label=f"Voter {index + 1:02d}",
            ballot=ballot, binary_vote=curve_vote(ballot),
        ))
    return tuple(voters)


@lru_cache(maxsize=128)
def _sample_ballot(ballot: ScalarBallot) -> tuple[tuple[float, bool], ...]:
    """Reuse the unchanged prepared curves across submissions, with bounded storage."""
    return tuple((probe.score, probe.approved) for probe in (
        evaluate_scalar(ballot, rate) for rate in CANDIDATES
    ))


def aggregate_electorate(electorate: ComparisonElectorate) -> ComparisonResult:
    """Tally the exact voters returned to the UI, with no hidden cohort weights.

    Binary ties retain the status quo. Rich-ballot ties return every maximizing
    grid rate, rather than inventing a winning compromise or choosing one tie.
    Approval counts describe individual clipping, never a collective veto.
    """
    voters = electorate.voters
    if not voters or len({voter.id for voter in voters}) != len(voters):
        raise ValueError("An electorate needs nonempty, uniquely identified voters.")
    user_indices = [index for index, voter in enumerate(voters) if voter.id == "you"]
    if len(user_indices) != 1:
        raise ValueError("An electorate must contain exactly one submitted user.")
    user_index = user_indices[0]
    yes = sum(voter.binary_vote == "yes" for voter in voters)
    no = sum(voter.binary_vote == "no" for voter in voters)
    binary = BinaryResult(yes, no, len(voters) - yes - no, yes > no, PROPOSAL if yes > no else STATUS_QUO)
    baseline_scores = tuple(
        voter.proposal_score if binary.passed else voter.status_quo_score for voter in voters
    )
    samples = tuple(_sample_ballot(voter.ballot) for voter in voters)
    points = []
    for rate, evaluations in zip(CANDIDATES, zip(*samples)):
        scores = tuple(evaluation[0] for evaluation in evaluations)
        comparisons = tuple(compare_scores(score, baseline) for score, baseline in zip(scores, baseline_scores))
        points.append(ComparisonPoint(
            rate=rate,
            mean_score=math.fsum(scores) / len(voters),
            approval_count=sum(evaluation[1] for evaluation in evaluations),
            user_score=scores[user_index],
            user_approved=evaluations[user_index][1],
            prefer_this=comparisons.count(1),
            prefer_binary=comparisons.count(-1),
            indifferent=comparisons.count(0),
        ))
    by_rate = {point.rate: point.mean_score for point in points}
    pair_comparison = compare_scores(by_rate[PROPOSAL], by_rate[STATUS_QUO])
    pair_winners = ((PROPOSAL,) if pair_comparison > 0 else (STATUS_QUO,) if pair_comparison < 0
                    else (STATUS_QUO, PROPOSAL))
    maximum = max(point.mean_score for point in points)
    return ComparisonResult(
        electorate=electorate,
        binary=binary,
        pair=PairResult(by_rate[STATUS_QUO], by_rate[PROPOSAL], pair_winners),
        winner_rates=tuple(point.rate for point in points if compare_scores(point.mean_score, maximum) == 0),
        max_mean_score=maximum,
        points=tuple(points),
    )


def compare_ballots(ballot: ScalarBallot, binary_vote: Literal["yes", "no"]) -> ComparisonResult:
    """Add the exact submitted ballot and explicit binary vote to the fixed 99."""
    if binary_vote not in ("yes", "no"):
        raise ValueError("The submitted binary vote must be yes or no.")
    return aggregate_electorate(ComparisonElectorate(
        id="scalar-electorate-v1",
        label="One electorate, 100 different curves",
        description=("99 reproducible fictional voters plus your submitted ballot. Ideals, tapers, and "
                     "approval ranges vary; this is an illustration, not a sample of Colorado voters."),
        seed=ELECTORATE_SEED,
        voters=(*prepared_voters(), ComparisonVoter("you", "You", ballot, binary_vote)),
    ))
