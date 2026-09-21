"""Run the bounded synthetic comparison and export auditable plotting data.

This wraps the existing evaluator without changing inference or metrics.
Results describe fixed-item latent-order recovery, never human ballot accuracy.
Use a fresh output directory; existing generated evidence is not overwritten.
"""

import argparse
import csv
import gzip
import hashlib
import json
import math
import platform
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from itertools import combinations, product
from pathlib import Path

import numpy as np
import scipy

from preferences.acquisition import create_selector
from preferences.model import create_model
from preferences.questions.bank import QuestionBank

from .personas import generate_personas
from .preference_eval import EvalConfig, holdout_split, run_comparison
from .response_models import create_response_model

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).parent / "benchmarks/synthetic_v1/config.json"
METRICS = (
    "latent_direction_log_score",
    "latent_direction_accuracy",
    "latent_direction_brier",
    "kendall_tau",
)
PAIRED_COLUMNS = (
    "response_model", "contrast_kind", "left_model_name", "left_policy_name",
    "right_model_name", "right_policy_name", "persona_name", "seed",
    "n_questions", "metric", "left_value", "right_value", "difference",
)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def prepare_comparisons(settings: dict) -> tuple[tuple, list[EvalConfig]]:
    """Validate every configuration before launching any expensive comparison."""
    generator = settings["persona_generator"]
    if generator["n"] < 1 or generator["concentration"] <= 0:
        raise ValueError("persona count and concentration must be positive")
    if generator["jitter_std"] < 0:
        raise ValueError("persona jitter must be nonnegative")
    personas = tuple(generate_personas(**generator))
    options = dict(settings["evaluation"])
    options["model_names"] = tuple(options["model_names"])
    options["policy_names"] = tuple(options["policy_names"])
    if options["n_seeds"] < 1 or options["n_questions"] < 1:
        raise ValueError("seed and question counts must be positive")
    if not 0 < options["holdout_fraction"] < 1:
        raise ValueError("holdout_fraction must be in (0, 1)")
    if options["n_reliability_bins"] < 1 or options["tie_epsilon"] < 0:
        raise ValueError("invalid reliability-bin count or tie tolerance")
    for names in (options["model_names"], options["policy_names"]):
        if not names or len(names) != len(set(names)):
            raise ValueError("model and policy lists must be nonempty and unique")
    train, _ = holdout_split(
        QuestionBank.load_default().item_ids(), options["holdout_fraction"],
        options["base_seed"],
    )
    if options["n_questions"] > len(train):
        raise ValueError("question budget exceeds eligible pair count")
    for name in options["model_names"]:
        create_model(name, **options["model_params"])
    for name in options["policy_names"]:
        create_selector(name)
    configs = []
    for name, params in settings["response_scenarios"].items():
        responder = create_response_model(name, **params)
        resolved = asdict(responder)
        if any(not math.isfinite(value) for value in resolved.values()):
            raise ValueError("response parameters must be finite")
        if resolved.get("noise_std", 0) < 0:
            raise ValueError("response noise_std must be nonnegative")
        for key in ("temperature", "magnitude", "response_scale", "gain"):
            if key in resolved and resolved[key] <= 0:
                raise ValueError(f"response {key} must be positive")
        if not 0 <= resolved.get("lapse_rate", 0) <= 1:
            raise ValueError("response lapse_rate must be in [0, 1]")
        configs.append(
            EvalConfig(
                **options,
                response_model=name,
                response_model_params=resolved,
            )
        )
    if not configs:
        raise ValueError("at least one response scenario is required")
    return personas, configs


