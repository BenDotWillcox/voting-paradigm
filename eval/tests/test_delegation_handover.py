"""Tests for demo 5's exploratory handover benchmark, eval/benchmarks/delegation_handover_v1/."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from delegation.comparison import runner
from delegation.comparison.protocol import PRIMARY_CITIES, TURNOUT_GRID
from delegation.comparison.sweeps import PRIMARY_POINT
from eval import delegation_handover as handover
from eval.delegation_handover import (
    DEPTHS,
    MANIFEST,
    POINT,
    HandoverError,
    check_manifest,
    check_rows,
    manifest,
    run,
    wrong_ballot,
)

CLEAN = runner.CodeState("0" * 40, False, None)
DIRTY = runner.CodeState("0" * 40, True, "ab" * 32)


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
