"""
Preference-model evaluation harness (demo 2, fixed-bank track).

Scores every (model, acquisition policy) combination against synthetic
personas with known latent utilities. Held-out pairs are excluded from
acquisition, so metrics measure withheld-pair interpolation within the fixed
item universe rather than recall of asked pairs.

Metrics per trial, tracked as curves over questions asked:
- Held-out latent-direction log score (mean log probability assigned to the
  sign of the persona's true utility gap).
- Held-out latent-direction accuracy and one-coordinate binary Brier score.
- Kendall tau-b between the posterior-mean ranking and the true ranking; an
  all-tied posterior ranking is assigned 0.0 as a no-rank-information
  convention.
Plus a final-state latent-direction reliability table and the first question
count where tau reaches a configured threshold. The log score applies a
1e-9 probability floor to keep a confidently wrong event finite. Threshold
attainment is not a claim of sustained convergence.

For probability-score comparability, the evaluator derives the tie-split
latent-direction probability P(u_a > u_b) + 0.5 P(u_a = u_b) from the Gaussian
posterior stored by either model. This is exact for the Gaussian model and uses
Bradley-Terry's Laplace-Gaussian posterior approximation. It does not compare
the Gaussian model's latent-order probability with
Bradley-Terry's distinct posterior-predictive choice probability. This
evaluation-only readout does not change either model's production
`predict_preference` behavior.

Reproducibility: a trial is identified by the full EvalConfig plus its model,
policy, persona, and seed, and is byte-deterministic given those inputs.
Aggregates report mean +/- std across personas x seeds.
"""

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np
from scipy.stats import kendalltau, norm

from preferences.acquisition import create_selector
from preferences.model import create_model
from preferences.model.common import posterior_diff_stats
from preferences.questions.bank import QuestionBank
from preferences.types import ItemId, PreferenceState

from .personas import DEFAULT_PERSONAS, Persona
from .response_models import create_response_model

Pair = tuple[ItemId, ItemId]

_PROB_CLAMP = 1e-9
_NO_SCORABLE_HOLDOUT = "holdout has no scorable latent preference directions"
SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION = "preference_eval_synthetic_result.v1"


@dataclass(frozen=True)
class EvalConfig:
    """Configuration for one comparison run. Fully determines the results.

    `response_model` names how personas answer (see eval/response_models.py)
    — sweeping it tests sensitivity to distinct synthetic response processes.
    `model_params` overrides preference-model hyperparameters (applied to
    every model in `model_names`) for sensitivity sweeps.
    """

    n_questions: int = 25
    holdout_fraction: float = 0.2
    n_seeds: int = 5
    base_seed: int = 42
    response_model: str = "gaussian_gap"
    response_model_params: dict = field(default_factory=dict)
    model_params: dict = field(default_factory=dict)
    tie_epsilon: float = 1e-9  # |true gap| at/below this is not scored
    tau_threshold: float = 0.7
    n_reliability_bins: int = 10
    model_names: tuple[str, ...] = ("gaussian_linear", "bradley_terry")
    policy_names: tuple[str, ...] = (
        "fixed_sequence",
        "random",
        "max_variance",
    )

    def __post_init__(self) -> None:
        if not 0.0 < self.tau_threshold <= 1.0:
            raise ValueError("tau_threshold must be in (0, 1]")


@dataclass
class MetricPoint:
    """Latent-preference recovery after `n_questions` answered."""

    n_questions: int
    latent_direction_log_score: float
    latent_direction_accuracy: float
    latent_direction_brier: float
    kendall_tau: float


@dataclass
class LatentDirectionReliabilityBin:
    """Reliability bin for confidence in the predicted latent direction."""

    lo: float
    hi: float
    n: int
    mean_confidence: float
    latent_direction_accuracy: float


@dataclass
class TrialResult:
    """One elicitation run within the enclosing result's full EvalConfig."""

    model_name: str
    policy_name: str
    persona_name: str
    seed: int
    curve: list[MetricPoint]
    latent_direction_reliability: list[LatentDirectionReliabilityBin]
    first_tau_threshold_question: Optional[int]
    n_holdout_pairs: int
    n_scored_holdout_pairs: int
    asked_pairs: list[Pair] = field(default_factory=list)