def comparison_rows(result: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Export macro-average curves and count-weighted final reliability bins.

    SD and percentiles describe persona/seed variation, not sampling uncertainty.
    In particular, the evaluator shares each seed's noise stream across personas.
    """
    summaries, curves, reliability = [], [], []
    scenario = result["config"]["response_model"]
    for summary in result["summaries"]:
        identity = {
            "response_model": scenario,
            "model_name": summary["model_name"],
            "policy_name": summary["policy_name"],
        }
        trials = [
            t for t in result["trials"]
            if all(t[k] == identity[k] for k in ("model_name", "policy_name"))
        ]
        summaries.append({
            **identity,
            **{k: v for k, v in summary.items() if k != "mean_curve"},
            "threshold_attained_trials": sum(
                t["first_tau_threshold_question"] is not None for t in trials
            ),
            "raw_holdout_pair_observations": sum(t["n_holdout_pairs"] for t in trials),
            "scored_holdout_pair_observations": sum(
                t["n_scored_holdout_pairs"] for t in trials
            ),
        })
        expected_steps = list(range(result["config"]["n_questions"] + 1))
        if any(
            [p["n_questions"] for p in t["curve"]] != expected_steps for t in trials
        ):
            raise ValueError("benchmark requires complete common question checkpoints")
        for step in expected_steps:
            for metric in METRICS:
                values = np.array([t["curve"][step][metric] for t in trials])
                curves.append({
                    **identity, "n_questions": step, "metric": metric,
                    "n_trials": len(trials), "mean": float(values.mean()),
                    "std": float(values.std()),
                    "p10": float(np.quantile(values, 0.1)),
                    "p90": float(np.quantile(values, 0.9)),
                })
        for index in range(result["config"]["n_reliability_bins"]):
            bins = [t["latent_direction_reliability"][index] for t in trials]
            count = sum(b["n"] for b in bins)
            reliability.append({
                **identity, "lo": bins[0]["lo"], "hi": bins[0]["hi"], "n": count,
                "mean_confidence": (
                    sum(b["n"] * b["mean_confidence"] for b in bins) / count
                    if count else None
                ),
                "latent_direction_accuracy": (
                    sum(b["n"] * b["latent_direction_accuracy"] for b in bins) / count
                    if count else None
                ),
            })
    return summaries, curves, reliability


def paired_difference_rows(result: dict) -> list[dict]:
    """Compare endpoints within identical persona/seed blocks, descriptively.

    Each contrast changes only model or policy, ordered by the configuration.
    Differences are left minus right; negative Brier differences favor the left.
    Matching compares methods within each persona/seed block; differences can
    still vary by persona. Shared seed streams prevent independent-sample claims.
    """
    config = result["config"]
    models, policies = config["model_names"], config["policy_names"]
    blocks = list(product(
        result["personas"],
        range(config["base_seed"], config["base_seed"] + config["n_seeds"]),
    ))
    expected_blocks = set(blocks)
    if not blocks or len(blocks) != len(expected_blocks):
        raise ValueError("paired comparison requires nonempty unique blocks")
    endpoints = {cell: {} for cell in product(models, policies)}
    for trial in result["trials"]:
        cell = (trial["model_name"], trial["policy_name"])
        block = (trial["persona_name"], trial["seed"])
        if cell not in endpoints or block not in expected_blocks:
            raise ValueError("paired comparison contains an unexpected cell or block")
        if block in endpoints[cell]:
            raise ValueError("paired comparison contains a duplicate block")
        if not trial["curve"] or (
            trial["curve"][-1]["n_questions"] != config["n_questions"]
        ):
            raise ValueError("paired comparison requires the common final checkpoint")
        endpoints[cell][block] = trial["curve"][-1]
    if any(set(values) != expected_blocks for values in endpoints.values()):
        raise ValueError("paired comparison requires every block in every cell")
    contrasts = [
        ("model", (left, policy), (right, policy))
        for left, right in combinations(models, 2) for policy in policies
    ] + [
        ("policy", (model, left), (model, right))
        for model in models for left, right in combinations(policies, 2)
    ]
    rows = []
    for kind, left, right in contrasts:
        for persona, seed in blocks:
            for metric in METRICS:
                left_value = endpoints[left][persona, seed][metric]
                right_value = endpoints[right][persona, seed][metric]
                rows.append({
                    "response_model": config["response_model"],
                    "contrast_kind": kind,
                    "left_model_name": left[0], "left_policy_name": left[1],
                    "right_model_name": right[0], "right_policy_name": right[1],
                    "persona_name": persona, "seed": seed,
                    "n_questions": config["n_questions"], "metric": metric,
                    "left_value": left_value, "right_value": right_value,
                    "difference": left_value - right_value,
                })
    return rows


def write_csv(
    path: Path, rows: list[dict], fieldnames: tuple[str, ...] | None = None,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fieldnames or list(rows[0]), lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def source_hashes() -> dict[str, str]:
    """Record the numerical implementation and public bank, not unrelated code."""
    paths = [
        REPO_ROOT / "eval" / name for name in (
            "run_synthetic_benchmark.py", "preference_eval.py", "personas.py",
            "response_models.py",
        )
    ]
    paths += [
        p for p in (REPO_ROOT / "preferences").rglob("*.py")
        if "tests" not in p.parts
    ]
    paths.append(REPO_ROOT / "preferences/questions/seed_items.json")
    return {
        path.relative_to(REPO_ROOT).as_posix(): hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for path in sorted(paths)
    }


def run_benchmark(settings: dict, output_dir: Path, workers: int = 1) -> dict:
    personas, configs = prepare_comparisons(settings)
    if workers < 1:
        raise ValueError("workers must be positive")
    filenames = [f"{c.response_model}.json.gz" for c in configs] + [
        "run_config.json", "personas.json", "metadata.json",
        "summary.csv", "curves.csv", "reliability.csv", "paired_differences.csv",
    ]
    if any((output_dir / name).exists() for name in filenames):
        raise ValueError("generated files already exist; use a fresh output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance = source_hashes()
    # Parallelism is by scenario only. Every trial retains the evaluator's seed.
    if workers == 1:
        results = [run_comparison(c, personas) for c in configs]
    else:
        with ProcessPoolExecutor(max_workers=min(workers, len(configs))) as pool:
            results = list(pool.map(run_comparison, configs, [personas] * len(configs)))
    if source_hashes() != provenance:
        raise ValueError("numerical source changed during benchmark execution")
    (output_dir / "run_config.json").write_bytes(json_bytes(settings))
    (output_dir / "personas.json").write_bytes(
        json_bytes([asdict(p) for p in personas])
    )
    tables: tuple[list, list, list] = ([], [], [])
    for result in results:
        # mtime=0 removes wall-clock variation from gzip output.
        compressed = gzip.compress(json_bytes(result), compresslevel=9, mtime=0)
        name = f"{result['config']['response_model']}.json.gz"
        (output_dir / name).write_bytes(compressed)
        for combined, rows in zip(tables, comparison_rows(result)):
            combined.extend(rows)
        print(f"{result['config']['response_model']}: {len(result['trials'])} trials")
    for name, rows in zip(("summary", "curves", "reliability"), tables):
        write_csv(output_dir / f"{name}.csv", rows)
    write_csv(
        output_dir / "paired_differences.csv",
        [row for result in results for row in paired_difference_rows(result)],
        PAIRED_COLUMNS,
    )
    metadata = {
        "benchmark_id": settings["benchmark_id"],
        "estimand": "fixed_item_held_out_latent_direction_recovery",
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__, "platform": platform.platform(),
        },
        "resolved_model_parameters": {
            name: vars(create_model(name, **settings["evaluation"]["model_params"]))
            for name in settings["evaluation"]["model_names"]
        },
        "source_sha256_lf_normalized": provenance,
        "artifact_sha256": {
            name: hashlib.sha256((output_dir / name).read_bytes()).hexdigest()
            for name in filenames if name != "metadata.json"
        },
        "trial_count": sum(len(r["trials"]) for r in results),
        "cell_count": len(tables[0]),
        "uncertainty_description": "descriptive trial spread, not confidence intervals",
        "pairing": "same persona/seed blocks; noise streams shared across personas",
        "paired_differences": "endpoint left minus right; one-factor contrasts",
        "inference_provider_calls": 0,
        "participant_data": False,
    }
    (output_dir / "metadata.json").write_bytes(json_bytes(metadata))
    return metadata


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    settings = json.loads(args.config.read_text(encoding="utf-8"))
    result = run_benchmark(settings, args.output_dir, args.workers)
    print(f"Complete: {result['trial_count']} trials, {result['cell_count']} cells")


if __name__ == "__main__":
    main()
