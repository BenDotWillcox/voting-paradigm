# Apportionment research data

Primary sources and the fact register behind the apportionment essay
(demo 4, `/apportionment`). See `prompts/demo-4-apportionment-essay.md`.

## `sources/`

Vendored exactly as fetched by `scripts/fetch_apportionment_sources.py`. The
build reads only these files, so it is offline and reproducible, and
`public/data/apportionment-story/manifest.json` records each file's SHA-256.

| File | Source | Role |
|---|---|---|
| `house_historian_apportionment.pdf` / `.txt` | Office of the Historian, U.S. House, *Representatives Apportioned to Each State (1st to 24th Census, 1790–2020)* | Primary: seats by state, 1787–2020 |
| `senate_manual_113_apportionments.htm` | U.S. Senate Manual, 113th Congress (S. Doc. 113-1), pp. 1415–1416 | Cross-check; method and ratio for each era |
| `census_apportionment_1910_2020.csv` | U.S. Census Bureau, Historical Apportionment Data (1910–2020) | Cross-check; population per seat, 1910–2020 |
| `census_decennial_population_1790_1920.csv` | U.S. Census Bureau decennial facts pages | Resident population, 1790–1920 |

Known differences between sources are asserted in
`apportionment/tests/test_history.py`. Any new difference fails the tests.

## `facts.json`

Every historical or sourced claim the essay may make, with its source and
status:

- `verified`: read in the primary or authoritative source.
- `derived`: computed from vendored data; the entry says how, and a test
  checks it.
- `unverified`: a research lead. The essay must not use it.

To refresh: run `python scripts/fetch_apportionment_sources.py`, then
`python scripts/build_apportionment_story.py`, then
`pytest apportionment`.
