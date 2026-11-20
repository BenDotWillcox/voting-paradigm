# Everyone votes: a reference point, v1 (exploratory)

> **Exploratory.** This analysis was declared on 2026-11-20, after the
> frozen benchmark's results had been seen. It is descriptive: it computes
> no threshold, gate or verdict, and it changes no frozen reading. It is
> reported beside the frozen results, never in place of them.

The frozen benchmark,
[`delegation_frontier_v1`](../delegation_frontier_v1/README.md), measures
every arrangement at ten levels of citizen turnout, from 0.1 to 0.9. The
story at `/liquid` first shows the idea and the basic mechanism before
turnout enters, so it needs the arrangements with everyone voting. This
benchmark measures them on the same 200 cities.

It is a simulation: no participant data, no model calls, no real voters.
The run was made from commit `770f413ac350ac0b79662d974e00d0c1e7d2f137`
on a clean checkout, with the frozen beliefs file.

The declaration, written before the run, is in
[`prompts/demo-5-liquid-democracy.md`](../../../prompts/demo-5-liquid-democracy.md),
"Exploratory analyses after the freeze", item 3.

**Seen before the declaration.** One city (primary position 1) was
computed to check that the setting runs on the frozen code, and its
measures were seen.

## How it was computed

- **The setting.** Every resident votes on every history and evaluation
  question, and every office holder and delegate votes on every question
  (`TurnoutPolicy(office_rate=1, resolver_turnout=1)`).
- **The frozen code, unchanged.** Turnout has its own random stream, so the
  population's legacy uniform bounds set to [1, 1], with no dial mean, keep
  each city's residents, beliefs, candidates and questions. Only turnout
  changes. A test checks this against the frozen city.
- **Every arrangement `compare` runs.** Liquid and the proxy are calibrated
  by the frozen overhead rule on history questions, as at every level: the
  highest acceptance level whose history overhead is at most 10%, or the
  lowest-overhead level where none is.
- **Cities.** The 200 primary cities, on their pinned seeds.
- **Reported.**
  - `measures.csv`: for each arrangement, the mean over cities of every
    frozen measure, with 95% t-intervals for fidelity and overhead.
  - `contrasts.csv`: the frozen runner's declared contrasts (H1,
    specialisation and the ladder's steps), as fidelity differences with
    95% t-intervals.
  - `cap.csv`: how many cities' liquid and proxy stay at or under the 10%
    cap, on evaluation and on history questions.
- **Checks.** In every city no ballot goes uncast under any arrangement,
  and direct voting equals full turnout. `publish` refuses a run that fails
  either.

## Results

Run 2026-11-20 on 14 workers; all 200 cities passed both checks. Values
are means over the 200 cities, with 95% t-intervals over cities in
brackets.

### The four arrangements

| Arrangement | Fidelity | Overhead |
|---|---|---|
| Direct voting (here equal to full turnout) | 100% | 100% |
| District representative | 63.3% [62.9, 63.6] | 1.0% |
| Personal proxy | 79.0% [78.9, 79.1] | 10.6% [10.4, 10.7] |
| Liquid delegation | 81.0% [80.9, 81.1] | 18.3% [18.1, 18.4] |

- **Liquid sits between the corners.** It is 17.8 points more faithful than
  the representative [17.5, 18.1], at about a fifth of direct voting's
  overhead.
- **No city's liquid stays under the 10% cap** (0 of 200; the proxy does in
  114).
  - All of liquid's overhead is from loops: its loop share equals its
    overhead, 18.3%.
  - With everyone voting, every record is full, so nearly every resident
    hands every topic over, and chains have nowhere to end but a loop. Its
    members decide for themselves.
  - This continues the frozen benchmark's high edge. Liquid's loop share
    there is 0.8% at turnout 0.1, 3.0% at 0.45 and 11.5% at 0.9.

### The ladder

The frozen runner's declared contrasts, in order from the representative to
liquid, so the steps add up to the lead. The first is the frozen
`platform_against_record` with its sign reversed.

| Step | Contrast | Fidelity change (points) |
|---|---|---|
| Ranking the candidates by record, not platform | representative by record − representative | +2.0 [+1.7, +2.2] |
| The cost of sharing | own of three, election voters − representative by record | +5.3 [+5.1, +5.5] |
| Choice by non-voters | own of three, everyone − own of three, election voters | 0 (everyone votes in the election) |
| The city-wide proxy (combined) | proxy − own of three, everyone | +8.5 [+8.3, +8.7] |
| Topic delegates | liquid − proxy | +2.0 [+1.9, +2.1] |
| **Liquid − representative** | the steps' sum | **+17.8 [+17.5, +18.1]** |

As at Swiss turnout in the frozen benchmark, most of the lead arrives
before topics: 15.8 of the 17.8 points come from steps that keep one
person for every topic, and topic delegates add 2.0.

### Other measures

- **Concentration is below a representative's.** On average the largest
  single decider holds 10.3% of a question's votes under liquid, and 16.5%
  on a city's worst question. A representative holds 20%.
- **Poor representation all but vanishes.** 0.01% of residents are matched
  on fewer than half their questions under liquid, against 13.6% under the
  representative.
- **Outcomes.** Liquid's winners agree with full turnout's on 92.3% of
  questions, and the representative's on 83.1%.

### What this is for, and its limits

- It is the reference point for the story's first two parts, which show
  the idea before turnout enters. It is not a test, and everyone voting is
  not a real condition.
- The calibration rule is the frozen one, designed for real turnout. Here
  no acceptance level meets the cap, so the rule takes its lowest-overhead
  level, as it does at the frozen edges.
- One city (position 1) was seen before the declaration; see above.

## Reproduce

From the repository root, with the project's Python 3.11 environment:

```bash
python -m eval.delegation_everyone_votes verify
```

**The city records are not in the repository.** `cities.jsonl.gz` is listed
in this directory's `.gitignore`. `metadata.json` keeps its hash, so a
regenerated copy is checked byte for byte.

- **Without the city records,** `verify` checks every committed file against
  its hash, the run manifest, and the setting's invariants in
  `measures.csv`.
- **With them,** it also rebuilds `measures.csv`, `contrasts.csv`,
  `cap.csv` and `metadata.json` byte for byte.

To regenerate the city records, check out commit `770f413` and run the
two commands below.

```bash
python -m eval.delegation_everyone_votes run --workers 14
```

```bash
python -m eval.delegation_everyone_votes publish
```

- `run` refuses a checkout with uncommitted changes.
- `publish` refuses a run that does not cover all 200 cities on their pinned
  seeds, or that breaks either check.
- Every city is seeded, so a fresh run gives the same city records. Its
  manifest records its own start time, so `manifest.json` differs in that
  field and `metadata.json` in the manifest's hash.
