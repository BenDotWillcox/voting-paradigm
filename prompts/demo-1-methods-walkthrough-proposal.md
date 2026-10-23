# Proposal: a ballot-by-ballot walkthrough for the methods instrument

Status: proposal, 2026-10-23. No code changes yet. It follows the narrative
slices in `demo-1-methods-narrative-proposal.md` (all merged, #64–#68) and
revises their order. The playground, the artifacts, the API, the claims
module and the drafting-table identity stay.

## The problem

Ben's review of the finished narrative flow:

1. The page compares seven counts before the reader knows what any ballot
   asks or how any count works. The comparison is the payoff, but nothing
   earns it. Each ballot and each count needs its own introduction, one at a
   time, and no step should make the reader scroll.
2. The paradox gallery and the at-scale charts drop the reader into dense
   figures (a 56-cell table, a 21-cell matrix) without first showing what
   one cell means.

## The shape

Four chapters. Each chapter is a run of steps; each step fits on one desktop
screen and says one thing.

| Chapter | Steps | What the reader leaves with |
|---|---|---|
| **1. Ballots and counts** | 14 | What each ballot asks, and how each count turns ballots into a winner |
| **2. Same voters, different winners** | 2 | The side-by-side comparison, now earned |
| **3. When methods break** | 5 | What a fairness criterion is, three failures as stories, then the gallery |
| **4. Across many elections** | 4 | One random election, then the atlas, disagreement and Condorcet efficiency |

### Chapter 1: Ballots and counts

One electorate throughout: **center squeeze** (100 voters in three groups).
Each count step ends by adding its winner to a **scoreboard**, a strip of
seven slots that fills in as the chapter goes. By the end the reader has
watched the counts split (A, then B, then C five times) one at a time.

| # | Step | Kind | Shows | One-line point |
|---|---|---|---|---|
| 1.1 | Meet the voters | Voters | Three groups on their 0–10 scales: 35 put A at 10, C at 6, B at 0; 33 put B at 10, C at 6, A at 0; 32 put C at 10, B at 4, A at 0 | Every ballot below is read off these scales |
| 1.2 | Single choice | Ballot | Each group marks only its favorite: A, B, C | The ballot hides everything but the top choice |
| 1.3 | Plurality | Count | 35 / 33 / 32 → **A** | A wins with 35%, though 65 voters put A last |
| 1.4 | Ranked | Ballot | A›C›B, B›C›A, C›B›A | Now every preference is on the ballot, but only as an order |
| 1.5 | Instant runoff | Count | Round 1: C has fewest, out; C's 32 go to B → **B** 65 | Eliminating the weakest first choice can drop everyone's compromise |
| 1.6 | Borda count | Count | 2 points for first, 1 for second: A 70, B 98, C 132 → **C** | Second choices count, so the compromise wins |
| 1.7 | Head to head | Concept | The three two-way races: C beats A 65–35, C beats B 67–33, B beats A 65–35 | A candidate who wins every race is the **Condorcet winner**; one who loses every race is the **Condorcet loser** |
| 1.8 | Ranked Pairs | Count | Lock the strongest wins (C›B, C›A, B›A) → **C** | Built from the races, it always elects a Condorcet winner |
| 1.9 | Approval | Ballot | Approve everyone above your own average: {A, C}, {B, C}, {C} | Approval lets a voter say "these are fine," not just "this is best" |
| 1.10 | Approval | Count | A 35, B 33, C 100 → **C** | Everyone finds C acceptable |
| 1.11 | Score | Ballot | Rescale each voter's scale to 0–10: (10, 0, 6), (0, 10, 6), (0, 4, 10) | Strength now counts, not just order |
| 1.12 | Score | Count | A 350, B 458, C 728 → **C** | |
| 1.13 | Quadratic | Ballot | 100 credits; v votes cost v²; votes follow distance from your average: (+7, −7, +1), (−7, +7, +1), (−7, −1, +7) | Votes against are possible, and strong views cost more |
| 1.14 | Quadratic | Count | Net votes A −210, B −46, C 292 → **C** | |

Notes:

- Ballots come before the counts that read them, so ranked (1.4) is followed
  by all three ranked counts, with head to head (1.7) introduced just before
  Ranked Pairs, which needs it. Head to head also defines the Condorcet
  terms the comparison and the paradoxes use.
- Each ballot step shows the ballot **card** for one ballot type (the
  existing ballots panel, one card at a time) for each of the three groups,
  and states the sincere-v1 rule in plain words.
- Each count step shows that method's trace (the existing trace views,
  stepped where the method has steps: IRV rounds, Ranked Pairs locks), the
  winner, and the scoreboard.
- "About this method" and the gallery links stay, inside each count step,
  closed by default.

### Chapter 2: Same voters, different winners

| # | Step | Shows |
|---|---|---|
| 2.1 | The comparison | The seven counts side by side for center squeeze; claim title as now ("Plurality elects A, instant runoff elects B, the other five elect C"). The criteria key now refers to terms defined in 1.7 |
| 2.2 | Change the voters | Example chips (consensus, majority cycle) with their notes and the head-to-head graph beside the counts: in the cycle, there is no Condorcet winner to find. "Try it yourself" opens the playground here |

### Chapter 3: When methods break

