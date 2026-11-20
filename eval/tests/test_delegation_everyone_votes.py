"""Tests for demo 5's everyone-votes reference point, eval/benchmarks/delegation_everyone_votes_v1/."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
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


# ---------------------------------------------------------------------------
# The published benchmark
# ---------------------------------------------------------------------------

BENCHMARK = everyone.DEFAULT_OUT
RUN_COMMIT = "770f413ac350ac0b79662d974e00d0c1e7d2f137"
needs_cities = pytest.mark.skipif(
    not everyone.has_cities(BENCHMARK), reason="the city records are kept out of the repository"
)


def _sha256(path: Any) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _published(name: str, key: str) -> dict[str, dict[str, str]]:
    with (BENCHMARK / name).open(encoding="utf-8", newline="") as handle:
        return {r[key]: r for r in csv.DictReader(handle)}


class TestPublishedFiles:
    def test_every_file_matches_its_recorded_hash(self) -> None:
        outputs = json.loads((BENCHMARK / everyone.METADATA).read_text(encoding="utf-8"))["outputs"]
        assert set(outputs) == {everyone.CITIES, MANIFEST, everyone.MEASURES, everyone.CONTRASTS_CSV, everyone.CAP_CSV}
        for name, digest in outputs.items():
            if name == everyone.CITIES and not (BENCHMARK / name).exists():
                continue
            assert _sha256(BENCHMARK / name) == digest, name

    def test_the_city_records_are_not_committed(self) -> None:
        assert everyone.CITIES in (BENCHMARK / ".gitignore").read_text(encoding="utf-8").splitlines()

    def test_without_the_city_records_every_committed_file_is_still_checked(self, tmp_path: Any) -> None:
        copy_dir = tmp_path / "benchmark"
        shutil.copytree(BENCHMARK, copy_dir, ignore=shutil.ignore_patterns(everyone.CITIES))
        assert everyone.verify(copy_dir) == []
        (copy_dir / everyone.CAP_CSV).write_bytes(b"tampered\n")
        assert everyone.verify(copy_dir) == [f"{everyone.CAP_CSV} does not match its recorded hash"]

    def test_the_run_is_the_declared_run_from_its_commit(self) -> None:
        recorded = json.loads((BENCHMARK / MANIFEST).read_text(encoding="utf-8"))
        check_manifest(recorded)
        assert recorded["commit"] == RUN_COMMIT

    def test_the_summaries_were_built_by_the_current_code(self) -> None:
        recorded = json.loads((BENCHMARK / everyone.METADATA).read_text(encoding="utf-8"))
        for source, digest in recorded["source_sha256_lf_normalized"].items():
            data = (everyone.ROOT / source).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(data).hexdigest() == digest, f"{source} changed: republish the benchmark"

    def test_the_setting_holds_in_the_published_measures(self) -> None:
        assert everyone.setting_problems(BENCHMARK) == []

    @needs_cities
    def test_the_summaries_rebuild_from_the_city_records(self) -> None:
        for name, data in everyone.build(BENCHMARK).items():
            assert (BENCHMARK / name).read_bytes() == data, name


class TestReadmeReadings:
    """The README's statements, read again from the published summaries."""

    @pytest.mark.parametrize(
        ("arrangement", "name", "value"),
        [
            ("representative", "fidelity", 0.633),
            ("proxy", "fidelity", 0.790),
            ("liquid", "fidelity", 0.810),
            ("proxy", "overhead", 0.106),
            ("liquid", "overhead", 0.183),
            ("liquid", "mean_largest_share", 0.103),
            ("liquid", "max_largest_share", 0.165),
            ("representative", "share_below_half", 0.136),
            ("liquid", "outcome_agreement", 0.923),
            ("representative", "outcome_agreement", 0.831),
        ],
    )
    def test_quoted_measures(self, arrangement: str, name: str, value: float) -> None:
        assert float(_published(everyone.MEASURES, "arrangement")[arrangement][name]) == pytest.approx(
            value, abs=5e-4
        )

    def test_all_of_liquids_overhead_is_loops(self) -> None:
        liquid = _published(everyone.MEASURES, "arrangement")["liquid"]
        assert float(liquid["loop_share"]) == pytest.approx(float(liquid["overhead"]), abs=1e-9)

    def test_no_citys_liquid_meets_the_cap(self) -> None:
        cap = _published(everyone.CAP_CSV, "arrangement")
        assert (cap["liquid"]["meets_cap"], cap["proxy"]["meets_cap"]) == ("0", "114")

    def test_the_ladder(self) -> None:
        contrasts = {k: float(r["estimate"]) for k, r in _published(everyone.CONTRASTS_CSV, "quantity").items()}
        assert contrasts["h1"] == pytest.approx(0.178, abs=5e-4)
        assert contrasts["specialisation"] == pytest.approx(0.020, abs=5e-4)
        assert contrasts["choice_by_non_voters"] == 0.0
        steps = (
            -contrasts["platform_against_record"]
            + contrasts["cost_of_sharing"]
            + contrasts["choice_by_non_voters"]
            + contrasts["city_wide_proxy_combined"]
            + contrasts["specialisation"]
        )
        assert steps == pytest.approx(contrasts["h1"], abs=5e-6)


def test_the_manifest_records_the_declared_analysis() -> None:
    value = manifest(CLEAN)
    assert value["label"] == "exploratory"
    assert value["setting"] == "everyone votes"
    assert value["turnout_policy"] == {"office_rate": 1.0, "resolver_turnout": 1.0}
    json.dumps(value)
    assert MANIFEST == "manifest.json"
