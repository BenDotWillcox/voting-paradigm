#!/usr/bin/env python3
"""Build the static data artifacts for the apportionment essay.

Reads only vendored sources (data/apportionment/sources/, fetched by
scripts/fetch_apportionment_sources.py) and the 2020 populations in the
apportionment package, and writes JSON to public/data/apportionment-story/:

- history.json      one record per apportionment, 1787-2020
- race-2020.json    seats 51-435 in award order, with the leading candidates
- house-sizes.json  inequality statistics at every House size up to the
                    Article I limit, plus the full award order (columnar)
- anchors.json      the rule-defined House sizes and seats at each
- states-2020.json  per-state 2020 populations, seats, and the official
                    average per seat (the essay's person-to-seat figures)
- manifest.json     source and output SHA-256 hashes

Deterministic: the same sources produce byte-identical outputs.

Usage:
    python scripts/build_apportionment_story.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apportionment import (  # noqa: E402
    US_2020_APPORTIONMENT_POPULATIONS,
    US_2020_KNOWN_APPORTIONMENT,
)
from apportionment.analysis import (  # noqa: E402
    allocation_race,
    award_order,
    house_size_rules,
    house_size_sweep,
    seats_at,
)
from apportionment.data.state_names import STATE_ABBRS, STATE_NAMES  # noqa: E402
from apportionment.history import (  # noqa: E402
    RATIO_ACTS,
    build_history,
    parse_census_csv,
    parse_decennial_population,
    parse_house_historian,
)

SOURCES = ROOT / "data" / "apportionment" / "sources"
OUT = ROOT / "public" / "data" / "apportionment-story"
ARTIFACT_VERSION = 1

SOURCE_FILES = {
    "house_historian_apportionment.pdf": (
        "Office of the Historian, U.S. House of Representatives, Representatives Apportioned to Each State "
        "(1st to 24th Census, 1790-2020)",
        "https://history.house.gov/Institution/Apportionment/state_apportionment_pdf_2021/",
    ),
    "house_historian_apportionment.txt": (
        "Text of the House Historian table, extracted with `pdftotext -raw`",
        "https://history.house.gov/Institution/Apportionment/state_apportionment_pdf_2021/",
    ),
    "census_apportionment_1910_2020.csv": (
        "U.S. Census Bureau, Historical Apportionment Data (1910-2020)",
        "https://www2.census.gov/programs-surveys/decennial/2020/data/apportionment/apportionment.csv",
    ),
    "senate_manual_113_apportionments.htm": (
        "U.S. Senate Manual, 113th Congress (S. Doc. 113-1), Apportionments of Representatives, pp. 1415-1416",
        "https://www.govinfo.gov/content/pkg/SMAN-113/html/SMAN-113-pg1415.htm",
    ),
    "census_decennial_population_1790_1920.csv": (
        "U.S. Census Bureau, decennial census facts pages (national population), 1790-1920",
        "https://www.census.gov/programs-surveys/decennial-census/decade/decennial-facts.1790.html",
    ),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    artifacts = build_artifacts()
    outputs: dict[str, str] = {}
    for name, payload in artifacts.items():
        body = dumps(payload).encode("utf-8")
        # Bytes, not text mode: Windows text mode would write CRLF and the
        # files would no longer match their manifest hashes.
        (OUT / name).write_bytes(body)
        outputs[name] = sha256(body)
        print(f"{name}: {len(body) / 1024:.1f} KB")

    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "generator": "scripts/build_apportionment_story.py",
        "sources": {
            name: {
                "title": title,
                "url": url,
                "sha256": sha256((SOURCES / name).read_bytes()),
            }
            for name, (title, url) in SOURCE_FILES.items()
        },
        "outputs": outputs,
    }
    (OUT / "manifest.json").write_bytes(dumps(manifest).encode("utf-8"))
    print("manifest.json written")
    return 0


def build_artifacts() -> dict[str, Any]:
    populations = US_2020_APPORTIONMENT_POPULATIONS
    name_to_fips = {name: fips for fips, name in STATE_NAMES.items()}
    historian = parse_house_historian(read("house_historian_apportionment.txt"), name_to_fips)
    census = parse_census_csv(read("census_apportionment_1910_2020.csv"), name_to_fips)
    decennial = parse_decennial_population(read("census_decennial_population_1790_1920.csv"))
    history = build_history(historian, census, decennial)

    rules = house_size_rules(populations)
    max_size = max(rule.seats for rule in rules)
    order = award_order(populations, max_size)
    if seats_at(order, populations, 435) != US_2020_KNOWN_APPORTIONMENT:
        raise AssertionError("Award order does not reproduce the 2020 apportionment")
    fips_list = sorted(populations)
    index = {fips: i for i, fips in enumerate(fips_list)}
    sweep = house_size_sweep(populations, 435, max_size)
    race = allocation_race(populations, 435)

    states = [
        {
            "fips": fips,
            "abbr": STATE_ABBRS[fips],
            "name": STATE_NAMES[fips],
            "population": populations[fips],
        }
        for fips in fips_list
    ]

    return {
        "history.json": {
            "apportionments": [
                {
                    "census_year": a.census_year,
                    "reapportioned": a.reapportioned,
                    "method": a.method,
                    "ratio_act": RATIO_ACTS.get(a.census_year),
                    "house_size": a.house_size,
                    "resident_population": a.resident_population,
                    "resident_per_seat": _round(a.resident_per_seat, 1),
                    "apportionment_per_seat": a.apportionment_per_seat,
                    "state_seats": dict(sorted(a.state_seats.items())),
                }
                for a in history
            ],
            "notes": [
                "Seats follow the House Historian convention: states admitted between apportionments "
                "appear from the next census, except states admitted between a census and its "
                "apportionment act, which are counted with that census.",
                "resident_per_seat uses national resident population; apportionment_per_seat is the "
                "official Census figure (1910 onward), which uses apportionment population.",
                "1790-1900 population is the Census Bureau's originally reported count; revised figures "
                "differ slightly for 1830 and 1840.",
            ],
        },
        "race-2020.json": {
            "house_size": 435,
            "states": states,
            "steps": [
                {
                    "seat": step.seat_number,
                    "winner": step.winner,
                    "seats": step.winner_new_seats,
                    "priority": _round(step.winner_priority, 2),
                    "leaders": [
                        [c.fips, c.current_seats, _round(c.priority, 2)] for c in step.leaders
                    ],
                }
                for step in race
            ],
        },
        "house-sizes.json": {
            "states": states,
            "start": 435,
            "stop": max_size,
            "ratio": [_round(s.ratio, 5) for s in sweep],
            "largest": [index[s.largest] for s in sweep],
            "smallest": [index[s.smallest] for s in sweep],
            "median_abs_deviation": [_round(s.median_abs_deviation, 6) for s in sweep],
            # Seat recipients for seats 51..stop, as indexes into `states`.
            "award_order": [index[fips] for fips in order],
        },
        "states-2020.json": {
            "source": "U.S. Census Bureau, 2020 Census apportionment results (historical apportionment CSV)",
            "notes": [
                "resident_population is the 2020 census resident population of the state. For a state "
                "with one seat this is also the population of its at-large congressional district.",
                "average_per_seat is the Census Bureau's average apportionment population per "
                "representative for the state: a state average, not the population of any one district.",
            ],
            "states": [
                {
                    "fips": fips,
                    "abbr": STATE_ABBRS[fips],
                    "name": STATE_NAMES[fips],
                    "seats": census[2020].state_seats[fips],
                    "apportionment_population": populations[fips],
                    "resident_population": census[2020].state_population[fips],
                    "average_per_seat": census[2020].state_average_per_seat[fips],
                    "at_large": census[2020].state_seats[fips] == 1,
                }
                for fips in fips_list
            ],
        },
        "anchors.json": {
            "total_population": sum(populations.values()),
            "rules": [
                {
                    "key": rule.key,
                    "label": rule.label,
                    "formula": rule.formula,
                    "seats": rule.seats,
                    "state_seats": dict(sorted(seats_at(order, populations, rule.seats).items())),
                }
                for rule in rules
            ],
        },
    }


def read(name: str) -> str:
    return (SOURCES / name).read_text(encoding="utf-8")


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)



if __name__ == "__main__":
    sys.exit(main())
