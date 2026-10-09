"""
Historical House apportionments, parsed from vendored primary sources.

Sources (vendored under data/apportionment/sources/ by
scripts/fetch_apportionment_sources.py):

- **House Historian table** (primary): Office of the Historian, U.S. House of
  Representatives, "Representatives Apportioned to Each State (1st to 24th
  Census, 1790-2020)". Seats per state for the Constitution's 1787 allocation
  and every census apportionment through 2020, with one convention
  throughout: states admitted between apportionments appear from the next
  census, except states admitted in the interval between a census and its
  apportionment act (its footnote 4: e.g. Kansas 1861, Arizona and New
  Mexico 1912), which are counted with that census.
- **Senate Manual table** (cross-check): U.S. Senate Manual, 113th Congress,
  "Apportionments of Representatives". Also the source of the method used
  for each apportionment and the fixed ratios of the early acts.
- **Census historical apportionment CSV** (cross-check, and resident and
  apportionment population per seat for 1910-2020).
- **Census decennial population totals** (resident population, 1790-1920).

Parsing is pure (text in, records out) so it is testable without I/O.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

#: Columns of the House Historian table (no 1920 column: no reapportionment).
HISTORIAN_YEARS: tuple[int, ...] = (
    1787, 1790, 1800, 1810, 1820, 1830, 1840, 1850, 1860, 1870, 1880, 1890,
    1900, 1910, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020,
)

#: Senate Manual row labels -> 2-digit state FIPS codes.
SENATE_MANUAL_STATE_FIPS: dict[str, str] = {
    "Alabama": "01", "Alaska": "02", "Arizona": "04", "Arkansas": "05",
    "California": "06", "Colorado": "08", "Connecticut": "09", "Delaware": "10",
    "Florida": "12", "Georgia": "13", "Hawaii": "15", "Idaho": "16",
    "Illinois": "17", "Indiana": "18", "Iowa": "19", "Kansas": "20",
    "Kentucky": "21", "Louisiana": "22", "Maine": "23", "Maryland": "24",
    "Mass": "25", "Michigan": "26", "Minnesota": "27", "Mississippi": "28",
    "Missouri": "29", "Montana": "30", "Nebraska": "31", "Nevada": "32",
    "N. Hamp": "33", "N. Jersey": "34", "N. Mexico": "35", "New York": "36",
    "N. Carolina": "37", "N. Dakota": "38", "Ohio": "39", "Oklahoma": "40",
    "Oregon": "41", "Penn": "42", "Rhode Is": "44", "S. Carolina": "45",
    "S. Dakota": "46", "Tennessee": "47", "Texas": "48", "Utah": "49",
    "Vermont": "50", "Virginia": "51", "Washington": "53", "W. Virginia": "54",
    "Wisconsin": "55", "Wyoming": "56",
}

#: How each apportionment was computed. Census Bureau, "Congressional
#: Apportionment: Historical Perspective": Jefferson 1790-1830 (fixed ratio,
#: fractions dropped), Webster 1840 (fixed ratio, major fractions kept),
#: Vinton/Hamilton 1850-1900, equal proportions 1940 onward; the Senate
#: Manual note adds major fractions for 1910 and 1930.
APPORTIONMENT_METHODS: dict[int, str] = {
    1787: "Constitution (Art. I, sec. 2)",
    **{year: "Fixed ratio, fractions dropped (Jefferson)" for year in range(1790, 1840, 10)},
    1840: "Fixed ratio, major fractions kept (Webster)",
    **{year: "Vinton (Hamilton)" for year in range(1850, 1910, 10)},
    1910: "Major fractions (Webster)",
    1920: "None (no reapportionment)",
    1930: "Major fractions (Webster)",
    **{year: "Equal proportions (Huntington-Hill)" for year in range(1940, 2030, 10)},
}

#: Persons-per-representative ratios fixed by the acts for the 1st-6th
#: censuses (Senate Manual note).
RATIO_ACTS: dict[int, int] = {
    1790: 33_000, 1800: 33_000, 1810: 35_000,
    1820: 40_000, 1830: 47_700, 1840: 70_680,
}

_HISTORIAN_ROW = re.compile(r"^(?P<name>[A-Z][A-Za-z ]+?)(?P<notes>(?: \[\d\])*)(?P<values>(?: \d+)+)\s*$")
_SENATE_ROW = re.compile(r"^\s*(?P<name>[A-Za-z][A-Za-z. ]*?)\.{2,}\s+(?P<values>.+?)\s*$")


class SourceFormatError(ValueError):
    """A vendored source does not have the expected structure."""


# ----------------------------------------------------------------------
# House Historian table (primary)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class HistorianTable:
    #: fips -> year -> seats
    seats: dict[str, dict[int, int]]
    #: year -> printed total
    totals: dict[int, int]


def parse_house_historian(text: str, name_to_fips: dict[str, str]) -> HistorianTable:
    """
    Parse `pdftotext -raw` output of the House Historian table. Blank cells
    are dropped by the extraction, but every state's seats run contiguously
    from its first apportionment through 2020, so values align from the right.
    """
    seats: dict[str, dict[int, int]] = {}
    totals: dict[int, int] = {}
    for line in text.splitlines():
        match = _HISTORIAN_ROW.match(line.strip())
        if not match:
            continue
        name = match.group("name").strip()
        values = [int(v) for v in match.group("values").split()]
        if len(values) > len(HISTORIAN_YEARS):
            raise SourceFormatError(f"{name!r}: {len(values)} values for {len(HISTORIAN_YEARS)} columns")
        row = dict(zip(HISTORIAN_YEARS[-len(values):], values))
        if name == "Total":
            if len(values) != len(HISTORIAN_YEARS):
                raise SourceFormatError("Total row is incomplete")
            totals = row
        elif name in name_to_fips:
            seats[name_to_fips[name]] = row
    if len(seats) != 50:
        raise SourceFormatError(f"Expected 50 states, parsed {len(seats)}")
    if not totals:
        raise SourceFormatError("Total row not found")
    return HistorianTable(seats=seats, totals=totals)


# ----------------------------------------------------------------------
# Senate Manual table (cross-check)
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SenateManualTable:
    years: tuple[int, ...]
    #: fips -> year -> (seats, admitted_after_apportionment)
    seats: dict[str, dict[int, tuple[int, bool]]]
    #: year -> printed column total (includes later admissions)
    printed_totals: dict[int, int]


def parse_senate_manual(html: str) -> SenateManualTable:
    """Parse the fixed-width Senate Manual apportionment table."""
    lines = html.splitlines()
    header = next((line for line in lines if line.strip().startswith("State") and "1787" in line), None)
    if header is None:
        raise SourceFormatError("Senate Manual header row not found")
    years = tuple(int(token) for token in header.split()[1:])

    seats: dict[str, dict[int, tuple[int, bool]]] = {}
    printed_totals: dict[int, int] = {}
    for line in lines:
        match = _SENATE_ROW.match(line)
        if not match:
            continue
        name = match.group("name").strip()
        values = match.group("values").split()
        if len(values) != len(years):
            raise SourceFormatError(f"{name!r}: expected {len(years)} columns, got {len(values)}")
        if name == "Total":
            printed_totals = {year: int(value) for year, value in zip(years, values)}
            continue
        fips = SENATE_MANUAL_STATE_FIPS.get(name)
        if fips is None:
            raise SourceFormatError(f"Unknown Senate Manual state label {name!r}")
        row: dict[int, tuple[int, bool]] = {}
        for year, value in zip(years, values):
            if set(value) == {"."}:
                continue
            row[year] = (int(value.lstrip("*")), value.startswith("*"))
        seats[fips] = row

    if len(seats) != 50:
        raise SourceFormatError(f"Expected 50 states, parsed {len(seats)}")
    if not printed_totals:
        raise SourceFormatError("Total row not found")
    return SenateManualTable(years=years, seats=seats, printed_totals=printed_totals)


# ----------------------------------------------------------------------
# Census CSV and decennial population
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class CensusCsvYear:
    year: int
    resident_population: int
    representatives: int
    #: Official average apportionment population per representative.
    apportionment_per_seat: int
    #: fips -> seats (states with seats only)
    state_seats: dict[str, int]
    #: fips -> resident population
    state_population: dict[str, int]
    #: fips -> official average apportionment population per representative
    state_average_per_seat: dict[str, int] = field(default_factory=dict)


@dataclass
class _CsvYearBuilder:
    nation: tuple[int, int, int] | None = None
    state_seats: dict[str, int] = field(default_factory=dict)
    state_population: dict[str, int] = field(default_factory=dict)
    state_average_per_seat: dict[str, int] = field(default_factory=dict)


def parse_census_csv(text: str, name_to_fips: dict[str, str]) -> dict[int, CensusCsvYear]:
    """Parse the Census historical apportionment CSV (1910-2020)."""
    builders: dict[int, _CsvYearBuilder] = {}
    for row in csv.DictReader(io.StringIO(text)):
        builder = builders.setdefault(int(row["Year"]), _CsvYearBuilder())
        kind = row["Geography Type"]
        if kind == "Nation":
            builder.nation = (
                _int(row["Resident Population"]),
                _int(row["Number of Representatives"]),
                _int(row["Average Apportionment Population Per Representative"]),
            )
        elif kind == "State":
            fips = name_to_fips.get(row["Name"])
            if fips is None:
                continue  # DC and Puerto Rico have no voting seats
            builder.state_population[fips] = _int(row["Resident Population"])
            if row["Number of Representatives"]:
                builder.state_seats[fips] = _int(row["Number of Representatives"])
            if row["Average Apportionment Population Per Representative"]:
                builder.state_average_per_seat[fips] = _int(
                    row["Average Apportionment Population Per Representative"]
                )

    result: dict[int, CensusCsvYear] = {}
    for year, builder in sorted(builders.items()):
        if builder.nation is None:
            raise SourceFormatError(f"No Nation row for {year}")
        resident, representatives, per_seat = builder.nation
        result[year] = CensusCsvYear(
            year=year,
            resident_population=resident,
            representatives=representatives,
            apportionment_per_seat=per_seat,
            state_seats=builder.state_seats,
            state_population=builder.state_population,
            state_average_per_seat=builder.state_average_per_seat,
        )
    return result


def parse_decennial_population(text: str) -> dict[int, int]:
    """Parse the vendored year,resident_population CSV (1790-1920)."""
    rows = csv.DictReader(io.StringIO(text))
    return {int(row["year"]): int(row["resident_population"]) for row in rows}


# ----------------------------------------------------------------------
# Merged history
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Apportionment:
    """One census's apportionment of the House."""

    census_year: int
    house_size: int
    method: str
    #: National resident population at that census (None for 1787).
    resident_population: int | None
    #: Official average apportionment population per seat (1910 onward).
    apportionment_per_seat: int | None
    #: fips -> seats
    state_seats: dict[str, int]
    #: False for 1920, the only census with no reapportionment.
    reapportioned: bool = True

    @property
    def resident_per_seat(self) -> float | None:
        if self.resident_population is None:
            return None
        return self.resident_population / self.house_size


