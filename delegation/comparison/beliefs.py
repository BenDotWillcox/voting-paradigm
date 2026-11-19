"""
Simulated cities drawn from the belief model fitted to measured data.

The fit (scripts/fit_ces_beliefs.py) is a multidimensional probit item
response model of the CES 2024 Common Content: each person has a latent
position theta in K dimensions and supports a question when
a . theta + b + e > 0, e ~ N(0, 1). Its aggregates are committed in
delegation/data/beliefs_ces2024_v2.json. From them a city is drawn:

  - Districts. A seeded sample of real congressional districts. Each
    district's mean is drawn from its posterior in the hierarchical fit
    (theta_i ~ N(mu_district, W), mu_district ~ N(0, T)), and its residents
    from N(that mean, W). Drawing the mean, rather than using its posterior
    mean, keeps the spread between districts at the level the data
    supports; a point estimate shrunk toward the national mean understated
    it (version 1 of the fit reproduced only about 0.62 of the observed
    between-district spread of support rates). How much districts differ
    is therefore measured, not chosen.
  - Questions. Each question belongs to one of the eight topics. Its
    (a, b) is drawn from that topic's normal distribution, centred on the
    topic's measured items aligned to one wording direction, and then
    worded either way with equal chance, with the fitted covariance scaled by
    `within_topic_spread` squared. How different future questions in a
    topic are from today's is the largest assumption left; the spread
    multiplier is a robustness sweep (1 is the fit).
  - Sincere votes follow the model's own rule with a fresh idiosyncratic
    term per person and question. Turnout and the two periods work as in
    the structural model.

The structural one-factor model in `population` remains as a robustness
sweep over chosen correlation; this is the primary population for H1.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

from .population import (
    NO,
    TURNOUT_LOGIT_SD,
    YES,
    FloatArray,
    IntArray,
    Population,
    QuestionSet,
    check_turnout,
    draw_turnout,
    person_id,
    stream,
)

# Mean turnout per vote in Swiss federal ballots, the reference marker on the
# turnout dial (amendment A6): 43% to 49% in recent years, Geneva close to the
# national average (Goldberg and Sciarini 2021)
SWISS_TURNOUT: Final = 0.45

BELIEFS_PATH: Final = Path(__file__).resolve().parents[1] / "data" / "beliefs_ces2024_v2.json"
BELIEFS_VERSION: Final = "beliefs.ces2024.v2"

# Streams, distinct from the structural model's
_DISTRICTS: Final = 21
_RESIDENTS: Final = 22
_TURNOUT: Final = 23
_HISTORY: Final = 24
_EVALUATION: Final = 25
_DISTRICT_MEANS: Final = 26


@dataclass(frozen=True, eq=False)
class BeliefModel:
    """The aggregates of one fit."""

    dimensions: int
    topics: tuple[str, ...]
    # Per topic: the mean and covariance of (a, b), length K + 1
    topic_means: Mapping[str, FloatArray]
    topic_covs: Mapping[str, FloatArray]
    national_mean: FloatArray
    within_cov: FloatArray
    # Real district key -> posterior mean and covariance of its mean
    district_means: Mapping[str, FloatArray]
    district_covs: Mapping[str, FloatArray]
    district_respondents: Mapping[str, int]
    source_sha256: str


def load_beliefs(path: Path = BELIEFS_PATH) -> BeliefModel:
    """Read a fit's aggregates, checking its version."""
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != BELIEFS_VERSION:
        raise ValueError(f"{path} is not {BELIEFS_VERSION}")
    k = int(raw["dimensions"])
    topics = tuple(sorted(raw["topics"]))
    means = {t: np.asarray(raw["topics"][t]["mean"], dtype=np.float64) for t in topics}
    covs = {t: np.asarray(raw["topics"][t]["cov"], dtype=np.float64) for t in topics}
    for t in topics:
        if means[t].shape != (k + 1,) or covs[t].shape != (k + 1, k + 1):
            raise ValueError(f"topic {t!r} has the wrong shape for K = {k}")
    pop = raw["population"]
    districts = pop["districts"]
    return BeliefModel(
        dimensions=k,
        topics=topics,
        topic_means=means,
        topic_covs=covs,
        national_mean=np.asarray(pop["national_mean"], dtype=np.float64),
        within_cov=np.asarray(pop["within_cov"], dtype=np.float64),
        district_means={g: np.asarray(d["mean"], dtype=np.float64) for g, d in districts.items()},
        district_covs={g: np.asarray(d["cov"], dtype=np.float64) for g, d in districts.items()},
        district_respondents={g: int(d["respondents"]) for g, d in districts.items()},
        source_sha256=str(raw["source"]["sha256"]),
    )


