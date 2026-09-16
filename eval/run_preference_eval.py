"""
CLI entry point for the preference-model comparison.

Usage (from the repo root, venv active):

    python -m eval.run_preference_eval
    python -m eval.run_preference_eval --n-questions 40 --n-seeds 10
    python -m eval.run_preference_eval --output eval/results/my_run.json

Prints a models x policies summary table and writes the full result
(config, per-trial curves, latent-direction reliability tables) as JSON for
plotting.
"""

import argparse
import json
from pathlib import Path

from .preference_eval import EvalConfig, run_comparison

RESULTS_DIR = Path(__file__).parent / "results"


def _format_table(summaries: list[dict]) -> str:
    header = (
        f"{'model':<16} {'policy':<14} {'latent log':>14} "
        f"{'dir acc':>9} {'dir Brier':>9} {'tau-b':>14} "
        f"{'tau hit%':>8} {'first q':>7}"
    )
    lines = [header, "-" * len(header)]
    for s in summaries:
        first_question = (
            f"{s['median_first_tau_threshold_question']:.0f}"
            if s["median_first_tau_threshold_question"] is not None
            else "-"
        )
        lines.append(
            f"{s['model_name']:<16} {s['policy_name']:<14} "
            f"{s['final_latent_direction_log_score_mean']:>7.4f}+-"
            f"{s['final_latent_direction_log_score_std']:.3f} "
            f"{s['final_latent_direction_accuracy_mean']:>9.3f} "
            f"{s['final_latent_direction_brier_mean']:>9.3f} "
            f"{s['final_kendall_tau_mean']:>7.3f}+-{s['final_kendall_tau_std']:.3f} "
            f"{100 * s['tau_threshold_attainment_rate']:>7.0f}% "
            f"{first_question:>7}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare preference models x acquisition policies "
        "against synthetic personas."
    )
    parser.add_argument("--n-questions", type=int, default=25)
    parser.add_argument("--n-seeds", type=int, default=5)
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument(
        "--response-model",
        choices=["gaussian_gap", "logistic_choice", "sloppy"],
        default="gaussian_gap",
        help="Synthetic response-process scenario",
    )
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "JSON output path (default: "
            "eval/results/preference_eval_<response_model>_"
            "seed<base_seed>.json)"
        ),
    )
    args = parser.parse_args()

    config = EvalConfig(
        n_questions=args.n_questions,
        n_seeds=args.n_seeds,
        base_seed=args.base_seed,
        response_model=args.response_model,
        holdout_fraction=args.holdout_fraction,
    )
    results = run_comparison(config)

    print(
        f"\nPreference model comparison -- "
        f"{config.n_questions} questions, {config.n_seeds} seeds/persona, "
        f"response_model={config.response_model}, "
        f"holdout={config.holdout_fraction:.0%}\n"
    )
    print(_format_table(results["summaries"]))

    output = args.output or (
        RESULTS_DIR
        / f"preference_eval_{config.response_model}_seed{config.base_seed}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(results, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(f"\nFull results written to {output}")


if __name__ == "__main__":
    main()
