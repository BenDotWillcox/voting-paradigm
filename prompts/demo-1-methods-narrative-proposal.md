# Proposal: a narrative spine for the methods instrument

Status: proposal, 2026-10-23. No code changes yet. It revises the slide
order and copy in `demo-1-methods-instrument.md` ("Revision: slides and a
playground") but keeps the slide format, the playground, the artifacts, the
API and the drafting-table identity.

## The problem in one line

The six slides are six instruments, not six steps of one argument: the page
explains ballots before it shows why anyone should care, changes its unit of
analysis three times without saying so, and shows most of the playground
twice.

## The spine

One claim, four zoom levels, each named as the reader crosses it.

> **Same voters, different winners — and no method is safe.**
>
> 1. *One election:* seven methods, three winners. (slides 1–3)
> 2. *The worst elections:* every method fails a fairness test somewhere. (slide 4)
> 3. *Every election in a plane:* where each method's winners live. (slide 5)
> 4. *Typical elections:* how often it matters. (slide 6)

Each slide gets a **claim title** (a sentence the graph proves), one
**takeaway line**, a **"how to read this"** aside, and a row of **examples**
in place of the electorate bar. Slide transitions name the zoom.

## Header

- Kicker: `Voting methods · instrument` (unchanged).
- H1: **Same voters, different winners.** (unchanged; slide titles stop
  repeating it).
- Lede, replacing the 60-word table of contents:
  *"Seven voting methods count the same voters. Here they elect three
  different candidates — and every one of them, somewhere, breaks a rule
  most people assume is basic fairness."*
- Target: the first slide's graph is above the fold at 1440×900.

## Slides

| # | Tab | Claim title | Takeaway (one line) | Graph | Examples |
|---|---|---|---|---|---|
| 1 | Seven counts | **Plurality elects A, instant runoff elects B, everyone else elects C** | The candidate with the *fewest* first choices wins under five of seven methods. | Seven channels + trace of the selected method | **Center squeeze** (default) · Consensus (all seven agree) · Majority cycle → "see slide 2" |
| 2 | Head to head | **C beats every rival one-on-one** | Plurality and IRV never let C reach a two-way race; when nobody beats everyone, each method breaks the cycle its own way. | Tournament graph | Center squeeze · Majority cycle (three winners, no Condorcet winner) · Clear Condorcet winner |
| 3 | Ballots | **Rated ballots hear how much, not just which order** | The ballot model, not just the count, decides what score, approval and quadratic voting see. | One voter type's utility track and its five ballots | A clear favorite · An indifferent middle (approval collapses to plurality) · A close second |
| 4 | Paradoxes | **Every method fails a fairness test** | Each ✗ is a real election, and the number is how few voters it takes. | Gallery grid + open specimen before/after | Spoiler (plurality, 7 voters) · Monotonicity (IRV, 17) · Clones (Borda, 5) · Quadratic monotonicity (4) |
| 5 | Atlas | **Same candidates, same voters, different maps** | With D at the center, plurality gives D 2.5% of the map; approval gives it 61%. | Main map + method thumbnails | Hub · Center squeeze · Clones · Ring of five · Spread out |
| 6 | At scale | **In typical elections they still disagree** | With five candidates, plurality and approval pick different winners in 55% of 10,000 elections, and plurality misses the Condorcet winner in 37%. | Disagreement matrix first, Condorcet efficiency second | 3 · 4 · 5 candidates |

Closing beat below slide 6: *"Your turn"* → opens the playground with the
current electorate.

### Transitions (one line at the top of each slide)

- 2: "Why does C win most counts but lose two? Look at the two-way races."
- 3: "Ranked methods read the order. The other three read a 0–10 scale —
  here is how a voter's scale becomes each ballot."
- 4: "So far, one electorate. Now the *worst* electorate we could find for
  each method."
- 5: "Worst cases are rare by construction. Here is every electorate in a
  plane at once."
- 6: "And across 30,000 random elections?" The slide also says the honest
  caveat outright: *in this spatial model a Condorcet winner exists in over
  99% of elections, so cycles are rare — disagreement is not.*

## Why this order

- **The thesis comes first.** Center squeeze shows "different winners" with
  an intuitive story (the compromise candidate squeezed out) and a clear
  Condorcet winner, so the criteria columns on slide 1 have something to
  report instead of 21 cells of "does not apply".
- **Each slide answers the previous slide's question.** Slide 1 raises "why
  C?"; slide 2 answers it with head-to-head races and introduces Condorcet
  where it is needed; slide 3 answers "why do the rated methods agree with
  each other?" by showing the ballot model.
- **Ballots move from 1 to 3.** They are the mechanism, not the hook. Slide 1
  says in one line where the rated ballots come from and links forward.
- **The atlas stays at 5** rather than becoming the hero: it needs the
  reader to already know what a Condorcet winner is and why plurality
  splits. A static atlas thumbnail could illustrate the header, but that is
  optional.

## What moves where

**Leaves the slides → playground only**
- The electorate bar (preset buttons, live summary, "Open in the
  playground"). Examples replace it; each example chip has a small
  "open in playground" affordance.
- Voter-count steppers and the full profile editor (already playground-only).

**Collapses within slides**
- Slide 1 trace: "Also called / Strengths / Weaknesses / Where it's used"
  move behind an "About this method" disclosure. Weaknesses that the gallery
  demonstrates link to their specimen (IRV non-monotonicity → the 17-voter
  specimen).
- Slide 1 criteria columns: Maj. / Cond. / Loser get full-word headers with
  hover definitions; a column whose criterion applies to no method in the
  current electorate is dimmed with one note, not repeated per row.
- Slide 4 intro: keep two sentences (what a ✗ and a number mean, what a ✓
  means). The search space ("middle candidate at 2.5, 5 or 7.5"), the
  re-checking and the clone construction move to a footnote under the grid.
  Criterion column headers get one-line definitions on hover/focus. The
  legend moves above the grid.
- Slide 5 intro: two sentences; the per-layout paragraph keeps one headline
  claim, with the rest behind "more on this layout". Layout tabs read
  "Hub · 4 candidates", not "Hub4".

**Moves to provenance**
- The page footer (ballot model, artifact hashes, endpoint, tiebreak seed)
  becomes a closed **"Methods & provenance"** disclosure at the bottom.
- Each figure keeps a single mono caption line (seed, n, interval) so the
  rigor requirement "seeds, bounds and hashes on every figure" still holds;
  full hashes live in the disclosure.

**Navigation**
- One playground entry point: the pinned "Try it yourself" tab, plus
  contextual "open in playground" on examples, specimens and atlas points.
  Remove the three repeated "Open in the playground" bar buttons.
- Keep tabs + arrows; drop the dots (redundant with the numbered tabs).

**Copy fixes regardless of the restructure**
- "load it above" (gallery) and "into the instrument above" (atlas) are
  stale; both open the playground.
- Default selected method on slide 1 should be the first channel that
  disagrees with the plurality winner, rather than IRV regardless of the electorate.

## Settled decisions this reverses

These were recorded as settled in `demo-1-methods-instrument.md`, so each
needs an explicit yes:

1. **Opening preset: majority cycle → center squeeze.** The cycle stays as
   the second example on slides 1 and 2, where it becomes the twist.
2. **Slide order: Ballots first → Ballots third.**
3. **Electorate bar on slides 1–3 → example chips.** (The revision already
   specified examples per slide; the bar is what shipped instead.)

## New content required

- **Consensus preset** (all seven agree): a new static artifact from the
  Python preset builder, with its resolution.
- **Clear-Condorcet-winner** and **ballot examples** (clear favorite,
  indifferent middle, close second) for slides 2 and 3: small presets or
  single-type profiles.
- Claim titles and takeaways above, checked against artifacts at build time
  (any number quoted in copy should come from the artifact, not be typed).

## Open questions

- **Carousel or vertical scroll?** The slide format was settled today and
  this proposal keeps it. A vertical scroll with a sticky chapter rail (as
  in the apportionment essay) would remove the variable-height track and the
  swipe-versus-atlas-drag conflict; worth revisiting only if the restructure
  still feels cramped.
- **Does slide 3 earn a full slide**, or does it become an expandable panel
  on slide 1 ("how were these ballots made?")? Five slides is a tighter arc.

## Suggested slices

1. Copy only: header lede, claim titles, takeaways, transitions, stale-copy
   fixes, provenance disclosure. No reordering. *Implemented 2026-10-23.*
   The counts and head-to-head claims, the counts transition and the
   at-scale takeaway are written from the shown electorate and the
   simulation artifact (`lib/methods/claims.ts`), so they stay true for any
   preset, specimen or edit. The gallery's "load it above" was not stale
   (the specimen banner opens above the table) and was only clarified.
2. Reorder slides and switch the opening preset; replace the electorate bar
   with example chips (existing presets and specimens only). *Implemented
   2026-10-23* with the two presets only: loading a specimen from slides 1–3
   would move the page to the paradox slide, so specimens stay in the
   gallery. Each example carries a note per slide (`PRESET_COPY` in
   `lib/methods/instrument-data.ts`), shown only while the preset is
   unedited, and a quiet "Explore it in the playground" link; the counts
   slide links forward to Ballots.
3. New presets (consensus, clear Condorcet winner, ballot examples) and
   slide-3 examples.
4. Collapse within slides: "About this method", criteria headers, gallery
   footnote and legend, atlas layout copy.