| # | Step | Shows |
|---|---|---|
| 3.1 | What "fair" means | One sentence each for the eight criteria, in plain words, grouped: *who should win* (majority, Condorcet winner, Condorcet loser), *what shouldn't backfire* (monotonicity, participation), *what shouldn't matter* (consistency, IIA, clones) |
| 3.2 | The spoiler | Plurality, 7 voters: B beats A 4–3. Add C, a near-copy of B; B's voters split 2–2, and A wins with 3. Before and after, counted |
| 3.3 | The no-show | Instant runoff, 11 voters: B wins. Two more voters turn out who rank C›B›A, and A, their least favorite, now wins |
| 3.4 | Ranking higher, losing | Instant runoff, 17 voters: A wins. Two voters move A from second to first, and A loses to B |
| 3.5 | Every method fails something | The gallery table, now readable: each ✗ is a story like the three just told, and its number is the voters it takes. Specimens open as before |

### Chapter 4: Across many elections

| # | Step | Shows |
|---|---|---|
| 4.1 | One random election | A plane with 101 voters and 3 candidates drawn at random (the simulation's model), and the seven winners beneath it. Two examples: one where all seven agree, one where they split |
| 4.2 | Every election in a plane | The atlas, introduced as "4.1, centered at every point" |
| 4.3 | How often they disagree | The disagreement matrix with a reading guide: one highlighted cell, read aloud ("plurality and approval pick different winners in 55% of 10,000 elections") |
| 4.4 | How often they find the Condorcet winner | Condorcet efficiency, defined by pointing back to 1.7; the 99% existence rate stated here as the honest caveat (cycles are rare in this model) |

## Format

- **Steps, not slides.** The deck keeps its horizontal track, but the tabs
  become the four chapters, and a step counter ("Step 5 of 14", previous /
  next, arrow keys) moves within a chapter. `?section=` becomes `?step=`
  with stable step ids (`ballot-ranked`, `count-irv`, `paradox-spoiler`, …).
- **No scrolling on desktop.** Each step fits in the viewport below the site
  header at 1280×720 and above. The page header (title and lede) shows only
  on the first step and collapses to the kicker line after it. On phones a
  step may scroll; the constraint is stated, not hidden.
- **The playground stays** as the pinned "Try it yourself" sheet, opened
  from any step, and it loads whatever electorate the step shows.

## New content

- **Copy:** a title, one-line point and short explainer for each of the 25
  steps. Numbers in copy come from the artifacts, as now.
- **Sample elections for 4.1:** two seeded elections from the simulation's
  sampler, exported with voter and candidate positions by
  `scripts/build_methods_artifacts.py` into a new artifact, chosen by a
  declared rule (the first seed where all seven agree; the first where they
  pick three or more winners). `simulation.json` stays as eval writes it.
- **Scoreboard:** a small component, seven slots in method order, filled
  through the current count step.
- **Single-card ballot view:** the ballots panel's cards, rendered one ballot
  type at a time for all three groups.

## Settled decisions this reverses

1. **Counts first** (narrative slice 2) → ballots and counts interleaved,
   comparison second.
2. **Six slides** → four chapters of steps.
3. **Head to head as a slide after the counts** → a concept step inside
   chapter 1, before Ranked Pairs.

## Open decisions (recommendation first)

1. **One electorate for chapter 1** (center squeeze), not a best-case
   example per count. It makes the comparison a payoff and the scoreboard
   possible; the trade-off is that some counts (approval, score, quadratic)
   all elect C, so their steps teach mechanics rather than surprise.
2. **Ballots for every group, not one voter.** Three groups fit on screen,
   and seeing all three is what makes each count legible.
3. **Paradox stories from existing specimens only** (the three above). They
   are the minimal ones, which is what makes them followable.

## Suggested slices

1. Step engine: chapters, step ids, counter, keyboard, no-scroll layout,
   collapsing header; current content mapped into steps so nothing is lost.
   *Implemented 2026-10-23* (`lib/methods/sections.ts`,
   `components/methods/instrument/step-deck.tsx`). Chapters are tabs; the
   six old slides map to steps 1.1 Ballots, 1.2 Head to head, 2.1 the
   comparison, 3.1 the gallery, 4.1 the atlas and 4.2 at scale, and old
   `?section=` links resolve to them. From 1024px wide, each step is sized
   to the window below the deck; content still taller than that scrolls
   inside its step until its chapter's slice fits it. Measured at
   1280×720, the space a step has is about **490px** (350px on the first
   step, under the full title). The current content overflows by 180px
   (head to head) to 1,000px (the comparison); slices 2–4 design to that
   budget.
2. Chapter 1: voters step, single-card ballot steps, count steps with the
   scoreboard, head-to-head concept step. *Implemented 2026-10-23*: steps
   1.1–1.14 (`lib/methods/walkthrough.ts` for copy written from the
   center-squeeze resolution, `components/methods/instrument/walkthrough.tsx`
   for the views). Chapter 1 always reads the preset's stored count, so it
   never waits on the API and ignores whatever the playground holds. Ranked
   Pairs shows its locking order even with a Condorcet winner, where the
   reference trace skips it. All 14 steps fit at 1280×720 with no inner
   scroll. The ballots and head-to-head example sets (`SLIDE_EXAMPLES`) and
   `headToHeadClaim` are unused until chapter 2.2 brings examples back.
3. Chapter 2 and 3: comparison steps, criteria step, the three paradox
   stories (before / change / after), gallery as reference.
4. Chapter 4: sample-election artifact and step, atlas framing, matrix
   reading guide, efficiency step.
