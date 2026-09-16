"""Tests for the preference-model eval harness."""

import json
import math
import sys
from dataclasses import asdict, replace

import pytest

from eval.personas import DEFAULT_PERSONAS, Persona
from eval.preference_eval import (
    SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION,
    EvalConfig,
    MetricPoint,
    _first_tau_threshold_question,
    _latent_direction_probability,
    compute_latent_direction_reliability,
    compute_metrics,
    holdout_split,
    run_comparison,
    run_trial,
)
from eval import run_preference_eval as preference_eval_cli
from eval.run_preference_eval import _format_table
from preferences.model import create_model
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
        assert (
            last.latent_direction_log_score
            > first.latent_direction_log_score
        )
        assert last.kendall_tau > first.kendall_tau
        assert (
            last.latent_direction_accuracy
            >= first.latent_direction_accuracy
        )

    def test_bradley_terry_also_learns(self):
        persona = DEFAULT_PERSONAS[2]
        config = EvalConfig(n_questions=15, n_seeds=1, base_seed=7)
        trial = run_trial("bradley_terry", "max_variance", persona, config, 7)
        assert trial.curve[-1].kendall_tau > trial.curve[0].kendall_tau

    def test_reports_the_effective_scored_holdout_denominator(self):
        persona = DEFAULT_PERSONAS[0]
        bank = QuestionBank.load_default()
        _, holdout = holdout_split(
            bank.item_ids(), TINY.holdout_fraction, seed=11
        )
        trial = run_trial("gaussian_linear", "random", persona, TINY, 11)

        expected_scored = sum(
            abs(persona.true_gap(a, b)) > TINY.tie_epsilon
            for a, b in holdout
        )
        assert trial.n_holdout_pairs == len(holdout) == 126
        assert trial.n_scored_holdout_pairs == expected_scored == 120
        assert (
            sum(item.n for item in trial.latent_direction_reliability)
            == expected_scored
        )

    def test_prior_probability_ties_receive_fractional_accuracy(self):
        config = EvalConfig(n_questions=0, n_seeds=1, base_seed=11)
        persona = DEFAULT_PERSONAS[0]

        for model_name in config.model_names:
            trial = run_trial(
                model_name, "fixed_sequence", persona, config, seed=11
            )
            prior = trial.curve[0]
            assert prior.latent_direction_log_score == pytest.approx(
                math.log(0.5)
            )
            assert prior.latent_direction_accuracy == 0.5
            assert prior.latent_direction_brier == 0.25
            nonempty_bins = [
                item
                for item in trial.latent_direction_reliability
                if item.n
            ]
            assert len(nonempty_bins) == 1
            assert nonempty_bins[0].n == trial.n_scored_holdout_pairs
            assert nonempty_bins[0].mean_confidence == 0.5
            assert nonempty_bins[0].latent_direction_accuracy == 0.5

    def test_probability_scores_do_not_use_family_specific_readout(self):
        persona = DEFAULT_PERSONAS[0]
        bank = QuestionBank.load_default()
        _, holdout = holdout_split(bank.item_ids(), 0.2, seed=11)
        model = create_model("bradley_terry")
        state = model.initialize(
            user_id="eval_persona",
            session_id="common_latent_readout",
            item_ids=bank.item_ids(),
        )

        def reject_family_specific_readout(*_args, **_kwargs):
            raise AssertionError("family-specific readout must not be used")

        model.predict_preference = reject_family_specific_readout
        point = compute_metrics(
            model,
            state,
            persona,
            holdout,
            n_questions=0,
            tie_epsilon=1e-9,
        )
        assert point.latent_direction_log_score < 0.0

    def test_common_readout_uses_posterior_gap_probability(self):
        model = create_model("bradley_terry")
        initialized = model.initialize(
            user_id="eval_persona",
            session_id="known_posterior",
            item_ids=["a", "b"],
        )
        state = replace(
            initialized,
            mu=[1.0, 0.0],
            sigma_flat=[1.0, 0.0, 1.0],
        )
        degenerate_tie = replace(
            initialized,
            mu=[0.0, 0.0],
            sigma_flat=[0.0, 0.0, 0.0],
        )
        assert _latent_direction_probability(state, "a", "b") == (
            pytest.approx(0.7602499389)
        )
        assert _latent_direction_probability(
            degenerate_tie,
            "a",
            "b",
        ) == 0.5

    def test_tau_threshold_attainment_includes_the_prior(self):
        curve = [
            MetricPoint(
                n_questions=0,
                latent_direction_log_score=math.log(0.5),
                latent_direction_accuracy=0.5,
                latent_direction_brier=0.25,
                kendall_tau=0.8,
            )
        ]
        assert _first_tau_threshold_question(curve, 0.7) == 0

    @pytest.mark.parametrize("tau_threshold", [0.0, -0.1, 1.1, math.nan])
    def test_rejects_invalid_tau_thresholds(self, tau_threshold):
        with pytest.raises(
            ValueError,
            match=r"tau_threshold must be in \(0, 1\]",
        ):
            EvalConfig(tau_threshold=tau_threshold)

    def test_rejects_a_holdout_with_no_scorable_latent_directions(self):
        bank = QuestionBank.load_default()
        persona = Persona(
            name="all_ties",
            description="Every latent utility is equal.",
            utilities={item_id: 0.0 for item_id in bank.item_ids()},
        )
        with pytest.raises(
            ValueError,
            match="holdout has no scorable latent preference directions",
        ):
            run_trial("gaussian_linear", "random", persona, TINY, seed=11)

    def test_exact_latent_ties_stay_unscored_at_zero_tolerance(self):
        bank = QuestionBank.load_default()
        persona = Persona(
            name="all_ties",
            description="Every latent utility is equal.",
            utilities={item_id: 0.0 for item_id in bank.item_ids()},
        )
        config = EvalConfig(
            n_questions=0,
            n_seeds=1,
            base_seed=11,
            tie_epsilon=0.0,
        )
        with pytest.raises(
            ValueError,
            match="holdout has no scorable latent preference directions",
        ):
            run_trial(
                "gaussian_linear",
                "fixed_sequence",
                persona,
                config,
                seed=11,
            )

    def test_reliability_rejects_a_holdout_without_scorable_directions(self):
        bank = QuestionBank.load_default()
        model = create_model("gaussian_linear")
        state = model.initialize(
            user_id="eval_persona",
            session_id="all_ties",
            item_ids=bank.item_ids(),
        )
        persona = Persona(
            name="all_ties",
            description="Every latent utility is equal.",
            utilities={item_id: 0.0 for item_id in bank.item_ids()},
        )
        _, holdout = holdout_split(bank.item_ids(), 0.2, seed=11)

        with pytest.raises(
            ValueError,
            match="holdout has no scorable latent preference directions",
        ):
            compute_latent_direction_reliability(
                state,
                persona,
                holdout,
                tie_epsilon=0.0,
                n_bins=10,
            )


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
            assert "final_latent_direction_log_score_mean" in s
            assert "final_log_likelihood_mean" not in s
        trial = results["trials"][0]
        assert "first_tau_threshold_question" in trial
        assert "questions_to_convergence" not in trial
        assert "n_scored_holdout_pairs" in trial
        assert "tau_threshold" in results["config"]
        assert "convergence_tau" not in results["config"]

    def test_results_json_serializable(self):
        results = run_comparison(TINY, personas=DEFAULT_PERSONAS[:1])
        json.dumps(results, allow_nan=False)  # must not raise

    def test_corrected_result_schema_is_explicit(self):
        results = run_comparison(TINY, personas=DEFAULT_PERSONAS[:1])
        assert results["schema_version"] == SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION
        assert set(results) == {
            "schema_version",
            "config",
            "personas",
            "summaries",
            "trials",
        }
        assert set(results["trials"][0]) == {
            "model_name",
            "policy_name",
            "persona_name",
            "seed",
            "curve",
            "latent_direction_reliability",
            "first_tau_threshold_question",
            "n_holdout_pairs",
            "n_scored_holdout_pairs",
            "asked_pairs",
        }
        assert set(results["trials"][0]["curve"][0]) == {
            "n_questions",
            "latent_direction_log_score",
            "latent_direction_accuracy",
            "latent_direction_brier",
            "kendall_tau",
        }
        assert set(results["trials"][0]["latent_direction_reliability"][0]) == {
            "lo",
            "hi",
            "n",
            "mean_confidence",
            "latent_direction_accuracy",
        }
        assert set(results["summaries"][0]) == {
            "model_name",
            "policy_name",
            "n_trials",
            "final_latent_direction_log_score_mean",
            "final_latent_direction_log_score_std",
            "final_latent_direction_accuracy_mean",
            "final_latent_direction_brier_mean",
            "final_kendall_tau_mean",
            "final_kendall_tau_std",
            "tau_threshold_attainment_rate",
            "median_first_tau_threshold_question",
            "mean_curve",
        }

    def test_summary_table_uses_corrected_metric_names(self):
        results = run_comparison(TINY, personas=DEFAULT_PERSONAS[:1])
        table = _format_table(results["summaries"])
        assert "latent log" in table
        assert "dir Brier" in table
        assert "tau hit%" in table
        header, separator, *rows = table.splitlines()
        assert len(header) == len(separator)
        for row in rows:
            assert len(row) == len(header)

    def test_cli_writes_versioned_default_result(
        self,
        monkeypatch,
        tmp_path,
        capsys,
    ):
        monkeypatch.setattr(preference_eval_cli, "RESULTS_DIR", tmp_path)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_preference_eval",
                "--n-questions",
                "0",
                "--n-seeds",
                "1",
                "--base-seed",
                "19",
                "--response-model",
                "sloppy",
            ],
        )

        preference_eval_cli.main()

        output = tmp_path / "preference_eval_sloppy_seed19.json"
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["schema_version"] == SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION
        assert "latent log" in capsys.readouterr().out
