# Demo 3 explainer: how a district map gets computed

Status: outline agreed 2026-10-30; all nine chapters built the same day. It
refines Phase 3a of `prompts/storytelling-redesign.md` (Michigan, recorded
solver snapshots, enacted comparison, link to the explorer).

## Decisions so far

- **Walkthrough state: Michigan, 13 districts (House 435).** It exercises every
  core stage at a readable scale: a dense Detroit core against a sparse Upper
  Peninsula, 37 detached pieces to repair, 29 rebalancing moves. It also has
  the most complete explorer assets (land display, derived water paths, cities,
  block chunks).
- **Detours for the one stage Michigan never needs.** Michigan is strictly
  connected because census water blocks share edges with land blocks across the
  Straits of Mackinac, so it has no recorded links. Hawaii (16 recorded water
  links between islands) and Kentucky (the Kentucky Bend exclave, 1 recorded
  link) show the recorded-link policy.
- **Real data, not illustrations.** Every stage shows the saved Michigan run,
  except where a stage was never saved (see the data section).
- **One page.** `/districts` is the whole demo: the explorer and this
  walkthrough on the same page, replacing the old story cover.
  `/districts/explore` redirects there (decided 2026-10-30).
- **Explorer first.** The page opens on the explorer; this walkthrough follows
  below it as "how the map above was computed" (decided 2026-10-30).
- **Visual language matches the explorer.** Peridot board, mono readouts,
  indicator lights; map data colors stay the explorer's.

## The numbers the story is built on (Michigan K13, seed 20200955)

| Stage | Largest deviation from ideal (775,179.31) | What happened |
|---|---|---|
| Power diagram, blocks assigned by point | ±121 people | 13 cells; 80 outer iterations, cap reached |
| Connectivity repair | ±635 people | 37 detached pieces absorbed: 77 blocks, 1,960 people, 13 pieces with no residents |
| Rebalancing | ±1.69 people | 29 single-block moves to a local optimum; largest − smallest district = 3 people |

Repair concentrates in Wayne (18 blocks), Roscommon (10), Monroe (9) and
Oakland (7). The largest detached piece is 17 blocks; the most populous holds
474 people. The largest rebalancing move carries 372 people, the smallest 1.

Final weights are relative (mean-centered, m²). The Upper Peninsula district's
weight is about +18.9 × 10⁹ m², roughly a 137 km "reach bonus"; the Detroit-area
districts sit near −2.7 × 10⁹ m². That contrast is the clearest single picture
of what a weight does.

## Story outline (agreed with Ben, 2026-10-30)

The walkthrough sits below the explorer as "how the map above was computed".
Each chapter is a figure with numbered steps beside it; sequences get
step/play controls. Reduced motion shows each step's end state.

1. **Michigan, in census blocks.** Start with the state, then zoom into a single
   2020 census block (a generic census-form illustration, not the Bureau's
   logo). 254,730 blocks, 10,077,331 residents. Block boundaries follow roads,
   streams and shorelines, not population: a tiny dense Detroit block next to
   an enormous Upper Peninsula one. The 15-digit block ID broken into state,
   county, tract and block. 10,332 blocks have no land at all (water).
2. **The block graph.** Two blocks touch only if they share a boundary of
   positive length; corners don't count. Water blocks are ordinary blocks,
   which is how the Upper Peninsula reaches the Lower Peninsula across the
   Straits of Mackinac without any invented bridge. Some blocks are several
   separate polygons; connectivity is checked part by part, so two pieces of
   one block do not count as connected because they share an ID.
3. **When land doesn't touch.** 7 of 50 states needed recorded links, 76 in
   all (polygons unchanged; a link counts only when both endpoints share a
   district):
   - Hawaii: 16 open-ocean links between islands, the longest about 277 km.
   - Kentucky Bend: an exclave cut off by a loop of the Mississippi, with
     Missouri across the river and Tennessee to the south; one 5.1 km link.
   - New York County: a 795 m water link to Liberty Island and an 852 m
     exclave link to Ellis Island (also crossing New Jersey land), both from
     New York's harbor water (confirmed from the endpoint blocks).
   - Alaska: 49 links up to about 293 km along the Aleutians, drawn in a frame
     continuous across the 180° meridian.
