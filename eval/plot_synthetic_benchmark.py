"""Render the three fixed-bank synthetic benchmark result files as PNGs.

Usage: python -m eval.plot_synthetic_benchmark DIRECTORY
The figures describe synthetic persona-by-seed trials, not sampled voters.
"""

import argparse
import gzip
import hashlib
from io import BytesIO
import json
from math import log, log2, sqrt
from pathlib import Path
import platform

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, PercentFormatter
import numpy as np

from .preference_eval import SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION

SCENARIOS = {
    "gaussian_gap": "Gaussian-gap responses",
    "logistic_choice": "Logistic-choice responses",
    "sloppy": "Sloppy responses (stress condition)",
}
MODELS = {
    "gaussian_linear": ("Gaussian", "#276A93", "o"),
    "bradley_terry": ("Bradley-Terry", "#C06427", "s"),
}
POLICIES = {
    "fixed_sequence": ("Fixed", ":"),
    "random": ("Random", "--"),
    "max_variance": ("Max variance", "-"),
}
METRICS = {
    "latent_direction_log_score": (
        "Latent-direction log score\n(nats; higher is better)"
    ),
    "latent_direction_brier": "Binary Brier score\n(lower is better)",
    "latent_direction_accuracy": "Latent-direction accuracy\n(higher is better)",
    "kendall_tau": "Kendall tau-b\n(higher is better)",
}
CELLS = [(model, policy) for model in MODELS for policy in POLICIES]
SCORE_PRIORS = {
    "latent_direction_log_score": -log(2),
    "latent_direction_brier": 0.25,
}


def pool_reliability(trials: list[dict]) -> list[dict]:
    """Pool same-boundary bins by scored-pair count, excluding empty bins."""
    totals: dict[tuple[float, float], list[float]] = {}
    for trial in trials:
        for item in trial["latent_direction_reliability"]:
            n = item["n"]
            if n == 0:
                continue
            sums = totals.setdefault((item["lo"], item["hi"]), [0, 0.0, 0.0])
            sums[0] += n
            sums[1] += n * item["mean_confidence"]
            sums[2] += n * item["latent_direction_accuracy"]
    return [
        {
            "lo": lo,
            "hi": hi,
            "n": int(n),
            "mean_confidence": confidence / n,
            "latent_direction_accuracy": accuracy / n,
        }
        for (lo, hi), (n, confidence, accuracy) in sorted(totals.items())
    ]


def load_results(directory: Path) -> dict[str, dict]:
    """Read only the named, versioned benchmark files; reject missing cells."""
    results = {}
    for scenario in SCENARIOS:
        path = directory / f"{scenario}.json.gz"
        with gzip.open(path, "rt", encoding="utf-8") as source:
            result = json.load(source)
        if result.get("schema_version") != SYNTHETIC_EVAL_RESULT_SCHEMA_VERSION:
            raise ValueError(f"{scenario}: unsupported synthetic result schema")
        if result["config"]["response_model"] != scenario:
            raise ValueError(f"{scenario}: response scenario does not match filename")
        summaries = result["summaries"]
        if len(summaries) != len(CELLS) or {
            (item["model_name"], item["policy_name"]) for item in summaries
        } != set(CELLS):
            raise ValueError(f"{scenario}: expected all six model-policy summaries")
        for model, policy in CELLS:
            trials = _cell_trials(result, model, policy)
            summary = next(
                s for s in summaries
                if (s["model_name"], s["policy_name"]) == (model, policy)
            )
            if (not trials or not summary["mean_curve"]
                    or any(not t["curve"] for t in trials)):
                raise ValueError(f"{scenario}/{model}/{policy}: empty trial or curve")
            if not pool_reliability(trials):
                raise ValueError(
                    f"{scenario}/{model}/{policy}: no scored reliability pairs"
                )
        results[scenario] = result
    return results


