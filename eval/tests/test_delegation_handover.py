"""Tests for demo 5's exploratory handover benchmark, eval/benchmarks/delegation_handover_v1/."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from delegation.comparison import runner
from delegation.comparison.protocol import PRIMARY_CITIES, TURNOUT_GRID
from delegation.comparison.sweeps import PRIMARY_POINT
from eval import delegation_handover as handover
from eval.delegation_handover import (
    CITIES,
    CURVE,
    DEFAULT_OUT,
    DEPTHS,
    FRONTIER,
    MANIFEST,
    METADATA,
    POINT,
    ROOT,
    SOURCES,
    WRONG_BALLOT,
    HandoverError,
    build,
    check_manifest,
    check_rows,
    depth_zero_problems,
    has_cities,
    manifest,
    run,
    verify,
    wrong_ballot,
)

CLEAN = runner.CodeState("0" * 40, False, None)
DIRTY = runner.CodeState("0" * 40, True, "ab" * 32)
BENCHMARK = DEFAULT_OUT
RUN_COMMIT = "1d92e08e2e553a96f9ffdce2fccfeb3e0fbcd173"

# The city records are not committed; the checks that read them run where
# they have been regenerated (python -m eval.delegation_handover publish)
needs_cities = pytest.mark.skipif(
    not has_cities(BENCHMARK), reason="the city records are kept out of the repository"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _fake_city(position: int) -> dict[str, Any]:
    levels: dict[str, Any] = {}
    for level in TURNOUT_GRID:
        config = PRIMARY_POINT.config(position, level)
        levels[repr(level)] = {
            "seed": config.seed,
            "turnout_mean": config.turnout_mean,
            "pairs": 10,
            "direct_matches": 4,
            "depths": {str(d): {"matches": 4 if d == 0 else 5, "measures": {}} for d in DEPTHS},
        }
    return {"point": POINT, "position": position, "levels": levels}


class TestRunning:
    def test_a_run_writes_each_city_and_resumes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(handover, "run_city", _fake_city)
        assert run(tmp_path, positions=[1, 2], state=CLEAN) == 2
        assert run(tmp_path, positions=[1, 2, 3], state=CLEAN) == 1
        assert sorted(int(r["position"]) for r in runner.load_records(tmp_path)) == [1, 2, 3]

    def test_an_uncommitted_checkout_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(HandoverError, match="uncommitted"):
            run(tmp_path, positions=[1], state=DIRTY)

    def test_a_resumed_run_must_be_the_same_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(handover, "run_city", _fake_city)
        run(tmp_path, positions=[1], state=CLEAN)
        with pytest.raises(HandoverError, match="commit"):
            run(tmp_path, positions=[2], state=runner.CodeState("1" * 40, False, None))


class TestChecks:
    def test_every_declared_city_is_required(self) -> None:
        rows = [_fake_city(p) for p in range(1, PRIMARY_CITIES + 1)]
        check_rows(rows)
        with pytest.raises(HandoverError, match=f"{PRIMARY_CITIES - 1} of {PRIMARY_CITIES}"):
            check_rows(rows[:-1])

    def test_depth_zero_must_be_direct_voting(self) -> None:
        rows = [_fake_city(p) for p in range(1, PRIMARY_CITIES + 1)]
        rows[0]["levels"][repr(TURNOUT_GRID[0])]["depths"]["0"]["matches"] = 5
        with pytest.raises(HandoverError, match="depth 0 is not direct voting"):
            check_rows(rows)

    def test_a_city_on_the_wrong_seed_is_refused(self) -> None:
        rows = [_fake_city(p) for p in range(1, PRIMARY_CITIES + 1)]
        rows[3]["levels"][repr(TURNOUT_GRID[2])]["seed"] += 1
        with pytest.raises(HandoverError, match="wrong seed"):
            check_rows(rows)

    def test_only_a_committed_declared_run_is_published(self) -> None:
        check_manifest(manifest(CLEAN))
        with pytest.raises(HandoverError, match="committed"):
            check_manifest(manifest(DIRTY))
        with pytest.raises(HandoverError, match="depths"):
            check_manifest({**manifest(CLEAN), "depths": [0, 1]})


def test_wrong_ballot_scores_come_from_the_frozen_shares() -> None:
    rows = list(csv.DictReader(io.StringIO(wrong_ballot().decode("utf-8"))))
    assert len(rows) == len(TURNOUT_GRID) * len(handover.SCORED)
    at = {(r["level"], r["arrangement"]): r for r in rows}
    representative = at[("0.45", "representative")]
    assert float(representative["score_w0"]) == pytest.approx(0.60633, abs=1e-6)
    assert float(representative["score_w1"]) == pytest.approx(0.60633 - 0.35332, abs=2e-6)
    # Direct voting never casts a contrary ballot, so w changes nothing
    direct = at[("0.9", "direct")]
    assert direct["score_w0"] == direct["score_w1"]
    assert float(at[("0.45", "full_turnout")]["score_w1"]) == 1.0


def test_the_manifest_records_the_declared_analysis() -> None:
    value = manifest(CLEAN)
    assert value["label"] == "exploratory"
    assert value["depths"] == list(range(9))
    assert value["turnout_grid"] == list(TURNOUT_GRID)
    json.dumps(value)
    assert MANIFEST == "manifest.json"


# ---------------------------------------------------------------------------
# The published benchmark
# ---------------------------------------------------------------------------


def _curve() -> dict[tuple[float, int], dict[str, str]]:
    with (BENCHMARK / CURVE).open(encoding="utf-8", newline="") as handle:
        return {(float(r["level"]), int(r["depth"])): r for r in csv.DictReader(handle)}


def _along(curve: dict[tuple[float, int], dict[str, str]], level: float, name: str) -> list[float]:
    return [float(curve[(level, depth)][name]) for depth in DEPTHS]


class TestPublishedFiles:
    def test_every_file_matches_its_recorded_hash(self) -> None:
        outputs = json.loads((BENCHMARK / METADATA).read_text(encoding="utf-8"))["outputs"]
        assert set(outputs) == {CITIES, MANIFEST, CURVE, WRONG_BALLOT}
        for name, digest in outputs.items():
            if name == CITIES and not (BENCHMARK / name).exists():
                continue
            assert sha256(BENCHMARK / name) == digest, name

    def test_the_city_records_are_not_committed(self) -> None:
        assert CITIES in (BENCHMARK / ".gitignore").read_text(encoding="utf-8").splitlines()

    def test_without_the_city_records_every_committed_file_is_still_checked(self, tmp_path: Path) -> None:
        copy_dir = tmp_path / "benchmark"
        shutil.copytree(BENCHMARK, copy_dir, ignore=shutil.ignore_patterns(CITIES))
        assert not has_cities(copy_dir)
        assert verify(copy_dir) == []
        (copy_dir / WRONG_BALLOT).write_bytes(b"tampered\n")
        assert verify(copy_dir) == [f"{WRONG_BALLOT} does not match its recorded hash"]

    def test_the_run_is_the_declared_run_from_its_commit(self) -> None:
        recorded = json.loads((BENCHMARK / MANIFEST).read_text(encoding="utf-8"))
        check_manifest(recorded)
        assert recorded["commit"] == RUN_COMMIT
        assert recorded["label"] == "exploratory"

    def test_the_summaries_were_built_by_the_current_code(self) -> None:
        recorded = json.loads((BENCHMARK / METADATA).read_text(encoding="utf-8"))
        assert recorded["inputs"]["frontier measures.csv"] == sha256(FRONTIER / "measures.csv")
        assert set(recorded["source_sha256_lf_normalized"]) == set(SOURCES)
        for source, digest in recorded["source_sha256_lf_normalized"].items():
            assert lf_sha256(ROOT / source) == digest, f"{source} changed: republish the benchmark"

    def test_the_figure_is_drawn_from_the_published_summaries_by_the_current_code(self) -> None:
        figures = json.loads((BENCHMARK / "figures.json").read_text(encoding="utf-8"))
        inputs = {CURVE: BENCHMARK / CURVE, "frontier measures.csv": FRONTIER / "measures.csv"}
        assert set(figures["input_sha256"]) == set(inputs)
        for name, digest in figures["input_sha256"].items():
            assert sha256(inputs[name]) == digest, name
        for name, digest in figures["png_sha256"].items():
            assert sha256(BENCHMARK / name) == digest, name
        for source, digest in figures["source_sha256_lf_normalized"].items():
            assert lf_sha256(ROOT / source) == digest, f"{source} changed: redraw the figure"

    def test_depth_zero_reproduces_frozen_direct_voting(self) -> None:
        assert depth_zero_problems(BENCHMARK) == []

    @needs_cities
    def test_the_summaries_rebuild_from_the_city_records(self) -> None:
        for name, data in build(BENCHMARK).items():
            assert (BENCHMARK / name).read_bytes() == data, name


class TestReadmeReadings:
    """The README's statements, read again from curve.csv."""

    def test_overhead_falls_with_every_topic_handed_over(self) -> None:
        curve = _curve()
        for level in TURNOUT_GRID:
            overhead = _along(curve, level, "overhead")
            assert all(b < a for a, b in zip(overhead, overhead[1:], strict=False)), level

    def test_fidelity_rises_with_every_topic_up_to_0_7_and_falls_at_0_9(self) -> None:
        curve = _curve()
        for level in TURNOUT_GRID:
            fidelity = _along(curve, level, "fidelity")
            steps = [b - a for a, b in zip(fidelity, fidelity[1:], strict=False)]
            if level <= 0.7:
                assert all(step > 0 for step in steps), level
            if level == 0.9:
                assert all(step < 0 for step in steps)
        at_08 = _along(curve, 0.8, "fidelity")
        assert max(DEPTHS, key=lambda d: at_08[d]) == 2

    def test_the_intervals_at_depth_0_and_depth_8_do_not_overlap(self) -> None:
        curve = _curve()
        for level in TURNOUT_GRID:
            low, high = sorted((curve[(level, 0)], curve[(level, DEPTHS[-1])]), key=lambda r: float(r["fidelity"]))
            assert float(low["fidelity_upper"]) < float(high["fidelity_lower"]), level

    @pytest.mark.parametrize(
        ("level", "depth", "name", "value"),
        [
            (0.45, 8, "overhead", 0.052),
            (0.45, 8, "fidelity", 0.721),
            (0.45, 8, "contrary_share", 0.244),
            (0.45, 8, "fidelity_resolved", 0.729),
            (0.45, 4, "fidelity_resolved", 0.744),
            (0.8, 2, "fidelity", 0.807),
            (0.9, 8, "fidelity", 0.790),
            (0.1, 8, "overhead", 0.236),
            (0.2, 8, "overhead", 0.122),
            (0.9, 8, "overhead", 0.115),
        ],
    )
    def test_quoted_values(self, level: float, depth: int, name: str, value: float) -> None:
        assert float(_curve()[(level, depth)][name]) == pytest.approx(value, abs=5e-4)

    def test_the_calibrated_point_is_depth_8_where_no_level_meets_the_cap(self) -> None:
        curve = _curve()
        frozen = {(float(r["level"]), r["arrangement"]): r for r in handover._frontier_rows(FRONTIER)}
        for level in (0.1, 0.2, 0.9):
            for name in ("fidelity", "overhead"):
                deepest = float(curve[(level, DEPTHS[-1])][name])
                assert deepest == pytest.approx(float(frozen[(level, "liquid")][name]), abs=3e-4), (level, name)
