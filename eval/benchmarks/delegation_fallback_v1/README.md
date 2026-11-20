# The fallback study, v1: the representative as default (exploratory)

> **Exploratory.** Declared on 2026-11-20, after the frozen benchmark's
> results had been seen, with one hypothesis approved by Ben before any of
> the 200 cities ran. It changes no frozen reading and is reported beside
> the frozen results, never in place of them.

**Outcome: supported.** At turnout 0.1, 0.2 and 0.3, liquid delegation with
the representative as default leads the district representative, and every
one of the 200 cities keeps its overhead at or under 10%.

The declaration is in
[`prompts/demo-5-liquid-democracy.md`](../../../prompts/demo-5-liquid-democracy.md),
"Exploratory analyses after the freeze", item 4. It said in advance that the
hypothesis favours itself by construction, so the result is mainly a measure
of how large the default's effect is.

It is a simulation: no participant data, no model calls, no real voters.
The run was made from commit `c5a297161febb1bbc5aa62d32bdb28190bc74fd6` on a
clean checkout, with the frozen beliefs file.

**Seen before the declaration.** The rule was tested on three development
cities (seeds 1 to 3, outside the primary namespace). No primary city was
computed.

## The arrangement

The frozen calibrated liquid arrangement, with two rules added:
- **(a)** a resident with no delegate for a topic (they keep it only because
  no candidate cleared the acceptance level, or they have no record) is
  represented on it by their district's representative;
- **(b)** a vote still uncast at close takes the representative's ballot.

Delegations, the calibrated acceptance level, routing, the loop rule and the
turnout draws are the frozen arrangement's. Delegates vote at their own rate.
A representative holding default votes votes at the larger of their own rate
and the office-holder rate (0.96). A vote the representative does not cast
stays uncast.

## Results

All 200 cities at every level of the dial. Values are means over cities;
brackets are 95% t-intervals. Differences are in points of fidelity.

### The hypothesis (0.1 to 0.3)

| Turnout | Lead over the representative | Cities under the cap | Frozen per-level verdict |
|---|---|---|---|
| 0.1 | +5.7 [+5.4, +5.9] | 200 of 200 | supported |
| 0.2 | +8.8 [+8.6, +9.1] | 200 of 200 | supported |
| 0.3 | +11.0 [+10.7, +11.3] | 200 of 200 | supported |

Without the default, frozen liquid trails the representative by 10.6 points
at 0.1, and 7.5% of cities meet the cap at 0.2.

### What the default changes

| Turnout | Arrangement | Fidelity | Contrary | No ballot | Overhead |
|---|---|---|---|---|---|
| 0.1 | Representative | 60.4% | 35.6% | 4.0% | 1.0% |
| 0.1 | Liquid (frozen) | 49.8% | 23.3% | 27.0% | 23.6% |
| 0.1 | Liquid with the default | 66.0% | 32.9% | 1.1% | 1.8% |
| 0.45 | Liquid (frozen) | 70.9% | 22.6% | 6.6% | 9.8% |
| 0.45 | Liquid with the default | 74.0% | 25.7% | 0.3% | 4.3% |
| 0.9 | Liquid (frozen) | 79.0% | 20.6% | 0.5% | 11.5% |
| 0.9 | Liquid with the default | 79.2% | 20.8% | 0.0% | 11.6% |

- **The low edge closes.** At 0.1 the default adds 16.3 points of fidelity
  [16.0, 16.5] and overhead falls from 23.6% to 1.8%. Residents with an
  empty record go from 0.1% fidelity to 60.3%, the representative's own.
- **It fills absences with ballots, some of them contrary.** At 0.1 the
  no-ballot share falls from 27.0% to 1.1%, and the contrary share rises
  from 23.3% to 32.9%. Scored with contrary ballots against (the
  wrong-ballot table's w = 1), the gain is smaller.
- **The high edge stays.** At 0.9 the default changes almost nothing (+0.3
  points): hardly anyone keeps a topic for want of a delegate, and liquid's
  overhead is its loops (11.5%). Only 1% of cities meet the cap there,
  against 96% at 0.8. The expected cost, the default replacing ballots
  residents would have cast themselves, does not appear: at high turnout
  the rules rarely trigger.
- **Under the frozen test's per-level rules,** liquid with the default is
  supported at every level from 0.1 to 0.8, and fails the overhead
  condition only at 0.9. That reading is reported, not tested.

### Limits

- The hypothesis was expected from how the default works; the declaration
  says so. What the run adds is the size of the effect at each level.
- The default leans on the representative being elected and voting at the
  office-holder rate, as in the frozen design.
- The backup delegate, the per-voter ceiling and a personal agent are not in
  this study.

## Reproduce

From the repository root, with the project's Python 3.11 environment:

```bash
python -m eval.delegation_fallback verify
```

**The city records are not in the repository.** `cities.jsonl.gz` is listed
in this directory's `.gitignore`; `metadata.json` keeps its hash.
- **Without the city records,** `verify` checks every committed file against
  its hash, the run manifest, and that the frozen arrangements it reports
  equal the frozen benchmark's.
- **With them,** it also rebuilds `measures.csv`, `levels.csv`,
  `hypothesis.json` and `metadata.json` byte for byte.

To regenerate the city records, check out commit `c5a2971` and run:

```bash
python -m eval.delegation_fallback run --workers 14
```

```bash
python -m eval.delegation_fallback publish
```
