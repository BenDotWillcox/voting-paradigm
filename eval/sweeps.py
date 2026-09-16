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

import json
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
    Every config passes EvalConfig validation before any comparison runs.
    """
    unknown = set(grid) - set(EvalConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(
            f"Unknown EvalConfig fields in sweep grid: {sorted(unknown)}"
        )
    keys = sorted(grid)
    configurations: list[tuple[dict, EvalConfig]] = []
    for values in product(*(grid[k] for k in keys)):
        overrides = dict(zip(keys, values))
        configurations.append((overrides, replace(base_config, **overrides)))

    rows: list[dict] = []
    for overrides, config in configurations:
        rows.append(
            {
                "overrides": overrides,
                "results": run_comparison(config, personas=tuple(personas)),
            }
        )
    return rows


def sweep_summary_table(rows: list[dict]) -> list[dict]:
    """Flatten sweep rows into one dict per (grid point, model, policy).

    Each entry merges the full effective config with that cell's final
    summary metrics. Nested parameter maps are canonical JSON strings so all
    columns remain hashable for pandas grouping and deduplication, without
    making pandas or matplotlib harness dependencies.
    """
    table: list[dict] = []
    for row in rows:
        result = row["results"]
        config = {
            **result["config"],
            "response_model_params": json.dumps(
                result["config"]["response_model_params"],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "model_params": json.dumps(
                result["config"]["model_params"],
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        for summary in result["summaries"]:
            table.append(
                {
                    "schema_version": result["schema_version"],
                    **config,
                    "model_name": summary["model_name"],
                    "policy_name": summary["policy_name"],
                    "n_trials": summary["n_trials"],
                    "final_latent_direction_log_score_mean": summary[
                        "final_latent_direction_log_score_mean"
                    ],
                    "final_latent_direction_log_score_std": summary[
                        "final_latent_direction_log_score_std"
                    ],
                    "final_latent_direction_accuracy_mean": summary[
                        "final_latent_direction_accuracy_mean"
                    ],
                    "final_latent_direction_brier_mean": summary[
                        "final_latent_direction_brier_mean"
                    ],
                    "final_kendall_tau_mean": summary["final_kendall_tau_mean"],
                    "final_kendall_tau_std": summary["final_kendall_tau_std"],
                    "tau_threshold_attainment_rate": summary[
                        "tau_threshold_attainment_rate"
                    ],
                    "median_first_tau_threshold_question": summary[
                        "median_first_tau_threshold_question"
                    ],
                }
            )
    return table