def _cell_trials(result: dict, model: str, policy: str) -> list[dict]:
    return [
        t for t in result["trials"]
        if (t["model_name"], t["policy_name"]) == (model, policy)
    ]


def _scenario_title(scenario: str, result: dict) -> str:
    profiles = len({t["persona_name"] for t in result["trials"]})
    seeds = len({t["seed"] for t in result["trials"]})
    counts = sorted({len(_cell_trials(result, m, p)) for m, p in CELLS})
    questions = sorted({t["curve"][-1]["n_questions"] for t in result["trials"]})
    return (
        f"{SCENARIOS[scenario]}\n"
        f"{profiles} synthetic profiles × {seeds} seeds; "
        f"{'/'.join(map(str, counts))} trials/cell\n"
        f"{'/'.join(map(str, questions))} questions at final state"
    )


def _metric_limits(results: dict[str, dict]) -> dict[str, tuple[float, float]]:
    """Share focused score ranges, including every trial checkpoint and prior."""
    limits = {"kendall_tau": (-1.0, 1.0), "latent_direction_accuracy": (0.0, 1.0)}
    for metric, prior in SCORE_PRIORS.items():
        values = [prior] + [
            point[metric] for result in results.values()
            for trial in result["trials"] for point in trial["curve"]
        ]
        lo, hi = min(values), max(values)
        margin = max(0.005, (hi - lo) * 0.05)
        limits[metric] = (lo - margin, hi + margin)
    return limits


def _metric_axis(ax, metric: str, limits: tuple[float, float]) -> None:
    ax.set_ylim(*limits)
    if metric in SCORE_PRIORS:
        ax.axhline(
            SCORE_PRIORS[metric], color="#555B61", linestyle="--",
            linewidth=1, label="_uniform_prior", zorder=1,
        )
    if metric == "latent_direction_accuracy":
        ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.grid(axis="y", color="#E1E4E7", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def _question_ticks(final_question: int) -> list[int]:
    ticks = MaxNLocator(nbins=5, integer=True).tick_values(0, final_question)
    return [int(t) for t in ticks if 0 <= t < final_question] + [final_question]


def _reliability_marker_area(count: int) -> float:
    """A fixed log-count encoding, in points squared, shared by every panel."""
    return min(120.0, 12.0 + 8.0 * log2(count + 1))


def learning_curves(results: dict[str, dict]):
    """Four metric rows with shared per-metric scales across scenarios."""
    fig, axes = plt.subplots(4, 3, figsize=(15, 12), sharex=True, sharey="row")
    limits = _metric_limits(results)
    final_question = max(
        p["n_questions"] for result in results.values()
        for summary in result["summaries"] for p in summary["mean_curve"]
    )
    for col, scenario in enumerate(SCENARIOS):
        for row, (metric, label) in enumerate(METRICS.items()):
            ax = axes[row, col]
            for summary in results[scenario]["summaries"]:
                model_label, color, marker = MODELS[summary["model_name"]]
                policy_label, linestyle = POLICIES[summary["policy_name"]]
                curve = summary["mean_curve"]
                ax.plot(
                    [p["n_questions"] for p in curve],
                    [p[metric] for p in curve],
                    color=color, linestyle=linestyle, marker=marker, markersize=3,
                    markevery=max(1, len(curve) // 5), linewidth=1.7,
                    label=f"{model_label} / {policy_label}",
                )
            _metric_axis(ax, metric, limits[metric])
            ax.set_xticks(_question_ticks(final_question))
            ax.set_xlim(0, max(1, final_question) * 1.02)
            if row == 0:
                ax.set_title(_scenario_title(scenario, results[scenario]), fontsize=10)
            if col == 0:
                ax.set_ylabel(label)
            if row == 3:
                ax.set_xlabel("Questions answered (0 = prior)")
    fig.suptitle("Synthetic preference recovery: mean learning curves", y=0.995)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.966),
        ncol=3, frameon=False,
    )
    fig.text(
        0.5, 0.012,
        "Equal-weight means across persona × seed trials; "
        "endpoint spread is in final_spread.png.\n"
        "Log score and Brier use focused shared scales covering all trial states; "
        "gray dashed lines show the uniform prior.\n"
        "Within-bank held-out pairs; synthetic sensitivity evidence, "
        "not a voter-population estimate.",
        ha="center",
    )
    fig.tight_layout(rect=(0, 0.065, 1, 0.90))
    return fig