4. **The rules.** Inputs are block shapes and population counts only: no party,
   race or incumbents' addresses. Goal: equal population, 775,179.31 people
   per district. Constraints: exactly 13 districts (from apportionment, link to
   `/apportionment`); whole blocks only; every block assigned, water included;
   each district one connected piece of the graph. Not a constraint:
   compactness, which the squared-distance math produces on its own. Note the
   2020 block counts carry the Census Bureau's privacy noise; state totals are
   exact, so balance is measured on published counts.
5. **Seeds.** Population-weighted k-means++ from a fixed seed (20200955): each
   seed is drawn with probability proportional to residents × distance² from
   the seeds already chosen. Same seed, same map.
6. **The power diagram, running.** A time-lapse of Michigan's 80 iterations: a
   block goes to the center minimizing distance² − weight; an inner solve sets
   the weights that balance population (semi-discrete optimal transport,
   L-BFGS-B); each center then moves to its population centroid. The Upper
   Peninsula's weight is a ~137 km reach bonus. The method never looks at the
   graph. It ends at ±121 people with 37 pieces cut off from their districts,
   and the iterations hit the 80-round cap before the centers fully settled.
7. **Repair.** Each district keeps its most-populous connected piece; every
   detached piece joins a touching district, choosing the least balance damage.
   Balance gets worse: ±635. The 37 real moves, in order.
8. **Rebalance.** One boundary block at a time, only if the move strictly lowers
   the worst deviation and disconnects nobody. 29 moves to ±1.7 people;
   largest and smallest district end 3 apart.
9. **What was checked, and what wasn't.** Independent population, graph and
   polygon validation. Not claimed: a global optimum, compactness, county
   preservation, Voting Rights Act compliance, partisan fairness. Michigan's
   computed map next to its enacted one, then back up to the explorer with
   Michigan selected.

## Data build (static-first)

One script, `scripts/build_districting_explainer.py`, writes hashed JSON for
the story. Sources:

- **Saved, reusable as is:** every block's assignment after the power diagram,
  after repair and final; the ordered repair and rebalance moves with their
  blocks; final centers and weights. These live in the original checkout's
  cache (`BLOCK_PLAN_CACHE_ROOT`, `state-block-benchmark/suite-through-1000/
  states/26/districts-13/`), not in the explorer bundle.
- **Recomputable cheaply:** the 13 k-means++ seeds in order (same seed, no solve).
- **Needs one instrumented rerun:** centers, weights and cell populations per
  outer iteration. The saved run kept only optimizer diagnostics per iteration.
  The rerun (about 3 minutes) must reproduce the saved final centers and
  assignments exactly before its snapshots are trusted.
- **Derived geometry:** power-cell polygons per snapshot clipped to the state
  outline; dissolved district outlines for the power-diagram and after-repair
  stages; polygons for the 106 moved blocks.

Payload targets: the story's first view loads no block-level data; block points
and move polygons load per chapter.

Rebuild order: `scripts/record_michigan_power_diagram.py` (about 3 minutes)
and `scripts/record_michigan_validation.py` (about 10 seconds), both with
`--cache-root` and `--pipeline-root`, then the explainer build (about 40
seconds). The build stops if any recorded or replayed figure disagrees with the
saved run.

## Built so far (2026-10-30)

- `scripts/build_districting_explainer.py --cache-root <BLOCK_PLAN_CACHE_ROOT>`
  (run with `BLOCK_PLAN_PYTHON`) verifies the TIGER archive and GEOID order
  against the saved K13 run and the shared-edge graph cache, then writes
  `public/data/districting-explainer/` (every block's internal point and
  population in graph order, curated geometry windows, stats, hash manifest).
  The client fetches files by content hash and verifies each SHA-256.
