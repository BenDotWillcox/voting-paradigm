#!/usr/bin/env python3
"""Fetch and vendor the primary sources behind the apportionment essay.

Writes to data/apportionment/sources/:

- house_historian_apportionment.pdf   House Office of the Historian,
  "Representatives Apportioned to Each State (1st to 24th Census)"
- house_historian_apportionment.txt   its text, via `pdftotext -raw` (the
  build reads this; pdftotext ships with Poppler and Git for Windows)
- census_apportionment_1910_2020.csv  Census Bureau historical apportionment
- senate_manual_113_apportionments.htm U.S. Senate Manual apportionment table
  (independent cross-check of the Historian table)
- census_decennial_population_1790_1920.csv  national resident population
  per census, extracted from the Census Bureau's per-decade facts pages

The build (scripts/build_apportionment_story.py) reads only these vendored
files, so it is offline and deterministic; this script documents how they
were obtained. Re-running it may change files if a publisher revises a page;
the build manifest records each file's SHA-256 so any change is visible.

Usage:
    python scripts/fetch_apportionment_sources.py
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "apportionment" / "sources"

CENSUS_CSV_URL = (
    "https://www2.census.gov/programs-surveys/decennial/2020/data/"
    "apportionment/apportionment.csv"
)
HOUSE_HISTORIAN_URL = "https://history.house.gov/Institution/Apportionment/state_apportionment_pdf_2021/"
SENATE_MANUAL_URL = "https://www.govinfo.gov/content/pkg/SMAN-113/html/SMAN-113-pg1415.htm"
DECENNIAL_FACTS_URL = (
    "https://www.census.gov/programs-surveys/decennial-census/decade/decennial-facts.{year}.html"
)
DECENNIAL_YEARS = range(1790, 1930, 10)
USER_AGENT = "nebula-civitas-apportionment-essay/1 (research; contact via repository)"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pdf = OUT / "house_historian_apportionment.pdf"
    pdf.write_bytes(fetch(HOUSE_HISTORIAN_URL))
    extracted = subprocess.run(
        ["pdftotext", "-raw", "-enc", "UTF-8", str(pdf), "-"],
        check=True,
        capture_output=True,
    ).stdout
    # Normalize line endings so the vendored text (and its hash) is the same
    # whichever platform ran the extraction.
    write_lf(OUT / "house_historian_apportionment.txt", extracted.decode("utf-8"))
    (OUT / "census_apportionment_1910_2020.csv").write_bytes(fetch(CENSUS_CSV_URL))
    (OUT / "senate_manual_113_apportionments.htm").write_bytes(fetch(SENATE_MANUAL_URL))

    rows = ["year,resident_population,source_url"]
    for year in DECENNIAL_YEARS:
        url = DECENNIAL_FACTS_URL.format(year=year)
        population = extract_population(fetch(url).decode("utf-8", errors="replace"))
        rows.append(f"{year},{population},{url}")
        print(f"{year}: {population:,}")
    write_lf(OUT / "census_decennial_population_1790_1920.csv", "\n".join(rows) + "\n")
    return 0


def write_lf(path: Path, text: str) -> None:
    """Write UTF-8 with LF endings (text mode would write CRLF on Windows)."""
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def extract_population(page: str) -> int:
    """The national count: the first number after the "Population" label."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    match = re.search(r"Population ((?:\d{1,3},)+\d{3})\b", text)
    if not match:
        raise ValueError("Population figure not found on page")
    return int(match.group(1).replace(",", ""))


if __name__ == "__main__":
    sys.exit(main())
