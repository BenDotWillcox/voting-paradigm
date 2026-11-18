"""Tests for cities drawn from a fitted belief model (delegation.comparison.beliefs)."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from delegation.comparison import ChoicePolicy, compare
from delegation.comparison.beliefs import (
    BELIEFS_PATH,
    BELIEFS_VERSION,
    BeliefCityConfig,
    load_beliefs,
    simulate_belief_city,
)


def _write_model(path, k=2, topics=("alpha", "beta", "gamma"), districts=12):
    rng = np.random.default_rng(0)
    raw = {
        "version": BELIEFS_VERSION,
        "dimensions": k,
        "source": {"sha256": "test"},
        "topics": {
            t: {
                "items": [],
                "mean": rng.normal(0, 0.6, k + 1).tolist(),
                "cov": (np.eye(k + 1) * 0.05).tolist(),
            }
            for t in topics
        },
        "population": {
            "national_mean": [0.0] * k,
            "within_cov": (np.eye(k) * 0.9).tolist(),
            "between_cov": (np.eye(k) * 0.1).tolist(),
            "districts": {
                f"{s}-{d}": {
                    "respondents": 40 + 10 * d,
                    "effective_respondents": 30.0,
                    "mean": rng.normal(0, 0.3, k).tolist(),
                    "cov": (np.eye(k) * 0.01).tolist(),
                }
                for s in (1, 2)
                for d in range(districts // 2)
            },
        },
    }
    path.write_text(json.dumps(raw))
    return path


@pytest.fixture()
def model(tmp_path):
    return load_beliefs(_write_model(tmp_path / "beliefs.json"))


SMALL = BeliefCityConfig(
    districts=3,
    residents_per_district=30,
    history_questions_per_topic=6,
    evaluation_questions_per_topic=4,
)


def test_load_rejects_other_versions(tmp_path):
    path = _write_model(tmp_path / "beliefs.json")
    raw = json.loads(path.read_text())
    raw["version"] = "other"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        load_beliefs(path)


def test_city_shape_and_determinism(model):
    a = simulate_belief_city(model, SMALL)
    b = simulate_belief_city(model, SMALL)
    assert a.size == 90
    assert a.categories == ("alpha", "beta", "gamma")
    assert len(a.history) == 18 and len(a.evaluation) == 12
    assert np.bincount(a.history.dimension).tolist() == [6, 6, 6]
    assert a.district_names == b.district_names
    assert np.array_equal(a.positions, b.positions)
    assert np.array_equal(a.evaluation.sincere, b.evaluation.sincere)


def test_only_districts_with_enough_respondents(model):
    city = simulate_belief_city(model, replace(SMALL, min_district_respondents=80))
    for name in city.district_names:
        assert model.district_respondents[name] >= 80
    with pytest.raises(ValueError):
        simulate_belief_city(model, replace(SMALL, min_district_respondents=10_000))


def test_zero_spread_repeats_the_topic_mean(model):
    city = simulate_belief_city(model, replace(SMALL, within_topic_spread=0.0))
    q = city.evaluation
    flipped = 0
    for t, name in enumerate(model.topics):
        rows = np.flatnonzero(q.dimension == t)
        mean = model.topic_means[name]
        for r in rows:
            # Each question is the topic mean, worded one way or the other
            params = np.append(q.loadings[r], q.intercepts[r])
            same, reflected = np.allclose(params, mean), np.allclose(params, -mean)
            assert same or reflected
            flipped += reflected
    # Both wording directions occur
    assert 0 < flipped < len(q)


def test_votes_follow_the_model(model):
    city = simulate_belief_city(model, replace(SMALL, residents_per_district=400))
    from scipy.special import ndtr

    q = city.evaluation
    # P(support) = Phi(a . theta + b), averaged over people and questions
    expected = ndtr(city.positions @ q.loadings.T + q.intercepts).mean()
    observed = (q.sincere == 1).mean()
    assert observed == pytest.approx(expected, abs=0.02)


def test_comparison_runs_on_a_fitted_city(model):
    result = compare(simulate_belief_city(model, SMALL)).measures
    assert result["full_turnout"].fidelity == 1.0
    assert 0.0 <= result["liquid"].overhead <= 1.0


@pytest.mark.skipif(not BELIEFS_PATH.exists(), reason="no committed fit yet")
def test_committed_fit_loads():
    model = load_beliefs()
    assert len(model.topics) == 8
    assert model.national_mean.shape == (model.dimensions,)
    city = simulate_belief_city(model)
    assert city.size == 500


def test_topic_counts():
    from delegation.comparison.beliefs import topic_counts

    assert topic_counts(12, 3, None).tolist() == [4, 4, 4]
    assert topic_counts(10, 3, (2.0, 1.0, 1.0)).tolist() == [5, 3, 2]
    assert topic_counts(10, 2, (0.0, 1.0)).tolist() == [0, 10]
    with pytest.raises(ValueError):
        topic_counts(10, 3, (1.0, 1.0))


def test_uneven_agenda_changes_evaluation_overhead(model):
    from delegation.comparison import compare, liquid_at_overhead

    even = simulate_belief_city(model, SMALL)
    skewed = simulate_belief_city(model, replace(SMALL, evaluation_topic_weights=(6.0, 1.0, 1.0)))
    assert np.bincount(skewed.evaluation.dimension).tolist() == [9, 2, 1]
    # The same history, so the same calibrated acceptance
    assert compare(even).liquid_acceptance == compare(skewed).liquid_acceptance
    # Evaluation overhead is each topic's self-resolution rate weighted by
    # the evaluation agenda, so it moves with the agenda
    outcome, _ = liquid_at_overhead(skewed)
    topic = skewed.evaluation.dimension
    rate = np.array([outcome.kept[:, topic == t].mean() for t in range(3)])
    weights = np.bincount(topic) / len(topic)
    assert outcome.kept.mean() == pytest.approx(float(rate @ weights))
