"""
CLI entry point for the preference-model comparison.

Usage (from the repo root, venv active):

    python -m eval.run_preference_eval
    python -m eval.run_preference_eval --n-questions 40 --n-seeds 10
    python -m eval.run_preference_eval --output eval/results/my_run.json

Prints a models x policies summary table and writes the full result
(config, per-trial curves, calibration tables) as JSON for plotting.
"""

import argparse
import json
from pathlib import Path

from .preference_eval import EvalConfig, run_comparison

RESULTS_DIR = Path(__file__).parent / "results"


def _format_table(summaries: list[dict]) -> str:
    header = (
        f"{'model':<16} {'policy':<14} {'held-out LL':>12} "
        f"{'accuracy':>9} {'Brier':>7} {'tau':>14} {'conv%':>6} {'med q':>6}"
    )
    lines = [header, "-" * len(header)]
    for s in summaries:
        conv = (
            f"{s['median_questions_to_convergence']:.0f}"
            if s["median_questions_to_convergence"] is not None
            else "-"
        )
        lines.append(
            f"{s['model_name']:<16} {s['policy_name']:<14} "
            f"{s['final_log_likelihood_mean']:>7.4f}+-{s['final_log_likelihood_std']:.3f} "
            f"{s['final_accuracy_mean']:>9.3f} "
            f"{s['final_brier_mean']:>7.3f} "
            f"{s['final_kendall_tau_mean']:>7.3f}+-{s['final_kendall_tau_std']:.3f} "
            f"{100 * s['convergence_rate']:>5.0f}% "
            f"{conv:>6}"
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
    parser.add_argument("--noise-std", type=float, default=0.3)
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON output path (default: eval/results/preference_eval_seed<base_seed>.json)",
    )
    args = parser.parse_args()

    config = EvalConfig(
        n_questions=args.n_questions,
        n_seeds=args.n_seeds,
        base_seed=args.base_seed,
        noise_std=args.noise_std,
        holdout_fraction=args.holdout_fraction,
    )
    results = run_comparison(config)

    print(
        f"\nPreference model comparison -- "
        f"{config.n_questions} questions, {config.n_seeds} seeds/persona, "
        f"noise_std={config.noise_std}, holdout={config.holdout_fraction:.0%}\n"
    )
    print(_format_table(results["summaries"]))

    output = args.output or (
        RESULTS_DIR / f"preference_eval_seed{config.base_seed}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nFull results written to {output}")


if __name__ == "__main__":
    main()
