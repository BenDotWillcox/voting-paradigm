# Demo 1: Voting methods as an instrument

Status: design settled with Ben on 2026-10-21; slices A to G built. Supersedes
Phase 2 of `prompts/storytelling-redesign.md`.

## Why an instrument, not an essay

Each demo gets a presentation that suits its argument. Apportionment is an
argument, so it became an essay that the reader scrolls through. The methods
demo compares rules: the reader learns most by changing the voters and
watching every method respond. So the page is an instrument with a short
tour, not a story in acts.

What the page has to show an AI/ML-engineering reader is rigor, not tallies:

- every method's typed trace, stepped through;
- every criterion failure backed by the smallest profile a search could find,
  re-resolved by the reference package;
- every pass backed by a citation, never by a search that came up empty;
- seeds, bounds, and artifact hashes on every figure.

Prior art the page must clear: Ka-Ping Yee's 2005 spatial diagrams and Nicky
Case's *To Build a Better Ballot* (2016). The differences: all seven methods,
an explicit ballot model for rated methods, and machine-found, re-verifiable
counterexamples.

## What this fixes in the current lab

1. **"Same ballots" is true only for the ranked methods.** IRV, Borda and
   Ranked Pairs share ranked ballots. Plurality, approval, score and quadratic
   ballots are derived from bloc utilities by hand-written rules in
   `api/demo_scenarios.py` (for example an approval threshold of
   `54 + (polarization − 50)·0.08`), so some "method differences" are
   translation differences.
2. **The sliders are magic numbers.** Polarization and intensity scale
   utilities by `0.72 + p·0.5 + i·0.18`; turnout and compromise reweight blocs
   by bespoke biases. A voting-theory reader will discount them.
3. **Ranked Pairs ties are not reproducible.** Found while probing for this
   doc:
   - `_sort_victories` orders equal-strength victories with an unseeded
     `random.shuffle`, ignoring the injected tiebreak. With a lexicographic
     tiebreak, the profile `2 A>C>B, 4 B>A>C, 2 C>A>B, 1 C>B>A` elected B in
     102 of 200 runs and A in 98.
   - `tiebreak_applied` is set whenever a victory is skipped, which is every
     majority cycle. It cannot distinguish a real tie from normal resolution,
     so a "tie-free" filter would wrongly drop every cycle.
   - The package default `random_tiebreak` calls unseeded `random.choice`,
     against the reproducibility invariant in CLAUDE.md.
4. **Everything has equal weight.** Cards, tabs and badges compete, and no
   single moment shows the thesis.

## Decisions

Settled 2026-10-21:

- **Format:** one page holding the instrument with the paradox gallery as its
  index. The spatial atlas comes second and the simulation study third.
- **No acts.** A tour of at most six presets replaces the essay structure;
  its middle steps load gallery specimens, so the tour is an index into the
  gallery rather than separate content.
- **Opening preset is a majority cycle** (keeping the 2026-09-25 decision),
  chosen so the ranked methods disagree.
- **Style:** the "drafting table" direction (geometric, cool, flat primaries),
  borrowing the instrument direction's mono numerals and channel rows.
- **Static-first for content:** presets and specimens are build-time
  artifacts written by Python. Only free editing needs a live resolver.
- **Candidates are fully abstract:** glyphs and letters everywhere, with no
  civic labels, including on tour presets.
- **Criteria at launch are the core eight** in the gallery table below.
  Later-no-harm waits for truncated ballots.
- **All seven methods, side by side** (revised 2026-10-22; the first cut
  showed only the four ranked methods and read as a step down from the lab).
  The electorate is voter types with utilities; a declared, versioned ballot
  model (sincere v1) turns each type into all five ballot formats, and rated
  gallery cells say "under model v1".
- **Python resolves live edits.** Presets and specimens stay static; revisit
  when the atlas needs in-browser resolution.

## The page