def build_history(
    historian: HistorianTable,
    census_csv: dict[int, CensusCsvYear],
    decennial_population: dict[int, int],
) -> list[Apportionment]:
    """One record per apportionment, 1787-2020, with 1920's carried seats."""
    history: list[Apportionment] = []
    for year in HISTORIAN_YEARS:
        seats = {fips: row[year] for fips, row in historian.seats.items() if year in row}
        csv_year = census_csv.get(year)
        history.append(
            Apportionment(
                census_year=year,
                house_size=sum(seats.values()),
                method=APPORTIONMENT_METHODS[year],
                resident_population=(
                    csv_year.resident_population if csv_year else decennial_population.get(year)
                ),
                apportionment_per_seat=csv_year.apportionment_per_seat if csv_year else None,
                state_seats=seats,
            )
        )

    carried = next(a for a in history if a.census_year == 1910).state_seats
    history.append(
        Apportionment(
            census_year=1920,
            house_size=sum(carried.values()),
            method=APPORTIONMENT_METHODS[1920],
            resident_population=census_csv[1920].resident_population,
            apportionment_per_seat=census_csv[1920].apportionment_per_seat,
            state_seats=dict(carried),
            reapportioned=False,
        )
    )
    return sorted(history, key=lambda a: a.census_year)


def _int(value: str) -> int:
    return int(value.replace(",", "").strip())
