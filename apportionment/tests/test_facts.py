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
