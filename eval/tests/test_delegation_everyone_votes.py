"""Tests for demo 5's everyone-votes reference point, eval/benchmarks/delegation_everyone_votes_v1/."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import numpy as np
import pytest

from delegation.comparison import runner
from delegation.comparison.protocol import PRIMARY_CITIES, SWISS_MARKER
from delegation.comparison.runner import CONTRASTS
from delegation.comparison.sweeps import PRIMARY_POINT
from eval import delegation_everyone_votes as everyone
from eval.delegation_everyone_votes import (
    ARRANGEMENTS,
    MANIFEST,
    POINT,
    SETTING,
    EveryoneVotesError,
    cap_csv,
    check_manifest,
    check_rows,
    config,
    contrasts_csv,
    manifest,
    measures_csv,
    population,
    run,
)

CLEAN = runner.CodeState("0" * 40, False, None)
DIRTY = runner.CodeState("0" * 40, True, "ab" * 32)
PAIRS = 10


def _fake_city(position: int) -> dict[str, Any]:
    matches = {name: PAIRS if name in ("full_turnout", "direct") else 7 for name in ARRANGEMENTS}
    measure = {name: 0.5 for name in everyone.MEASURE_FIELDS}
    return {
        "point": POINT,
        "position": position,
        "seed": PRIMARY_POINT.config(position, SWISS_MARKER).seed,
        "setting": SETTING,
        "pairs": PAIRS,
        "matches": matches,
        "uncast": {name: 0 for name in ARRANGEMENTS},
        "attribution": {},
        "liquid_meets_cap": position % 2 == 0,
        "proxy_meets_cap": True,
        "liquid_acceptance": {"feasible": position % 2 == 0},
        "proxy_acceptance": {"feasible": True},
        "measures": {name: {**measure, "fidelity": matches[name] / PAIRS} for name in ARRANGEMENTS},
    }


def _rows() -> list[dict[str, Any]]:
    return [_fake_city(p) for p in range(1, PRIMARY_CITIES + 1)]


class TestTheSetting:
    def test_only_turnout_changes_from_the_frozen_city(self) -> None:
        frozen = runner._population(PRIMARY_POINT.config(1, SWISS_MARKER))
        city = population(1)
        assert (city.turnout == 1.0).all()
        assert config(1).seed == PRIMARY_POINT.config(1, SWISS_MARKER).seed
        assert city.ids == frozen.ids
        assert np.array_equal(city.district, frozen.district)
        assert np.array_equal(city.positions, frozen.positions)
        assert np.array_equal(city.history.sincere, frozen.history.sincere)
        assert np.array_equal(city.evaluation.sincere, frozen.evaluation.sincere)
        assert np.array_equal(city.evaluation.dimension, frozen.evaluation.dimension)

    def test_every_resident_votes_in_the_history(self) -> None:
        city = population(1)
        assert (city.history.own_votes != everyone.NOT_CAST).all()


class TestRunning:
    def test_a_run_writes_each_city_and_resumes(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(everyone, "run_city", _fake_city)
        assert run(tmp_path, positions=[1, 2], state=CLEAN) == 2
        assert run(tmp_path, positions=[1, 2, 3], state=CLEAN) == 1
        assert sorted(int(r["position"]) for r in runner.load_records(tmp_path)) == [1, 2, 3]

    def test_an_uncommitted_checkout_is_refused(self, tmp_path: Any) -> None:
        with pytest.raises(EveryoneVotesError, match="uncommitted"):
            run(tmp_path, positions=[1], state=DIRTY)

    def test_a_resumed_run_must_be_the_same_run(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(everyone, "run_city", _fake_city)
        run(tmp_path, positions=[1], state=CLEAN)
        with pytest.raises(EveryoneVotesError, match="commit"):
            run(tmp_path, positions=[2], state=runner.CodeState("1" * 40, False, None))


class TestChecks:
    def test_every_declared_city_is_required(self) -> None:
        rows = _rows()
        check_rows(rows)
        with pytest.raises(EveryoneVotesError, match=f"{PRIMARY_CITIES - 1} of {PRIMARY_CITIES}"):
            check_rows(rows[:-1])

    def test_a_city_on_the_wrong_seed_is_refused(self) -> None:
        rows = _rows()
        rows[3]["seed"] += 1
        with pytest.raises(EveryoneVotesError, match="wrong seed"):
            check_rows(rows)

    def test_an_uncast_ballot_is_refused(self) -> None:
        rows = _rows()
        rows[5]["uncast"]["representative"] = 1
        with pytest.raises(EveryoneVotesError, match="uncast"):
            check_rows(rows)

    def test_direct_voting_must_be_full_turnout(self) -> None:
        rows = _rows()
        rows[7]["matches"]["direct"] = PAIRS - 1
        with pytest.raises(EveryoneVotesError, match="direct voting is not full turnout"):
            check_rows(rows)

    def test_only_a_committed_declared_run_is_published(self) -> None:
        check_manifest(manifest(CLEAN))
        with pytest.raises(EveryoneVotesError, match="committed"):
            check_manifest(manifest(DIRTY))
        with pytest.raises(EveryoneVotesError, match="turnout_policy"):
            check_manifest({**manifest(CLEAN), "turnout_policy": {"office_rate": 0.96, "resolver_turnout": 0.0}})


class TestSummaries:
    def test_measures_list_every_arrangement_in_order(self) -> None:
        rows = list(csv.DictReader(io.StringIO(measures_csv(_rows()).decode("utf-8"))))
        assert [r["arrangement"] for r in rows] == list(ARRANGEMENTS)
        assert float(rows[1]["fidelity"]) == 1.0
        assert rows[1]["fidelity_lower"] == rows[1]["fidelity_upper"] == rows[1]["fidelity"]

    def test_contrasts_are_the_frozen_runners(self) -> None:
        rows = list(csv.DictReader(io.StringIO(contrasts_csv(_rows()).decode("utf-8"))))
        assert [r["quantity"] for r in rows] == list(CONTRASTS)
        assert {r["quantity"]: (r["first"], r["second"]) for r in rows} == CONTRASTS

    def test_cap_counts_cities(self) -> None:
        rows = {r["arrangement"]: r for r in csv.DictReader(io.StringIO(cap_csv(_rows()).decode("utf-8")))}
        assert rows["liquid"]["meets_cap"] == str(PRIMARY_CITIES // 2)
        assert rows["proxy"]["history_feasible"] == str(PRIMARY_CITIES)


def test_the_manifest_records_the_declared_analysis() -> None:
    value = manifest(CLEAN)
    assert value["label"] == "exploratory"
    assert value["setting"] == "everyone votes"
    assert value["turnout_policy"] == {"office_rate": 1.0, "resolver_turnout": 1.0}
    json.dumps(value)
    assert MANIFEST == "manifest.json"
