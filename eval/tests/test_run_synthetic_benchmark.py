"""Synthetic benchmark publication checks against a real, bounded evaluation."""

import copy
import csv
import gzip
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from statistics import mean, pstdev

import pytest

from eval import run_synthetic_benchmark as benchmark
from eval.preference_eval import EvalConfig, holdout_split


def make_tiny_settings():
    evaluation = asdict(
        EvalConfig(
            n_questions=2,
            n_seeds=1,
            base_seed=42,
            # Exercise the distinction between raw and scorable denominators.
            tie_epsilon=0.1,
        )
    )
    evaluation.pop("response_model")
    evaluation.pop("response_model_params")
    evaluation["model_names"] = list(evaluation["model_names"])
    evaluation["policy_names"] = list(evaluation["policy_names"])
    return {
        "benchmark_id": "synthetic_benchmark_test",
        "persona_generator": {
            "n": 2,
            "seed": 20260916,
            "concentration": 0.5,
            "jitter_std": 0.15,
        },
        "evaluation": evaluation,
        "response_scenarios": {
            "gaussian_gap": {"noise_std": 0.3, "response_scale": 5.0},
            "logistic_choice": {"temperature": 0.5, "magnitude": 5.0},
        },
    }


@pytest.fixture
def tiny_settings():
    return make_tiny_settings()


@pytest.fixture(scope="module")
def tiny_outputs(tmp_path_factory):
    # Keep the expensive part shared while each test receives fresh decoded data.
    settings = make_tiny_settings()
    root = tmp_path_factory.mktemp("synthetic_benchmark")
    first, second = root / "first", root / "repeat"
    benchmark.run_benchmark(settings, first)
    benchmark.run_benchmark(settings, second)
    return settings, first, second


def read_results(output_dir):
    return {
        path.name.removesuffix(".json.gz"): json.loads(
            gzip.decompress(path.read_bytes())
        )
        for path in sorted(output_dir.glob("*.json.gz"))
    }


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def matching_trials(result, row):
    return [
        trial
        for trial in result["trials"]
        if trial["model_name"] == row["model_name"]
        and trial["policy_name"] == row["policy_name"]
    ]