```
┌──────────────────────────────────────────────────────────────────────┐
│ Same voters, different winners.                  Tour  1 2 3 4 5 6   │
│ 15 voters · 3 different winners · majority cycle                     │
├─────────────────────────┬────────────────────────────────────────────┤
│ Profile                 │ Channels                                   │
│  4  ● ■ ▲      − +      │ Plurality     ▮▮▮▮▯▯▯▯▯  ▲ B   CW –  CL –  │
│  6  ▲ ● ■      − +      │ IRV           ▮▮▮▮▮▮▯▯▯  ■ C   CW –  CL –  │
│  3  ■ ● ▲      − +      │ Borda         ▮▮▮▮▮▯▯▯▯  ● A   CW –  CL –  │
│  2  ■ ▲ ●      − +      │ Ranked Pairs  ▮▮▮▮▮▮▮▯▯  ● A   CW –  CL –  │
│  + add ranking          │ ── rated · model v1 ────────────────────── │
│ Tournament   ●→■→▲→●    │ Approval / Score / Quadratic               │
├─────────────────────────┴────────────────────────────────────────────┤
│ Trace (selected channel) · step ◂ ▸                                  │
├──────────────────────────────────────────────────────────────────────┤
│ Paradox gallery · methods × criteria                                 │
└──────────────────────────────────────────────────────────────────────┘
```

On phones the profile, channels and trace stack, and the gallery becomes a
list grouped by method.

### Profile editor

- Each row is a voter type: a count and a **utility track**, the candidates'
  glyphs placed on a 0–10 scale. Order along the track is the ranked ballot;
  spacing is intensity, which only the rated ballots can see.
- 3 to 5 candidates in fixed glyph order ● ▲ ■ ◆ ★.
- Each glyph is a slider: drag it, or focus it and use the arrow keys (Page
  Up/Down for larger steps, Home/End for the ends). Rows can be added and
  removed; counts cap at 999.
- The URL carries the profile (`?p=6:100,50,0.4:0,100,50`), so any state can
  be shared. Earlier ranked links (`?p=6ABC.4BCA`) still load, spaced evenly.
- The **tournament graph** (pairwise-majority arrows labelled with margins)
  reads the ranked ballots. A cycle visibly closes.

### Ballots panel

For the selected voter type, the five ballots it casts under sincere v1, each
naming the methods that read it: single choice (plurality), ranked (IRV,
Borda, Ranked Pairs), approval, score and quadratic. Every card states its
rule, so the step from preferences to ballots is never hidden.

### Channels

- One row per method, grouped by the ballot it reads, in fixed order.
  Position always means method and color always means candidate.
- Each row has a compact tally in candidate colors, the winner glyph, and
  lights for the single-profile criteria: majority winner elected, Condorcet
  winner elected (– when none exists), Condorcet loser avoided. A tie light
  names the tiebreak and seed when one decided the result.
