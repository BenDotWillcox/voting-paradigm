"""
Cross-checks between the vendored historical sources.

The House Historian table is the primary source for seats by state. The
Senate Manual table and the Census CSV are independent publications; every
disagreement between them must be one of the documented, explained cases
below, so any new discrepancy (a bad re-fetch, a parser regression) fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apportionment import US_2020_KNOWN_APPORTIONMENT
from apportionment.data.state_names import STATE_NAMES
from apportionment.history import (
    HISTORIAN_YEARS,
    build_history,
    parse_census_csv,
    parse_decennial_population,
    parse_house_historian,
    parse_senate_manual,
)

SOURCES = Path(__file__).resolve().parents[2] / "data" / "apportionment" / "sources"
NAME_TO_FIPS = {name: fips for fips, name in STATE_NAMES.items()}

# Standard House sizes at each apportionment (the Historian's printed totals).
EXPECTED_HOUSE_SIZES = {
    1787: 65, 1790: 105, 1800: 141, 1810: 181, 1820: 213, 1830: 240, 1840: 223,
    1850: 234, 1860: 241, 1870: 292, 1880: 325, 1890: 356, 1900: 386, 1910: 435,
    **{year: 435 for year in range(1920, 2030, 10)},
}

# Known, explained disagreements between the Historian and Senate Manual tables.
DOCUMENTED_SENATE_DIFFERENCES = {
    # Historian footnote 6: Maine was part of Massachusetts at the 1810
    # apportionment; the Senate Manual shows the 1820-21 split instead.
    (1810, "23"),
    (1810, "25"),
    # Senate Manual erratum: it prints Maine's 1860 apportionment as 3; the
    # 1862 act gave Maine 5, and only 5 makes the column sum to 241.
    (1860, "23"),
}


@pytest.fixture(scope="module")
def historian():
    return parse_house_historian(_read("house_historian_apportionment.txt"), NAME_TO_FIPS)


@pytest.fixture(scope="module")
def senate():
    return parse_senate_manual(_read("senate_manual_113_apportionments.htm"))


@pytest.fixture(scope="module")
def census():
    return parse_census_csv(_read("census_apportionment_1910_2020.csv"), NAME_TO_FIPS)


@pytest.fixture(scope="module")
def history(historian, census):
    decennial = parse_decennial_population(_read("census_decennial_population_1790_1920.csv"))
    return build_history(historian, census, decennial)


class TestHistorianTable:
    def test_rows_sum_to_printed_totals(self, historian):
        for year in HISTORIAN_YEARS:
            column = sum(row.get(year, 0) for row in historian.seats.values())
            assert column == historian.totals[year], year

    def test_house_sizes_match_the_historical_record(self, history):
        assert {a.census_year: a.house_size for a in history} == EXPECTED_HOUSE_SIZES

    def test_2020_matches_the_known_apportionment(self, history):
        latest = next(a for a in history if a.census_year == 2020)
        assert latest.state_seats == US_2020_KNOWN_APPORTIONMENT

    def test_1920_carries_the_1910_seats(self, history):
        by_year = {a.census_year: a for a in history}
        assert not by_year[1920].reapportioned
        assert by_year[1920].state_seats == by_year[1910].state_seats


class TestSenateManualCrossCheck:
    def test_only_documented_differences(self, historian, senate):
        differences = set()
        for fips in STATE_NAMES:
            for year in senate.years:
                entry = senate.seats[fips].get(year)
                # Seats the Senate Manual marks as added on later admission are
                # outside the apportionment; the Historian counts some interim
                # admissions (its footnote 4), so compare apportioned seats only.
                senate_seats = entry[0] if entry and not entry[1] else None
                historian_seats = historian.seats[fips].get(year)
                if entry and entry[1] and historian_seats == entry[0]:
                    continue
                if senate_seats != historian_seats:
                    differences.add((year, fips))
        assert differences == DOCUMENTED_SENATE_DIFFERENCES


class TestCensusCsvCrossCheck:
    def test_seats_agree_for_1930_to_2020(self, historian, census):
        for year in range(1930, 2030, 10):
            if year == 1920:
                continue
            expected = {f: row[year] for f, row in historian.seats.items() if year in row}
            assert census[year].state_seats == expected, year

    def test_1910_differs_only_by_interim_admissions(self, historian, census):
        expected = {f: row[1910] for f, row in historian.seats.items() if 1910 in row}
        missing = set(expected) - set(census[1910].state_seats)
        assert missing == {"04", "35"}  # Arizona, New Mexico (admitted 1912)

    def test_population_sources_agree_where_they_overlap(self, census):
        decennial = parse_decennial_population(_read("census_decennial_population_1790_1920.csv"))
        for year in (1910, 1920):
            relative = abs(decennial[year] - census[year].resident_population) / census[year].resident_population
            assert relative < 1e-6, year  # revisions of a few dozen people


def _read(name: str) -> str:
    return (SOURCES / name).read_text(encoding="utf-8")
