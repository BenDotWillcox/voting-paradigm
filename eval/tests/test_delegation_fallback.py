"""
Tests for demo 5's fallback study (R2), eval/delegation_fallback.py. The
rule is checked on development cities only (seeds outside the primary
namespace), never on the declared 200.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from delegation.comparison import PopulationConfig, compare, runner
from delegation.comparison.arrangements import DIAL_TURNOUT
from delegation.comparison.population import NOT_CAST, simulate_population
from delegation.comparison.protocol import DEVELOPMENT_SEEDS, PRIMARY_CITIES, TURNOUT_GRID
from delegation.comparison.sweeps import PRIMARY_POINT
from eval import delegation_fallback as fallback
from eval.delegation_fallback import (
    ARRANGEMENTS,
    DEFAULT_ARRANGEMENT,
    POINT,
    FallbackError,
    check_manifest,
    check_rows,
    hypothesis,
    manifest,
    run,
    with_default,
)

CLEAN = runner.CodeState("0" * 40, False, None)
DIRTY = runner.CodeState("0" * 40, True, "ab" * 32)


@pytest.fixture(scope="module", params=[(1, 0.1), (2, 0.45), (3, 0.9)], ids=["low", "swiss", "high"])
def city(request: pytest.FixtureRequest) -> tuple[Any, Any, Any, Any]:
    seed, level = request.param
    assert seed in DEVELOPMENT_SEEDS
    population = simulate_population(PopulationConfig(seed=seed, turnout_mean=level))
    result = compare(population, DIAL_TURNOUT, 0.10)
    liquid, representative = result.outcomes["liquid"], result.outcomes["representative"]
    return population, liquid, representative, with_default(population, liquid, representative)


class TestTheDefault:
    def test_only_loop_members_keep(self, city: tuple[Any, Any, Any, Any]) -> None:
        _, liquid, _, defaulted = city
        assert (defaulted.kept == (liquid.kept & liquid.looped)).all()
        assert (defaulted.kept == liquid.looped).all()

    def test_no_one_decides_alone_for_want_of_a_delegate(self, city: tuple[Any, Any, Any, Any]) -> None:
        population, liquid, representative, defaulted = city
        voters = np.arange(population.size)[:, None]
        # Deciding one's own vote now means being on a loop, or being the representative
        alone = (defaulted.resolver == voters) & ~liquid.looped & (representative.resolver != voters)
        assert not alone.any()

    def test_delegations_are_unchanged_where_a_ballot_was_cast(self, city: tuple[Any, Any, Any, Any]) -> None:
        _, liquid, _, defaulted = city
        cast_delegated = ~liquid.kept & (liquid.counted != NOT_CAST)
        assert np.array_equal(defaulted.resolver[cast_delegated], liquid.resolver[cast_delegated])
        assert np.array_equal(defaulted.counted[cast_delegated], liquid.counted[cast_delegated])

    def test_a_vote_left_uncast_is_the_representatives(self, city: tuple[Any, Any, Any, Any]) -> None:
        _, _, representative, defaulted = city
        uncast = defaulted.counted == NOT_CAST
        assert np.array_equal(defaulted.resolver[uncast], representative.resolver[uncast])

    def test_fewer_ballots_go_missing(self, city: tuple[Any, Any, Any, Any]) -> None:
        _, liquid, _, defaulted = city
        assert (defaulted.counted == NOT_CAST).sum() < (liquid.counted == NOT_CAST).sum()

    def test_the_record_reports_every_arrangement(self, city: tuple[Any, Any, Any, Any]) -> None:
        population = city[0]
        record = fallback.evaluate(population)
        assert list(record["measures"]) == list(ARRANGEMENTS)
        assert record["measures"][DEFAULT_ARRANGEMENT]["arrangement"] == DEFAULT_ARRANGEMENT

    def test_a_recount_that_differs_from_the_frozen_outcome_is_refused(self, city: tuple[Any, Any, Any, Any]) -> None:
        population, liquid, representative, _ = city
        tampered = np.array(liquid.counted, copy=True)
        tampered[0, 0] = NOT_CAST if tampered[0, 0] != NOT_CAST else 1
        from dataclasses import replace

        with pytest.raises(FallbackError, match="recount"):
            with_default(population, replace(liquid, counted=tampered), representative)


def _fake_city(position: int, lead: float = 0.05, meets: bool = True) -> dict[str, Any]:
    levels: dict[str, Any] = {}
    for level in TURNOUT_GRID:
        config = PRIMARY_POINT.config(position, level)
        # A little spread so the t-intervals are finite
        wobble = (position % 5) - 2
        levels[repr(level)] = {
            "seed": config.seed,
            "turnout_mean": config.turnout_mean,
            "pairs": 1000,
            "matches": {
                "representative": 600,
                "liquid": 550,
                DEFAULT_ARRANGEMENT: int(600 + 1000 * lead) + wobble,
            },
            "meets_cap": {"liquid": False, DEFAULT_ARRANGEMENT: meets},
            "measures": {name: {} for name in ARRANGEMENTS},
        }
    return {"point": POINT, "position": position, "levels": levels}


def _rows(**kw: Any) -> list[dict[str, Any]]:
    return [_fake_city(p, **kw) for p in range(1, PRIMARY_CITIES + 1)]


class TestTheHypothesisReading:
    def test_a_lead_under_the_cap_supports_it(self) -> None:
        assert hypothesis(_rows())["outcome"] == "supported"

    def test_no_lead_does_not_support_it(self) -> None:
        reading = hypothesis(_rows(lead=-0.05))
        assert reading["outcome"] == "not supported: no lead at the low levels"
        assert [lv["leads"] for lv in reading["levels"]] == [False, False, False]

    def test_a_lead_over_the_cap_does_not_support_it(self) -> None:
        reading = hypothesis(_rows(meets=False))
        assert reading["outcome"] == "not supported: overhead condition not met where liquid leads"

    def test_it_reads_only_the_low_levels(self) -> None:
        assert [lv["level"] for lv in hypothesis(_rows())["levels"]] == [0.1, 0.2, 0.3]


class TestRunning:
    def test_a_run_writes_each_city_and_resumes(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fallback, "run_city", _fake_city)
        assert run(tmp_path, positions=[1, 2], state=CLEAN) == 2
        assert run(tmp_path, positions=[1, 2, 3], state=CLEAN) == 1

    def test_an_uncommitted_checkout_is_refused(self, tmp_path: Any) -> None:
        with pytest.raises(FallbackError, match="uncommitted"):
            run(tmp_path, positions=[1], state=DIRTY)

    def test_every_declared_city_is_required(self) -> None:
        rows = _rows()
        check_rows(rows)
        with pytest.raises(FallbackError, match=f"{PRIMARY_CITIES - 1} of {PRIMARY_CITIES}"):
            check_rows(rows[:-1])

    def test_a_city_on_the_wrong_seed_is_refused(self) -> None:
        rows = _rows()
        rows[3]["levels"]["0.2"]["seed"] += 1
        with pytest.raises(FallbackError, match="wrong seed"):
            check_rows(rows)

    def test_only_a_committed_declared_run_is_published(self) -> None:
        check_manifest(manifest(CLEAN))
        with pytest.raises(FallbackError, match="committed"):
            check_manifest(manifest(DIRTY))
        assert manifest(CLEAN)["label"] == "exploratory"
