"""
Preference-model evaluation harness (demo 2, fixed-bank track).

Scores every (model, acquisition policy) combination against synthetic
personas with known latent utilities. Held-out pairs are excluded from
acquisition, so metrics measure generalization, not memorization.

Metrics per trial, tracked as curves over questions asked:
- Held-out pairwise log-likelihood (mean log p of the true direction).
- Held-out direction accuracy and Brier score.
- Kendall tau between the posterior-mean ranking and the true ranking.
Plus a final-state reliability table (calibration bins) and a
questions-to-convergence marker (first step where tau >= threshold).

Note on comparability: `predict_preference` means slightly different things
per model family — the Gaussian linear model reports P(u_a > u_b) under the
posterior; Bradley-Terry reports the posterior-predictive choice probability.
Both are "the model's probability that the user prefers a", which is what the
metrics need; the distinction is documented rather than hidden.

Reproducibility: a trial is identified by (model, policy, persona, seed) and
is byte-deterministic given that tuple. Aggregates report mean +/- std across
personas x seeds.
"""

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np
from scipy.stats import kendalltau

from preferences.acquisition import create_selector
from preferences.model import create_model
from preferences.questions.bank import QuestionBank
from preferences.types import ItemId, PreferenceState

from .personas import DEFAULT_PERSONAS, Persona
from .response_models import create_response_model

Pair = tuple[ItemId, ItemId]

_PROB_CLAMP = 1e-9