- A computed summary line ("15 voters · 3 different winners · majority
  cycle").
- Selecting a channel opens its trace: plurality counts, IRV rounds with
  transfers (`IRVRound`), Borda points by position, the Ranked Pairs matrix
  with lock order and the skipped edge, approvals, score totals, and net
  quadratic votes. Below it sit the lab's method descriptions (strengths,
  weaknesses, where it's used), corrected where they overclaimed.
- Motion appears only to show cause and effect (a transfer, a lock). Every
  trace steps forward and back from the keyboard, and nothing is timed.

### Tour

1. **Majority cycle** (opening). `6 A>B>C, 4 B>C>A, 2 C>A>B, 3 C>B>A`
   elects A under plurality, C under IRV, and B under Borda and Ranked Pairs,
   with pairwise margins 1, 5 and 3 (A over B, B over C, C over A). It is the
   first 15-voter profile in canonical order, and no smaller decisive cycle
   gives three winners; the build script finds it (`presets.json`).
2. **Center squeeze.** `35 A>C>B, 33 B>C>A, 32 C>B>A` elects A under
   plurality, B under IRV, and C, the Condorcet winner, under Borda and Ranked
   Pairs.
3. **Spoiler** (plurality, IIA) — a gallery specimen.
4. **Teaming** (Borda, clones) — a gallery specimen.
5. **Monotonicity** (IRV) — a gallery specimen.
6. **Your turn** — the editor unlocks with a note on what to try.

### Paradox gallery

Rows are methods and columns are criteria. Each cell is in one of these
states:

| State | Meaning |
|---|---|
| Fails · specimen | The smallest profile found, re-resolved by the package. "Minimal" only when the search was exhaustive to that size. |
| Fails · cited | A known theorem; the specimen is pending or beyond search bounds. |
| Passes · cited | A proof reference. An empty search never fills this cell; it reads "no specimen ≤ N voters". |
| Open | No specimen up to the bound and no proof; the cell's note says why. |

Opening a specimen loads it into the instrument as before → after, with the
transformation highlighted (raised ballots, added voters, removed candidate,
inserted clone, or the two electorates of a consistency failure).

Single-profile criteria appear both as instrument lights and in the gallery.
Cross-profile criteria (monotonicity, participation, consistency, IIA, clones)
appear only as specimens.

Expected cells for the ranked methods, from the literature. Each must be
confirmed by a specimen or a citation before it ships:

| Criterion | Plurality | IRV | Borda | Ranked Pairs |
|---|---|---|---|---|
| Majority | pass | pass | fail | pass |
| Condorcet winner | fail | fail | fail | pass |
| Condorcet loser | fail | pass | pass | pass |
| Monotonicity | pass | fail | pass | pass |
| Participation | pass | fail | pass | fail (≥ 4 candidates; Moulin 1988) |
| Consistency | pass | fail | pass | fail (Young 1975) |
| IIA (spoiler) | fail | fail | fail | fail |
| Independence of clones | fail | pass | fail | pass (Tideman 1987) |

Rated-method cells are judged under model v1 (see Ballot model v1) and were
not pre-filled.

Search results with three candidates (slice B build): the voters in each
minimal specimen, or "none" when nothing was found up to the bound. Every
cell agrees with the expected table above.

| Criterion (bound) | Plurality | IRV | Borda | Ranked Pairs |
|---|---|---|---|---|
| Majority (24) | none | none | 5 | none |
| Condorcet winner (24) | 7 | 5 | 5 | none |
| Condorcet loser (24) | 7 | none | none | none |
| Monotonicity (24) | none | 17 | none | none |
| Participation (20) | none | 11 | none | none (needs ≥ 4 candidates) |
| Consistency (24) | none | 13 | none | 15 |
| IIA (24) | 7 | 5 | 5 | 7 |
| Independence of clones (24) | 7 | none | 5 | none |

Rated search results (slice F build), over voter types under sincere-v1.
"Proof" and "open" mark the cells with no specimen; the gallery carries the
proofs and the open cell's reason (`lib/methods/gallery.ts`). Clones are
exact: every voter gives the clone the original's utility.

| Criterion (bound) | Approval | Score | Quadratic |
|---|---|---|---|
| Majority (8) | 3 | 3 | 3 |
| Condorcet winner (8) | 3 | 3 | 3 |
| Condorcet loser (8) | 5 | 5 | 7 |
| Monotonicity (7) | none · proof | none · proof | 4 |
| Participation (7) | none · proof | none · proof | none · open |
| Consistency (7) | none · proof | none · proof | none · proof |
| IIA (8) | 3 | 3 | 3 |
| Independence of exact clones (8) | 3 | none · proof | 2 |

- **Proofs.** All three sincere-v1 rules are unchanged by rescaling a
  voter's utilities. Approval: raising the winner lifts the voter's mean, so
  it can only gain an approval and the rest can only lose one. Score: the
  winner's rescaled score can only rise and the others' only fall. A voter
  approves (or scores at least as high) everyone they like more, which gives
  participation. Approvals, scores and net votes add, which gives
  consistency. An exact clone leaves each voter's lowest and highest utility
  in place, so score totals are unchanged and the clone ties the original.
- **Quadratic monotonicity fails in 4 voters.** Two voters at (A 0, B 50,
  C 100) move to (A 0, B 25, C 100), a rescaled raise of C. Their credits
  shift from opposing A to opposing B, and A overtakes C.
- **Quadratic participation is open.** Exact proportional votes satisfy it,
  but whole-vote rounding and trimming to the budget can put two close
  favorites one vote out of order. No proof covers the model as implemented,
  and the search found nothing up to 7 voters.

### Search engine

- `voting/criteria/`: pure predicates (majority winner, Condorcet winner and
  loser) and transformations (raise a candidate, add voters, combine two
  electorates, remove a candidate, test for clones). No search code.
- `voting/search/`: enumerates anonymous profiles as count vectors over the
  k! rankings, in ascending size and a fixed canonical order, so the first
  decisive violation is minimal (fewest voters, then first in that order).
  `outcomes.py` resolves through the reference methods; `specimens.py` holds
  the records and `certify()`; `paradoxes.py` has one search per criterion.
- **Consistency uses winner tables** (`tables.py`): every profile up to the
  bound is resolved once by the reference method, and pairs of profiles are
  checked as numpy lookups of their pooled count vectors. No method logic is
  re-implemented.
- **Rated searches** (`rated.py`) enumerate count vectors over 18 voter
  types: each of the six rankings with its top at 100, bottom at 0 and middle
  at 25, 50 or 75. Each type's ballots are cast once by sincere-v1 and
  profiles are totaled as matrix products; a test checks those totals against
  the reference methods on random profiles, and `certify()` re-resolves every
  rated specimen from freshly cast ballots. A raise moves voters to a type
  whose utilities are a rescaling of the old ones with the winner raised;
  participation adds voters of one type; a clone gets the original's utility
  from every voter (`voting/criteria/utility_transformations.py`). The space
  grows much faster than over six rankings, so the bounds are 7 or 8 voters.
- `scripts/build_methods_artifacts.py` runs all 56 searches in parallel,
  certifies each specimen, and writes `specimens.json`, `presets.json` and a
  `manifest.json` (voting source hash and output hashes) to
  `public/data/methods/`. Tests re-certify every committed specimen and
  re-run the small searches to check they reproduce.
- **Measured cost:** the reference package resolves about 9,500
  three-candidate profiles a second under all four methods on one process.
  The full build (56 searches: ranked bounds of 20 to 24 voters, rated
  bounds of 7 or 8) takes under three minutes on 8 worker processes, and two
  runs under different hash seeds produce byte-identical outputs.
- **Four or more candidates** (24+ ranking types) cannot be enumerated very
  far. Use a seeded bounded search or an ILP, label results "smallest found",
  and record the seed and bounds.
- **Tie rule:** every profile in a specimen must be decisive: no method
  applied a tiebreak (for Ranked Pairs, no equal-strength victories whose
  order mattered), and for IRV no round eliminated several candidates tied
  for last. IRV needs the extra check because the package eliminates every
  candidate tied for last together, without a tiebreak, whenever at least
  one candidate would remain.

Search record (the committed IRV monotonicity specimen):

```json
{
  "method": "irv",
  "criterion": "monotonicity",
  "max_voters": 24,
  "specimen": {
    "id": "irv-monotonicity-3c",
    "method": "irv",
    "criterion": "monotonicity",
    "voters": 17,
    "focus": null,
    "transformation": { "kind": "raise", "candidate": "A", "ranking": ["C", "A", "B"], "position": 0, "voters": 2 },
    "profiles": [
      { "role": "before", "candidates": ["A", "B", "C"],
        "rows": [[6, ["A", "B", "C"]], [5, ["B", "A", "C"]], [2, ["C", "A", "B"]], [4, ["C", "B", "A"]]],
        "winner": "A" },
      { "role": "after", "candidates": ["A", "B", "C"],
        "rows": [[6, ["A", "B", "C"]], [2, ["A", "C", "B"]], [5, ["B", "A", "C"]], [4, ["C", "B", "A"]]],
        "winner": "B" }
    ]
  }
}
```

Raising A on two C>A>B ballots drops C below B in first choices, so C is
eliminated instead of B, and C's voters elect B.

Roles are `profile` for single-profile criteria, `before` and `after` for
monotonicity, participation, IIA and clones, and `first`, `second` and
`combined` for consistency. `specimen` is `null` when the search found
nothing up to `max_voters`.

### Ballot model v1

Ballots come from a ballot model (`voting/ballot_models/`): an interface that
takes a voter's utilities and returns the ballot it casts in every format. A
strategic model would be another implementation, built with beliefs about the
other voters. The first implementation is the sincere voter, `sincere-v1`:

- **Single choice and rankings:** the utility order; equal utilities keep
  candidate order.
- **Approval:** every candidate strictly above the voter's mean utility. An
  indifferent voter approves no one.
- **Score:** rescaled so the least favorite scores 0 and the favorite 10,
  rounded half up. An indifferent voter scores everyone 5.
- **Quadratic:** votes proportional to each utility's distance from the
  voter's mean, scaled to spend the 100-credit budget, rounded half away from
  zero, then trimmed from the largest vote until the cost fits. An
  indifferent voter casts no votes.

Rated gallery cells read "under model v1". A consequence worth showing:
approval is often said to satisfy IIA when ballots are held fixed, but under
a mean-threshold model, removing a loser moves the mean and can change the
winner.

### Atlas

Ka-Ping Yee's spatial diagram, for all seven methods. Settled with Ben on
2026-10-22:

- **Each point is an electorate.** Candidates sit at fixed positions in a
  two-dimensional issue space, the unit square with y growing downward as on
  screen. Each cell of a 64 × 64 grid holds the same voter cloud centered
  there and is colored by its winner. A cell where a tiebreak decided the
  winner is drawn lighter, never hidden.
- **The cloud is 19 voter types of 5 voters each (95 voters)** on a
  sunflower (Vogel) spiral whose radii are quantiles of a circular Gaussian
  with standard deviation 0.16. A hexagonal lattice was tried first: its
  voters share columns, and as the cloud slides, a whole column crosses a
  boundary at once and stripes the maps. The spiral gives every type its own
  x and y. An odd total rules out tied head-to-head counts.
- **The spread is fixed** and was chosen so the methods visibly disagree. A
  symmetric cloud's nearest candidate is its Condorcet winner, so the
  Condorcet-consistent methods draw near-Voronoi maps and only plurality, IRV
  and approval stray far from them; the layouts place candidates close
  enough, relative to the cloud, for that to show.
- **Utility is linear in distance.** Each voter's distances are rescaled so
  the nearest candidate gets 100 and the farthest 0, rounded half up.
  Sincere-v1 casts the same ballots under any rescaling, so the spread is
  the only free parameter, and rankings do not depend on the utility shape at
  all.
- **The reference methods count every cell,** exactly as the instrument
  counts a profile: one fresh tiebreak per method, seeded with the default
  seed. Cells with identical ballots are counted once (neighbors mostly share
  them), and Ranked Pairs reads its pairwise matrix from the aggregated
  rankings. A map takes one to five seconds, so the methods need no second,
  faster implementation.
- **Reference maps:** the Condorcet winner, with no color where the majority
  relation cycles; the utilitarian winner, the candidate with the least total
  raw distance (raw distances, not rescaled utilities, so it is a welfare
  benchmark rather than a restatement of score voting); and the disagreement
  map, the number of different winners among the seven methods.
- **Clicking a cell loads its electorate** into the instrument.
  `POST /api/voting/atlas/point` builds the cell's 19 voter types and returns
  the same response as `POST /api/voting/profile/resolve`, so the instrument
  shows exactly the electorate the map counted.
- **Moving a candidate recomputes on release** through
  `POST /api/voting/atlas`. Curated layouts ship precomputed in
  `public/data/methods/atlas.json`, so they render with no API.
- **Layouts:** a four-candidate hub (D inside A, B and C: the center squeeze
  in two dimensions), a center squeeze on a line, a clone pair, a ring of
  five, and a spread-out triangle where the methods mostly agree.
- **Where it lives:** a section of `/methods` below the gallery, with three
  to five candidates.

### Live resolution

Python remains the only resolver:

- Presets and specimens are static.
- Free edits call a new `POST /api/voting/profile/resolve` (an anonymous
  profile tagged with its ballot type in; every method's result with the
  ties its tiebreak settled, the single-profile criteria and the tournament
  out). Calls are debounced and cached by canonical profile hash.
- The deployed API is a Vercel Python function with cold starts, so the page
  pings it on load. When it is unreachable, presets and the gallery still
  work and editing shows a short offline note.
- The atlas counts 4,096 electorates per map in one request, still through
  the reference methods (see Atlas).

### Visual identity: drafting table

The contrast with apportionment is deliberate. Apportionment is about people
and places, so it is warm and humanist. Methods is about rules, so it is cool
and geometric.

| | Apportionment (almanac) | Methods (drafting table) |
|---|---|---|
| Reader | Passenger: scrolls through acts | Operator: edits, selects, steps |
| Time to thesis | Builds over many screens | Under 10 seconds |
| Type | Newsreader serif | No serif. Instrument Sans, plus a mono (JetBrains Mono or IBM Plex Mono) for every number and profile row |
| Color | Warm paper, one ink-blue accent | Cool white, flat primaries; color means candidate only |
| Motif | Hemicycle, persona | Candidate glyphs, tournament graph, ballot row |
| Motion | Timed, cinematic | Causal only, always steppable |
| Voice | Investigative history | Claim, specimen, verified |

- A `methods` token scope in `app/globals.css`, separate from the story
  kit's serif. It reuses the palette mechanism: validate the candidate colors
  with the same validator as `lib/story/palette.ts` against the methods
  surfaces. Starting hues to test: blue, vermilion, yellow with an ink
  outline, teal, violet. Glyph shape double-encodes every color.
- Text never wears a candidate color.
- A faint drafting grid sits behind figures only, never behind prose or
  controls. Hairline ink rules; small radii.
- Every figure carries a provenance chip: seed, artifact hash, package SHA.
- A dark variant is derived, not designed first.

### Routes

- `/methods` becomes the instrument, replacing the story cover.
- `/methods/lab` redirects to `/methods` (slice E); the lab's UI is gone.
  The Python `/api/elections` routes and civic scenarios still exist but
  nothing in the web app calls them.
- `?p=` holds a profile, and `?s=` with `?v=` a specimen and which of its
  profiles is showing.
- The home page gets a methods card in this identity in a later slice, like
  apportionment's.

### Accessibility and performance

- Every channel has a text readout; traces step from the keyboard; the
  gallery has a table view; glyphs back up color; reduced motion removes
  transitions.
- First load under about 500 KB of JS and data, the districting target.
  Gallery artifacts under about 150 KB gzipped.

## Build slices (one PR each)

A. **Package fixes and profile model.** Seeded default tiebreak; Ranked Pairs
   orders equal-strength victories with the injected tiebreak and sets
   `tiebreak_applied` only for real ties; an anonymous-profile type;
   single-profile criteria predicates; tests. Review with the
   `voting-package-conventions` and `voting-method-correctness` skills.
B. **Search and specimens.** Transformations, the three-candidate exhaustive
   search, the build script and artifacts, and tests that re-resolve every
   specimen.
C. **Profile endpoint.** `POST /api/voting/profile/resolve` with Pydantic
   schemas and a typed TS client. The request is tagged with its ballot type
   (`"ranked"` for now) so partial rankings, rated ballots and weights can be
   added later without breaking it. Each method's result reports every tie a
   tiebreak settled (the candidates it chose among), not only the winner.
D. **Instrument.** Voter-type editor with utility tracks, ballots panel,
   tournament graph, seven channels grouped by ballot, and traces with the
   method descriptions on `/methods`; the endpoint accepts utility profiles
   (`"ballot_type": "utility"`) and runs all seven methods through sincere v1.
   Presets are voter types: the opening cycle with evenly spaced utilities and
   the center squeeze with authored ones (C a close second for A and B voters,
   so approval, score and quadratic all find it). Presets store their full
   endpoint response in `presets.json`, so they render with no API; the
   `methods` tokens' candidate colors (light
   `#2a78d6 #d8452b #eda100 #14957a #a8479e`, dark
   `#3987e5 #e34f5f #ad8c00 #199e80 #b665c4`) pass the dataviz validator on
   all pairs, with glyph and letter as the second encoding.