@dataclass
class ComparisonSummary:
    """Aggregate over personas x seeds for one (model, policy) cell."""

    model_name: str
    policy_name: str
    n_trials: int
    final_latent_direction_log_score_mean: float
    final_latent_direction_log_score_std: float
    final_latent_direction_accuracy_mean: float
    final_latent_direction_brier_mean: float
    final_kendall_tau_mean: float
    final_kendall_tau_std: float
    tau_threshold_attainment_rate: float  # fraction of trials reaching threshold
    # Median among threshold-attaining trials; None when no trial attains it.
    median_first_tau_threshold_question: Optional[float]
    mean_curve: list[MetricPoint] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Splits and metrics
# ---------------------------------------------------------------------------


def all_pairs(item_ids: list[ItemId]) -> list[Pair]:
    """All unordered pairs in canonical (sorted) order."""
    ids = sorted(item_ids)
    return [
        (ids[i], ids[j])
        for i in range(len(ids))
        for j in range(i + 1, len(ids))
    ]


def holdout_split(
    item_ids: list[ItemId],
    holdout_fraction: float,
    seed: int,
) -> tuple[list[Pair], list[Pair]]:
    """Seeded (train_pairs, holdout_pairs) split over all unordered pairs."""
    pairs = all_pairs(item_ids)
    rng = random.Random(seed)
    rng.shuffle(pairs)
    n_holdout = max(1, int(round(len(pairs) * holdout_fraction)))
    return pairs[n_holdout:], pairs[:n_holdout]


def _scored_holdout_pairs(
    persona: Persona,
    holdout: list[Pair],
    tie_epsilon: float,
) -> list[Pair]:
    """Return pairs whose latent gap exceeds the configured tie tolerance."""
    return [
        (a, b)
        for a, b in holdout
        if abs(persona.true_gap(a, b)) > tie_epsilon
    ]


def _latent_direction_probability(
    state: PreferenceState,
    item_a: ItemId,
    item_b: ItemId,
) -> float:
    """Return tie-split P(u_a ranks above u_b) under a Gaussian posterior."""
    mean_diff, std_diff = posterior_diff_stats(state, item_a, item_b)
    if std_diff == 0.0:
        if mean_diff > 0.0:
            return 1.0
        if mean_diff < 0.0:
            return 0.0
        return 0.5
    return float(norm.cdf(mean_diff / std_diff))


