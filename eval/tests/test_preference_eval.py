"""Tests for the preference-model eval harness."""

from dataclasses import asdict

from eval.personas import DEFAULT_PERSONAS
from eval.preference_eval import (
    EvalConfig,
    holdout_split,
    run_comparison,
    run_trial,
)
from preferences.questions.bank import QuestionBank

TINY = EvalConfig(n_questions=4, n_seeds=1, base_seed=11)


class TestHoldoutSplit:
    def test_split_is_disjoint_and_covering(self):
        ids = QuestionBank.load_default().item_ids()
        train, holdout = holdout_split(ids, 0.2, seed=1)
        n = len(ids)
        assert len(train) + len(holdout) == n * (n - 1) // 2
        assert not (set(train) & set(holdout))

    def test_split_is_seeded(self):
        ids = QuestionBank.load_default().item_ids()
        assert holdout_split(ids, 0.2, 5) == holdout_split(ids, 0.2, 5)
        assert holdout_split(ids, 0.2, 5) != holdout_split(ids, 0.2, 6)


class TestRunTrial:
    def test_deterministic(self):
        persona = DEFAULT_PERSONAS[0]
        t1 = run_trial("gaussian_linear", "max_variance", persona, TINY, 11)
        t2 = run_trial("gaussian_linear", "max_variance", persona, TINY, 11)
        assert asdict(t1) == asdict(t2)

    def test_holdout_pairs_never_asked(self):
        persona = DEFAULT_PERSONAS[1]
        bank = QuestionBank.load_default()
        _, holdout = holdout_split(
            bank.item_ids(), TINY.holdout_fraction, seed=11
        )
        holdout_keys = {frozenset(p) for p in holdout}
        trial = run_trial("gaussian_linear", "random", persona, TINY, 11)
        assert len(trial.curve) == TINY.n_questions + 1  # +1 for prior point
        asked_keys = {frozenset(p) for p in trial.asked_pairs}
        assert len(asked_keys) == TINY.n_questions  # no repeats
        assert not (asked_keys & holdout_keys)

    def test_learning_improves_over_prior(self):
        """After a few questions, held-out metrics beat the prior point."""
        persona = DEFAULT_PERSONAS[0]
        config = EvalConfig(n_questions=15, n_seeds=1, base_seed=7)
        trial = run_trial(
            "gaussian_linear", "max_variance", persona, config, 7
        )
        first, last = trial.curve[0], trial.curve[-1]
        assert last.log_likelihood > first.log_likelihood
        assert last.kendall_tau > first.kendall_tau
        assert last.accuracy >= first.accuracy

    def test_bradley_terry_also_learns(self):
        persona = DEFAULT_PERSONAS[2]
        config = EvalConfig(n_questions=15, n_seeds=1, base_seed=7)
        trial = run_trial("bradley_terry", "max_variance", persona, config, 7)
        assert trial.curve[-1].kendall_tau > trial.curve[0].kendall_tau


class TestRunComparison:
    def test_smoke_all_cells(self):
        results = run_comparison(TINY, personas=DEFAULT_PERSONAS[:1])
        # 2 models x 3 policies
        assert len(results["summaries"]) == 6
        cells = {
            (s["model_name"], s["policy_name"]) for s in results["summaries"]
        }
        assert cells == {
            ("gaussian_linear", "fixed_sequence"),
            ("gaussian_linear", "random"),
            ("gaussian_linear", "max_variance"),
            ("bradley_terry", "fixed_sequence"),
            ("bradley_terry", "random"),
            ("bradley_terry", "max_variance"),
        }
        for s in results["summaries"]:
            assert s["n_trials"] == 1
            assert len(s["mean_curve"]) == TINY.n_questions + 1

    def test_results_json_serializable(self):
        import json

        results = run_comparison(TINY, personas=DEFAULT_PERSONAS[:1])
        json.dumps(results)  # must not raise
