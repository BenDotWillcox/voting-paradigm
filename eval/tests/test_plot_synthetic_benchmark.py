"""Numeric pooling and real-result smoke checks for static benchmark figures."""

import copy
import gzip
import hashlib
import json
from math import log
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pytest

from eval import plot_synthetic_benchmark as plots
from eval.personas import DEFAULT_PERSONAS
from eval.preference_eval import EvalConfig, run_comparison


@pytest.fixture(scope="module")
def tiny_results():
    return {
        scenario: run_comparison(
            EvalConfig(n_questions=1, n_seeds=1, base_seed=17, response_model=scenario),
            personas=DEFAULT_PERSONAS[:1],
        )
        for scenario in plots.SCENARIOS
    }


def write_results(directory, results):
    for scenario, result in results.items():
        path = directory / f"{scenario}.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as target:
            json.dump(result, target, allow_nan=False)


@pytest.fixture
def small_publication(tiny_results, tmp_path, monkeypatch):
    """Exercise real PNG publication without repeatedly rendering large panels."""
    def make_draw(name):
        def draw(results):
            figure, ax = plt.subplots(figsize=(1, 1))
            ax.plot([0, 1], [0, 1], color=plots.MODELS["gaussian_linear"][1])
            return figure

        draw.__name__ = name
        return draw

    write_results(tmp_path, tiny_results)
    for name in ("learning_curves", "final_reliability", "final_spread"):
        monkeypatch.setattr(plots, name, make_draw(name))
    paths = plots.render_benchmark(tmp_path) + [tmp_path / "figures.json"]
    original_bytes = {path.name: path.read_bytes() for path in paths}
    manifest = json.loads(original_bytes["figures.json"])
    assert manifest["png_sha256"] == {
        name: hashlib.sha256(data).hexdigest()
        for name, data in original_bytes.items() if name.endswith(".png")
    }
    label, _, marker = plots.MODELS["gaussian_linear"]
    monkeypatch.setitem(plots.MODELS, "gaussian_linear", (label, "#FF0000", marker))
    return original_bytes


def test_reliability_pools_by_counts_and_omits_empty_bins():
    def bin_(lo, hi, n, confidence, accuracy):
        return {"lo": lo, "hi": hi, "n": n, "mean_confidence": confidence,
                "latent_direction_accuracy": accuracy}

    trials = [
        {"latent_direction_reliability": [bin_(0.5, 0.6, 1, 0.51, 0),
                                          bin_(0.6, 0.7, 0, None, None)]},
        {"latent_direction_reliability": [bin_(0.5, 0.6, 9, 0.59, 1),
                                          bin_(0.6, 0.7, 0, None, None)]},
    ]
    pooled = plots.pool_reliability(trials)
    assert len(pooled) == 1
    assert pooled[0]["n"] == 10
    assert pooled[0]["mean_confidence"] == pytest.approx(0.582)
    assert pooled[0]["latent_direction_accuracy"] == pytest.approx(0.9)
    assert plots.pool_reliability([]) == []


@pytest.mark.parametrize("last", [0, 1, 25, 26])
def test_question_ticks_include_prior_and_final_without_clutter(last):
    ticks = plots._question_ticks(last)
    assert ticks[0] == 0 and ticks[-1] == last
    assert ticks == sorted(set(ticks))
    assert len(ticks) <= 7


def test_marker_area_uses_fixed_bounded_log_count_scale():
    assert plots._reliability_marker_area(1) == 20
    assert plots._reliability_marker_area(100) == pytest.approx(
        12 + 8 * np.log2(101)
    )
    assert plots._reliability_marker_area(10**9) == 120
    assert (plots._reliability_marker_area(1)
            < plots._reliability_marker_area(100)
            < plots._reliability_marker_area(1000))