def test_real_run_repeats_all_artifact_bytes_and_hashes(tiny_outputs):
    settings, first, second = tiny_outputs
    names = {path.name for path in first.iterdir()}
    assert names == {path.name for path in second.iterdir()}
    assert names == {
        "gaussian_gap.json.gz", "logistic_choice.json.gz", "run_config.json",
        "personas.json", "metadata.json", "summary.csv", "curves.csv",
        "reliability.csv", "paired_differences.csv",
    }
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    metadata = json.loads((first / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["trial_count"] == 24  # 2 scenarios x 6 cells x 2 personas
    assert metadata["cell_count"] == 12
    assert metadata["inference_provider_calls"] == 0
    assert metadata["participant_data"] is False
    saved_settings = json.loads(
        (first / "run_config.json").read_text(encoding="utf-8")
    )
    assert saved_settings == settings
    assert set(metadata["artifact_sha256"]) == names - {"metadata.json"}
    for name, digest in metadata["artifact_sha256"].items():
        assert digest == hashlib.sha256((first / name).read_bytes()).hexdigest()


def test_actual_denominators_checkpoints_and_pair_exclusions(tiny_outputs):
    settings, output_dir, _ = tiny_outputs
    persona_records = json.loads(
        (output_dir / "personas.json").read_text(encoding="utf-8")
    )
    personas = {
        persona["name"]: persona["utilities"]
        for persona in persona_records
    }
    results = read_results(output_dir)
    effective_counts = []
    for result in results.values():
        keys = set()
        for trial in result["trials"]:
            key = tuple(
                trial[name]
                for name in ("model_name", "policy_name", "persona_name", "seed")
            )
            assert key not in keys
            keys.add(key)
            utilities = personas[trial["persona_name"]]
            _, holdout = holdout_split(
                list(utilities),
                settings["evaluation"]["holdout_fraction"],
                trial["seed"],
            )
            expected_scored = sum(
                abs(utilities[a] - utilities[b]) > settings["evaluation"]["tie_epsilon"]
                for a, b in holdout
            )
            assert trial["n_holdout_pairs"] == len(holdout) == 126
            assert trial["n_scored_holdout_pairs"] == expected_scored
            effective_counts.append(expected_scored)
            assert (
                sum(bin_["n"] for bin_ in trial["latent_direction_reliability"])
                == expected_scored
            )
            assert [point["n_questions"] for point in trial["curve"]] == [0, 1, 2]
            asked = {frozenset(pair) for pair in trial["asked_pairs"]}
            assert len(asked) == len(trial["asked_pairs"]) == 2
            assert asked.isdisjoint(frozenset(pair) for pair in holdout)
            prior = trial["curve"][0]
            assert prior["latent_direction_log_score"] == pytest.approx(math.log(0.5))
            assert prior["latent_direction_accuracy"] == 0.5
            assert prior["latent_direction_brier"] == 0.25
            assert prior["kendall_tau"] == 0.0
    assert min(effective_counts) < 126
    assert min(effective_counts) > 0


def test_csv_summary_and_curve_statistics_match_raw_trials(tiny_outputs):
    _, output_dir, _ = tiny_outputs
    results = read_results(output_dir)
    summary_rows = read_csv(output_dir / "summary.csv")
    curve_rows = read_csv(output_dir / "curves.csv")
    assert len(summary_rows) == 12
    assert len(curve_rows) == 12 * 3 * len(benchmark.METRICS)
    for row in summary_rows:
        trials = matching_trials(results[row["response_model"]], row)
        assert int(row["n_trials"]) == len(trials) == 2
        assert int(row["raw_holdout_pair_observations"]) == sum(
            t["n_holdout_pairs"] for t in trials
        )
        assert int(row["scored_holdout_pair_observations"]) == sum(
            t["n_scored_holdout_pairs"] for t in trials
        )
        hits = [
            t["first_tau_threshold_question"]
            for t in trials
            if t["first_tau_threshold_question"] is not None
        ]
        assert int(row["threshold_attained_trials"]) == len(hits)
        assert float(row["tau_threshold_attainment_rate"]) == len(hits) / len(trials)
        if not hits:
            assert row["median_first_tau_threshold_question"] == ""
        for metric in benchmark.METRICS:
            values = [t["curve"][-1][metric] for t in trials]
            assert float(row[f"final_{metric}_mean"]) == pytest.approx(mean(values))
    for row in curve_rows:
        trials = matching_trials(results[row["response_model"]], row)
        step = int(row["n_questions"])
        values = [t["curve"][step][row["metric"]] for t in trials]
        assert int(row["n_trials"]) == len(values)
        assert float(row["mean"]) == pytest.approx(mean(values))
        assert float(row["std"]) == pytest.approx(pstdev(values))
        ordered = sorted(values)
        # Two observations: linear-interpolation quantiles have this closed form.
        assert float(row["p10"]) == pytest.approx(0.9 * ordered[0] + 0.1 * ordered[1])
        assert float(row["p90"]) == pytest.approx(0.1 * ordered[0] + 0.9 * ordered[1])


def test_reliability_csv_count_weights_and_blanks_empty_bins(tiny_outputs):
    _, output_dir, _ = tiny_outputs
    results = read_results(output_dir)
    rows = read_csv(output_dir / "reliability.csv")
    empty_rows = 0
    assert len(rows) == 12 * 10
    for row in rows:
        trials = matching_trials(results[row["response_model"]], row)
        bins = [
            bin_
            for trial in trials
            for bin_ in trial["latent_direction_reliability"]
            if bin_["lo"] == float(row["lo"]) and bin_["hi"] == float(row["hi"])
        ]
        assert len(bins) == len(trials)
        count = sum(bin_["n"] for bin_ in bins)
        assert int(row["n"]) == count
        if count == 0:
            empty_rows += 1
            assert row["mean_confidence"] == ""
            assert row["latent_direction_accuracy"] == ""
        else:
            for metric in ("mean_confidence", "latent_direction_accuracy"):
                expected = sum(bin_["n"] * bin_[metric] for bin_ in bins) / count
                assert float(row[metric]) == pytest.approx(expected)
    assert empty_rows > 0


def test_paired_csv_matches_raw_endpoints_with_one_factor_held_fixed(tiny_outputs):
    settings, output_dir, _ = tiny_outputs
    results = read_results(output_dir)
    rows = read_csv(output_dir / "paired_differences.csv")
    # 2 scenarios x (3 model + 6 policy contrasts) x 2 blocks x 4 metrics.
    assert len(rows) == 144
    assert tuple(rows[0]) == benchmark.PAIRED_COLUMNS
    identities = set()
    contrasts = set()
    for row in rows:
        result = results[row["response_model"]]
        endpoints = {
            (t["model_name"], t["policy_name"], t["persona_name"], t["seed"]):
            t["curve"][-1]
            for t in result["trials"]
        }
        block = row["persona_name"], int(row["seed"])
        left_cell = row["left_model_name"], row["left_policy_name"]
        right_cell = row["right_model_name"], row["right_policy_name"]
        left, right = endpoints[(*left_cell, *block)], endpoints[(*right_cell, *block)]
        metric = row["metric"]
        assert int(row["n_questions"]) == left["n_questions"] == right["n_questions"]
        assert float(row["left_value"]) == left[metric]
        assert float(row["right_value"]) == right[metric]
        assert float(row["difference"]) == left[metric] - right[metric]
        if row["contrast_kind"] == "model":
            assert left_cell[1] == right_cell[1]
            order = settings["evaluation"]["model_names"]
            assert order.index(left_cell[0]) < order.index(right_cell[0])
        else:
            assert row["contrast_kind"] == "policy"
            assert left_cell[0] == right_cell[0]
            order = settings["evaluation"]["policy_names"]
            assert order.index(left_cell[1]) < order.index(right_cell[1])
        identity = row["response_model"], left_cell, right_cell, block, metric
        assert identity not in identities
        identities.add(identity)
        contrasts.add((
            row["response_model"], row["contrast_kind"], left_cell, right_cell,
        ))
    assert len(contrasts) == 18
    # Pairing is by the named block, not by adjacency or source row position.
    for result in results.values():
        expected = benchmark.paired_difference_rows(result)
        result["trials"].reverse()
        assert benchmark.paired_difference_rows(result) == expected


@pytest.mark.parametrize("mutation,error", [
    ("missing", "every block in every cell"),
    ("duplicate", "duplicate block"),
    ("unexpected_seed", "unexpected cell or block"),
    ("empty_curve", "common final checkpoint"),
    ("different_endpoint", "common final checkpoint"),
])
def test_pairing_rejects_incomplete_or_ambiguous_blocks(tiny_outputs, mutation, error):
    _, output_dir, _ = tiny_outputs
    result = read_results(output_dir)["gaussian_gap"]
    if mutation == "missing":
        result["trials"].pop()
    elif mutation == "duplicate":
        result["trials"].append(copy.deepcopy(result["trials"][0]))
    elif mutation == "unexpected_seed":
        result["trials"][0]["seed"] += 1
    elif mutation == "empty_curve":
        result["trials"][0]["curve"] = []
    else:
        result["trials"][0]["curve"][-1]["n_questions"] -= 1
    with pytest.raises(ValueError, match=error):
        benchmark.paired_difference_rows(result)


def test_single_cell_comparison_exports_header_without_invented_contrasts(
    tiny_outputs, tmp_path,
):
    _, output_dir, _ = tiny_outputs
    result = read_results(output_dir)["gaussian_gap"]
    result["config"]["model_names"] = ["gaussian_linear"]
    result["config"]["policy_names"] = ["random"]
    result["trials"] = [
        t for t in result["trials"]
        if t["model_name"] == "gaussian_linear" and t["policy_name"] == "random"
    ]
    rows = benchmark.paired_difference_rows(result)
    assert rows == []
    path = tmp_path / "paired.csv"
    benchmark.write_csv(path, rows, benchmark.PAIRED_COLUMNS)
    assert path.read_text(encoding="utf-8") == ",".join(benchmark.PAIRED_COLUMNS) + "\n"


@pytest.mark.parametrize("mutation", ["drop", "duplicate"])
def test_incomplete_common_checkpoints_are_rejected(tiny_outputs, mutation):
    _, output_dir, _ = tiny_outputs
    result = read_results(output_dir)["gaussian_gap"]
    if mutation == "drop":
        result["trials"][0]["curve"].pop()
    else:
        result["trials"][0]["curve"][1]["n_questions"] = 0
    with pytest.raises(ValueError, match="complete common question checkpoints"):
        benchmark.comparison_rows(result)


@pytest.mark.parametrize("scenario,parameters", [
    ("unknown_scenario", {}),
    ("sloppy", {"noise_std": -0.1}),
])
def test_invalid_later_scenario_is_rejected_before_any_comparison(
    tiny_settings, tmp_path, monkeypatch, scenario, parameters
):
    tiny_settings["response_scenarios"][scenario] = parameters
    calls = []
    monkeypatch.setattr(benchmark, "run_comparison", lambda *args: calls.append(args))
    output_dir = tmp_path / "invalid"
    with pytest.raises(ValueError):
        benchmark.run_benchmark(tiny_settings, output_dir)
    assert calls == []
    assert not output_dir.exists()


def test_question_budget_uses_the_evaluators_rounded_holdout_count(tiny_settings):
    # 630 * .201 = 126.63: the evaluator withholds 127, leaving only 503.
    tiny_settings["evaluation"].update(holdout_fraction=0.201, n_questions=504)
    with pytest.raises(ValueError, match="question budget exceeds eligible pair count"):
        benchmark.prepare_comparisons(tiny_settings)


def test_existing_generated_output_refused_without_compute_or_changes(
    tiny_outputs, monkeypatch
):
    settings, output_dir, _ = tiny_outputs
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    calls = []
    monkeypatch.setattr(benchmark, "run_comparison", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="already exist"):
        benchmark.run_benchmark(copy.deepcopy(settings), output_dir)
    assert calls == []
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == before


def test_output_directory_creation_failure_precedes_expensive_work(
    tiny_settings, tmp_path, monkeypatch,
):
    output_dir = tmp_path / "cannot_create"
    calls = []
    original_mkdir = Path.mkdir

    def refuse_output(path, *args, **kwargs):
        if path == output_dir:
            raise PermissionError("output directory is not writable")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse_output)
    monkeypatch.setattr(benchmark, "run_comparison", lambda *args: calls.append(args))
    with pytest.raises(PermissionError, match="not writable"):
        benchmark.run_benchmark(tiny_settings, output_dir)
    assert calls == []
