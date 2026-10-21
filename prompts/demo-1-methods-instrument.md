# Demo 1: Voting methods as an instrument

Status: design settled with Ben on 2026-10-21; no slice built yet. Supersedes
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
- **Rated methods are a second layer** under a declared, versioned ballot
  model (model v1), and their gallery cells say so.
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

- Anonymous profiles in the notation voting theorists use: a count and a
  strict ranking per row.
- 3 to 5 candidates in fixed glyph order ● ▲ ■ ◆ ★.
- Edits: change a count, reorder a ranking by drag or arrow keys, add or
  remove rows and candidates. Cap at 999 voters.
- The URL carries the profile (`?p=4ACB.6BAC.3CAB.2CBA`), so any state can be
  shared.
- The **tournament graph** (pairwise-majority arrows labelled with margins)
  is the persistent anchor figure. A cycle visibly closes.

### Channels

- One row per method in fixed order. Position always means method and color
  always means candidate.
- Each row has a compact tally in candidate colors, the winner glyph, and
  lights for the single-profile criteria: majority winner elected, Condorcet
  winner elected (– when none exists), Condorcet loser avoided. A tie light
  names the tiebreak and seed when one decided the result.
- A computed summary line ("15 voters · 3 different winners · majority
  cycle").
- Selecting a channel opens its trace: plurality counts, IRV rounds with
  transfers (`IRVRound`), Borda points by position, and the Ranked Pairs matrix
  with lock order and the skipped edge (`locked_victories`,
  `skipped_victories`).
- Motion appears only to show cause and effect (a transfer, a lock). Every
  trace steps forward and back from the keyboard, and nothing is timed.

### Tour

1. **Majority cycle** (opening). `4 A>C>B, 6 B>A>C, 3 C>A>B, 2 C>B>A` elects
   B under plurality, C under IRV, and A under Borda and Ranked Pairs, with
   pairwise margins 1, 3 and 5 (no ties). An exhaustive probe found it as the
   smallest tie-free cycle where the ranked methods give three winners, among
   all 593,774 three-candidate profiles of up to 24 voters. The build script
   must reproduce this.
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
| Not applicable | The criterion is undefined for this ballot type. |

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

Rated-method cells are judged under model v1 (see Rated methods) and are not
pre-filled.

### Search engine

- `voting/criteria/`: pure predicates and transformations (Condorcet winner
  and loser, majority winner, raise, add voters, remove a candidate, insert a
  clone, split an electorate). No search code; fully unit-tested.
- `voting/search/`: enumerates anonymous profiles as compositions of n voters
  over the k! ranking types, in ascending n and canonical order, so the first
  hit is minimal (fewest voters, then lexicographic). Writes specimen records.
- `scripts/build_methods_artifacts.py` writes hashed JSON to
  `public/data/methods/`. Tests re-resolve every committed specimen with the
  reference package.
- **Measured cost:** the reference package resolved 593,774 three-candidate
  profiles (n ≤ 24) under four methods in 62 s on one process (about 9,500
  profiles a second). Cross-profile criteria multiply that by their
  neighborhood size (about 10 raise moves per profile for monotonicity), so
  three-candidate searches take minutes at build time.
- **Four or more candidates** (24+ ranking types) cannot be enumerated very
  far. Use a seeded bounded search or an ILP, label results "smallest found",
  and record the seed and bounds.
- **Optional fast kernel:** if build time becomes a problem, a numpy kernel
  may propose candidates, but only the reference package certifies a
  specimen. The kernel gets its own parity tests.
- **Tie rule:** every profile in a specimen must be tie-free. That means no
  winner tiebreak in any method and, for Ranked Pairs, no equal-strength
  victories. This depends on fixing the Ranked Pairs tie problems first.

Specimen record (sketch):

```json
{
  "id": "irv-monotonicity-3c",
  "method": "irv",
  "criterion": "monotonicity",
  "candidates": ["A", "B", "C"],
  "before": { "profile": [[4, "ACB"], [6, "BAC"]], "winner": "A" },
  "transformation": { "kind": "raise", "candidate": "A", "rows": [1], "voters": 2 },
  "after": { "profile": [[6, "ACB"], [4, "BAC"]], "winner": "B" },
  "voters": 10,
  "search": { "engine": "exhaustive", "max_voters": 24, "minimal": true, "seed": null },
  "verified": { "package_sha": "…", "tiebreak_applied": false },
  "sha256": "…"
}
```

(The profiles above show the shape only, not a real counterexample.)

### Rated methods

Rated methods are a second layer below the ranked channels. They run in a
utility mode in which ballots come from a named, versioned sincere model,
*model v1*:

- **Plurality and rankings:** the utility order. The editor enforces distinct
  utilities so rankings are strict.
- **Approval:** approve every candidate above the voter's mean utility.
- **Score:** min-max normalize to 0–10 and round half up.
- **Quadratic:** votes proportional to utility minus the voter's mean, scaled
  to spend the 100-credit budget, rounded to integers within budget.

Rated gallery cells read "under model v1". A consequence worth showing:
approval is often said to satisfy IIA when ballots are held fixed, but under
a mean-threshold model, removing a loser moves the mean and can change the
winner.

### Live resolution

Python remains the only resolver:

- Presets and specimens are static.
- Free edits call a new `POST /api/voting/profile/resolve` (an anonymous
  profile in; every method's result, the single-profile criteria and the
  tournament out). Calls are debounced and cached by canonical profile hash.
- The deployed API is a Vercel Python function with cold starts, so the page
  pings it on load. When it is unreachable, presets and the gallery still
  work and editing shows a short offline note.
- Revisit when the atlas needs thousands of resolutions a frame.

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
- `/methods/lab` redirects to `/methods` once the instrument covers it. The
  civic slider scenarios retire.
- `?p=` holds a profile and `?s=` a specimen ID.
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
   schemas and a typed TS client.
D. **Instrument.** Profile editor, tournament graph, channels and traces on
   `/methods`, with the opening and center-squeeze presets and the `methods`
   tokens.
E. **Gallery and tour.** Gallery UI wired to specimens, the tour, and the
   `/methods/lab` redirect.
F. **Rated layer.** Utility mode, model v1, and the rated gallery cells.
G. **Atlas.** Spatial winner maps.
H. **Simulation.** Disagreement rates and Condorcet efficiency in `eval/`.
I. **Home card.**

## Out of scope for now

- No verdict on a "best" method. The criteria are trade-offs (Arrow,
  Gibbard–Satterthwaite).
- Strategic voting is not modelled; the strategy slider retires. Editing
  ballots by hand can still show burial or compromise.
- Later-no-harm needs truncated rankings, and `RankedChoiceBallot` requires
  complete ones today. Adding it also needs a Borda truncation convention.
- Civic framing. The civic scenarios (transit, energy, parks, budget) retire
  with the sliders.