@pytest.mark.parametrize("draw,axes_count", [
    (plots.learning_curves, 12), (plots.final_reliability, 6), (plots.final_spread, 12),
])
def test_real_result_figures_have_expected_axes_and_visible_data(
    tiny_results, draw, axes_count,
):
    fig = draw(tiny_results)
    try:
        assert len(fig.axes) == axes_count
        fig.canvas.draw()
        for ax in fig.axes[:3]:
            assert "1 synthetic profiles × 1 seeds; 1 trials/cell" in ax.get_title()
            assert "1 questions at final state" in ax.get_title()
        for ax in fig.axes:
            assert ax.has_data()
            assert all(np.isfinite(line.get_ydata()).all() for line in ax.lines)
        if draw is plots.learning_curves:
            assert [len(ax.lines) for ax in fig.axes] == [7] * 6 + [6] * 6
            assert all(list(ax.get_xticks()) == [0, 1] for ax in fig.axes)
            for row in range(4):
                row_axes = fig.axes[row * 3:(row + 1) * 3]
                assert len({ax.get_ylim() for ax in row_axes}) == 1
        elif draw is plots.final_reliability:
            assert all(len(ax.lines) == 4 for ax in fig.axes)
            assert all(len(ax.collections) == 3 for ax in fig.axes)
            for index, (model, policy) in enumerate(plots.CELLS):
                trial = next(
                    t for t in tiny_results["gaussian_gap"]["trials"]
                    if (t["model_name"], t["policy_name"]) == (model, policy)
                )
                line = fig.axes[3 * (index // 3)].lines[1 + index % 3]
                assert len(line.get_xdata()) == sum(
                    b["n"] > 0 for b in trial["latent_direction_reliability"]
                )
                points = fig.axes[3 * (index // 3)].collections[index % 3]
                expected_sizes = [
                    plots._reliability_marker_area(b["n"])
                    for b in trial["latent_direction_reliability"] if b["n"] > 0
                ]
                assert points.get_sizes() == pytest.approx(expected_sizes)
        else:
            assert all(len(ax.patches) == 6 for ax in fig.axes)
            notes = " ".join(text.get_text() for text in fig.texts)
            assert "not confidence intervals" in notes
    finally:
        plt.close(fig)


@pytest.mark.parametrize("draw", [plots.learning_curves, plots.final_spread])
def test_score_axes_include_all_trial_states_and_the_uniform_prior(
    tiny_results, draw,
):
    results = copy.deepcopy(tiny_results)
    # These intermediate raw observations are absent from the summary means.
    point = results["sloppy"]["trials"][0]["curve"][0]
    point["latent_direction_log_score"] = -1.3
    point["latent_direction_brier"] = 0.46
    fig = draw(results)
    try:
        for row, (metric, prior) in enumerate([
            ("latent_direction_log_score", -log(2)),
            ("latent_direction_brier", 0.25),
        ]):
            values = [prior] + [
                p[metric] for result in results.values()
                for trial in result["trials"] for p in trial["curve"]
            ]
            minimum, maximum = min(values), max(values)
            margin = max(0.005, (maximum - minimum) * 0.05)
            for ax in fig.axes[row * 3:(row + 1) * 3]:
                lo, hi = ax.get_ylim()
                assert (lo, hi) == pytest.approx(
                    (minimum - margin, maximum + margin)
                )
                assert lo < minimum <= prior <= maximum < hi
                references = [
                    line for line in ax.lines if line.get_label() == "_uniform_prior"
                ]
                assert len(references) == 1
                assert list(references[0].get_ydata()) == pytest.approx([prior, prior])
        assert all(ax.get_ylim() == (0, 1) for ax in fig.axes[6:9])
        assert all(ax.get_ylim() == (-1, 1) for ax in fig.axes[9:12])
        notes = " ".join(text.get_text() for text in fig.texts)
        assert "focused shared scales" in notes
        assert "gray dashed lines show the uniform prior" in notes
    finally:
        plt.close(fig)


def test_spread_model_labels_are_centered_on_data_positions(tiny_results):
    fig = plots.final_spread(tiny_results)
    try:
        for ax in fig.axes[-3:]:
            assert ax.get_xlabel() == ""
            assert [text.get_text() for text in ax.texts] == [
                "Gaussian", "Bradley-Terry"
            ]
            assert [text.get_position()[0] for text in ax.texts] == [2, 6]
            assert all(
                text.get_transform() == ax.get_xaxis_transform() for text in ax.texts
            )
    finally:
        plt.close(fig)


def test_cli_exports_three_pngs_without_open_figures(
    tiny_results, tmp_path, monkeypatch, capsys,
):
    write_results(tmp_path, tiny_results)
    monkeypatch.setattr(sys, "argv", ["plot_synthetic_benchmark", str(tmp_path)])
    plots.main()
    first_bytes = {}
    for name in ("learning_curves", "final_reliability", "final_spread"):
        path = tmp_path / f"{name}.png"
        first_bytes[path.name] = path.read_bytes()
        image = plt.imread(path)
        assert image.shape[0] >= 1000 and image.shape[1] >= 1500
        assert image[:, :, :3].std() > 0.05
    assert len(capsys.readouterr().out.splitlines()) == 3
    assert not plt.get_fignums()
    manifest_path = tmp_path / "figures.json"
    first_bytes[manifest_path.name] = manifest_path.read_bytes()
    manifest = json.loads(first_bytes[manifest_path.name])
    assert manifest["figure_manifest_version"] == 1
    assert manifest["input_sha256"] == {
        f"{scenario}.json.gz": hashlib.sha256(
            (tmp_path / f"{scenario}.json.gz").read_bytes()
        ).hexdigest()
        for scenario in plots.SCENARIOS
    }
    assert manifest["png_sha256"] == {
        name: hashlib.sha256(data).hexdigest()
        for name, data in first_bytes.items() if name.endswith(".png")
    }
    assert manifest["source_sha256"] == {
        "eval/plot_synthetic_benchmark.py": hashlib.sha256(
            Path(plots.__file__).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
    }
    assert set(manifest["environment"]) == {"python", "matplotlib", "numpy"}
    assert all(manifest["environment"].values())
    plots.render_benchmark(tmp_path)
    assert all(
        (tmp_path / name).read_bytes() == data for name, data in first_bytes.items()
    )
    assert not plt.get_fignums()


@pytest.mark.parametrize("existing_publication", [False, True])
def test_render_rejects_input_drift_without_touching_published_files(
    small_publication, tmp_path, monkeypatch, existing_publication,
):
    original_bytes = small_publication if existing_publication else {}
    if not existing_publication:
        for name in small_publication:
            (tmp_path / name).unlink()
    original_draw = plots.final_spread

    def changing_draw(results):
        figure = original_draw(results)
        path = tmp_path / "sloppy.json.gz"
        path.write_bytes(path.read_bytes() + b"changed")
        return figure

    changing_draw.__name__ = "final_spread"
    monkeypatch.setattr(plots, "final_spread", changing_draw)
    with pytest.raises(ValueError, match="changed during rendering"):
        plots.render_benchmark(tmp_path)
    for name in small_publication:
        path = tmp_path / name
        if name in original_bytes:
            assert path.read_bytes() == original_bytes[name]
        else:
            assert not path.exists()
    assert not (tmp_path / ".figures.json.tmp").exists()
    assert not plt.get_fignums()


@pytest.mark.parametrize("failure_stage", ["draw", "save"])
def test_late_render_failure_preserves_the_entire_previous_publication(
    small_publication, tmp_path, monkeypatch, failure_stage,
):
    original_draw = plots.final_spread

    def fail(*args, **kwargs):
        raise OSError("third figure could not render")

    def failing_draw(results):
        if failure_stage == "draw":
            fail()
        figure = original_draw(results)
        monkeypatch.setattr(figure, "savefig", fail)
        return figure

    failing_draw.__name__ = "final_spread"
    monkeypatch.setattr(plots, "final_spread", failing_draw)
    with pytest.raises(OSError, match="third figure could not render"):
        plots.render_benchmark(tmp_path)
    assert all(
        (tmp_path / name).read_bytes() == data
        for name, data in small_publication.items()
    )
    assert not (tmp_path / ".figures.json.tmp").exists()
    assert not plt.get_fignums()


@pytest.mark.parametrize("failure_stage", ["png_write", "manifest_replace"])
def test_publication_failure_invalidates_the_manifest_and_cleans_staging(
    small_publication, tmp_path, monkeypatch, failure_stage,
):
    original_write = Path.write_bytes
    original_replace = Path.replace

    def failing_write(path, data):
        if path == tmp_path / "final_reliability.png":
            raise OSError("publication write failed")
        return original_write(path, data)

    def failing_replace(path, target):
        if path == tmp_path / ".figures.json.tmp":
            raise OSError("publication write failed")
        return original_replace(path, target)

    if failure_stage == "png_write":
        monkeypatch.setattr(Path, "write_bytes", failing_write)
    else:
        monkeypatch.setattr(Path, "replace", failing_replace)
    with pytest.raises(OSError, match="publication write failed"):
        plots.render_benchmark(tmp_path)
    assert (tmp_path / "learning_curves.png").read_bytes() != small_publication[
        "learning_curves.png"
    ]
    if failure_stage == "png_write":
        assert (tmp_path / "final_spread.png").read_bytes() == small_publication[
            "final_spread.png"
        ]
    assert not (tmp_path / "figures.json").exists()
    assert not (tmp_path / ".figures.json.tmp").exists()
    assert not plt.get_fignums()


def test_manifest_staging_failure_preserves_the_previous_publication(
    small_publication, tmp_path, monkeypatch,
):
    original_write = Path.write_bytes

    def failing_write(path, data):
        if path == tmp_path / ".figures.json.tmp":
            original_write(path, b"partial")
            raise OSError("manifest staging failed")
        return original_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write)
    with pytest.raises(OSError, match="manifest staging failed"):
        plots.render_benchmark(tmp_path)
    assert all(
        (tmp_path / name).read_bytes() == data
        for name, data in small_publication.items()
    )
    assert not (tmp_path / ".figures.json.tmp").exists()
    assert not plt.get_fignums()


def test_loader_rejects_empty_cell(tiny_results, tmp_path):
    results = copy.deepcopy(tiny_results)
    results["gaussian_gap"]["trials"].pop()
    write_results(tmp_path, results)
    with pytest.raises(ValueError, match="empty trial or curve"):
        plots.load_results(tmp_path)


def test_loader_rejects_misnamed_scenario(tiny_results, tmp_path):
    results = copy.deepcopy(tiny_results)
    results["gaussian_gap"]["config"]["response_model"] = "sloppy"
    write_results(tmp_path, results)
    with pytest.raises(ValueError, match="scenario does not match filename"):
        plots.load_results(tmp_path)