- Chapter 1 (state → Detroit slice → block 2016 in Wayne County with its ID
  split → a 155 km² Luce County block → every block as a point), chapter 2
  (Detroit neighbor links → a real corner-only pair → the 10-block St. Ignace
  to Mackinaw City chain, 4 water blocks, drawn through shared-boundary
  doorways → a 4-piece Huron County island block → the 254,730-node,
  617,141-edge graph) and chapter 3 (the rules sheet), in
  `components/districting/walkthrough/`. Figures use the explorer's own
  Michigan outline and projection; the camera uses van Wijk smooth zoom.
- Chapter 3 (Hawaii's 16 links; the Kentucky Bend, whose cut-off piece is
  found from the data as the part of Kentucky the window encloses; Liberty and
  Ellis Islands against New Jersey; Alaska's 49 links in its continuous frame)
  and chapter 4 (the rules). Kentucky and New York use their own blocks plus
  neighbors dissolved from their own block sources; Hawaii and Alaska use the
  explorer's state outlines; links come from each House-435 plan through the
  bundle's hash allowlist.
- Chapters 5–6 come from `scripts/record_michigan_power_diagram.py`, an
  instrumented rerun of the K13 solve with the exact recorded solver (a
  preserved byte-identical copy) and block loader, checked by SHA-256 against
  the run. It is written to `data/districting-explainer/` only if the final
  centers, weights and all 254,730 assignments equal the saved run. The
  explainer build turns it into exact power cells (half-plane clipping in the
  solver's plane) for the seeds, all 80 rounds and the final balance pass.
  Chapter 5: points → seed 1 (∝ population) → the residents × d² draw for
  seed 2 in five equal-chance shades → 13 numbered seeds → nearest-seed
  cells (±2,145,221). Chapter 6: the power-distance and border formulas with
  reach circles √(wᵢ − min w) → an autoplaying round player (paused under
  reduced motion) with center trails, population bars and a log trace of
  center moves → the 147 km northern reach vs Detroit's 0 → the 80-round cap,
  ±121, and 37 cut-off pieces.
- Chapters 7–8 replay the saved move audit; the repair code that ran is not
  preserved byte for byte, so nothing reruns. The build replays the 37 repair
  and 29 balancing moves from the saved power-diagram assignments and stops
  unless they reproduce the saved after-repair and final plans exactly, each
  repair move is a whole non-anchor piece touching its new district, and each
  balancing move strictly improves the exact objective with a connected donor.
  It ships the power-diagram labels (one byte per block; the client replays
  the moves for later stages) and three block windows. Chapter 7: 37 pieces in
  all 13 districts → the west end of Belle Isle (17 empty blocks) cut off from
  District 10 → joining District 2 as move 15 → 5 Oakland County blocks with
  474 people (District 8 → 1) → every district connected, ±635. Chapter 8: the
  first 372-person move (±635 → ±263) → the four move rules on the block graph
  → 29 moves to ±1.69 → a local optimum, 3-person spread vs ±0.69 best.
- Chapter 9 runs the pipeline's read-only validator
  (`final_state_plan_validation.py`) through
  `scripts/record_michigan_validation.py`; the build cross-checks its findings
  against its own replay and rechecks final graph connectivity. The enacted map
  is TIGER/Line 2023 CD118 (`enacted-cd118/26/` in the cache, with a manifest
  and SHA-256), assigned by block internal point; area-majority assignment gives
  identical populations, and 4 empty Detroit River blocks fall outside the 2023
  boundary. Enacted: ±635, 1,122-person spread, 15 of 83 counties split, mean
  Polsby-Popper 0.37; computed: ±1.69, 3, 36, 0.27. Compactness uses
  full-resolution shapes clipped to the 1:500,000 cartographic land outline.
  Steps: checks → what is not claimed → the enacted map → side by side →
  back to the explorer with Michigan selected. `DistrictingMethodPanel` is
  retired.

## Review pass (2026-10-31)

Page order is now walkthrough first, explorer last (`#explorer`, with a jump
link under the title "A practical, apolitical algorithm"). Changes from Ben's
walkthrough review:

- Navigation: the last step's Next scrolls to the next chapter, and to the
  explorer after chapter 9.
- Chapter 2: the graph grows out of the Detroit blocks in rings. The Straits
  step now uses the true fewest-block crossing between the peninsulas (5
  blocks, 3 water, just west of the Mackinac Bridge; no water block touches
  both shores, 12 chains tie), drawn as the shortest line through the chain and
  lit block by block in a loop. The old 10-block chain was the fewest blocks
  between two chosen town blocks.
- Chapter 3: renamed "Special cases"; the Kentucky Bend opens on Kentucky,
  Missouri and Tennessee and flies in; Alaska's 180° wording rewritten.
- Chapter 4: the rules take the stage, five rows with illustrations, facts and
  reasons.
- Chapter 5: each k-means++ draw replayed exactly in the build (u, chance,
  rank) and played seed by seed with its chance map and formulas.
- Chapter 6: opens on why the seeds aren't enough; adds the Kantorovich dual
  and its gradient; the time-lapse slows early, speeds up, and zooms to a
  three-district junction in western Wayne County (down to 0.8 km).
- Chapters 7–8: before/after loops with a corner badge; Belle Isle's 283 m gap
  to District 10 is drawn and crossed out; the integer objective is written out.
- Chapter 9 (revised 2026-11-01): six steps. Checks; four decisions (the
  last combines communities, race and election data); "Gerrymandering, side
  by side" for North Carolina, Illinois, Texas and Maryland, each with its
  sourced case (Rucho in the intro), a focus city's district count within 10
  km on both maps (Chicago 7 vs 4, Austin 4 vs 2, Greensboro 3 vs 1,
  Baltimore 3 vs 3) and the serving map's least compact district outlined
  with the cities it takes in (Illinois's 17th: Peoria, Rockford,
  Bloomington, Moline); Michigan's enacted map; Michigan side by side;
  "Explore all 50 states", which opens the explorer on the national view.
  All compactness is Polsby-Popper on land shapes simplified to about 500 m.

Loading (2026-11-02) runs down the page: the walkthrough's chapters 1–4
data, then chapters 5–9, then, at low priority while the browser is idle,
the seven files the explorer opens with at House 435 (about 26 MB, served
immutable, so the explorer later reads them from the HTTP cache). Data saver
and 2G/3G connections skip that step. The explorer mounts two screens ahead
of the reader. The jump buttons open it at once, hold back the chapters they
scroll past, and keep it in place while the chapters around the landing draw.

## Proposed slices

1. Done: data build plus chapters 1–4 (blocks, the graph, recorded links, the
   rules).
2. Done: seeds and the power-diagram time-lapse (chapters 5–6).
3. Done: chapters 7–8, repair and rebalancing from the real moves.
4. Done: chapter 9, validation, enacted comparison and explorer handoff; the
   method panel is retired.
5. Done (2026-11-02): demo 3's home card, in the dashboard's circuit-board
   identity like the methods and apportionment cards. On hover or focus,
   Michigan's recorded solve plays from the 13 seeds through sampled
   balancing rounds, then rings mark the 37 repaired pieces and the 29
   rebalanced blocks, beside each stage's largest gap from the target
   (±2,145,221, ±121, ±635, ±1.69 people). Touch screens play it while it is
   on screen; reduced motion holds on the seeds, and every gap stays in the
   list. The cells are drawn in the solver's own plane from
   `michigan-power-diagram.json` and `michigan-repair.json`, prepared on the
   server (`lib/districting-home-card.ts`).

## Open questions

- Whether to add a second compactness measure (Reock) beside Polsby-Popper.
