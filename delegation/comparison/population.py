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
    min_turnout: float = 0.3
    max_turnout: float = 0.9
    candidates_per_district: int = 3

    def __post_init__(self) -> None:
        for name in (
            "districts",
            "residents_per_district",
            "dimensions",
            "history_questions_per_dimension",
            "evaluation_questions_per_dimension",
            "candidates_per_district",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.candidates_per_district > self.residents_per_district:
            raise ValueError("candidates_per_district exceeds residents_per_district")
        if not 0.0 <= self.factor_loading <= 1.0:
            raise ValueError("factor_loading must be in [0, 1]")
        for name in ("district_lean_sd", "cutpoint_sd", "preference_noise_sd"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be a non-negative number")
        if not 0.0 <= self.min_turnout <= self.max_turnout <= 1.0:
            raise ValueError("turnout bounds must satisfy 0 <= min <= max <= 1")

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
    positions = loading * factor[:, None] + math.sqrt(1.0 - loading**2) * specific
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
    casts = rng.random((config.size, count)) < turnout[:, None]
    return QuestionSet(
        ids=tuple(f"{prefix}{i:04d}" for i in range(count)),
        dimension=dimension,
        direction=direction,
        cutpoint=np.asarray(cutpoint, dtype=np.float64),
        sincere=sincere,
        casts=np.asarray(casts, dtype=np.bool_),
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
    turnout = stream(config.seed, _TURNOUT).uniform(
        config.min_turnout, config.max_turnout, size=config.size
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
