"""Tests for the sweep helper."""

import pytest

from eval.personas import DEFAULT_PERSONAS
from eval.preference_eval import EvalConfig
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
        # compare log-likelihood, which is sensitive to posterior scale.
        ll_a = rows[0]["results"]["summaries"][0]["final_log_likelihood_mean"]
        ll_b = rows[1]["results"]["summaries"][0]["final_log_likelihood_mean"]
        assert ll_a != ll_b

    def test_unknown_field_raises(self):
        with pytest.raises(ValueError, match="Unknown EvalConfig fields"):
            run_sweep(TINY, {"nonsense_field": [1]}, DEFAULT_PERSONAS[:1])


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
            assert entry["model_name"] == "gaussian_linear"
