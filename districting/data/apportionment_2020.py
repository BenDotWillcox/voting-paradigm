"""
2020 Census apportionment data for the 50 states.

Source: US Census Bureau, "Apportionment Population and Number of
Representatives by State: 2020 Census" (released April 26, 2021).
https://www.census.gov/data/tables/2020/dec/2020-apportionment-data.html

The "apportionment population" differs slightly from the "resident
population": it is the resident population of each state plus federal
employees (and their dependents) living overseas allocated back to their
home state of record. Apportionment population is the figure mandated by
2 U.S.C. § 2a for use in the apportionment of House seats.

State keys are 2-character FIPS codes (with leading zeros) to match the
Census Bureau's standard identifier and the TIGER/Line shapefiles we will
load later for geometry. The District of Columbia and US territories are
intentionally omitted: they receive no voting House representation under
current law and are out of scope for v1 of the districting demo (see
prompts/demo-3-districting.md, decision #5).

KNOWN_APPORTIONMENT below is the actual 435-seat apportionment that
resulted from the 2020 census. It serves as the regression test for our
implementation: feeding the populations through Method of Equal
Proportions with cap=435 must reproduce these counts exactly.
"""

from __future__ import annotations

from typing import Final


# State FIPS code -> 2020 apportionment population
US_2020_APPORTIONMENT_POPULATIONS: Final[dict[str, int]] = {
    "01": 5_030_053,   # Alabama
    "02": 736_081,     # Alaska
    "04": 7_158_923,   # Arizona
    "05": 3_013_756,   # Arkansas
    "06": 39_576_757,  # California
    "08": 5_782_171,   # Colorado
    "09": 3_608_298,   # Connecticut
    "10": 990_837,     # Delaware
    "12": 21_570_527,  # Florida
    "13": 10_725_274,  # Georgia
    "15": 1_460_137,   # Hawaii
    "16": 1_841_377,   # Idaho
    "17": 12_822_739,  # Illinois
    "18": 6_790_280,   # Indiana
    "19": 3_192_406,   # Iowa
    "20": 2_940_865,   # Kansas
    "21": 4_509_342,   # Kentucky
    "22": 4_661_468,   # Louisiana
    "23": 1_363_582,   # Maine
    "24": 6_185_278,   # Maryland
    "25": 7_033_469,   # Massachusetts
    "26": 10_084_442,  # Michigan
    "27": 5_709_752,   # Minnesota
    "28": 2_963_914,   # Mississippi
    "29": 6_160_281,   # Missouri
    "30": 1_085_407,   # Montana
    "31": 1_963_333,   # Nebraska
    "32": 3_108_462,   # Nevada
    "33": 1_379_089,   # New Hampshire
    "34": 9_294_493,   # New Jersey
    "35": 2_120_220,   # New Mexico
    "36": 20_215_751,  # New York
    "37": 10_453_948,  # North Carolina
    "38": 779_702,     # North Dakota
    "39": 11_808_848,  # Ohio
    "40": 3_963_516,   # Oklahoma
    "41": 4_241_500,   # Oregon
    "42": 13_011_844,  # Pennsylvania
    "44": 1_098_163,   # Rhode Island
    "45": 5_124_712,   # South Carolina
    "46": 887_770,     # South Dakota
    "47": 6_916_897,   # Tennessee
    "48": 29_183_290,  # Texas
    "49": 3_275_252,   # Utah
    "50": 643_503,     # Vermont
    "51": 8_654_542,   # Virginia
    "53": 7_715_946,   # Washington
    "54": 1_795_045,   # West Virginia
    "55": 5_897_473,   # Wisconsin
    "56": 577_719,     # Wyoming
}


# Sum across all 50 states. Cross-check value used in tests.
US_2020_TOTAL_APPORTIONMENT_POPULATION: Final[int] = sum(
    US_2020_APPORTIONMENT_POPULATIONS.values()
)


# Actual 435-seat apportionment that resulted from the 2020 census.
# Used as the regression test for our Method of Equal Proportions
# implementation.
US_2020_KNOWN_APPORTIONMENT: Final[dict[str, int]] = {
    "01": 7,    # Alabama
    "02": 1,    # Alaska
    "04": 9,    # Arizona
    "05": 4,    # Arkansas
    "06": 52,   # California
    "08": 8,    # Colorado
    "09": 5,    # Connecticut
    "10": 1,    # Delaware
    "12": 28,   # Florida
    "13": 14,   # Georgia
    "15": 2,    # Hawaii
    "16": 2,    # Idaho
    "17": 17,   # Illinois
    "18": 9,    # Indiana
    "19": 4,    # Iowa
    "20": 4,    # Kansas
    "21": 6,    # Kentucky
    "22": 6,    # Louisiana
    "23": 2,    # Maine
    "24": 8,    # Maryland
    "25": 9,    # Massachusetts
    "26": 13,   # Michigan
    "27": 8,    # Minnesota
    "28": 4,    # Mississippi
    "29": 8,    # Missouri
    "30": 2,    # Montana
    "31": 3,    # Nebraska
    "32": 4,    # Nevada
    "33": 2,    # New Hampshire
    "34": 12,   # New Jersey
    "35": 3,    # New Mexico
    "36": 26,   # New York
    "37": 14,   # North Carolina
    "38": 1,    # North Dakota
    "39": 15,   # Ohio
    "40": 5,    # Oklahoma
    "41": 6,    # Oregon
    "42": 17,   # Pennsylvania
    "44": 2,    # Rhode Island
    "45": 7,    # South Carolina
    "46": 1,    # South Dakota
    "47": 9,    # Tennessee
    "48": 38,   # Texas
    "49": 4,    # Utah
    "50": 1,    # Vermont
    "51": 11,   # Virginia
    "53": 10,   # Washington
    "54": 2,    # West Virginia
    "55": 8,    # Wisconsin
    "56": 1,    # Wyoming
}
