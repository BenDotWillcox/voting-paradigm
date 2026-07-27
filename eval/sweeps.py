"""
Grid sweeps over EvalConfig fields, for notebook consumption.

A sweep is a cartesian product over config overrides — response models,
noise levels, model hyperparameters, question budgets — with one
`run_comparison` per grid point. Results stay fully deterministic: the grid
point plus the base config's seeds identify every trial.

Typical notebook use:

    rows = run_sweep(
        EvalConfig(n_seeds=3),
        {
            "response_model": ["gaussian_gap", "logistic_choice", "sloppy"],
            "n_questions": [15, 25, 40],
        },
        personas=generate_personas(50, seed=0),
    )
    table = sweep_summary_table(rows)   # flat dicts, ready for plotting
"""

from dataclasses import replace
from itertools import product

from .personas import DEFAULT_PERSONAS, Persona
from .preference_eval import EvalConfig, run_comparison


def run_sweep(
    base_config: EvalConfig,
    grid: dict[str, list],
    personas: tuple[Persona, ...] = DEFAULT_PERSONAS,
) -> list[dict]:
    """Run `run_comparison` at every point of the override grid.

    `grid` maps EvalConfig field names to the values to sweep. Returns one
    row per grid point: {"overrides": {...}, "results": run_comparison(...)}.
    Keys are iterated in sorted order so the row order is deterministic.
    """
    unknown = set(grid) - set(EvalConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(
            f"Unknown EvalConfig fields in sweep grid: {sorted(unknown)}"
        )
    keys = sorted(grid)
    rows: list[dict] = []
    for values in product(*(grid[k] for k in keys)):
        overrides = dict(zip(keys, values))
        config = replace(base_config, **overrides)
        rows.append(
            {
                "overrides": overrides,
                "results": run_comparison(config, personas=tuple(personas)),
            }
        )
    return rows


def sweep_summary_table(rows: list[dict]) -> list[dict]:
    """Flatten sweep rows into one dict per (grid point, model, policy).

    Each entry merges the grid overrides with that cell's final summary
    metrics — a tidy table ready for pandas/matplotlib without either being
    a harness dependency.
    """
    table: list[dict] = []
    for row in rows:
        for summary in row["results"]["summaries"]:
            table.append(
                {
                    **row["overrides"],
                    "model_name": summary["model_name"],
                    "policy_name": summary["policy_name"],
                    "n_trials": summary["n_trials"],
                    "final_log_likelihood_mean": summary[
                        "final_log_likelihood_mean"
                    ],
                    "final_log_likelihood_std": summary[
                        "final_log_likelihood_std"
                    ],
                    "final_accuracy_mean": summary["final_accuracy_mean"],
                    "final_brier_mean": summary["final_brier_mean"],
                    "final_kendall_tau_mean": summary["final_kendall_tau_mean"],
                    "final_kendall_tau_std": summary["final_kendall_tau_std"],
                    "convergence_rate": summary["convergence_rate"],
                    "median_questions_to_convergence": summary[
                        "median_questions_to_convergence"
                    ],
                }
            )
    return table