def final_reliability(results: dict[str, dict]):
    """Final confidence versus accuracy, pooled by pair counts within bins."""
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True, sharey=True)
    for row, (model, (model_label, color, marker)) in enumerate(MODELS.items()):
        for col, scenario in enumerate(SCENARIOS):
            ax = axes[row, col]
            ax.plot(
                [0.5, 1], [0.5, 1], color="#555B61", linewidth=1, label="Ideal"
            )
            for policy, (label, linestyle) in POLICIES.items():
                bins = pool_reliability(_cell_trials(results[scenario], model, policy))
                confidence = [b["mean_confidence"] for b in bins]
                accuracy = [b["latent_direction_accuracy"] for b in bins]
                ax.plot(
                    confidence, accuracy, color=color,
                    linestyle=linestyle, label=label,
                )
                ax.scatter(
                    confidence, accuracy,
                    s=[_reliability_marker_area(b["n"]) for b in bins],
                    marker=marker, color=color, edgecolors="white",
                    linewidths=0.5, zorder=3,
                )
            ax.set(xlim=(0.49, 1.01), ylim=(0, 1.02))
            ax.xaxis.set_major_formatter(PercentFormatter(1))
            ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.grid(color="#E1E4E7", linewidth=0.7)
            ax.spines[["top", "right"]].set_visible(False)
            if row == 0:
                ax.set_title(_scenario_title(scenario, results[scenario]), fontsize=10)
            if col == 0:
                ax.set_ylabel(f"{model_label}\nLatent-direction accuracy")
            if row == 1:
                ax.set_xlabel("Mean confidence in predicted latent direction")
    fig.suptitle("Final-state latent-direction reliability", y=0.99)
    fig.legend(
        [Line2D([], [], color="#555B61", linestyle=style)
         for _, style in POLICIES.values()],
        [label for label, _ in POLICIES.values()], loc="upper center",
        bbox_to_anchor=(0.5, 0.95), ncol=3, frameon=False,
    )
    legend_counts = (1, 100, 1000)
    fig.legend(
        [Line2D([], [], color="#555B61", marker="o", linestyle="none",
                markersize=sqrt(_reliability_marker_area(n)))
         for n in legend_counts],
        [f"n = {n:,}" for n in legend_counts], loc="upper center",
        bbox_to_anchor=(0.5, 0.905), ncol=3, frameon=False,
    )
    fig.text(
        0.5, 0.016,
        "Bin means weighted by scored held-out pair count; empty bins omitted. "
        "Gray line: ideal reliability.\n"
        "Marker area = min(120, 12 + 8 log₂(n + 1)) pt²; "
        "n = pooled scored pairs in a bin.\n"
        "Pairs and seeds reuse synthetic personas; these points are descriptive, "
        "not independent voter observations.",
        ha="center",
    )
    fig.tight_layout(rect=(0, 0.105, 1, 0.85))
    return fig


