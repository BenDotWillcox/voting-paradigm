# Voting-methods simulation v1

How often the seven methods of the `/methods` instrument disagree, and how
often each elects the Condorcet winner, over 10,000 seeded
elections for each of 3, 4, 5 candidates
(30,000 elections in all). Design:
[`prompts/demo-1-methods-instrument.md`](../../../prompts/demo-1-methods-instrument.md),
section Simulation.

## Model

- **Electorates:** each election draws its candidates and then
  101 voters independently from the same standard bivariate Gaussian
  (`voting.spatial.sample_spatial_election`).
- **Utilities and ballots:** utility falls linearly with distance, rescaled
  per voter so the nearest candidate gets 100 and the farthest 0, rounded
  half up. The sincere ballot model `sincere-v1` casts every ballot format.
- **Counting:** the reference methods, exactly as the instrument counts a
  profile: one fresh tiebreak per method seeded with 0
  (`voting.spatial.ProfileCounter`). `api/tests/test_simulation_parity.py`
  checks sampled elections against `POST /api/voting/profile/resolve`.
- **Seeds:** election *i* with *k* candidates uses the generator
  `numpy.random.default_rng([20261023, k, i])`, so any election can be
  regenerated on its own and the outputs do not depend on the worker count.
- **Intervals:** every rate is shown with its 95% Wilson score interval.

## Results

### Condorcet efficiency (%)

The share of elections with a Condorcet winner in which the method elects
it. Ranked Pairs is Condorcet-consistent, so its 100% is a check on the
counting, not a finding.

| Method | 3 candidates | 4 candidates | 5 candidates |
|---|---|---|---|
| Plurality | 83.9 (83.1–84.6) | 73.1 (72.3–74.0) | 62.7 (61.7–63.6) |
| Instant runoff | 95.6 (95.2–96.0) | 90.0 (89.4–90.6) | 84.0 (83.3–84.7) |
| Borda count | 92.9 (92.4–93.4) | 89.3 (88.6–89.8) | 88.3 (87.7–88.9) |
| Ranked Pairs | 100.0 (100.0–100.0) | 100.0 (100.0–100.0) | 100.0 (100.0–100.0) |
| Approval | 87.7 (87.1–88.4) | 81.1 (80.3–81.9) | 75.7 (74.9–76.5) |
| Score voting | 90.6 (90.0–91.1) | 86.4 (85.7–87.1) | 84.5 (83.8–85.2) |
| Quadratic voting | 90.9 (90.3–91.4) | 87.3 (86.6–87.9) | 85.4 (84.7–86.0) |

| Measure | 3 candidates | 4 candidates | 5 candidates |
|---|---|---|---|
| Condorcet winner exists | 99.78 (99.67–99.85) | 99.54 (99.39–99.65) | 99.28 (99.09–99.43) |

### Disagreement (%)

The share of elections in which two methods elect different winners. All 21
pairs are in `summary.json`; a selection:

| Pair | 3 candidates | 4 candidates | 5 candidates |
|---|---|---|---|
| Plurality vs Approval | 25.1 (24.2–25.9) | 42.2 (41.2–43.1) | 55.1 (54.1–56.0) |
| Plurality vs Borda count | 22.8 (22.0–23.6) | 35.2 (34.3–36.2) | 45.8 (44.8–46.7) |
| Plurality vs Instant runoff | 13.1 (12.5–13.8) | 21.1 (20.4–22.0) | 29.2 (28.3–30.1) |
| Instant runoff vs Ranked Pairs | 4.5 (4.1–5.0) | 10.3 (9.7–10.9) | 16.3 (15.6–17.1) |
| Borda count vs Ranked Pairs | 7.2 (6.7–7.7) | 10.9 (10.4–11.6) | 12.0 (11.4–12.6) |
| Approval vs Ranked Pairs | 12.3 (11.7–13.0) | 19.1 (18.3–19.8) | 24.6 (23.7–25.4) |
| Score voting vs Quadratic voting | 0.7 (0.6–0.9) | 2.0 (1.7–2.3) | 3.6 (3.2–3.9) |

### Tie rate (%)

The share of elections in which the winner was not decided by the ballots
alone: the seeded tiebreak chose, or, for instant runoff, several candidates
tied for last were eliminated together. Tied elections keep the winner the
tiebreak drew, as in the instrument.

| Method | 3 candidates | 4 candidates | 5 candidates |
|---|---|---|---|
| Plurality | 1.46 (1.24–1.71) | 2.40 (2.12–2.72) | 2.83 (2.52–3.17) |
| Instant runoff | 1.11 (0.92–1.33) | 4.64 (4.24–5.07) | 12.46 (11.83–13.12) |
| Borda count | 0.75 (0.60–0.94) | 0.85 (0.69–1.05) | 0.74 (0.59–0.93) |
| Ranked Pairs | 0.11 (0.06–0.20) | 0.15 (0.09–0.25) | 0.24 (0.16–0.36) |
| Approval | 1.35 (1.14–1.60) | 2.25 (1.98–2.56) | 2.66 (2.36–2.99) |
| Score voting | 0.16 (0.10–0.26) | 0.31 (0.22–0.44) | 0.41 (0.30–0.56) |
| Quadratic voting | 0.08 (0.04–0.16) | 0.18 (0.11–0.28) | 0.37 (0.27–0.51) |

Instant runoff's ties by kind (elections; `irv_ties` in `summary.json`). With
votes, eliminating the tied candidates one at a time could have changed the
result; without, the order cannot matter.

| Kind | 3 candidates | 4 candidates | 5 candidates |
|---|---|---|---|
| Seeded tiebreak | 0 | 0 | 0 |
| Eliminated together, with votes | 111 | 464 | 1,243 |
| Eliminated together, without votes | 0 | 0 | 3 |

## What this shows, and what it does not

- It describes sincere voting in one electorate model: a single Gaussian
  cloud, candidates from the same distribution, linear utility and 101
  voters. Polarized, random-utility and one-dimensional electorates,
  satisfaction efficiency and criterion-failure rates are not in this study.
- Under this model a Condorcet winner almost always exists, so Condorcet
  efficiency is measured over nearly every election. Models with more
  cycles (impartial culture, for example) would change both numbers.
- Nothing here models strategic voting.
- The rates are for elections the model generates, not real ones.

## Files

| File | Contents |
|---|---|
| `config.json` | The executed configuration |
| `elections.csv.gz` | One row per election: the Condorcet winner, each method's winner and whether the ballots alone decided it |
| `summary.json` | Every rate above with counts and intervals |
| `metadata.json` | Python and NumPy versions, the source hash and output hashes |

The `/methods` page reads the same summary from
`public/data/methods/simulation.json`.
`eval/tests/test_methods_simulation.py` recomputes the summary from the
election rows, checks the page copy against it, and regenerates a sample of
elections.

## Reproduce

```bash
python -m eval.run_methods_simulation --overwrite
```

Source hash `b086495839dc…`, Python 3.11.3, NumPy 2.4.6.
