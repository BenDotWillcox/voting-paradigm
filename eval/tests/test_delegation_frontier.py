"""Tests for demo 5's published benchmark, eval/benchmarks/delegation_frontier_v1/."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from delegation.comparison import protocol, runner
from eval.delegation_frontier import (
    CITIES,
    FREEZE_COMMIT,
    MANIFEST,
    METADATA,
    MODES,
    PRIMARY_KEY,
    REPORTS,
    SUMMARIES,
    PublishError,
    _check_run,
    _num,
    _unpack,
    bands,
    has_cities,
    load_cities,
    load_report,
    publish,
    reanalyse,
    verify,
)

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "eval" / "benchmarks" / "delegation_frontier_v1"

# The city records are not committed; the checks that read them run where
# they have been regenerated (python -m eval.delegation_frontier publish)
needs_cities = pytest.mark.skipif(
    not has_cities(BENCHMARK), reason="the city records are kept out of the repository"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def primary() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((BENCHMARK / MANIFEST).read_text(encoding="utf-8"))["primary"]
    return manifest, load_report(BENCHMARK, "primary"), load_cities(BENCHMARK, "primary")


class TestPublishedFiles:
    def test_every_file_matches_its_recorded_hash(self) -> None:
        outputs = json.loads((BENCHMARK / METADATA).read_text(encoding="utf-8"))["outputs"]
        expected = {*CITIES.values(), *REPORTS.values(), MANIFEST, *SUMMARIES}
        assert set(outputs) == expected
        for name, digest in outputs.items():
            if name in CITIES.values() and not (BENCHMARK / name).exists():
                continue
            assert sha256(BENCHMARK / name) == digest, name

    def test_the_city_records_are_not_committed(self) -> None:
        ignore = (BENCHMARK / ".gitignore").read_text(encoding="utf-8")
        assert "*_cities.jsonl.gz" in ignore.splitlines()
        assert all(name.endswith("_cities.jsonl.gz") for name in CITIES.values())

    def test_without_the_city_records_every_committed_file_is_still_checked(self, tmp_path: Path) -> None:
        copy_dir = tmp_path / "benchmark"
        shutil.copytree(BENCHMARK, copy_dir, ignore=shutil.ignore_patterns("*_cities.jsonl.gz"))
        assert not has_cities(copy_dir)
        assert verify(copy_dir) == []
        (copy_dir / "thresholds.csv").write_bytes(b"tampered\n")
        assert verify(copy_dir) == ["thresholds.csv does not match its recorded hash"]

    def test_the_figures_are_drawn_from_the_published_summaries_by_the_current_code(self) -> None:
        figures = json.loads((BENCHMARK / "figures.json").read_text(encoding="utf-8"))
        for name, digest in figures["input_sha256"].items():
            assert sha256(BENCHMARK / name) == digest, name
        for name, digest in figures["png_sha256"].items():
            assert sha256(BENCHMARK / name) == digest, name
        for source, digest in figures["source_sha256_lf_normalized"].items():
            text = (ROOT / source).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(text).hexdigest() == digest, f"{source} changed: redraw the figures"

    def test_both_runs_are_the_frozen_runs(self) -> None:
        manifests = json.loads((BENCHMARK / MANIFEST).read_text(encoding="utf-8"))
        for mode in MODES:
            manifest = manifests[mode]
            assert manifest["commit"] == FREEZE_COMMIT
            assert manifest["dirty"] is False and manifest["diff_sha256"] is None
            assert manifest["runner_version"] == runner.RUNNER_VERSION
            assert manifest["protocol"]["frozen"] == protocol.PROTOCOL_FROZEN
            report = load_report(BENCHMARK, mode)
            assert report["manifest"] == manifest
            assert report["reanalysis"] is False
            assert report["missing_points"] == []

    def test_the_headline_is_the_frozen_verdict(self) -> None:
        threshold = load_report(BENCHMARK, "primary")["points"][PRIMARY_KEY]["threshold"]
        assert threshold["verdict"] == "overhead condition not met where liquid is ahead"
        assert threshold["bracket"] == [0.1, 0.2]
        assert threshold["confidence"] == [0.1, 0.3]
        assert threshold["gate_holds"] is False

    def test_the_summaries_rebuild_and_the_runs_check_out(self) -> None:
        assert verify(BENCHMARK, analyse=False) == []

    @needs_cities
    def test_every_verdict_is_reproduced_from_the_published_cities(self) -> None:
        # The current runner and protocol, reading the published cities
        # afresh, give exactly the published reports
        assert reanalyse(BENCHMARK) == []


@needs_cities
class TestPublish:
    def test_publishing_the_recorded_runs_reproduces_every_published_file(self, tmp_path: Path) -> None:
        runs = tmp_path / "runs"
        for mode in MODES:
            _unpack(BENCHMARK, mode, runs / mode)
            (runs / mode / "report.json").write_bytes(gzip.decompress((BENCHMARK / REPORTS[mode]).read_bytes()))
        out = tmp_path / "out"
        publish(runs, out)
        for name in (*CITIES.values(), *REPORTS.values(), MANIFEST, *SUMMARIES, METADATA):
            assert (out / name).read_bytes() == (BENCHMARK / name).read_bytes(), name

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("commit", "0" * 40, "commit"),
            ("dirty", True, "dirty"),
            ("diff_sha256", "ab" * 32, "diff_sha256"),
            ("runner_version", 2, "runner_version"),
        ],
    )
    def test_a_run_not_from_the_frozen_clean_commit_is_refused(
        self, primary: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]], field: str, value: Any, message: str
    ) -> None:
        manifest, report, rows = copy.deepcopy(primary)
        manifest[field] = value
        report["manifest"] = manifest
        with pytest.raises(PublishError, match=message):
            _check_run("primary", manifest, report, rows)

    def test_a_reanalysed_report_is_refused(
        self, primary: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]
    ) -> None:
        manifest, report, rows = copy.deepcopy(primary)
        report["reanalysis"] = True
        with pytest.raises(PublishError, match="own analysis"):
            _check_run("primary", manifest, report, rows)

    def test_a_report_for_another_manifest_is_refused(
        self, primary: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]
    ) -> None:
        manifest, report, rows = copy.deepcopy(primary)
        report["manifest"] = {**manifest, "numpy": "0.0"}
        with pytest.raises(PublishError, match="manifest"):
            _check_run("primary", manifest, report, rows)

    def test_a_run_missing_a_city_is_refused(
        self, primary: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]
    ) -> None:
        manifest, report, rows = copy.deepcopy(primary)
        with pytest.raises(PublishError, match="199 of 200"):
            _check_run("primary", manifest, report, rows[:-1])


@needs_cities
class TestBands:
    def test_the_recomputed_band_gives_the_recorded_confidence_set(
        self, primary: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]
    ) -> None:
        _, report, rows = primary
        reading = report["points"][PRIMARY_KEY]
        band = bands(rows, PRIMARY_KEY, reading)
        low, high = band["all_cities"]
        estimates = [reading["by_level"][repr(level)]["h1"]["all_cities"]["estimate"] for level in reading["levels"]]
        assert all(lo <= est <= hi for lo, est, hi in zip(low, estimates, high, strict=True))

    def test_a_band_that_does_not_give_the_recorded_set_is_an_error(
        self, primary: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]
    ) -> None:
        _, report, rows = primary
        reading = copy.deepcopy(report["points"][PRIMARY_KEY])
        reading["threshold"]["band_critical"] = "inf"
        with pytest.raises(PublishError, match="recomputed band"):
            bands(rows, PRIMARY_KEY, reading)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, ""),
        (True, "true"),
        (200, "200"),
        (0.1, "0.1"),
        (0.10230125, "0.102301"),
        (-1e-9, "0"),
        (float("inf"), "inf"),
        ("-inf", "-inf"),
    ],
)
def test_summary_numbers(value: Any, text: str) -> None:
    assert _num(value) == text