def final_spread(results: dict[str, dict]):
    """Endpoint distributions; whiskers describe spread, never confidence intervals."""
    fig, axes = plt.subplots(4, 3, figsize=(15, 12), sharex=True, sharey="row")
    limits = _metric_limits(results)
    for col, scenario in enumerate(SCENARIOS):
        result = results[scenario]
        for row, (metric, label) in enumerate(METRICS.items()):
            ax = axes[row, col]
            values = [
                [t["curve"][-1][metric] for t in _cell_trials(result, m, p)]
                for m, p in CELLS
            ]
            boxes = ax.boxplot(
                values, positions=[1, 2, 3, 5, 6, 7], widths=0.65, whis=(10, 90),
                patch_artist=True, medianprops={"color": "#222222"},
                flierprops={
                    "marker": ".", "markersize": 3, "markeredgecolor": "#555B61"
                },
            )
            for patch, (model, _) in zip(boxes["boxes"], CELLS):
                patch.set(
                    facecolor=MODELS[model][1], alpha=0.65,
                    hatch="//" if model == "bradley_terry" else "",
                )
            _metric_axis(ax, metric, limits[metric])
            ax.set_xticks([1, 2, 3, 5, 6, 7], ["Fixed", "Random", "Max var."] * 2)
            if row == 0:
                ax.set_title(_scenario_title(scenario, result), fontsize=10)
            if col == 0:
                ax.set_ylabel(label)
            if row == 3:
                for x, (model_label, _, _) in zip((2, 6), MODELS.values()):
                    ax.text(
                        x, -0.19, model_label, transform=ax.get_xaxis_transform(),
                        ha="center", va="top",
                    )
    fig.suptitle("Final-state spread across synthetic persona × seed trials", y=0.985)
    fig.text(
        0.5, 0.013,
        "Boxes: 25th–75th percentiles; center: median; whiskers: "
        "10th–90th percentiles; dots: observations beyond whiskers.\n"
        "Log score and Brier use focused shared scales covering all trial states; "
        "gray dashed lines show the uniform prior.\n"
        "Descriptive trial spread, not confidence intervals or a sample of voters.",
        ha="center",
    )
    fig.tight_layout(rect=(0, 0.07, 1, 0.955))
    return fig


def render_benchmark(directory: Path) -> list[Path]:
    """Render before replacing files; publish the manifest only after all PNGs."""
    input_paths = [directory / f"{scenario}.json.gz" for scenario in SCENARIOS]
    input_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in input_paths
    }
    source_path = Path(__file__)
    source_bytes = source_path.read_bytes().replace(b"\r\n", b"\n")
    results = load_results(directory)
    rendered: dict[Path, bytes] = {}
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10}):
        for draw in (learning_curves, final_reliability, final_spread):
            fig = draw(results)
            path = directory / f"{draw.__name__}.png"
            try:
                with BytesIO() as buffer:
                    fig.savefig(
                        buffer, format="png", dpi=150, facecolor="white",
                        metadata={"Software": "synthetic-benchmark"},
                    )
                    rendered[path] = buffer.getvalue()
            finally:
                plt.close(fig)
    if any(
        hashlib.sha256(path.read_bytes()).hexdigest() != input_hashes[path.name]
        for path in input_paths
    ) or source_path.read_bytes().replace(b"\r\n", b"\n") != source_bytes:
        raise ValueError("benchmark inputs or plotter changed during rendering")
    manifest = {
        "figure_manifest_version": 1,
        "input_sha256": input_hashes,
        "source_sha256": {
            "eval/plot_synthetic_benchmark.py": hashlib.sha256(source_bytes).hexdigest()
        },
        "environment": {
            "python": platform.python_version(),
            "matplotlib": matplotlib.__version__,
            "numpy": np.__version__,
        },
        "png_sha256": {
            path.name: hashlib.sha256(data).hexdigest()
            for path, data in rendered.items()
        },
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    manifest_path = directory / "figures.json"
    staged_manifest = directory / ".figures.json.tmp"
    try:
        staged_manifest.write_bytes(manifest_bytes)
        # This is a single-writer CLI, not a multi-file transaction. Invalidate
        # the old claim before publication so a partial write cannot retain it.
        manifest_path.unlink(missing_ok=True)
        for path, data in rendered.items():
            path.write_bytes(data)
        staged_manifest.replace(manifest_path)
    finally:
        staged_manifest.unlink(missing_ok=True)
    return list(rendered)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    for path in render_benchmark(args.directory):
        print(path)


if __name__ == "__main__":
    main()
