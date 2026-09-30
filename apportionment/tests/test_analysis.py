"""Tests for the analyses behind the apportionment essay."""

from __future__ import annotations

import pytest

from apportionment import (
    US_2020_APPORTIONMENT_POPULATIONS as POPULATIONS,
    US_2020_KNOWN_APPORTIONMENT,
    apportion,
)
from apportionment.analysis import (
    allocation_race,
    article_one_max_size,
    award_order,
    cube_root_size,
    house_size_rules,
    house_size_sweep,
    seats_at,
    wyoming_rule_size,
)

MINNESOTA, NEW_YORK, OHIO = "27", "36", "39"
DELAWARE, MONTANA = "10", "30"


class TestRuleDefinedHouseSizes:
    def test_wyoming_rule_uses_apportionment_populations(self):
        # 331,108,434 / 577,719 (Wyoming's apportionment population) = 573.1
        assert wyoming_rule_size(POPULATIONS) == 573

    def test_cube_root(self):
        assert cube_root_size(POPULATIONS) == 692

    def test_article_one_limit_rounds_down(self):
        # 331,108,434 / 30,000 = 11,036.9; 11,037 would exceed the ratio.
        assert article_one_max_size(POPULATIONS) == 11_036
        assert 11_036 * 30_000 <= sum(POPULATIONS.values()) < 11_037 * 30_000

    def test_rules_are_ascending(self):
        sizes = [rule.seats for rule in house_size_rules(POPULATIONS)]
        assert sizes == sorted(sizes) and sizes[0] == 435


class TestAwardOrder:
    def test_prefix_reproduces_2020(self):
        order = award_order(POPULATIONS, 435)
        assert seats_at(order, POPULATIONS, 435) == US_2020_KNOWN_APPORTIONMENT

    @pytest.mark.parametrize("size", [51, 574, 692, 1_000, 5_000])
    def test_prefix_matches_direct_apportionment(self, size):
        order = award_order(POPULATIONS, 5_000)
        assert seats_at(order, POPULATIONS, size) == apportion(POPULATIONS, size)


class TestAllocationRace:
    def test_seat_435_goes_to_minnesota_with_new_york_next(self):
        last = allocation_race(POPULATIONS, 435)[-1]
        assert last.seat_number == 435
        assert last.winner == MINNESOTA and last.winner_new_seats == 8
        assert [c.fips for c in last.leaders[:3]] == [MINNESOTA, NEW_YORK, OHIO]

    def test_winners_match_award_order(self):
        race = allocation_race(POPULATIONS, 435)
        assert [step.winner for step in race] == award_order(POPULATIONS, 435)

    def test_winner_priority_never_increases(self):
        priorities = [step.winner_priority for step in allocation_race(POPULATIONS, 435)]
        assert all(a >= b for a, b in zip(priorities, priorities[1:]))


@pytest.fixture(scope="module")
def sweep():
    return {s.house_size: s for s in house_size_sweep(POPULATIONS, 435, 11_036)}


class TestHouseSizeSweep:
    def test_435_is_delaware_versus_montana(self, sweep):
        stats = sweep[435]
        assert (stats.largest, stats.smallest) == (DELAWARE, MONTANA)
        assert stats.ratio == pytest.approx(990_837 / (1_085_407 / 2))

    def test_endpoints(self, sweep):
        assert sweep[435].ratio == pytest.approx(1.83, abs=0.005)
        assert sweep[11_036].ratio == pytest.approx(1.04, abs=0.005)

    def test_modest_growth_barely_helps(self, sweep):
        assert sweep[573].ratio > 1.75 and sweep[692].ratio > 1.74
        assert sweep[1_000].ratio < 1.36

    def test_not_monotonic(self, sweep):
        assert sweep[800].ratio > sweep[692].ratio
