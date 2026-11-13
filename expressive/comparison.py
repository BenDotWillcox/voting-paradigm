"""Compare two ballot formats using a reproducible, fictional electorate.

The binary question uses Colorado's 2022 Proposition 121 rates. The 99 prepared
curves are illustrative fixtures, not a model of Colorado voters. The
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
ComparisonScenario = Literal["prepared", "broad-agreement", "polarized", "intense-minority"]
COMPARISON_SCENARIOS: tuple[ComparisonScenario, ...] = (
    "prepared", "broad-agreement", "polarized", "intense-minority",
)
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


@dataclass(frozen=True)
class AuthoredCohort:
    count: int
    ideals: tuple[float, float]
    half_widths: tuple[float, float]
    approval_min: tuple[float, float]
    approval_max: tuple[float, float]
    # Most bounds are absolute policy rates; the narrow minority instead draws
    # positive distances below and above its individually sampled ideal.
    approval_offsets: bool = False


@dataclass(frozen=True)
class AuthoredScenario:
    label: str
    description: str
    seed: int
    cohorts: tuple[AuthoredCohort, ...]


# These bounds and seeds are authored teaching choices, not population estimates
# or measured welfare levels. Each parameter is a separate uniform draw, rounded
# to three decimals; neither the submitted user nor any tally is consulted.
# No seed search, winner conditioning, rejection sampling, or hidden weights.
AUTHORED_SCENARIOS: dict[ComparisonScenario, AuthoredScenario] = {
    "broad-agreement": AuthoredScenario(
        label="Broad agreement",
        description=("99 fictional voters with ideals sampled from 3.70% to 5.00%. Independent "
                     "draws vary both tapers and the endpoints of broadly overlapping approval "
                     "ranges. These authored ranges use a fixed seed; your unchanged ballot "
                     "is the 100th."),
        seed=20221109,
        cohorts=(AuthoredCohort(99, (3.7, 5.0), (0.9, 2.6), (2.4, 3.6), (5.1, 7.2)),),
    ),
    "polarized": AuthoredScenario(
        label="Polarized electorate",
        description=("99 fictional voters in two camps: 49 have ideals sampled from 2.40% to "
                     "3.70%, and 50 from 5.30% to 6.70%. Independent draws vary both tapers "
                     "and approval endpoints, with disjoint approval ranges between camps. "
                     "These authored ranges use a fixed seed; your unchanged ballot is the 100th."),
        seed=20221110,
        cohorts=(AuthoredCohort(49, (2.4, 3.7), (0.45, 1.0), (1.2, 2.3), (4.4, 4.48)),
                 AuthoredCohort(50, (5.3, 6.7), (0.45, 1.0), (4.49, 4.55), (6.8, 8.0))),
    ),
    "intense-minority": AuthoredScenario(
        label="Intense minority",
        description=("99 fictional voters: 65 have ideals sampled from 4.55% to 5.10% with "
                     "broad tapers, while 34 have ideals from 4.25% to 4.45% with narrow "
                     "tapers. Both tapers and approval endpoints vary independently; the "
                     "narrow group's approval bounds are sampled as distances from each ideal. "
                     "These authored ranges use a fixed seed. Larger declared score gaps "
                     "do not measure interpersonal welfare; your unchanged ballot is the 100th."),
        seed=20221111,
        cohorts=(AuthoredCohort(65, (4.55, 5.1), (1.3, 3.6), (2, 4), (5.5, 8)),
                 AuthoredCohort(34, (4.25, 4.45), (0.07, 0.18), (0.15, 0.5), (0.15, 0.4),
                                approval_offsets=True)),
    ),
}


def _cohort_ballot(cohort: AuthoredCohort, rng: random.Random) -> ScalarBallot:
    """Draw one curve from the declared bounds without conditioning its result."""
    def draw(bounds: tuple[float, float]) -> float:
        return round(rng.uniform(*bounds), 3)

    ideal = draw(cohort.ideals)
    lower_width, upper_width = draw(cohort.half_widths), draw(cohort.half_widths)
    lower, upper = draw(cohort.approval_min), draw(cohort.approval_max)
    if cohort.approval_offsets:
        lower, upper = round(ideal - lower, 3), round(ideal + upper, 3)
    return ScalarBallot(ideal, lower_width, upper_width, lower, upper)


@lru_cache(maxsize=4)
def scenario_voters(scenario: ComparisonScenario) -> tuple[ComparisonVoter, ...]:
    """Return the selected fixed 99 without consulting any submitted ballot."""
    if scenario == "prepared":
        return prepared_voters()
    if scenario not in AUTHORED_SCENARIOS:
        raise ValueError("Unknown comparison scenario.")
    fixture = AUTHORED_SCENARIOS[scenario]
    rng = random.Random(fixture.seed)
    voters = []
    for cohort in fixture.cohorts:
        for _ in range(cohort.count):
            index = len(voters) + 1
            ballot = _cohort_ballot(cohort, rng)
            voters.append(ComparisonVoter(
                id=f"voter-{index:03d}", label=f"Voter {index:02d}",
                ballot=ballot, binary_vote=curve_vote(ballot),
            ))
    return tuple(voters)


# Retain all four fixed backgrounds plus a bounded set of recent user curves.
# Otherwise switching among 99-unique-voter scenarios thrashes a 128-entry cache.
@lru_cache(maxsize=4 * 99 + 32)
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


def compare_ballots(
    ballot: ScalarBallot,
    binary_vote: Literal["yes", "no"],
    scenario: ComparisonScenario = "prepared",
) -> ComparisonResult:
    """Add the exact submitted pair to the selected fixed 99, with equal weight."""
    if binary_vote not in ("yes", "no"):
        raise ValueError("The submitted binary vote must be yes or no.")
    voters = (*scenario_voters(scenario), ComparisonVoter("you", "You", ballot, binary_vote))
    if scenario != "prepared":
        fixture = AUTHORED_SCENARIOS[scenario]
        return aggregate_electorate(ComparisonElectorate(
            id=f"scalar-electorate-{scenario}-v2",
            label=fixture.label,
            description=fixture.description,
            seed=fixture.seed,
            voters=voters,
        ))
    return aggregate_electorate(ComparisonElectorate(
        id="scalar-electorate-v1",
        label="One electorate, 100 different curves",
        description=("99 reproducible fictional voters plus your submitted ballot. Ideals, tapers, and "
                     "approval ranges vary; this is an illustration, not a sample of Colorado voters."),
        seed=ELECTORATE_SEED,
        voters=voters,
    ))
