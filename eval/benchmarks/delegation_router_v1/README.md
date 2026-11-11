# Delegation router evaluation, v1

Does highest-score-wins routing send a ballot question where a voter would
want it to go? This is the router evaluation for demo 5 (liquid democracy).
Design: `prompts/demo-5-liquid-democracy.md`.

- **Model:** hosted Jev, pinned to `jev-1.14.0`. Collected 2026-11-10.
- **Inputs:** `eval/fixtures/delegation_router_v1.json`, a synthetic pool of
  30 voter-style categories (14 nested inside a broader one) and 68 labelled
  ballot questions, three of which belong to no category.
- **Voter cases:** 544 seeded category lists of one to five categories, eight
  per question. Half are forced to include a category the question is about.
- **Rule under test:** `delegation.route` with a threshold of 0.7, first as
  plain highest-score-wins and then with the rule that a narrower category
  overrules the broader one it sits inside.

## Files

| File | What it holds |
|---|---|
| `judgments.jsonl` | 2,040 yes/no judgments, one per question and category. First response wins. |
| `choice.jsonl` | 544 answers from the single-choice comparison arm, one per voter case. |
| `repeats.jsonl` | 360 judgments each asked four times. |
| `nesting.jsonl` | 870 containment judgments: for every ordered pair of pool categories, whether the first sits inside the second. |
| `config.json` | The evaluation's fixed parameters and both instructions. |
| `summary.json` | Every reported number. |
| `metadata.json` | Source and file hashes. |

`python -m eval.run_delegation_router_eval report` rebuilds `config.json`,
`summary.json` and `metadata.json` from the recorded answers with no network
use, byte for byte. `collect --live` is the only command that calls Jev. In
all it sent 690 requests and was billed 365,220 input tokens, about $0.015
at list price.

## Results

### Routing errors at the 0.7 threshold

| | Count | Rate |
|---|---|---|
| Cases sent to a delegate | 292 of 544 | 53.7% coverage |
| Sent to a category the question is not about (false delegation) | 4 | 1.4% of those sent |
| Kept although an acceptable category was in the list (false keep) | 21 | 6.8% of the 309 cases with one |

Acceptable (question, category) pairs average a score of 0.90 and 92% clear
the threshold. The other 1,936 pairs average 0.04 and seven clear it. The
three questions that belong to no category never score above 0.08.

All four false delegations went to one of two broadly worded categories:
"the city budget and spending" (hiring police officers, funding health
clinics) and "housing and land use" (a property tax deferral for homeowners,
a woodland preserve). The same two categories account for all seven
unlabelled pairs that clear the threshold.

Raising the threshold trades false delegations for false keeps: 0.75 gives 3
and 23, 0.80 gives 1 and 39, and 0.85 gives 0 and 60.

### Nested categories under plain highest-score-wins

For the 28 cases where a question sits squarely inside a narrow category and
the voter also holds the broad category above it:

| Who gets the vote | Cases |
|---|---|
| The narrow category | 17 |
| The broad category | 10 |
| Exact tie, settled by the voter's list order | 1 |

Scores do not reliably prefer the narrow category. In 18 of the 28 cases the
two scores are within 0.04 of each other, in either direction. Five cases go
to the broad category by 0.13 or more, including both tree-frog questions
(0.81 and 0.83 against 0.95 and 0.96 for "the environment and
conservation"). Five go to the narrow category by 0.08 or more.

This result is why the routing rule changed.

### The narrower-category rule

A category that clears the threshold now gives way when a narrower category
inside it also clears. The same 28 cases, with the broad category listed
first in the voter's list:

| Who gets the vote | Highest score only | Rule, nesting as labelled | Rule, nesting as Jev detected it |
|---|---|---|---|
| The narrow category | 17 | 26 | 24 |
| The broad category | 11 (one an exact tie settled by list order) | 2 | 4 |

- Two cases stay with the broad category under every version, because the
  narrow category scores below the threshold: free bus fares (0.38 for "bus
  routes and transit service") and classroom air conditioning (0.54 for
  "building and repairing school buildings").
- The other two under detected nesting are pairs Jev did not detect as
  nested (see below), where the broad category also had the higher score.
- Both tree-frog questions go to the tree-frog category under the rule.
- The routing errors on the 544 voter cases are identical in all three
  versions: 4 false delegations and 21 false keeps.

### Nesting detection

Voters declare no hierarchy. For two categories A and B, Jev is asked whether
every decision about A is also a decision about B, in both directions. A
pair is nested when the answer is at least 0.7 one way and below 0.7 the
other. All 870 ordered pairs of the pool's 30 categories were asked.

| | Count |
|---|---|
| Nested pairs labelled in the fixture | 14 |
| Labelled pairs detected | 11 |
| Pairs detected that were not labelled | 0 of 856 |

- The three misses: "the fire department and ambulance service" inside
  "policing and public safety" (0.29), "civilian oversight of the police"
  inside the same (0.63), and "street trees and the urban tree canopy"
  inside "the environment and conservation" (0.64).
- The other eleven labelled pairs score between 0.73 and 0.91. No unlabelled
  pair scores above 0.48, and the median over all 870 is 0.05.
- Any threshold between 0.49 and 0.63 would detect 13 of the 14 with no
  extra pairs. The 0.7 used here was set before the data was seen.
- A missed pair costs little: routing falls back to the higher score for it,
  which is the rule as it was before.

### Single-choice comparison arm

The same 544 cases asked as one choice question with a "none of these"
option, taking the model's top choice:

| | Yes/no at 0.7 | Single choice |
|---|---|---|
| Coverage | 53.7% | 59.4% |
| False delegations | 4 (1.4%) | 14 (4.3%) |
| False keeps | 21 (6.8%) | 0 |

The single choice never missed an acceptable category but sent more
questions to a wrong one. At a matched coverage the two are close: yes/no at
a threshold of 0.40 has 58.6% coverage with 11 false delegations and 1 false
keep. The yes/no form's advantage is the threshold, which lets false
delegations be traded down.

### Repeat-call spread

Of 360 judgments asked four times each, 242 were identical every time. The
mean spread was 0.005 and the largest was 0.06. One judgment crossed the 0.7
threshold between calls (0.68 to 0.72). This is why judgments are recorded
and resolution reads only recorded ones.

## Limits

- The pool and questions are synthetic and were written and labelled by one
  author. Some unlabelled high scores are defensible (a protected-tree
  ordinance covering private land scored 0.85 for "housing and land use"),
  so the error rates reflect the labels as well as the model.
- The nesting labels give each narrow category exactly one parent, chosen by
  the same author. One is arguable: a fire department is public safety but
  not policing, and Jev scored that pair 0.29.
- With 14 labelled nested pairs, the detection result is a small sample.
- The voter lists are sampled, and half are forced to hold an acceptable
  category, so coverage here is not a forecast of real use.
- 68 questions is small. The threshold should not be tuned closely to it.
- Every number describes one pinned model on one day.