@dataclass(frozen=True)
class BeliefCityConfig:
    """The parameters of one city drawn from the fitted model."""

    seed: int = 20261116
    districts: int = 5
    residents_per_district: int = 100
    # One Congress of contested substantive roll calls over the eight topics
    # (amendment A4): 428 in the 117th House, 720 in the 118th, so 54 to 90
    # per topic; the lower, rounded down
    history_questions_per_topic: int = 50
    evaluation_questions_per_topic: int = 20
    # Multiplier on the fitted within-topic spread of question parameters
    within_topic_spread: float = 1.0
    # Legacy uniform turnout bounds, used only when turnout_mean is None
    min_turnout: float = 0.3
    max_turnout: float = 0.9
    # The turnout dial (amendment A6): the population's mean own rate, spread
    # on the logit scale as fitted to Geneva's register. The study sweeps it;
    # the default is the Swiss reference marker
    turnout_mean: float | None = SWISS_TURNOUT
    turnout_logit_sd: float = TURNOUT_LOGIT_SD
    candidates_per_district: int = 3
    # Only districts with at least this many respondents are sampled
    min_district_respondents: int = 50
    # Topic mix of each period, as weights over the model's topics in their
    # sorted order; None is an even mix. The total number of questions is
    # questions-per-topic times the number of topics either way. An uneven
    # evaluation mix tests whether the overhead cap, set on history, holds
    # on a different agenda (with an even mix in both periods and exact
    # routing, evaluation overhead equals history overhead by construction)
    history_topic_weights: tuple[float, ...] | None = None
    evaluation_topic_weights: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        for name in (
            "districts",
            "residents_per_district",
            "history_questions_per_topic",
            "evaluation_questions_per_topic",
            "candidates_per_district",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.candidates_per_district > self.residents_per_district:
            raise ValueError("candidates_per_district exceeds residents_per_district")
        if not math.isfinite(self.within_topic_spread) or self.within_topic_spread < 0:
            raise ValueError("within_topic_spread must be a non-negative number")
        check_turnout(self.turnout_mean, self.turnout_logit_sd, self.min_turnout, self.max_turnout)
        for name in ("history_topic_weights", "evaluation_topic_weights"):
            weights = getattr(self, name)
            if weights is not None and (
                any(not math.isfinite(w) or w < 0 for w in weights) or sum(weights) <= 0
            ):
                raise ValueError(f"{name} must be non-negative with a positive sum")

    @property
    def size(self) -> int:
        return self.districts * self.residents_per_district


def topic_counts(total: int, topics: int, weights: tuple[float, ...] | None) -> IntArray:
    """
    How many of `total` questions each topic gets: equal shares, or shares
    proportional to `weights` by largest remainder, ties to the lower index.
    """
    if weights is None:
        weights = (1.0,) * topics
    if len(weights) != topics:
        raise ValueError(f"expected {topics} topic weights, got {len(weights)}")
    exact = np.asarray(weights, dtype=np.float64) / sum(weights) * total
    counts = np.floor(exact).astype(np.int64)
    remainder = exact - counts
    order = np.lexsort((np.arange(topics), -remainder))
    counts[order[: total - int(counts.sum())]] += 1
    return counts


def _questions(
    model: BeliefModel,
    config: BeliefCityConfig,
    positions: FloatArray,
    turnout: FloatArray,
    *,
    per_topic: int,
    weights: tuple[float, ...] | None,
    purpose: int,
    prefix: str,
) -> QuestionSet:
    rng = stream(config.seed, purpose)
    topics = len(model.topics)
    count = per_topic * topics
    counts = topic_counts(count, topics, weights)
    topic = rng.permutation(np.repeat(np.arange(topics), counts)).astype(np.int64)
    k = model.dimensions
    params = np.empty((count, k + 1))
    for t, name in enumerate(model.topics):
        rows = np.flatnonzero(topic == t)
        cov = model.topic_covs[name] * config.within_topic_spread**2
        params[rows] = rng.multivariate_normal(
            model.topic_means[name], cov, size=rows.size, method="eigh"
        )
    # Topic distributions are fitted to items aligned to one wording
    # direction; each new question is worded either way with equal chance,
    # which reflects (a, b) and only swaps which answer counts as support
    flip = np.where(rng.random(count) < 0.5, -1.0, 1.0)
    params *= flip[:, None]
    loadings, intercepts = params[:, :k], params[:, k]
    noise = rng.standard_normal((positions.shape[0], count))
    utility = positions @ loadings.T + intercepts + noise
    sincere = np.where(utility > 0.0, YES, NO).astype(np.int8)
    draw = rng.random(utility.shape)
    casts = draw < turnout[:, None]
    return QuestionSet(
        ids=tuple(f"{prefix}{i:04d}" for i in range(count)),
        dimension=topic,
        sincere=sincere,
        casts=np.asarray(casts, dtype=np.bool_),
        turnout_draw=np.asarray(draw, dtype=np.float64),
        loadings=np.asarray(loadings, dtype=np.float64),
        intercepts=np.asarray(intercepts, dtype=np.float64),
    )


def simulate_belief_city(
    model: BeliefModel, config: BeliefCityConfig | None = None
) -> Population:
    """Draw one seeded city. The same model and config give identical arrays."""
    config = config or BeliefCityConfig()
    eligible = sorted(
        g
        for g, n in model.district_respondents.items()
        if n >= config.min_district_respondents
    )
    if len(eligible) < config.districts:
        raise ValueError("not enough districts meet min_district_respondents")
    chosen = stream(config.seed, _DISTRICTS).choice(
        len(eligible), size=config.districts, replace=False
    )
    names = tuple(eligible[i] for i in sorted(chosen))
    district: IntArray = np.repeat(
        np.arange(config.districts, dtype=np.int64), config.residents_per_district
    )
    draw_means = stream(config.seed, _DISTRICT_MEANS)
    means = np.array(
        [
            draw_means.multivariate_normal(
                model.district_means[g], model.district_covs[g], method="eigh"
            )
            for g in names
        ]
    )
    rng = stream(config.seed, _RESIDENTS)
    chol = np.linalg.cholesky(model.within_cov)
    positions = means[district] + rng.standard_normal(
        (config.size, model.dimensions)
    ) @ chol.T
    turnout = draw_turnout(
        config.seed, _TURNOUT, config.size,
        mean=config.turnout_mean, logit_sd=config.turnout_logit_sd,
        low=config.min_turnout, high=config.max_turnout,
    )
    history = _questions(
        model, config, positions, turnout,
        per_topic=config.history_questions_per_topic,
        weights=config.history_topic_weights, purpose=_HISTORY, prefix="h",
    )
    evaluation = _questions(
        model, config, positions, turnout,
        per_topic=config.evaluation_questions_per_topic,
        weights=config.evaluation_topic_weights, purpose=_EVALUATION, prefix="e",
    )
    return Population(
        config=config,
        ids=tuple(person_id(i) for i in range(config.size)),
        district=district,
        positions=np.asarray(positions, dtype=np.float64),
        turnout=np.asarray(turnout, dtype=np.float64),
        history=history,
        evaluation=evaluation,
        categories=model.topics,
        district_names=names,
    )
