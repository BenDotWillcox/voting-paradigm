# Demo 4: Apportionment as a scrolling essay

Status: slice A merged (PR #48); Acts I–IV and the coda built, in review.
Decisions made with Ben on 2026-09-30 and as each act was built.

## Why an essay

Each demo gets a presentation style that suits its argument. Apportionment is
the lightest demo technically (the Method of Equal Proportions is a short
priority-queue loop). Its strength is the argument and a counterintuitive
finding: the popular fixes barely close the gap in district size between
states. So it becomes a scrolling essay carried by animation, historical
research, and visualization.

## Decisions

- **Stance: investigative.** Open with a question, follow the evidence to the
  finding, present the costs of a larger House fairly, and let the reader
  conclude. No advocacy voice.
- **Research thread: history from 1789 to 1941.** Out for now: international
  comparisons, the Electoral College, and close-call anecdotes (e.g. New York
  missing the 435th seat by 89 people).
  (Act IV, 2026-10-07: Pew's 2018 OECD comparison is now used, with its date.)
- **Reader interaction: pick your state.** An early picker personalizes every
  later figure. Otherwise pure scroll; free exploration stays at
  `/apportionment/explore`.
- **Visual motif: the seat hemicycle**, one dot per seat.
- **Visual identity:** a "civic almanac" look inside the story kit: warm paper,
  ink-blue accent, hairline rules, act markers, citation sidenotes.

## What the research changed

- **Madison's amendment is not a "keep districts small" story.** As Congress
  sent it to the states, the final clause reads "nor *more* than one
  Representative for every fifty thousand persons", reversing the "nor less
  than" of the clause before it. It would allow any House from 200 seats up to
  about 6,622 today, so the current 435-seat House would satisfy it. The beat
  becomes: even the founders' own fix would not have required a larger House.
- **Wyoming Rule = 573, not 574.** Measured consistently (apportionment total
  ÷ Wyoming's apportionment population, or 50-state resident total ÷
  Wyoming's resident population), the rule gives 573. The widely reported 574
  mixes the two measures.
- **Article I allows at most 11,036 seats**, since 331,108,434 ÷ 30,000 =
  11,036.9. Rounding up to 11,037 would exceed the ratio.
- **Primary seat source:** the House Historian's table (1787–2020), with one
  convention throughout. The Senate Manual table and the Census CSV are
  cross-checks. The only disagreements are two documented conventions and a
  Senate Manual erratum (it prints Maine's 1860 apportionment as 3; the 1862
  act gave 5).
- **The cube-root law is contested.** Taagepera (1972) proposed it; Margaritondo
  (2021) argues its classic derivation is flawed. The essay presents it as an
  empirical regularity, not a rule.
- **The 1929 act never says 435.** Section 22 (46 Stat. 26–27, read against
  the page images) apportions "the then existing number of Representatives"
  and, if Congress "fails to enact a law", the President's statement takes
  effect. The House was frozen by carrying its size forward, not by a number.
- **Unverified and therefore not used:** that Madison's amendment "remains
  pending" (no primary text read yet).

## Revisions after review (2026-10-07)

An outside review read the whole essay; every recommendation was adopted.

- **Two gaps, kept apart.** How many people a member represents and how
  unequal that is across states are reported side by side at every proposed
  size (prose, header, and a persistent comparison strip with the change
  from 435). The conclusion follows the evidence: a larger House reliably
  shrinks constituencies, narrows interstate disparities unevenly, and has
  institutional costs arithmetic can't settle.
- **Corrections.** Every state average is first within 2% at 6,279 seats
  (not "only" at 11,036; it is +2.13% there); the typical state's gap falls
  "overall", widening on 303 of 565 additions from 435 to 1,000.
- **Precise measures.** State averages are never called districts; "using
  the 2020 census" replaces population "today"; the coda's scope is the 50
  states.
- **The 30,000-person benchmark** replaces "Article I's limit": the national
  reading gives 11,036, Washington's 1792 veto applied the cap state by
  state, and 23 states would average under 30,000 per seat at 11,036.
- **History.** People per seat rose 5.7-fold while the House grew; the
  growth counter shows "one seat per N people" beside the seat count. Long
  clips open on the operative passage, the full text a click away.
- **Costs and benefits.** Costs are at today's resources per member (an
  estimate, not a forecast), total and added; a step separates what the
  arithmetic establishes from what needs evidence (constituent service,
  committee specialization, floor time, leadership control).
- **What it would take.** A closing section: ordinary legislation, within
  the 30,000 cap, and the choice between a fixed number and a per-census
  rule (CRS IN11547).
- **Interaction.** Begin no longer blocked by the label layer; chapter menu,
  progress line and a text-only mode; skip control for the race; shorter
  holds and step gaps (about 48 viewport-heights to the coda at 1440×1000,
  under 9 in text mode); a unit label on every scene; the ladder as dots on
  a labeled log axis; the band chart labeled (log scale, the blue band as ±
  the median gap, half the states inside) with a cursor naming the extreme
  states; map classes by percentage with a neutral band within 3% and a
  state list; on phones a shorter pinned figure, notes folded into "About
  this chart", and an Expand control.

## The essay

Every number comes from generated artifacts, and every historical claim from
a `verified` or `derived` entry in `data/apportionment/facts.json`.

**Act I — "The Representation Gap"** (direction agreed 2026-10-01; approved
copy lives in `components/apportionment/essay/`):

1. Title with a stretch/tear motif that loops while on screen (tension,
   rip, hang apart, snap back), then the one-paragraph hook. Reduced motion
   holds a static partial tear.
2. One intro scene: a "Select a state" tile-map picker (any state, not
   necessarily the reader's) beside a figure headed "Someone in [State]" (a
   stand-in for anyone there, not the reader). Tiles are colored by 2020
   people per seat against the national average (teal fewer, clay more;
   three classes per arm, never red/blue), with a legend and a
   hover/selection readout. "Imagine a life in [State]." / "A fictional
   person in a real congressional district." Begin is a large button on the
   figure itself, visible without scrolling on a 1366×768 screen; Skip
   animation and a reduced-motion path; nothing locks scrolling.
3. Occupation shuffle (30 roles, including people outside paid work),
   settling on a role and a real district number, typed in: "A teacher in
   Ohio’s 11th congressional district." / "… Wyoming’s at-large
   congressional district." The stage stays light throughout.
4. "But nobody is just a teacher." The figure becomes a low-poly
   constellation and steps aside from center. Each shard is one value,
   concern, or circumstance: three named shards (a responsibility or
   circumstance, a belief or community tie, a concern or hope) arrive one
   at a time, each flying from its words, which show only while it lands.
   Then the figure returns to center as a rush of unnamed shards fills it,
   implying the many more. About 14 seconds in total. Narrow stages keep
   the figure centered with each piece's words beneath it.
5. Scroll-driven zoom out in the story kit's `stage` layout: on wide
   screens the figure fills the viewport (counter top left, visual in the
   right two-thirds) and each step's words pin as a lower-third caption at
   the bottom left while the figure acts them out; phones keep caption
   cards under the figure. One caption covers the zoom to 10,000; its
   last line ("By 10,000 people…") appears when the figure gets there. First
   the finished person lifts off the stage and
   glides into the crowd's empty circle (scroll-linked, reversible; scrolling
   on mid-intro finishes it; reduced motion skips the flight), where the
   canvas draws that same mesh and accessory. Then one person to 1,000 (the
   reader's person ringed until too small to see); then to 10,000, where the specks flow together
   into ten dots of exactly 1,000 (a balanced power-diagram split); then
   dots of 1,000 out to the constituency, which pours into one seat of the
   chamber, with the state's delegation highlighted.
6. The same figure carries the history: the crowd's chamber hands over to a
   <Hemicycle> drawn in exactly the same place, and the counter gives way to
   the House's own header (label, caption, seats, population). Header text
   changes the way captions do (old up and out, new up into place) while the
   numbers count. Why
   representatives (one step), ending on "How many people should one
   representative speak for?", beside today's House.
7. History, with primary sources as clips: verbatim quotes from the fact
   register brought in front of the chamber (which recedes), with phrases
   highlighted as the reader scrolls. 1789 (65 seats), then the
   Constitution's clause; Federalist 58 on growth and on who directs a large
   assembly.
8. The first proposed amendment: the version Congress sent to the states as
   a clip, its final clause highlighted, then stamped "Never ratified" as
   the caption says so (no modern calculation).
9. Growth census by census to 1913 (435 seats), keeping the 1911 act separate
   from the 1913 House. It starts back at the First Congress's 65 seats.
   Historical chambers order seats by age, not by state: the original 65
   (gray), every seat added since (muted blue), and the latest census's net
   additions (strong blue) at the right end, so the colored counts match the
   numbers exactly (per-state seats cannot: states gain and lose seats in
   the same census). New seats slide in from the side; removed ones (1840)
   slide out. The chamber's empty center counts seats added since 1789 and
   the change from the census before (under the chamber on phones).
10. "The country kept growing. The House did not.", with the numbers (92.2 →
    106 million people, still 435 seats): population 1910 → 1920 while the chamber
    stays at 435 ("No change since the 1910 census"), a padlock snaps shut
    over the chamber, and the title's tear returns. The act ends at the threshold
    of the 1920 story.

Pacing (revised 2026-09-30): Act I is about 14 viewport heights at desktop
size, down from 23. Scrolly steps are slots whose text is sticky, so words
never leave while their figure is still scrubbing; the last slot ends when the
pinned figure starts to scroll away. On phones every scrolly pins its figure
as an opaque band at the top; step cards pin just below it (higher if too
tall to fit) and slide away underneath it, so text never covers a figure.
The title, picker, and stage fill at least one screen, so Act I starts below
the fold.

**Population rules for the zoom.** At-large states use the 2020 census
resident population, because the district is the whole state. Multi-district
states use the Census Bureau's state average per seat, labelled as an
average and never as the named district's population; no district-level
data is vendored yet. With no state chosen, the zoom uses the national
average of 761,169.

**The person.** The person comes from `lib/apportionment/persona.ts`:
- Seeded per visitor and state, so it is stable across reloads, scrolling
  back and replays.
- 30 roles (including people outside paid work), each with its own accessory.
- A person is first a hidden fact sheet: household and children's ages,
  housing, pets, faith, veteran and union status, loans, business, commute,
  budget, health. Every statement (117 across responsibilities,
  circumstances, faith and community ties, concerns, and everyday life) is
  eligible only when those facts make it true, so pieces cannot contradict
  each other.
- `scripts/check-persona-consistency.mjs` (run by pytest) samples 300,000
  people against independent rules: incompatible pairs, role-only
  statements, reachability of every statement, label length, determinism.
- Views are never inferred from occupation, faith or other identity; a
  concern depends only on factual prerequisites (rent worries need a renter).

The earlier prologue and hemicycle cold open were superseded by this act.

**Act II — The freeze (1920–2020)** (built 2026-10-06; copy in
`components/apportionment/essay/act-two.tsx`). It continues on Act I's
stage, in the same Scrolly (`house-story.tsx` joins the two acts' steps), so
the locked chamber never leaves the screen:

1. 1920, one beat beside the locked chamber: the first urban majority
   (51.2%), apportionment shifting seats from smaller rural states to
   larger urban ones, rural and urban factions unable to agree, and the
   only census with no reapportionment.
2. 1929, the Permanent Apportionment Act as a clip (sec. 22 as enacted, from
   the Statutes at Large): highlighted, "the then existing number of
   Representatives", "fails to enact a law apportioning Representatives…",
   and "each State shall be entitled". The act never names a size: it froze
   the House by reapportioning whatever it had.
3. The locked chamber shrinks into the legend icon of a "Fixed at 435" band
   on a people-per-seat chart, and the line draws 1790 → 1920 (gray while
   the House grew, clay once it stopped).
4. Census by census, 1930 → 2020, the header counting population; 1941
   (equal proportions, still law) appears at 1940, with the temporary 437
   of 1959–63 as a footnote.
5. Finale: one seat for every 761,169 people, more than three times 1920's
   241,864.

People per seat is resident population ÷ seats through 1910 (the only
measure for the whole run) and the Census Bureau's apportionment population
per representative from 1920 (so the chart ends on the official 761,169);
the figure's caption says so.

**Act III — Dealing the seats** (built 2026-10-06; copy in
`components/apportionment/essay/act-three.tsx`, figures in `deal-figure.tsx`).
Still the same stage. Decisions (with Ben): same figure, formula plus a
visual, an even-paced race (the reader sets the speed), dot plot plus the
court clip.

1. The chamber grows back out of Act II's chart legend, its 435 seats empty
   rings, and the 50 guaranteed seats light across it west to east.
2. The formula as the Census Bureau writes it, claim to a state's nth seat =
   population ÷ √(n(n−1)) (the reciprocal of the geometric mean), with the
   reader's state's claims as a ladder on a log scale against the line that
   won seat 435 (762,998); Minnesota, the 435th seat's winner, when no state
   is chosen.
3. The race for seats 51–435: the eight strongest claims as re-sorting bars
   (the reader's state keeps a row), each award lighting a seat in its
   state's wedge, at an even pace across the step. Minnesota's 762,998 beats New York's 762,994. The race is
   computed in the browser and throws unless it reproduces the published
   apportionment.
4. Whole seats leave districts unequal: a one-axis swarm of all 50 states'
   people per seat, colored as on the picker, Montana (542,704) to Delaware
   (990,837); Act IV can reuse it across larger Houses.
5. *U.S. Department of Commerce v. Montana* (1992) as a clip from the United
   States Reports (p. 463): "inexorably compels a significant departure from
   the ideal" and "virtually impossible to have the same size district in
   any pair of States, let alone in all 50".
6. Montana regained its second seat after 2020 and now has the smallest
   districts; Delaware's single district has 83 percent more people.

The page then ends with a short threshold paragraph ("Would a bigger House
close these gaps?") and the explorer link.

**Act IV — Just add seats?** (built 2026-10-07; copy in
`components/apportionment/essay/act-four.tsx`, figures in `state-swarm.tsx`
and `bigger-figure.tsx`). Same stage. Decisions (with Ben): named stops,
extremes plus the typical state, practical costs with new sourcing (this
reverses the earlier "no international comparisons"), and the persona in
the coda.

1. Act III's dot plot becomes a swarm against the national average, and the
   50 dots glide through 435 → 573 (Wyoming Rule) → 692 (cube root) → 1,000 →
   11,036 (Article I's limit). The header gives the largest ÷ smallest ratio
   and the average district: 1.83×, 1.76×, 1.75×, 1.35×, 1.04×. At 573 and
   692 the largest district is further above average (+35%) than today
   (+30%). Where the states nearly agree (11,036) the dots pile into a clump
   and the extremes' labels point outward.
2. Every size from 435 to 11,036 (log scale) as a band: smallest to largest
   district against the average, with the typical state's gap inside it,
   drawn left to right. The extremes stall until about 1,000 seats (810 is
   wider than 692), and up to 1,000 they are always states with five seats
   or fewer; the typical state's gap falls steadily (3.4% → 1.4% at 1,000).
3. Costs: the chamber at 1,000 and 11,036 seats with what members cost
   (salary $174,000 plus the average office allowance $1,928,107, CRS 2026:
   $2.10 billion a year at 1,000, $23.2 billion at 11,036, up to 198,648
   staff), and the House's chamber, in use since 1857. The 448-seat count
   from older CRS editions was dropped by CRS in 2026, so it is not used.
4. Other democracies: Pew Research Center's 2018 OECD comparison (U.S. about
   747,000 per seat, Japan 272,108, Mexico 247,965, Iceland about 5,500).
5. Federalist 55 as a clip over the 11,036-seat chamber, then back to
   today's 435: "No House size makes every district equal."

The sweep runs in the browser (`lib/apportionment-sweep.ts`) and
`scripts/check-apportionment-parity.mjs` checks it against
`house-sizes.json` at every size: award order, extremes, ratio and median
deviation.

**Coda** (`coda.tsx`, `methods.tsx`). The person from the opening returns
(or "one person, anywhere in the country"), with how many people share
their representative at each named size, their state's people per seat at
every size (log scales, against the national average), and the explorer
link. Then Methods & Sources: how seats, populations and House sizes were
computed, and every verified or derived claim in the register with its
sources.

## Slices

| Slice | Contents | `/apportionment` after merge |
|---|---|---|
| A | Package lift, data pipeline, fact register, tests. No UI. | cover (unchanged) |
| B | Story-kit extensions + cold open + Act I | cover, picker, growth timeline |
| C | Acts II–III | + the freeze and the seat race |
| D | Act IV + coda + Methods & Sources | complete essay |

## Data pipeline (slice A)

- `apportionment/` package: `methods.py` (Method of Equal Proportions),
  `history.py` (source parsers and merged history), `analysis.py`
  (rule-defined sizes, award order, seat race, inequality sweep).
- `scripts/fetch_apportionment_sources.py` vendors the sources into
  `data/apportionment/sources/`. It needs network access and `pdftotext`.
- `scripts/build_apportionment_story.py` reads only vendored files and writes
  `public/data/apportionment-story/`:
  - `history.json`
  - `race-2020.json`
  - `house-sizes.json`
  - `anchors.json`
  - `manifest.json`

  The artifacts total about 52 KB gzipped.
- `.gitattributes` keeps both directories byte-exact so the hashes hold on
  every platform.
- Tests in `apportionment/tests/`:
  - Cross-checks between the three sources.
  - Every derived claim checked against the data.
  - The build is byte-identical and matches the committed artifacts.
  - The manifest hashes match the files.
  - TypeScript/Python parity, via `scripts/check-apportionment-parity.mjs`.