E. **Gallery and tour.** The gallery grid (four ranked methods × eight
   criteria) wired to the specimens, with proofs and citations for the cells
   no specimen settles (`lib/methods/gallery.ts`); a specimen banner with its
   before/after (or first/second/together) profiles; a six-step tour (two
   presets, three specimens, the reader's turn); and the `/methods/lab`
   redirect. Ranked specimens load as evenly spaced voter types, and the
   page says so. The build writes `specimen-resolutions.json` (every
   specimen profile resolved, keyed like the instrument's URL form), so the
   tour and gallery work without the API.
F. **Rated gallery cells.** Specimens for approval, score and quadratic
   under sincere v1, searched over 18 voter types (ranking × middle utility
   at 25, 50 or 75) with exact clones; utility transformations, a matrix-total
   search kernel certified by the reference methods, and specimens that
   record their `ballot_type` and `ballot_model`. The gallery shows all seven
   methods in two groups (searched over rankings, searched over utilities),
   with proofs for the rated passes and one open cell (quadratic
   participation). Rated specimens load with their utilities as found.
   Quadratic voting's totals now follow candidate order; a set-ordered dict
   had made its trace, and so the artifact bytes, depend on string hashing.
G. **Atlas.** Spatial winner maps for the seven methods plus Condorcet,
   utilitarian and disagreement references (see Atlas): a sunflower
   voter cloud, linear utility, every cell counted by the reference
   methods, curated layouts precomputed, dragging recomputed on release,
   and clicking a cell loads its electorate into the instrument.
H. **Simulation.** Disagreement rates and Condorcet efficiency in `eval/`.
   Electorate generators are seeded samplers that return profiles, so they
   can double as an agent's beliefs about other voters.
I. **Home card.**

## Toward a delegated agent

A later goal, outside these slices: an agent that votes on a user's behalf,
strategically where that helps, in any of these elections. It needs four
layers, and this demo builds two of them.

1. **What the user wants:** a posterior over the user's utility for each
   option, from demo 2's personal learner (`preferences/personal/`). It must
   be utilities, not Phase 4's option probabilities: whether a compromise
   vote is worth it depends on how much the user prefers each option.
2. **What other voters will do:** a distribution over profiles, from slice
   H's samplers or a hand-edited profile.
3. **How ballots become outcomes:** the voting package. The injectable
   tiebreak gives exact tie probabilities by branching on each choice.
4. **The decision:** the valid ballot with the highest expected utility, in
   `agents/`, shown beside the sincere ballot with its expected gain and the
   beliefs behind it. The user can override it.

Principles: preferences stay sincere, and strategic ballots never train the
preference model; strategy is shown, never hidden; elections are simulated.

Known extensions, none a rewrite: partial rankings (truncation is a real
strategy, and later-no-harm needs it); tie lotteries; count-based or weighted
tallies for large simulated electorates (liquid democracy needs weights too);
and manipulation specimens from slice B's search, since Gibbard–Satterthwaite
guarantees every method here has one.

## Out of scope for now

- No verdict on a "best" method. The criteria are trade-offs (Arrow,
  Gibbard–Satterthwaite).
- Strategic voting is not modelled in these slices; the strategy slider
  retires. Editing ballots by hand can still show burial or compromise. See
  "Toward a delegated agent" for how it fits later.
- Later-no-harm needs truncated rankings, and `RankedChoiceBallot` requires
  complete ones today. Adding it also needs a Borda truncation convention.
- Civic framing. The civic scenarios (transit, energy, parks, budget) retire
  with the sliders.
