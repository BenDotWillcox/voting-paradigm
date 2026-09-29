# Storytelling redesign: methods + districting

Status: Phase 1 merged (PR #46). Phase 0 (story kit) in review. Decisions
below were confirmed with Ben on 2026-09-25.

## Why

Both demos have strong ideas but read as dashboards: every card, tab, badge,
and control has equal weight, and there is no single moment where the viewer
*sees* the thesis. They are also slower than they should be. The target is the
long-form scroll narrative of Anthropic's Economic Index reports: editorial
typography, one sticky figure that changes as prose steps scroll past, big
annotated numbers, and restrained color.

## Baseline measurements (2026-09-25, local production build)

| Surface | Measurement |
|---|---|
| `/methods` first load | ~540 ms, ~300 KB JS — fine |
| `/methods` slider change | Server Action → Python, ~220 ms API alone, 55 KB response, no debounce or cache |
| `/districts?tab=districting&state=06` | **9.1 MB HTML, 2.2 s** — plan summaries (with dissolved geometry) embedded as RSC props, Michigan embedded on every state |
| California tract topology | **23 MB raw / 4.2 MB gzip**, quantized but unsimplified, one arc per ring (no shared arcs), rendered as ~9k SVG paths |
| `us-states.json` | 404 KB full-precision GeoJSON embedded in every districts page |
| Michigan playback | seed-center positions are a hard-coded jitter, not the recorded solver run |

## Decisions

1. **Enacted-map comparison: yes.** Districting story ends with algorithmic vs.
   enacted 118th-Congress districts (TIGER CD118): Polsby-Popper and population
   deviation, with an explicit note on the limits of geometric fairness.
2. **Static-first: yes.** Stories render with no Python process. Python remains
   the source of truth by generating seeded, hashed JSON artifacts at build
   time; only the interactive sandbox calls the live API.
3. **Methods leads with the Condorcet cycle.** Transit (vote splitting) becomes
   the second act.
4. **Explorers move out.** Current explorers move to `/methods/lab` and
   `/districts/explore`; the story pages ship without them. Revisit embedding a
   compact explorer at the bottom after reviewing the stories.
5. **Apportionment is its own demo (2026-09-29).** It answers a different
   question from districting (seats per state vs. lines within a state), with
   different evidence. It becomes demo 4 at `/apportionment` +
   `/apportionment/explore`, listed last among built demos because its
   technical surface is the lightest; liquid democracy becomes demo 5. An
   apportionment-methods comparison (divisor methods, paradoxes,
   Balinski–Young) is a possible later deepening, not planned.

## Phase 0 — Story kit (one PR)

Built: `components/story/` (`StoryRoot`, `StoryHeader`, `Prose`,
`SectionHeading`, `BigNumber`, `Scrolly` + `ScrollyStep` with
`useScrollyStep` / `useScrollyProgress`, `StoryFigure` + `DataTable`, chart
primitives `AxisX`, `AxisY`, `Annotation`, `ChartTooltip`, `useElementWidth`,
`useReducedMotion`), `.story` tokens in `app/globals.css`, and the
`/story-kit` reference page. Explorers moved to `/methods/lab`,
`/districts/explore`, and `/apportionment/explore` with redirects from old
URLs; `/methods`, `/districts`, and `/apportionment` are story covers until
their stories land.

Finding from the reference page (feeds Phase 3b): modest House growth barely
changes interstate inequality. The largest/smallest district ratio is 1.83×
at 435, 1.76× at 574 (Wyoming Rule), and 1.75× at 692 (Cube Root). It only
collapses past ~1,000 seats (1.35×) and reaches 1.04× at 11,037, because
states with one or two seats dominate the rounding error.

- `components/story/`: sticky-figure scrollytelling section driven by
  `IntersectionObserver` (no new dependency), prose step, big-number callout,
  chart annotation primitives.
- Design tokens: serif display face, ~65ch prose measure, warm neutral
  background, one accent plus a small validated categorical palette (replaces
  per-bloc rainbow OKLCH).
- Story charts are bespoke D3 + SVG/canvas; Recharts only in sandboxes.

## Phase 1 — Districting performance (this branch)

Goal: every districting page under ~500 KB on first load, no Python needed.

1. Stop passing plan geometry through RSC props. The server embeds only a small
   plan-metadata file; geometry is fetched as static assets.
2. New display pipeline (`scripts/build-district-display.mjs`, mapshaper):
   - full-resolution tract topology moves out of `public/` to
     `data/districting/tract-topo/` as the pipeline source;
   - per plan, emit `plan.json` (metrics, centers, no geometry),
     `districts.topo.json` (dissolved, simplified), and `tracts.topo.json`
     (shared-arc topology, simplified to display resolution).
3. Render the tract layer on `<canvas>` with a pick-buffer for hover; district
   outlines and centers stay as a small SVG overlay.
4. Replace the embedded state GeoJSON with a simplified, precision-reduced
   display copy.
5. Remove the Python round-trip from `/districts` and `/districts/[stateFips]`
   (the local apportionment sequence already produces the same numbers); make
   state pages static with `generateStaticParams`.

## Phase 2 — Methods, static-first story

Python build script (`scripts/build_methods_story.py`) writes seeded, hashed
artifacts to `public/data/methods-story/`:

- full resolutions at each story beat;
- one-at-a-time control sweeps (scenario × control × 21 values → winner per
  method) — instant sandbox moves plus a "winner strip" chart;
- a 21×21 phase diagram over the two most interesting controls, per method —
  the signature visual of where methods disagree;
- a simulation study in `eval/` (spatial model + impartial culture): pairwise
  method-disagreement rates, Condorcet efficiency, voter-satisfaction
  efficiency.

Story beats:

1. Condorcet cycle: three blocs, every option loses a head-to-head. The
   tournament graph closes into a loop; "majority rule" has no answer.
2. How each method breaks the cycle differently — seven methods, several
   winners.
3. Transit: 100 voters as dots; plurality elects Highway at 32%, then the dots
   re-sort to show 68% rank it last.
4. IRV rounds as flowing dots; approval/score bars.
5. Phase diagram: the method matters as much as the voters.
6. Criteria failures demonstrated (IRV monotonicity), not listed.
7. Simulation-at-scale results.
8. Link to `/methods/lab` (live API, resolves on slider commit, cache-first).

## Phase 3a — Districting story (`/districts`)

1. One-line bridge: apportionment fixes the number of districts per state
   (link to `/apportionment`).
2. Michigan balanced power diagram driven by **recorded** solver snapshots
   (precompute stores centers/weights/populations every k iterations; removes
   the jitter placeholder).
3. Algorithmic vs. enacted maps: compactness and population deviation.
4. Link to `/districts/explore`.

Implication of the split: the enacted-map comparison only exists at 435
seats, so precomputing district maps across other House sizes is no longer
needed for this story.

## Phase 3b — Apportionment story (`/apportionment`)

1. People per representative, 1790–2020, marking the 1929 freeze and the
   Article I 30,000 ratio.
2. Dot plot of people per seat by state at 435 seats.
3. Scroll-driven House growth 435 → 574 → 1,000 → 11,037 (the `/story-kit`
   beeswarm is the prototype): the extremes barely move until ~1,000 seats.
4. Equal Proportions as an animated priority queue.
5. Link to `/apportionment/explore`.

## Phase 4 — Stretch

Block-group resolution for selected states; extra enacted-map metrics; decide
whether compact explorers belong at the bottom of each story.
