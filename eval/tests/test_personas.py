"""Tests for the synthetic persona fixtures and generator."""

import numpy as np

from eval.personas import DEFAULT_PERSONAS, generate_personas
from preferences.questions.bank import QuestionBank


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


class TestGeneratePersonas:
    def test_deterministic_given_seed(self):
        p1 = generate_personas(10, seed=3)
        p2 = generate_personas(10, seed=3)
        assert [p.utilities for p in p1] == [p.utilities for p in p2]
        assert [p.name for p in p1] == [p.name for p in p2]

    def test_different_seeds_differ(self):
        p1 = generate_personas(5, seed=1)
        p2 = generate_personas(5, seed=2)
        assert [p.utilities for p in p1] != [p.utilities for p in p2]

    def test_covers_bank_and_stays_in_range(self):
        bank_ids = set(QuestionBank.load_default().item_ids())
        for persona in generate_personas(20, seed=0):
            assert set(persona.utilities.keys()) == bank_ids
            for u in persona.utilities.values():
                assert -1.0 <= u <= 1.0

    def test_mixture_recorded_in_description(self):
        persona = generate_personas(1, seed=0)[0]
        for arch in DEFAULT_PERSONAS:
            assert arch.name in persona.description

    def test_correlated_structure_preserved(self):
        """Archetype-level value correlations must survive generation:
        economic_freedom and property_rights agree in sign across every
        archetype, so generated personas should mostly agree too — unlike
        independent per-item sampling, which would agree ~50% of the time."""
        personas = generate_personas(100, seed=7)
        agree = sum(
            1
            for p in personas
            if p.utilities["economic_freedom"] * p.utilities["property_rights"]
            > 0
        )
        assert agree > 65

    def test_names_are_unique(self):
        personas = generate_personas(50, seed=4)
        assert len({p.name for p in personas}) == 50
