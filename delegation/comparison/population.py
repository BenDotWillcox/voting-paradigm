"""
The simulated population the four arrangements are compared on.

Everything here is an assumption chosen to make the comparison legible, and
the parameters that matter are meant to be swept, not trusted:

  - Positions. Each person has a position on D issue dimensions from a
    one-factor model: a shared left-right factor g and an independent part
    e per dimension, x = loading * g + sqrt(1 - loading^2) * e, plus their
    district's lean. Before district leans, two dimensions correlate at
    loading^2. With a loading of 1 everyone lies on one line and a single
    representative can stand for a voter on every issue; with 0 positions
    cut across issues and bundling is expensive.
  - Questions. Each question sits on one dimension with a cutpoint and a
    direction. A person's sincere vote is the side of the cutpoint they fall
    on, plus a seeded idiosyncratic term for considerations the dimension
    does not capture. The sincere vote is the reference every arrangement is
    scored against: it is the voter's own answer, so direct voting is
    correct for them by definition.
  - Turnout. Each person has a turnout rate, and whether they cast their own
    ballot on a question is one seeded draw per (person, question). The same
    draw is used by every arrangement, so arrangements differ only in whose
    ballot counts.
  - Two periods. Questions from the history period are what delegates are
    chosen from; everyone votes directly on them. Questions from the
    evaluation period are what arrangements are scored on. The two are drawn
    independently.

Random streams are split by purpose, so changing one parameter (the loading,
the number of evaluation questions) moves no draw that it does not have to:
a sweep over the loading reuses the same factor and specific draws.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final, Protocol

import numpy as np
import numpy.typing as npt
from scipy.optimize import brentq
from scipy.special import expit

from ..types import PersonId, QuestionId

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
VoteArray = npt.NDArray[np.int8]
BoolArray = npt.NDArray[np.bool_]

YES: Final = 1
NO: Final = -1
# A ballot that was not cast, in a vote matrix
NOT_CAST: Final = 0

# One integer per random stream, so streams never share draws.
_POSITIONS: Final = 1
_LEANS: Final = 2
_TURNOUT: Final = 3
_HISTORY: Final = 4
_EVALUATION: Final = 5
_CANDIDATES: Final = 6
_ELECTION: Final = 7
_BLOCKS: Final = 8

# The turnout dial (amendment A6, 2026-11-18). A resident's own rate is
# logistic(location + spread * z), with z ~ N(0, 1) fixed per resident and the
# location chosen so the population's mean rate is the dial's value. Turning
# the dial moves everyone's log-odds of voting by the same amount, so the same
# residents stay ranked the same at every level. The spread is calibrated to
# one register statistic under this model: Geneva's ten successive federal
# ballot days, mean participation 0.493, of which 20.2% of citizens took part
# in none and 15.9% in all (Sciarini et al. 2016, Table 1). Least squares on
# those two shares at that mean, with ballot days as independent draws, gives
# 2.81 (18.6% and 17.6%). The register counts ballot days, often several
# measures each; the model gives each question its own draw unless
# `attendance_cluster` groups them, so the transfer from days to questions is
# an assumption with its own sensitivity point.
TURNOUT_LOGIT_SD: Final = 2.81
_HERMITE_NODES, _HERMITE_WEIGHTS = np.polynomial.hermite_e.hermegauss(200)
_HERMITE_WEIGHTS = _HERMITE_WEIGHTS / _HERMITE_WEIGHTS.sum()


def mean_turnout(location: float, logit_sd: float) -> float:
    """The mean of logistic(location + logit_sd * z) over z ~ N(0, 1)."""
    return float((_HERMITE_WEIGHTS * expit(location + logit_sd * _HERMITE_NODES)).sum())


def turnout_location(mean: float, logit_sd: float) -> float:
    """The location at which the population's mean turnout rate is `mean`."""
    if not 0.0 < mean < 1.0:
        raise ValueError("mean turnout must be in (0, 1)")
    return float(brentq(lambda loc: mean_turnout(loc, logit_sd) - mean, -60.0, 60.0, xtol=1e-12))


