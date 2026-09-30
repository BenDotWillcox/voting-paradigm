# Demo 4: Apportionment as a scrolling essay

Status: slice A (package lift + research data) in review. Decisions made with
Ben on 2026-09-30.

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
- **Unverified and therefore not used:** that Madison's amendment "remains
  pending" (no primary text read yet).

## The essay

Every number comes from generated artifacts, and every historical claim from
a `verified` or `derived` entry in `data/apportionment/facts.json`.

**Cold open.** The 2020 House as a 435-dot hemicycle: "Each dot represents
761,169 people." The "Find your state" picker appears here.

**Act I — A House that grew (1789–1910).**
1. The Constitution's 65 seats and its one-per-30,000 limit. Madison's
   amendment and its final-clause reversal.
2. Scroll-scrubbed timeline, one census per notch: the hemicycle grows from
   105 to 435 seats while people per representative climbs from about 37K to
   about 212K. It shrank only once, after 1840. The method changed by era:
   fixed ratios, then Vinton, then major fractions.

**Act II — The freeze (1920–1941).**
3. 1920: the first urban majority (51.2%), and the only census with no
   reapportionment. In 1929 the Permanent Apportionment Act fixed the House
   at 435 and made apportionment automatic; the temporary 437 of 1959–63 is a
   footnote.
4. 1941: equal proportions becomes law. The seat count is flat while people
   per representative rises to 761,169 by 2020.

**Act III — Dealing the seats.**
5. One seat per state is guaranteed, so 385 remain. The priority value
   P = population / √(n(n+1)) is explained visually.
6. Scroll-scrubbed race for seats 51 to 435: a bar race of the leading
   priorities, each award lighting a hemicycle seat. Seat 435 goes to
   Minnesota.
7. Whole seats make districts unequal: Montana against Delaware, and
   *U.S. Department of Commerce v. Montana* (1992, unanimous).

**Act IV — Just add seats?**
8. A beeswarm through 435 → 573 → 692 → 1,000 → 11,036: the extremes barely
   move until about 1,000 seats.
9. A sawtooth of the largest/smallest ratio at every House size from 435 to
   11,036. It is non-monotonic (800 seats is worse than 692) because rounding
   error concentrates in delegations of one or two seats.
10. The costs, honestly: the hemicycle at 1,000 and 11,036 seats, and
    Federalist 55 and 58 on oversized assemblies.

**Coda.** Your state at every House size, a link to the explorer, and
Methods & Sources.

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
