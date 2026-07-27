"""Tests for the persona response-model simulators."""

import numpy as np
import pytest

from eval.personas import DEFAULT_PERSONAS
from eval.response_models import (
    GaussianGapResponseModel,
    LogisticChoiceResponseModel,
    SloppyResponseModel,
    create_response_model,
)
from preferences.types import EvidenceSource

PERSONA = DEFAULT_PERSONAS[0]  # market_libertarian
# economic_freedom (0.9) vs economic_security (-0.5): true gap = 1.4
PAIR = ("economic_freedom", "economic_security")


class TestGaussianGap:
    def test_deterministic_given_seed(self):
        m = GaussianGapResponseModel()
        ev1 = m.respond(PERSONA, *PAIR, np.random.default_rng(3))
        ev2 = m.respond(PERSONA, *PAIR, np.random.default_rng(3))
        assert ev1.value == ev2.value

    def test_noiseless_tracks_true_gap(self):
        m = GaussianGapResponseModel(noise_std=0.0)
        ev = m.respond(PERSONA, *PAIR, np.random.default_rng(0))
        assert ev.value == pytest.approx(7.0)  # gap 1.4 * scale 5
        assert ev.source is EvidenceSource.PAIRWISE

    def test_value_in_slider_range(self):
        m = GaussianGapResponseModel(noise_std=2.0)
        rng = np.random.default_rng(0)
        for _ in range(200):
            ev = m.respond(PERSONA, *PAIR, rng)
            assert -10.0 <= ev.value <= 10.0


class TestLogisticChoice:
    def test_magnitude_is_constant(self):
        m = LogisticChoiceResponseModel(magnitude=5.0)
        rng = np.random.default_rng(0)
        values = {abs(m.respond(PERSONA, *PAIR, rng).value) for _ in range(50)}
        assert values == {5.0}

    def test_direction_frequency_matches_logistic(self):
        """Empirical choice rate should approximate sigmoid(gap / T)."""
        m = LogisticChoiceResponseModel(temperature=0.5)
        rng = np.random.default_rng(1)
        n = 2000
        chose_a = sum(
            1 for _ in range(n) if m.respond(PERSONA, *PAIR, rng).value > 0
        )
        expected = 1.0 / (1.0 + np.exp(-1.4 / 0.5))  # ~0.943
        assert chose_a / n == pytest.approx(expected, abs=0.02)

    def test_near_tie_is_coin_flip(self):
        # institutional_trust (-0.2) vs global_cooperation (-0.2): gap 0
        m = LogisticChoiceResponseModel(temperature=0.5)
        rng = np.random.default_rng(2)
        n = 2000
        chose_a = sum(
            1
            for _ in range(n)
            if m.respond(
                PERSONA, "institutional_trust", "global_cooperation", rng
            ).value
            > 0
        )
        assert chose_a / n == pytest.approx(0.5, abs=0.03)


class TestSloppy:
    def test_values_are_integer_ticks(self):
        m = SloppyResponseModel(lapse_rate=0.0)
        rng = np.random.default_rng(0)
        for _ in range(100):
            ev = m.respond(PERSONA, *PAIR, rng)
            assert ev.value == int(ev.value)
            assert -10.0 <= ev.value <= 10.0

    def test_lapse_rate_produces_wrong_directions(self):
        """With a huge true gap, wrong-direction answers only come from
        lapses — their rate should be roughly lapse_rate / 2."""
        m = SloppyResponseModel(lapse_rate=0.4, noise_std=0.0, gain=5.0)
        rng = np.random.default_rng(3)
        n = 2000
        wrong = sum(
            1 for _ in range(n) if m.respond(PERSONA, *PAIR, rng).value < 0
        )
        assert wrong / n == pytest.approx(0.2, abs=0.03)

    def test_compression_limits_moderate_gaps(self):
        """tanh compression: a moderate gap should not saturate the slider."""
        m = SloppyResponseModel(lapse_rate=0.0, noise_std=0.0, gain=1.5)
        # meritocracy (0.7) vs strict_accountability (0.3): gap 0.4
        ev = m.respond(
            PERSONA, "meritocracy", "strict_accountability",
            np.random.default_rng(0),
        )
        assert ev.value == pytest.approx(round(np.tanh(0.4 * 1.5) * 10))
        assert abs(ev.value) < 10


class TestRegistry:
    def test_create_by_name_with_params(self):
        m = create_response_model("gaussian_gap", noise_std=0.7)
        assert isinstance(m, GaussianGapResponseModel)
        assert m.noise_std == 0.7

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError, match="Unknown response model"):
            create_response_model("telepathy")