def draw_turnout(
    seed: int,
    purpose: int,
    size: int,
    *,
    mean: float | None,
    logit_sd: float,
    low: float,
    high: float,
) -> FloatArray:
    """
    Each resident's own turnout rate: the dial when `mean` is set, otherwise
    the legacy uniform rate on [low, high] (kept so development results stay
    reproducible).
    """
    rng = stream(seed, purpose)
    if mean is None:
        return np.asarray(rng.uniform(low, high, size=size), dtype=np.float64)
    z = rng.standard_normal(size)
    return np.asarray(expit(turnout_location(mean, logit_sd) + logit_sd * z), dtype=np.float64)


def attendance_draws(
    rng: np.random.Generator, people: int, count: int, cluster: int
) -> FloatArray:
    """
    The uniform attendance draw for each person and question. With `cluster`
    above 1, consecutive questions share one draw, as the measures of one
    ballot day do; 1 is a fresh draw per question (the same draws as before
    the option existed).
    """
    if cluster == 1:
        return np.asarray(rng.random((people, count)), dtype=np.float64)
    groups = -(-count // cluster)
    shared = rng.random((people, groups))
    return np.asarray(shared[:, np.arange(count) // cluster], dtype=np.float64)


def check_turnout(mean: float | None, logit_sd: float, low: float, high: float) -> None:
    if mean is not None and not 0.0 < mean < 1.0:
        raise ValueError("turnout_mean must be in (0, 1)")
    if not math.isfinite(logit_sd) or logit_sd < 0.0:
        raise ValueError("turnout_logit_sd must be a non-negative number")
    if not 0.0 <= low <= high <= 1.0:
        raise ValueError("turnout bounds must satisfy 0 <= min <= max <= 1")


@dataclass(frozen=True)
class PopulationConfig:
    """The parameters of one simulated city. Every one is an assumption."""

    seed: int = 20261114
    districts: int = 5
    residents_per_district: int = 100
    dimensions: int = 6
    # Weight of the shared left-right factor; dimensions correlate at its
    # square before district leans
    factor_loading: float = 0.6
    # Blocks of related issues (sweep declared 2026-11-18): dimensions are
    # split into `blocks` contiguous groups, and each group shares a block
    # factor with this weight. Dimensions in one block correlate at
    # factor_loading^2 + block_loading^2, across blocks at factor_loading^2,
    # before district leans. 0 (the default) is the one-axis model.
    blocks: int = 1
    block_loading: float = 0.0
    # Spread of each district's lean on each dimension, in units of the
    # population's spread
    district_lean_sd: float = 0.4
    history_questions_per_dimension: int = 20
    evaluation_questions_per_dimension: int = 20
    # Spread of question cutpoints; small values make close questions,
    # large values make lopsided ones
    cutpoint_sd: float = 0.7
    # Spread of the idiosyncratic part of a sincere vote
    preference_noise_sd: float = 0.3
    # Legacy uniform turnout bounds, used when turnout_mean is None
    min_turnout: float = 0.3
    max_turnout: float = 0.9
    # The turnout dial (amendment A6): the population's mean own rate, with
    # rates spread on the logit scale by turnout_logit_sd. None keeps the
    # legacy uniform rate, so existing structural cities are unchanged
    turnout_mean: float | None = None
    turnout_logit_sd: float = TURNOUT_LOGIT_SD
    # Questions per shared attendance draw: 1 gives every question its own
    # draw; 3 groups consecutive questions like a ballot day of about three
    # measures, the Swiss average (sensitivity, amendment A6)
    attendance_cluster: int = 1
    candidates_per_district: int = 3

    def __post_init__(self) -> None:
        for name in (
            "districts",
            "residents_per_district",
            "dimensions",
            "history_questions_per_dimension",
            "evaluation_questions_per_dimension",
            "candidates_per_district",
            "attendance_cluster",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.candidates_per_district > self.residents_per_district:
            raise ValueError("candidates_per_district exceeds residents_per_district")
        if not 0.0 <= self.factor_loading <= 1.0:
            raise ValueError("factor_loading must be in [0, 1]")
        if not 1 <= self.blocks <= self.dimensions:
            raise ValueError("blocks must be between 1 and the number of dimensions")
        if not 0.0 <= self.block_loading <= 1.0:
            raise ValueError("block_loading must be in [0, 1]")
        if self.factor_loading**2 + self.block_loading**2 > 1.0 + 1e-12:
            raise ValueError("factor_loading^2 + block_loading^2 must be at most 1")
        for name in ("district_lean_sd", "cutpoint_sd", "preference_noise_sd"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be a non-negative number")
        check_turnout(self.turnout_mean, self.turnout_logit_sd, self.min_turnout, self.max_turnout)

    @property
    def size(self) -> int:
        """How many people live in the city."""
        return self.districts * self.residents_per_district


@dataclass(frozen=True, eq=False)
class QuestionSet:
    """
    The questions of one period and everyone's votes on them.

    Arrays are indexed [person, question] in population and question order.
    """

    ids: tuple[QuestionId, ...]
    # The category each question belongs to, as an index into
    # Population.categories (an issue dimension in the structural model, a
    # topic in the fitted one)
    dimension: IntArray
    # Each person's sincere vote, YES or NO
    sincere: VoteArray
    # Whether each person casts their own ballot on the question
    casts: BoolArray
    # The uniform draw behind `casts` (casts = draw < turnout rate). Kept so
    # a higher turnout rate for the same person and question reuses the
    # same draw: raising a rate only ever adds ballots
    turnout_draw: FloatArray
    # Structural model: +1 when a higher position favours yes, -1 when it
    # favours no, and the cutpoint on the question's dimension
    direction: IntArray | None = None
    cutpoint: FloatArray | None = None
    # Fitted model: each question's loadings and intercept
    loadings: FloatArray | None = None
    intercepts: FloatArray | None = None

    def __len__(self) -> int:
        return len(self.ids)

    @property
    def own_votes(self) -> VoteArray:
        """The ballots people cast themselves: sincere, or NOT_CAST."""
        return np.where(self.casts, self.sincere, NOT_CAST).astype(np.int8)

    def on_dimension(self, dimension: int) -> IntArray:
        """The indices of the questions in one category, in order."""
        return np.flatnonzero(self.dimension == dimension).astype(np.int64)


class CityConfig(Protocol):
    """What the arrangements need from any population's configuration."""

    @property
    def seed(self) -> int: ...

    @property
    def districts(self) -> int: ...

    @property
    def candidates_per_district(self) -> int: ...


@dataclass(frozen=True, eq=False)
class Population:
    """One simulated city: people, districts, positions and both periods."""

    config: CityConfig
    # Person ids in index order; sorting them gives the same order
    ids: tuple[PersonId, ...]
    district: IntArray
    # Each person's position; election platforms are compared by distance
    # in this space
    positions: FloatArray
    turnout: FloatArray
    history: QuestionSet
    evaluation: QuestionSet
    # The delegation categories, indexed by QuestionSet.dimension
    categories: tuple[str, ...]
    # A name per district, indexed by `district`
    district_names: tuple[str, ...]
    _index: dict[PersonId, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_index", {person: i for i, person in enumerate(self.ids)}
        )

    @property
    def size(self) -> int:
        """How many people live in the city."""
        return len(self.ids)

    def index_of(self, person: PersonId) -> int:
        """The array index of a person."""
        return self._index[person]

    def residents_of(self, district: int) -> IntArray:
        """The indices of the residents of one district, in order."""
        return np.flatnonzero(self.district == district).astype(np.int64)


def stream(seed: int, purpose: int) -> np.random.Generator:
    """An independent random stream for one purpose."""
    return np.random.default_rng(np.random.SeedSequence([seed, purpose]))


def person_id(index: int) -> PersonId:
    """The id of the person at an index. Ids sort in index order."""
    return f"p{index:05d}"


def _positions(config: PopulationConfig, district: IntArray) -> FloatArray:
    rng = stream(config.seed, _POSITIONS)
    factor = rng.standard_normal(config.size)
    specific = rng.standard_normal((config.size, config.dimensions))
    loading = config.factor_loading
    block = config.block_loading
    unique = math.sqrt(max(0.0, 1.0 - loading**2 - block**2))
    positions = loading * factor[:, None] + unique * specific
    if block > 0.0:
        # A separate stream, so the one-axis model's draws are unchanged
        block_of = np.arange(config.dimensions) * config.blocks // config.dimensions
        shared = stream(config.seed, _BLOCKS).standard_normal((config.size, config.blocks))
        positions = positions + block * shared[:, block_of]
    leans = stream(config.seed, _LEANS).standard_normal(
        (config.districts, config.dimensions)
    )
    return np.asarray(positions + config.district_lean_sd * leans[district])


def _questions(
    config: PopulationConfig,
    positions: FloatArray,
    turnout: FloatArray,
    *,
    per_dimension: int,
    purpose: int,
    prefix: str,
) -> QuestionSet:
    rng = stream(config.seed, purpose)
    count = per_dimension * config.dimensions
    # Balanced across dimensions, in a seeded order
    dimension = rng.permutation(np.arange(count) % config.dimensions).astype(np.int64)
    direction = rng.choice(np.array([1, -1]), size=count).astype(np.int64)
    cutpoint = rng.normal(0.0, config.cutpoint_sd, size=count)
    noise = rng.normal(0.0, config.preference_noise_sd, size=(config.size, count))
    utility = direction * (positions[:, dimension] - cutpoint) + noise
    sincere = np.where(utility > 0.0, YES, NO).astype(np.int8)
    draw = attendance_draws(rng, config.size, count, config.attendance_cluster)
    casts = draw < turnout[:, None]
    return QuestionSet(
        ids=tuple(f"{prefix}{i:04d}" for i in range(count)),
        dimension=dimension,
        direction=direction,
        cutpoint=np.asarray(cutpoint, dtype=np.float64),
        sincere=sincere,
        casts=np.asarray(casts, dtype=np.bool_),
        turnout_draw=np.asarray(draw, dtype=np.float64),
    )


def simulate_population(config: PopulationConfig | None = None) -> Population:
    """
    Build one seeded city. The same config always gives identical arrays.
    """
    config = config or PopulationConfig()
    district = np.repeat(
        np.arange(config.districts, dtype=np.int64), config.residents_per_district
    )
    positions = _positions(config, district)
    turnout = draw_turnout(
        config.seed, _TURNOUT, config.size,
        mean=config.turnout_mean, logit_sd=config.turnout_logit_sd,
        low=config.min_turnout, high=config.max_turnout,
    )
    history = _questions(
        config,
        positions,
        turnout,
        per_dimension=config.history_questions_per_dimension,
        purpose=_HISTORY,
        prefix="h",
    )
    evaluation = _questions(
        config,
        positions,
        turnout,
        per_dimension=config.evaluation_questions_per_dimension,
        purpose=_EVALUATION,
        prefix="e",
    )
    return Population(
        config=config,
        ids=tuple(person_id(i) for i in range(config.size)),
        district=district,
        positions=positions,
        turnout=np.asarray(turnout, dtype=np.float64),
        history=history,
        evaluation=evaluation,
        categories=tuple(f"issue dimension {d + 1}" for d in range(config.dimensions)),
        district_names=tuple(f"district {d + 1}" for d in range(config.districts)),
    )


# Streams the arrangements draw from, exported so they stay distinct from the
# population's own.
CANDIDATE_STREAM: Final = _CANDIDATES
ELECTION_STREAM: Final = _ELECTION
