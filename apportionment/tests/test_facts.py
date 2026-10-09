"""
The essay's fact register (data/apportionment/facts.json).

Structural rules keep the register honest; the "derived" claims are checked
against the data they are derived from, so a claim cannot drift from the
numbers the essay will show.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apportionment import US_2020_APPORTIONMENT_POPULATIONS as POPULATIONS
from apportionment.analysis import allocation_race, article_one_max_size, wyoming_rule_size

ROOT = Path(__file__).resolve().parents[2]
FACTS = json.loads((ROOT / "data" / "apportionment" / "facts.json").read_text(encoding="utf-8"))
HISTORY = json.loads(
    (ROOT / "public" / "data" / "apportionment-story" / "history.json").read_text(encoding="utf-8")
)["apportionments"]
BY_ID = {fact["id"]: fact for fact in FACTS["facts"]}


class TestRegisterStructure:
    def test_ids_are_unique(self):
        ids = [fact["id"] for fact in FACTS["facts"]]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("fact", FACTS["facts"], ids=lambda f: f["id"])
    def test_status_rules(self, fact):
        assert fact["status"] in {"verified", "derived", "unverified"}
        assert fact["claim"].strip()
        if fact["status"] == "verified":
            assert fact["sources"], "verified facts need a source"
            for source in fact["sources"]:
                assert source["url"].startswith("https://") and source["title"]
        if fact["status"] == "derived":
            assert fact.get("derivation"), "derived facts must say how"
        if fact["status"] == "unverified":
            assert fact.get("note"), "unverified facts must say what is missing"


class TestDerivedClaims:
    def test_constitution_allocation_matches_historian_1787(self):
        # NH 3, MA 8, RI 1, CT 5, NY 6, NJ 4, PA 8, DE 1, MD 6, VA 10, NC 5, SC 5, GA 3
        expected = {
            "33": 3, "25": 8, "44": 1, "09": 5, "36": 6, "34": 4, "42": 8,
            "10": 1, "24": 6, "51": 10, "37": 5, "45": 5, "13": 3,
        }
        first = next(a for a in HISTORY if a["census_year"] == 1787)
        assert first["state_seats"] == expected
        assert "Georgia three" in BY_ID["constitution-apportionment-clause"]["quote"]

    def test_house_shrank_only_after_1840(self):
        sizes = [(a["census_year"], a["house_size"]) for a in HISTORY if a["census_year"] <= 1910]
        shrinks = [year for (_, prev), (year, size) in zip(sizes, sizes[1:]) if size < prev]
        assert shrinks == [1840]

    def test_article_the_first_would_allow_todays_house(self):
        ceiling = sum(POPULATIONS.values()) // 50_000
        assert 200 <= 435 <= ceiling == 6_622
        assert "nor more than one Representative for every fifty thousand" in (
            BY_ID["article-the-first-text"]["quote"]
        )

    def test_montana_seat_history(self):
        montana = {a["census_year"]: a["state_seats"].get("30") for a in HISTORY}
        assert (montana[1980], montana[1990], montana[2000], montana[2010], montana[2020]) == (2, 1, 1, 1, 2)

    def test_seat_435(self):
        last = allocation_race(POPULATIONS, 435)[-1]
        assert (last.winner, last.winner_new_seats) == ("27", 8)

    def test_wyoming_and_article_one_sizes(self):
        assert wyoming_rule_size(POPULATIONS) == 573
        assert round(sum(POPULATIONS.values()) / 576_851) == 574  # the mixed-measure figure
        assert article_one_max_size(POPULATIONS) == 11_036

    def test_population_1910_1920(self):
        by_year = {a["census_year"]: a for a in HISTORY}
        assert by_year[1910]["resident_population"] == 92_228_531
        assert by_year[1920]["resident_population"] == 106_021_568
        assert by_year[1910]["house_size"] == by_year[1920]["house_size"] == 435

    def test_per_seat_1920_2020(self):
        by_year = {a["census_year"]: a for a in HISTORY}
        before, after = by_year[1920]["apportionment_per_seat"], by_year[2020]["apportionment_per_seat"]
        assert (before, after) == (241_864, 761_169)
        assert after / before > 3
        assert all(a["house_size"] == 435 for a in HISTORY if a["census_year"] >= 1910)

    def test_1929_act_names_no_size(self):
        # The act froze the House by apportioning whatever number it had.
        quote = BY_ID["permanent-apportionment-act-1929-text"]["quote"]
        assert "the then existing number of Representatives" in quote
        assert "fails to enact a law apportioning Representatives" in quote
        assert "435" not in quote


SIZES = json.loads(
    (ROOT / "public" / "data" / "apportionment-story" / "house-sizes.json").read_text(encoding="utf-8")
)


def _size(n: int) -> dict:
    """Ratio, extremes (FIPS and seats) and median deviation at House size n."""
    i = n - SIZES["start"]
    fips = [state["fips"] for state in SIZES["states"]]
    seats = {f: 1 for f in fips}
    for index in SIZES["award_order"][: n - len(fips)]:
        seats[fips[index]] += 1
    largest, smallest = fips[SIZES["largest"][i]], fips[SIZES["smallest"][i]]
    population = {state["fips"]: state["population"] for state in SIZES["states"]}
    average = sum(population.values()) / n
    return {
        "ratio": SIZES["ratio"][i],
        "typical": SIZES["median_abs_deviation"][i],
        "seats": (seats[largest], seats[smallest]),
        "high": population[largest] / seats[largest] / average - 1,
    }


class TestBiggerHouse:
    def test_extremes_barely_move_until_about_1000(self):
        ratios = {n: round(_size(n)["ratio"], 2) for n in (435, 573, 692, 810, 1000, 11036)}
        assert ratios == {435: 1.83, 573: 1.76, 692: 1.75, 810: 1.8, 1000: 1.35, 11036: 1.04}
        first = next(n for n in range(SIZES["start"], SIZES["stop"] + 1) if _size(n)["ratio"] < 1.5)
        assert first == 917
        assert [round(_size(n)["high"], 2) for n in (435, 573, 692)] == [0.30, 0.35, 0.34]

    def test_extremes_are_small_states(self):
        assert max(max(_size(n)["seats"]) for n in range(435, 1001)) == 5
        assert all(max(_size(n)["seats"]) <= 2 for n in (435, 573, 692, 810, 1000))

    def test_typical_gap(self):
        gaps = [round(_size(n)["typical"] * 100, 2) for n in (435, 692, 1000, 11036)]
        assert gaps == [3.39, 2.58, 1.39, 0.17]

    def _sweep(self, stop: int):
        """(size, per-seat by state, national average) for every size up to `stop`."""
        fips = [state["fips"] for state in SIZES["states"]]
        population = {state["fips"]: state["population"] for state in SIZES["states"]}
        total = sum(population.values())
        seats = {f: 1 for f in fips}
        for index in SIZES["award_order"][: SIZES["start"] - len(fips)]:
            seats[fips[index]] += 1
        for n in range(SIZES["start"], stop + 1):
            if n > SIZES["start"]:
                seats[fips[SIZES["award_order"][n - len(fips) - 1]]] += 1
            yield n, {f: population[f] / seats[f] for f in fips}, total / n

    def test_two_percent_threshold(self):
        worst = {n: max(abs(v / avg - 1) for v in per.values()) for n, per, avg in self._sweep(SIZES["stop"])}
        first = min(n for n, w in worst.items() if w <= 0.02)
        assert first == 6279
        assert sum(1 for n, w in worst.items() if n > first and w > 0.02) == 3301
        assert round(worst[11036] * 100, 2) == 2.13

    def test_typical_gap_is_jagged(self):
        increases = sum(1 for n in range(436, 1001) if _size(n)["typical"] > _size(n - 1)["typical"])
        assert increases == 303

    def test_states_below_thirty_thousand_at_limit(self):
        per = next(per for n, per, _ in self._sweep(11036) if n == 11036)
        assert sum(1 for v in per.values() if v < 30_000) == 23
        assert "separate and respective numbers of the States" in BY_ID["washington-veto-1792"]["quote"]

    def test_constituency_shrink(self):
        total = sum(state["population"] for state in SIZES["states"])
        averages = {n: round(total / n) for n in (435, 573, 692, 1000, 11036)}
        assert averages == {435: 761_169, 573: 577_851, 692: 478_480, 1000: 331_108, 11036: 30_003}
        shrink = {n: round((1 - averages[n] / averages[435]) * 100) for n in (573, 692, 1000, 11036)}
        assert shrink == {573: 24, 692: 37, 1000: 57, 11036: 96}

    def test_member_cost(self):
        per_member = 174_000 + 1_928_107
        assert per_member == 2_102_107
        assert (1000 - 435) * per_member == 1_187_690_455
        assert (11036 - 435) * per_member == 22_284_436_307
        assert 11036 * per_member == 23_198_852_852
        assert 11036 * 18 == 198_648
        assert "$1,928,107" in BY_ID["mra-2026"]["quote"] and "$174,000" in BY_ID["member-salary-2026"]["quote"]


STATES_2020 = json.loads(
    (ROOT / "public" / "data" / "apportionment-story" / "states-2020.json").read_text(encoding="utf-8")
)["states"]


class TestStates2020:
    def test_at_large_states(self):
        at_large = {s["abbr"] for s in STATES_2020 if s["at_large"]}
        assert at_large == {"AK", "DE", "ND", "SD", "VT", "WY"}
        assert all(s["seats"] == 1 for s in STATES_2020 if s["at_large"])

    def test_official_average_is_population_over_seats(self):
        for state in STATES_2020:
            assert abs(state["average_per_seat"] - state["apportionment_population"] / state["seats"]) <= 1

    def test_seats_match_known_apportionment(self):
        from apportionment import US_2020_KNOWN_APPORTIONMENT

        assert {s["fips"]: s["seats"] for s in STATES_2020} == US_2020_KNOWN_APPORTIONMENT

    def test_per_seat_spread(self):
        ordered = sorted(STATES_2020, key=lambda s: s["average_per_seat"])
        smallest, largest = ordered[0], ordered[-1]
        assert (smallest["abbr"], smallest["seats"], smallest["average_per_seat"]) == ("MT", 2, 542_704)
        assert (largest["abbr"], largest["seats"], largest["average_per_seat"]) == ("DE", 1, 990_837)

    def test_national_average(self):
        total = sum(s["apportionment_population"] for s in STATES_2020)
        assert round(total / 435) == 761_169