def _holdout_predictions(
    state: PreferenceState,
    persona: Persona,
    holdout: list[Pair],
    tie_epsilon: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Posterior latent-direction probabilities and true binary labels."""
    probs: list[float] = []
    labels: list[float] = []
    for a, b in _scored_holdout_pairs(persona, holdout, tie_epsilon):
        gap = persona.true_gap(a, b)
        probs.append(_latent_direction_probability(state, a, b))
        labels.append(1.0 if gap > 0 else 0.0)
    return np.asarray(probs), np.asarray(labels)


def _latent_direction_accuracy_credit(
    probs: np.ndarray,
    labels: np.ndarray,
) -> np.ndarray:
    """Award half credit when a posterior assigns exactly equal probability."""
    credit = ((probs > 0.5) == (labels > 0.5)).astype(float)
    credit[probs == 0.5] = 0.5
    return credit


def compute_metrics(
    model,
    state: PreferenceState,
    persona: Persona,
    holdout: list[Pair],
    n_questions: int,
    tie_epsilon: float,
) -> MetricPoint:
    probs, labels = _holdout_predictions(state, persona, holdout, tie_epsilon)
    if probs.size == 0:
        raise ValueError(_NO_SCORABLE_HOLDOUT)
    p = np.clip(probs, _PROB_CLAMP, 1.0 - _PROB_CLAMP)
    log_score = float(
        np.mean(labels * np.log(p) + (1.0 - labels) * np.log(1.0 - p))
    )
    accuracy = float(np.mean(_latent_direction_accuracy_credit(probs, labels)))
    brier = float(np.mean((probs - labels) ** 2))

    estimates = model.get_utility_estimates(state)
    item_ids = state.item_ids
    posterior_means = [estimates[i][0] for i in item_ids]
    true_utils = [persona.utilities[i] for i in item_ids]
    tau = kendalltau(posterior_means, true_utils, variant="b").statistic
    tau = float(tau) if not math.isnan(tau) else 0.0

    return MetricPoint(
        n_questions=n_questions,
        latent_direction_log_score=log_score,
        latent_direction_accuracy=accuracy,
        latent_direction_brier=brier,
        kendall_tau=tau,
    )


def compute_latent_direction_reliability(
    state: PreferenceState,
    persona: Persona,
    holdout: list[Pair],
    tie_epsilon: float,
    n_bins: int,
) -> list[LatentDirectionReliabilityBin]:
    """Reliability against the persona's fixed latent preference direction.

    Predictions are folded onto [0.5, 1] (confidence in the predicted
    direction) so every bin reads "when the model was X% sure, it was right
    Y% of the time against the latent ordering." The binary targets are not
    independently sampled held-out responses.
    """
    probs, labels = _holdout_predictions(state, persona, holdout, tie_epsilon)
    if probs.size == 0:
        raise ValueError(_NO_SCORABLE_HOLDOUT)
    confidence = np.where(probs >= 0.5, probs, 1.0 - probs)
    correct = _latent_direction_accuracy_credit(probs, labels)

    edges = np.linspace(0.5, 1.0, n_bins + 1)
    bins: list[LatentDirectionReliabilityBin] = []
    for k in range(n_bins):
        lo, hi = float(edges[k]), float(edges[k + 1])
        mask = (
            (confidence >= lo) & (confidence < hi)
            if k < n_bins - 1
            else (confidence >= lo) & (confidence <= hi)
        )
        n = int(mask.sum())
        bins.append(
            LatentDirectionReliabilityBin(
                lo=lo,
                hi=hi,
                n=n,
                mean_confidence=float(confidence[mask].mean()) if n else 0.0,
                latent_direction_accuracy=(
                    float(correct[mask].mean()) if n else 0.0
                ),
            )
        )
    return bins


# ---------------------------------------------------------------------------
# Trials
# ---------------------------------------------------------------------------


def _first_tau_threshold_question(
    curve: list[MetricPoint],
    tau_threshold: float,
) -> Optional[int]:
    """Return the first recorded question count meeting the tau threshold."""
    return next(
        (
            point.n_questions
            for point in curve
            if point.kendall_tau >= tau_threshold
        ),
        None,
    )


def run_trial(
    model_name: str,
    policy_name: str,
    persona: Persona,
    config: EvalConfig,
    seed: int,
    bank: Optional[QuestionBank] = None,
) -> TrialResult:
    """One deterministic elicitation run against a persona."""
    bank = bank or QuestionBank.load_default()
    model = create_model(model_name, **config.model_params)
    selector = create_selector(policy_name)
    responder = create_response_model(
        config.response_model, **config.response_model_params
    )
    selector_rng = random.Random(seed)
    response_rng = np.random.default_rng(seed)

    _, holdout = holdout_split(
        bank.item_ids(), config.holdout_fraction, seed
    )
    holdout_keys = {frozenset(p) for p in holdout}

    state = model.initialize(
        user_id="eval_persona",
        session_id=f"eval_{model_name}_{policy_name}_{persona.name}_{seed}",
        item_ids=bank.item_ids(),
    )

    curve = [
        compute_metrics(
            model, state, persona, holdout, 0, config.tie_epsilon
        )
    ]
    asked: set[frozenset[ItemId]] = set()
    asked_ordered: list[Pair] = []
    for t in range(1, config.n_questions + 1):
        pair = selector.select_pair(
            state=state,
            model=model,
            bank=bank,
            exclude_pairs=asked | holdout_keys,
            rng=selector_rng,
        )
        if pair is None:
            break  # train pairs exhausted
        a, b = pair
        asked.add(frozenset(pair))
        asked_ordered.append(pair)

        evidence = responder.respond(persona, a, b, response_rng)
        evidence.prompt_id = f"eval_q{t}_{a}_vs_{b}"
        state = model.update(state, evidence)

        point = compute_metrics(
            model, state, persona, holdout, t, config.tie_epsilon
        )
        curve.append(point)
    first_tau_threshold_question = _first_tau_threshold_question(
        curve,
        config.tau_threshold,
    )

    latent_direction_reliability = compute_latent_direction_reliability(
        state,
        persona,
        holdout,
        config.tie_epsilon,
        config.n_reliability_bins,
    )
    return TrialResult(
        model_name=model_name,
        policy_name=policy_name,
        persona_name=persona.name,
        seed=seed,
        curve=curve,
        latent_direction_reliability=latent_direction_reliability,
        first_tau_threshold_question=first_tau_threshold_question,
        n_holdout_pairs=len(holdout),
        n_scored_holdout_pairs=len(
            _scored_holdout_pairs(persona, holdout, config.tie_epsilon)
        ),
        asked_pairs=asked_ordered,
    )


def summarize_trials(
    model_name: str,
    policy_name: str,
    trials: list[TrialResult],
) -> ComparisonSummary:
    finals = [t.curve[-1] for t in trials]
    log_scores = np.array([f.latent_direction_log_score for f in finals])
    taus = np.array([f.kendall_tau for f in finals])
    threshold_questions = [
        t.first_tau_threshold_question
        for t in trials
        if t.first_tau_threshold_question is not None
    ]

    # Mean curve across trials (all trials share n_questions steps unless the
    # bank was exhausted early; truncate to the shortest).
    min_len = min(len(t.curve) for t in trials)
    mean_curve = [
        MetricPoint(
            n_questions=trials[0].curve[i].n_questions,
            latent_direction_log_score=float(
                np.mean(
                    [t.curve[i].latent_direction_log_score for t in trials]
                )
            ),
            latent_direction_accuracy=float(
                np.mean(
                    [t.curve[i].latent_direction_accuracy for t in trials]
                )
            ),
            latent_direction_brier=float(
                np.mean(
                    [t.curve[i].latent_direction_brier for t in trials]
                )
            ),
            kendall_tau=float(
                np.mean([t.curve[i].kendall_tau for t in trials])
            ),
        )
        for i in range(min_len)
    ]

    return ComparisonSummary(
        model_name=model_name,
        policy_name=policy_name,
        n_trials=len(trials),
        final_latent_direction_log_score_mean=float(log_scores.mean()),
        final_latent_direction_log_score_std=float(log_scores.std()),
        final_latent_direction_accuracy_mean=float(
            np.mean([f.latent_direction_accuracy for f in finals])
        ),
        final_latent_direction_brier_mean=float(
            np.mean([f.latent_direction_brier for f in finals])
        ),
        final_kendall_tau_mean=float(taus.mean()),
        final_kendall_tau_std=float(taus.std()),
        tau_threshold_attainment_rate=len(threshold_questions) / len(trials),
        median_first_tau_threshold_question=(
            float(np.median(threshold_questions))
            if threshold_questions
            else None
        ),
        mean_curve=mean_curve,
    )


def run_comparison(
    config: EvalConfig,
    personas: tuple[Persona, ...] = DEFAULT_PERSONAS,
) -> dict:
    """Full models x policies comparison. Returns a JSON-serializable dict."""
    bank = QuestionBank.load_default()
    summaries: list[ComparisonSummary] = []
    trials_out: list[TrialResult] = []

    for model_name in config.model_names:
        for policy_name in config.policy_names:
            cell_trials: list[TrialResult] = []
            for persona in personas:
                for s in range(config.n_seeds):
                    seed = config.base_seed + s
                    cell_trials.append(
                        run_trial(
                            model_name,
                            policy_name,
                            persona,
                            config,
                            seed,
                            bank=bank,
                        )
                    )
            summaries.append(
                summarize_trials(model_name, policy_name, cell_trials)
            )
            trials_out.extend(cell_trials)

    return {
        "schema_version": SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION,
        "config": asdict(config),
        "personas": [p.name for p in personas],
        "summaries": [asdict(s) for s in summaries],
        "trials": [asdict(t) for t in trials_out],
    }