@dataclass(frozen=True)
class EvalConfig:
    """Configuration for one comparison run. Fully determines the results.

    `response_model` names how personas answer (see eval/response_models.py)
    — sweeping it turns the model comparison into a misspecification study.
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
    tie_epsilon: float = 1e-9  # holdout pairs with |true gap| below are skipped
    convergence_tau: float = 0.7
    n_calibration_bins: int = 10
    model_names: tuple[str, ...] = ("gaussian_linear", "bradley_terry")
    policy_names: tuple[str, ...] = (
        "fixed_sequence",
        "random",
        "max_variance",
    )


@dataclass
class MetricPoint:
    """Held-out metrics after `n_questions` answered."""

    n_questions: int
    log_likelihood: float
    accuracy: float
    brier: float
    kendall_tau: float


@dataclass
class CalibrationBin:
    lo: float
    hi: float
    n: int
    mean_predicted: float
    frac_correct: float


@dataclass
class TrialResult:
    """One (model, policy, persona, seed) elicitation run."""

    model_name: str
    policy_name: str
    persona_name: str
    seed: int
    curve: list[MetricPoint]
    calibration: list[CalibrationBin]
    questions_to_convergence: Optional[int]  # first step with tau >= threshold
    n_holdout_pairs: int
    asked_pairs: list[Pair] = field(default_factory=list)


@dataclass
class ComparisonSummary:
    """Aggregate over personas x seeds for one (model, policy) cell."""

    model_name: str
    policy_name: str
    n_trials: int
    final_log_likelihood_mean: float
    final_log_likelihood_std: float
    final_accuracy_mean: float
    final_brier_mean: float
    final_kendall_tau_mean: float
    final_kendall_tau_std: float
    convergence_rate: float  # fraction of trials that reached the tau threshold
    median_questions_to_convergence: Optional[float]
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


def _holdout_predictions(
    model,
    state: PreferenceState,
    persona: Persona,
    holdout: list[Pair],
    tie_epsilon: float,
) -> tuple[np.ndarray, np.ndarray]:
    """(predicted p, true label) arrays over decidable holdout pairs."""
    probs: list[float] = []
    labels: list[float] = []
    for a, b in holdout:
        gap = persona.true_gap(a, b)
        if abs(gap) < tie_epsilon:
            continue  # no ground-truth direction to score against
        probs.append(model.predict_preference(state, a, b))
        labels.append(1.0 if gap > 0 else 0.0)
    return np.asarray(probs), np.asarray(labels)


def compute_metrics(
    model,
    state: PreferenceState,
    persona: Persona,
    holdout: list[Pair],
    n_questions: int,
    tie_epsilon: float,
) -> MetricPoint:
    probs, labels = _holdout_predictions(
        model, state, persona, holdout, tie_epsilon
    )
    p = np.clip(probs, _PROB_CLAMP, 1.0 - _PROB_CLAMP)
    log_lik = float(
        np.mean(labels * np.log(p) + (1.0 - labels) * np.log(1.0 - p))
    )
    accuracy = float(np.mean((probs > 0.5) == (labels > 0.5)))
    brier = float(np.mean((probs - labels) ** 2))

    estimates = model.get_utility_estimates(state)
    item_ids = state.item_ids
    posterior_means = [estimates[i][0] for i in item_ids]
    true_utils = [persona.utilities[i] for i in item_ids]
    tau = kendalltau(posterior_means, true_utils).statistic
    tau = float(tau) if not math.isnan(tau) else 0.0

    return MetricPoint(
        n_questions=n_questions,
        log_likelihood=log_lik,
        accuracy=accuracy,
        brier=brier,
        kendall_tau=tau,
    )


def compute_calibration(
    model,
    state: PreferenceState,
    persona: Persona,
    holdout: list[Pair],
    tie_epsilon: float,
    n_bins: int,
) -> list[CalibrationBin]:
    """Reliability table: predicted probability vs empirical accuracy.

    Predictions are folded onto [0.5, 1] (confidence in the predicted
    direction) so every bin reads "when the model was X% sure, it was right
    Y% of the time".
    """
    probs, labels = _holdout_predictions(
        model, state, persona, holdout, tie_epsilon
    )
    if probs.size == 0:
        return []
    confidence = np.where(probs >= 0.5, probs, 1.0 - probs)
    correct = ((probs > 0.5) == (labels > 0.5)).astype(float)

    edges = np.linspace(0.5, 1.0, n_bins + 1)
    bins: list[CalibrationBin] = []
    for k in range(n_bins):
        lo, hi = float(edges[k]), float(edges[k + 1])
        mask = (
            (confidence >= lo) & (confidence < hi)
            if k < n_bins - 1
            else (confidence >= lo) & (confidence <= hi)
        )
        n = int(mask.sum())
        bins.append(
            CalibrationBin(
                lo=lo,
                hi=hi,
                n=n,
                mean_predicted=float(confidence[mask].mean()) if n else 0.0,
                frac_correct=float(correct[mask].mean()) if n else 0.0,
            )
        )
    return bins


# ---------------------------------------------------------------------------
# Trials
# ---------------------------------------------------------------------------


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
    questions_to_convergence: Optional[int] = None

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
        if (
            questions_to_convergence is None
            and point.kendall_tau >= config.convergence_tau
        ):
            questions_to_convergence = t

    calibration = compute_calibration(
        model,
        state,
        persona,
        holdout,
        config.tie_epsilon,
        config.n_calibration_bins,
    )
    return TrialResult(
        model_name=model_name,
        policy_name=policy_name,
        persona_name=persona.name,
        seed=seed,
        curve=curve,
        calibration=calibration,
        questions_to_convergence=questions_to_convergence,
        n_holdout_pairs=len(holdout),
        asked_pairs=asked_ordered,
    )


def summarize_trials(
    model_name: str,
    policy_name: str,
    trials: list[TrialResult],
) -> ComparisonSummary:
    finals = [t.curve[-1] for t in trials]
    lls = np.array([f.log_likelihood for f in finals])
    taus = np.array([f.kendall_tau for f in finals])
    conv = [
        t.questions_to_convergence
        for t in trials
        if t.questions_to_convergence is not None
    ]

    # Mean curve across trials (all trials share n_questions steps unless the
    # bank was exhausted early; truncate to the shortest).
    min_len = min(len(t.curve) for t in trials)
    mean_curve = [
        MetricPoint(
            n_questions=trials[0].curve[i].n_questions,
            log_likelihood=float(
                np.mean([t.curve[i].log_likelihood for t in trials])
            ),
            accuracy=float(np.mean([t.curve[i].accuracy for t in trials])),
            brier=float(np.mean([t.curve[i].brier for t in trials])),
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
        final_log_likelihood_mean=float(lls.mean()),
        final_log_likelihood_std=float(lls.std()),
        final_accuracy_mean=float(np.mean([f.accuracy for f in finals])),
        final_brier_mean=float(np.mean([f.brier for f in finals])),
        final_kendall_tau_mean=float(taus.mean()),
        final_kendall_tau_std=float(taus.std()),
        convergence_rate=len(conv) / len(trials),
        median_questions_to_convergence=(
            float(np.median(conv)) if conv else None
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
        "config": asdict(config),
        "personas": [p.name for p in personas],
        "summaries": [asdict(s) for s in summaries],
        "trials": [asdict(t) for t in trials_out],
    }
