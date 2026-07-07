"""Tests for the synthetic persona fixtures."""

import numpy as np

from eval.personas import DEFAULT_PERSONAS, simulate_response
from preferences.questions.bank import QuestionBank
from preferences.types import EvidenceSource


class TestProfiles:
    def test_personas_cover_the_full_bank(self):
        bank_ids = set(QuestionBank.load_default().item_ids())
        for persona in DEFAULT_PERSONAS:
            assert set(persona.utilities.keys()) == bank_ids, persona.name

    def test_utilities_in_range(self):
        for persona in DEFAULT_PERSONAS:
            for item, u in persona.utilities.items():
                assert -1.0 <= u <= 1.0, f"{persona.name}:{item}"

    def test_personas_are_distinct(self):
        names = {p.name for p in DEFAULT_PERSONAS}
        assert len(names) == len(DEFAULT_PERSONAS)
        # Profiles should meaningfully disagree somewhere.
        lib = DEFAULT_PERSONAS[0].utilities
        soc = DEFAULT_PERSONAS[1].utilities
        disagreements = sum(
            1 for k in lib if (lib[k] > 0) != (soc[k] > 0)
        )
        assert disagreements > 5

    def test_true_ranking_is_stable(self):
        persona = DEFAULT_PERSONAS[0]
        ids = list(persona.utilities.keys())
        assert persona.true_ranking(ids) == persona.true_ranking(ids)


class TestSimulateResponse:
    def test_deterministic_given_seed(self):
        persona = DEFAULT_PERSONAS[0]
        ev1 = simulate_response(
            persona,
            "economic_freedom",
            "economic_security",
            np.random.default_rng(3),
        )
        ev2 = simulate_response(
            persona,
            "economic_freedom",
            "economic_security",
            np.random.default_rng(3),
        )
        assert ev1.value == ev2.value

    def test_value_in_slider_range(self):
        persona = DEFAULT_PERSONAS[0]
        rng = np.random.default_rng(0)
        for _ in range(200):
            ev = simulate_response(
                persona, "economic_freedom", "economic_security", rng,
                noise_std=1.0,
            )
            assert -10.0 <= ev.value <= 10.0

    def test_noiseless_response_tracks_true_gap(self):
        persona = DEFAULT_PERSONAS[0]  # market_libertarian
        ev = simulate_response(
            persona,
            "economic_freedom",   # 0.9
            "economic_security",  # -0.5
            np.random.default_rng(0),
            noise_std=0.0,
        )
        # gap 1.4 * scale 5 = 7.0
        assert ev.value == 7.0
        assert ev.source is EvidenceSource.PAIRWISE
