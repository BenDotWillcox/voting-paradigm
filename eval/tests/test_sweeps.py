"""Tests for the sweep helper."""

import pytest

from eval.personas import DEFAULT_PERSONAS
from eval.preference_eval import (
    SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION,
    EvalConfig,
)
from eval.sweeps import run_sweep, sweep_summary_table

TINY = EvalConfig(
    n_questions=3,
    n_seeds=1,
    base_seed=5,
    model_names=("gaussian_linear",),
    policy_names=("max_variance",),
)


class TestRunSweep:
    def test_grid_produces_cartesian_product(self):
        rows = run_sweep(
            TINY,
            {
                "response_model": ["gaussian_gap", "logistic_choice"],
                "n_questions": [2, 3],
            },
            personas=DEFAULT_PERSONAS[:1],
        )
        assert len(rows) == 4
        overrides = [r["overrides"] for r in rows]
        assert {"response_model": "gaussian_gap", "n_questions": 2} in overrides
        assert (
            {"response_model": "logistic_choice", "n_questions": 3} in overrides
        )

    def test_deterministic(self):
        grid = {"response_model": ["sloppy"]}
        r1 = run_sweep(TINY, grid, personas=DEFAULT_PERSONAS[:1])
        r2 = run_sweep(TINY, grid, personas=DEFAULT_PERSONAS[:1])
        assert r1 == r2

    def test_model_params_override_flows_through(self):
        """Sweeping prior_variance must change results (sanity that the
        override actually reaches the model constructor)."""
        rows = run_sweep(
            TINY,
            {"model_params": [{"prior_variance": 1.0}, {"prior_variance": 0.01}]},
            personas=DEFAULT_PERSONAS[:1],
        )
        # Kendall tau is rank-based (invariant to posterior shrinkage), so
        # Compare the latent-direction log score, which is sensitive to
        # posterior scale.
        score_a = rows[0]["results"]["summaries"][0][
            "final_latent_direction_log_score_mean"
        ]
        score_b = rows[1]["results"]["summaries"][0][
            "final_latent_direction_log_score_mean"
        ]
        assert score_a != score_b

    def test_unknown_field_raises(self):
        with pytest.raises(ValueError, match="Unknown EvalConfig fields"):
            run_sweep(TINY, {"nonsense_field": [1]}, DEFAULT_PERSONAS[:1])

    def test_invalid_later_config_fails_before_any_comparison(self, monkeypatch):
        def unexpected_comparison(*args, **kwargs):
            pytest.fail("comparison started before all configs were validated")

        monkeypatch.setattr("eval.sweeps.run_comparison", unexpected_comparison)
        with pytest.raises(ValueError, match="tau_threshold must be in"):
            run_sweep(
                TINY,
                {"tau_threshold": [0.5, 0.9, 0.0]},
                DEFAULT_PERSONAS[:1],
            )


class TestSummaryTable:
    def test_flattens_overrides_and_metrics(self):
        rows = run_sweep(
            TINY,
            {"response_model": ["gaussian_gap", "sloppy"]},
            personas=DEFAULT_PERSONAS[:1],
        )
        table = sweep_summary_table(rows)
        assert len(table) == 2  # 2 grid points x 1 model x 1 policy
        for entry in table:
            assert "response_model" in entry
            assert "final_kendall_tau_mean" in entry
            assert "final_latent_direction_log_score_mean" in entry
            assert "convergence_rate" not in entry
            assert entry["model_name"] == "gaussian_linear"

    def test_includes_base_response_model_when_not_swept(self):
        rows = run_sweep(
            TINY,
            {"n_questions": [2]},
            personas=DEFAULT_PERSONAS[:1],
        )
        table = sweep_summary_table(rows)
        assert [entry["response_model"] for entry in table] == [
            "gaussian_gap"
        ]
        assert table[0]["schema_version"] == (
            SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION
        )
        assert table[0]["n_questions"] == 2
        assert table[0]["tau_threshold"] == TINY.tau_threshold
        assert table[0]["response_model_params"] == "{}"
        assert table[0]["model_params"] == "{}"

    def test_parameter_maps_are_canonical_hashable_columns(self):
        config = EvalConfig(
            n_questions=1,
            n_seeds=1,
            model_names=("gaussian_linear",),
            policy_names=("fixed_sequence",),
            response_model_params={"noise_std": 0.2, "response_scale": 4.0},
            model_params={"prior_variance": 2.0},
        )
        table = sweep_summary_table(
            run_sweep(
                config,
                {"n_questions": [1]},
                personas=DEFAULT_PERSONAS[:1],
            )
        )

        assert table[0]["response_model_params"] == (
            '{"noise_std":0.2,"response_scale":4.0}'
        )
        assert table[0]["model_params"] == '{"prior_variance":2.0}'
