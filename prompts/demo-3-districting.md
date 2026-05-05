# Demo 3: Algorithmic Districting — Design Doc

Living design document for the districting demo. Edit when decisions change.

## What we're building

An interactive map of the United States showing congressional districts drawn by an algorithm — not by humans, not by political compromise. Two affordances:

1. **House-size slider.** The user adjusts the total number of congressional seats. The map redraws across all 50 states: apportionment (which state gets how many seats) updates first, then each state's district map updates to reflect its new seat count. Anchor markers on the slider call out historically and theoretically meaningful values (current 435, Wyoming Rule, Cube Root Rule, etc.).
2. **State detail view.** Clicking a state opens a higher-resolution view of that state's districts, with computed quality metrics (population deviation, compactness scores, edge counts).

The story being told: *the technology to draw transparent, constraint-driven district maps already exists. Here's what the country looks like under it. Here's how those maps respond when we revisit the size of the House — a question that has nothing to do with gerrymandering and everything to do with representational fidelity.*

## Algorithm: Balanced Power Diagrams (Cohen-Addad, Klein, Young, 2017)

Paper: *Balanced Power Diagrams for Redistricting*, arXiv:1710.03358. Code at district.cs.brown.edu.

A power diagram (a.k.a. additively-weighted Voronoi diagram) partitions space into convex polygonal cells. Each cell has a center `c_i` and a weight `w_i`; a point `x` is assigned to the cell minimizing `||x − c_i||² − w_i`. Adjusting weights moves cell boundaries while keeping cells convex.

The algorithm is a constrained Lloyd iteration:

1. Initialize `k` centers (`k` = number of districts in the state). Random or k-means++; we use a single fixed seed.
2. **Assign** each population unit (census tract) to a cell, with weights chosen so each cell contains exactly `total_state_population / k` people (population-balance constraint).
3. **Update** each center to the population-weighted centroid of its cell.
4. **Update** each weight to enforce step 2's balance constraint at the new centers.
5. Repeat until convergence (centers stabilize within tolerance).

**Properties guaranteed by construction:**
- *Convex polygonal cells* — power diagrams are convex by definition. No "salamander" shapes.
- *Population balance* — exact balance to within one indivisible unit (the granularity of our census tracts).
- *Contiguity* — convexity implies contiguity for tract-resolution input.
- *Compactness* — empirically the paper reports ~6 sides per district on average; convexity bounds the worst case sharply.

**Properties not guaranteed:**
- Respect for political boundaries (counties, municipalities). The algorithm is geometry-only.
- Voting Rights Act compliance (majority-minority districts). We don't model it.
- Communities-of-interest preservation. Same.

These omissions are honest: the demo is *"here's what pure geometric fairness looks like,"* not *"here's a deployable plan."* Acknowledge in the UI writeup.

## Locked-in decisions

1. **Census vintage:** 2020 decennial. Authoritative, matches the current apportionment, frozen reference point.
2. **Geographic unit:** census tracts (~85K nationwide). Bump to block groups (~240K) only if tract-level looks too coarse in state detail view.
3. **House size picker:** discrete toggle group over five educational anchors. The Python API still accepts any integer in **[435, 11037]** for flexibility, but the UI deliberately exposes only the values we plan to render. Anchors (computed from the 2020 apportionment population, 331,108,434):
   - **435** — current size, set by the Reapportionment Act of 1929
   - **574** — Wyoming Rule (smallest-state population sets district size; 331.1M / 576,851 ≈ 574)
   - **692** — Cube Root Rule (∛apportionment pop; ∛331.1M ≈ 692)
   - **1,000** — round-number "expanded" anchor for orientation
   - **11,037** — *Article I §2* ratio: one representative per 30,000 people, the constitutional minimum-district-size that the Reapportionment Act of 1929 abandoned
   - We do not let the user go below 435; the user has no interest in shrinking the House.

   **Why a picker, not a slider.** Earlier drafts of this doc proposed a logarithmic-scale slider over the full [435, 11037] range. We switched to a five-button toggle group at step 2 implementation: the precompute story has us computing maps at exactly five caps, not 10,600, and a continuous control would imply commitments we don't keep. URL params (`?cap=574`) still work and are snapped to the nearest anchor, so old links survive.
4. **Seed:** single canonical seed for all precomputed maps. Documented in the writeup; no UI affordance to change it. Reproducibility story stays clean.
5. **Coverage:** 50 states only. DC and territories deferred. Schema and code must not assume "exactly 50 states forever" — `state_fips` is the key, and adding rows later must Just Work.
6. **Cross-demo composition** (electorate from districting feeding methods comparison): noted, not built. Flag for future revisit.

## Architecture

Standard per-demo shape (see CLAUDE.md):

```
districting/                        Python domain package
  __init__.py
  apportionment.py                  Method of Equal Proportions; pure
  algorithm.py                      Balanced Lloyd / power diagram core; pure
  geometry.py                       Shapefile loading, polygon simplification
  metrics.py                        Polsby-Popper, population deviation, edge count
  precompute.py                     Offline pipeline (CLI entrypoint)
  tests/

api/routers/districting.py          HTTP surface
  GET  /api/districting/apportionment?cap=N        → {state_fips: seats}
  GET  /api/districting/state/{fips}?n=K           → district map for that state at K seats
  GET  /api/districting/national?cap=N             → composite national map at cap N

app/districts/
  page.tsx                          National overview + slider
  [stateFips]/page.tsx              State detail view

components/districts/               React components
db/schema/districting.ts            Drizzle tables (see Data model)
lib/districting-api.ts              Typed Python API client
```

**Boundary respect:** Python never writes the DB. The precompute pipeline calls a Server Action to persist results, OR runs as an offline seeding script (preferred — it's a one-shot, not a runtime path). Either way, runtime Python endpoints are read-only DB consumers.

**Domain isolation:** `districting/` does not import `voting/`, `preferences/`, or `delegation/`. If we later compose with methods comparison, the composition happens at the API layer, not by reaching into another package.

## Data model

New tables, all `district_*` prefixed:

### `district_state_geometry`

Pre-loaded census geometry per state. Loaded once per resolution level by the precompute pipeline.

| Column | Type | Notes |
|---|---|---|
| `state_fips` | text | PK part. e.g. "06" for California |
| `resolution_level` | enum | `tract` (initial) ; `block_group` (future) |
| `units_geojson` | jsonb | FeatureCollection of tract polygons |
| `unit_populations` | jsonb | `{ tract_geoid: population }` from 2020 decennial |
| `loaded_at` | timestamp | |

PK: `(state_fips, resolution_level)`.

### `district_run`

One row per `(state, n_districts, seed, resolution)` tuple. The cache layer for the algorithm.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `state_fips` | text | FK-conceptually to `district_state_geometry` |
| `n_districts` | int | |
| `seed` | int | The canonical seed; widening this column is how we'd add multi-seed support later |
| `resolution_level` | enum | matches state_geometry |
| `centers_jsonb` | jsonb | The `k` final `(x, y, weight)` triples — sufficient to *redraw* the diagram exactly without rerunning |
| `polygons_geojson` | jsonb | FeatureCollection: one Feature per district, with district_id property |
| `metrics_jsonb` | jsonb | `{ max_pop_deviation, mean_polsby_popper, edge_counts: [...] }` |
| `iterations` | int | How many Lloyd iterations to converge (telemetry) |
| `computed_at` | timestamp | |

Unique: `(state_fips, n_districts, seed, resolution_level)`.

Apportionment results are not stored — they're cheap and depend only on the cap.

### `district_apportionment_cache` *(optional, only if needed)*

If the apportionment computation surprises us by being expensive (it shouldn't be), we cache `cap → {state_fips: seats}`. Skip this table unless profiling demands it.

## Cost model and performance strategy

### Apportionment

Method of Equal Proportions: each round, the next seat goes to the state with the highest *priority value* `population / sqrt(n * (n+1))` where `n` is its current seat count. Total cost: O(C log S) for `C` seats and `S` states. Cap of 1000 → ~1ms. **Always run live.**

### Districting (the expensive operation)

Per-state Lloyd iteration. Empirically (rough estimates, validate during step 3):
- Small state (1–3 districts, few hundred tracts): under a second.
- Medium state (5–15 districts, few thousand tracts): a few seconds.
- California / Texas (40+ districts, ~9K tracts): tens of seconds.

This is too slow to run live for 50 states on every slider tick. **Precompute it.**

### Critical structural insight

A state's district map at a given seat count depends ONLY on `(state_fips, n_districts, seed, resolution_level)`. It does NOT depend on what other states received, on the global cap, or on anything else. So:

- The same California-at-52-seats map is reused whether the cap is 435, 500, or 600 — as long as the apportionment gives California 52.
- Total distinct precompute jobs = sum over states of (number of distinct seat counts that state ever receives across the cap range).

### Sizing the precompute job

For cap range [435, 11037], we enumerate apportionment at each integer cap value and collect the set of `(state_fips, n_districts)` pairs that appear. The total seat count across all 50 states equals the cap, so the sum of distinct seat counts per state across the range is bounded above by `(11037 − 435) + 50 ≈ 10,650` distinct `(state_fips, n_districts)` pairs.

Per-state ranges across [435, 11037]:
- Wyoming: 1 → ~19 districts (576,851 / 30,000)
- California: ~52 → ~1,316 districts (39.5M / 30,000)
- Texas: ~38 → ~967 districts
- Median state: a range of ~150–300 distinct values

**Total expected: ~9,000–11,000 distinct precompute jobs.**

Cost per job scales roughly as O(units × n_districts × iterations). California at 1,316 districts on ~9K tracts is the worst case — each Lloyd iteration is ~12M (unit, center) ops, with 50–200 iterations to converge. That's tens of seconds to a few minutes per worst-case job.

**Wall-clock estimate, parallelized across cores: 10–30 hours of one-time precompute.** Tractable but no longer "a few hours" — it's an overnight batch job. Worth running on a beefier machine than a laptop. If it bites, we can:
- Cap precompute at, say, 3,000 districts/state and fall back to live computation for higher counts (the user is unlikely to linger at the extreme end of the slider — the visualization is mostly a pixel mush there anyway).
- Drop to coarser-than-tract resolution for the upper half of the cap range (no one can see tract-level detail in a state with 800 districts on a national map).
- Use a faster solver: warm-start each `(state, K)` job from the converged result of `(state, K−1)` so most iterations only rebalance one new center.

Decide at step 5 based on actual measured costs from step 4.

### Visualization at high cap values

At cap=11,037, the average district has ~30,000 people. On a national map, individual districts are sub-pixel almost everywhere — California with 1,316 cells looks like uniform color. This is fine for the *story* the slider tells (the user is meant to feel the absurdity at the extreme), but the UI should:
- Render district *counts per state* as the primary signal at high cap values (color/label rather than polygon detail)
- Defer detailed polygon rendering to the state-detail view, where 1,316 California districts at state-level zoom *is* a meaningful visualization
- Possibly switch the national map to a choropleth of seat-count-change-vs-baseline at high caps, since individual polygons stop carrying information

This is a UI decision for step 5/6, not an algorithmic one.

### Runtime path

```
User drags slider to cap=N
   ↓
GET /api/districting/national?cap=N
   ↓ (Python, ~ms)
   apportion(cap=N) → {state_fips: seats}
   for each state: SELECT polygons FROM district_run
                   WHERE state_fips=? AND n_districts=? AND seed=CANONICAL
   ↓
   Composite national GeoJSON
   ↓
Frontend re-renders map
```

Latency budget: under 200ms for the slider to feel live. Apportionment is sub-ms; the 50 DB lookups can be a single query (`WHERE (state_fips, n_districts) IN (…)`). Bottleneck is GeoJSON serialization size — handled by simplifying geometry at precompute time.

### State detail view

Click a state → navigate to `/districts/{fips}?cap=N`. The single-state map is already cached; we just show it with more detail and the metrics panel. No live computation in the default flow.

## UI plan

### National overview (`/districts`)

- **Top:** title, one-paragraph framing, "How this is computed" disclosure.
- **Cap picker:** five-button toggle group, default 435 selected. Anchors:
  - 435 — Current (1929 cap)
  - 574 — Wyoming Rule
  - 692 — Cube Root Rule
  - 1000 — "Expanded" round-number anchor
  - 11,037 — Article I §2 ratio (1 per 30,000)
  Each button shows the cap number prominently with the anchor's label below; hover reveals a one-sentence explanation. URL `?cap=` query param is snapped to the nearest anchor for compatibility.
- **Map:** US albers projection, 50 states with district polygons overlaid, lightly tinted by district. Hover shows state + seat count. Click navigates to state detail.
- **Sidebar (right):** at the current cap, show: total seats, top-5 states by seat count, total state-level seat changes vs current 435 baseline, link to methodology writeup.

### State detail (`/districts/{fips}`)

- **Header:** state name, flag, current district count at the chosen cap, link back.
- **Map:** zoomed-in state, district polygons clearly distinct, district numbering visible.
- **Metrics panel:**
  - Population per district (with deviation from ideal)
  - Polsby-Popper compactness score per district + mean
  - Edge count per district (paper says ~6 average)
  - Iterations to convergence (algorithm telemetry, kept honest)
- **Comparison:** side-by-side option to show today's actual congressional districts (TIGER/Line) for the same state, for visual contrast. Real maps look very different from algorithmically convex ones; that's the point.

### Stretch: live regeneration

Not in v1. If we add it: a button "regenerate this state with a new seed" → fire request to `POST /api/districting/run` → progress indicator → updated map + metrics. Cache the new result. Surfaces the role of the seed.

## Build sequence

Each step is a shippable layer.

### Step 1 — Apportionment (Python only, ~100 LOC)

- Implement Method of Equal Proportions in `districting/apportionment.py`.
- Pure function `apportion(state_populations: dict[str, int], total_seats: int, *, min_per_state: int = 1) → dict[str, int]`.
- Pytest with the well-known 2020 apportionment as a regression test (we should reproduce 435 → known seat distribution exactly).
- FastAPI route `GET /api/districting/apportionment`.
- **Acceptance:** hitting the API with `cap=435` returns the actual 2020 apportionment.

### Step 2 — Static national map with real districts (UI only, no algorithm)

- Load TIGER/Line 2020 congressional district shapefiles into `district_state_geometry`-shaped storage (or a static asset).
- Build the national map UI with state interaction, click-to-detail navigation, slider component (slider works visually but at this stage only updates apportionment numbers, not maps).
- **Acceptance:** the full UI shell works, cap slider updates numbers, clicking a state navigates. No algorithm yet — maps are real congressional districts.
- This unblocks frontend work before the algorithm work blocks anything.

### Step 3 — Balanced power diagram core

- Implement Lloyd iteration with population-balance constraint in `districting/algorithm.py`.
- Pure function: `(units: list[Unit], n_districts: int, seed: int) → DistrictingResult`.
- `Unit` carries `(geoid, centroid, population, polygon)`. `DistrictingResult` carries centers, weights, assignments, polygons, iteration count.
- **Test plan:**
  - Unit tests: 100-point grid → 4 districts, verify population balance ≤ 1 unit, verify cells are convex, verify each unit assigned to nearest cell under power-diagram metric.
  - Property tests: random small inputs, check determinism given seed.
  - Validation: against published Brown maps for at least one state if we can match parameters.
- **Acceptance:** algorithm runs on a small synthetic input, reproduces the published demo for one state.

### Step 4 — Schema migration + precompute pipeline for one state

- Drizzle migration creating `district_state_geometry` and `district_run`.
- Loading script: download TIGER/Line tract shapefiles + 2020 decennial population, populate `district_state_geometry` for all 50 states at tract resolution.
- `districting/precompute.py` CLI: `python -m districting.precompute --state <fips> --n-districts <K>` writes one `district_run` row.
- Run for one moderate state (e.g., Colorado) at its current 8 districts. Visualize result.
- **Acceptance:** end-to-end: shapefile → algorithm → DB → API → rendered map for one state.

### Step 5 — Scale precompute to all 50 states across the cap range

- Enumerate the `(state_fips, n_districts)` set across cap range [435, 1000] by running apportionment at each cap.
- Filter out 1-district states (the trivial case — entire state is the one district).
- Run precompute for all jobs. Parallelize across cores. Log iteration counts and convergence stats — useful for the writeup.
- Wire the national overview to query `district_run` for all 50 states at the current cap's apportionment.
- **Acceptance:** dragging the slider updates all 50 states' maps in under 200ms.

### Step 6 — State detail page with metrics

- Implement metrics in `districting/metrics.py`: Polsby-Popper, population deviation, edge counts.
- Compute and store in `district_run.metrics_jsonb` during precompute.
- State detail page: zoomed map + metrics panel + comparison to real congressional districts.
- **Acceptance:** clicking a state shows a credible portfolio artifact — clean polygons, honest metrics, side-by-side with reality.

### Step 7 — Methodology writeup

- A `/districts/methodology` page (or expandable section) explaining: the algorithm, the constraints it does and does not enforce, the role of the seed, the limits of geometric fairness, link to the paper.
- Honest about what's missing: VRA compliance, communities of interest, political-boundary respect.

### Step 8 — Stretch (defer to its own branch)

- Live "regenerate with new seed" affordance for a single state.
- Side-by-side comparison of two seeds.
- Block-group resolution for state detail view.
- DC + territories.
- Cross-demo: feed a districting result into the methods-comparison demo to simulate House elections under different methods.

## Reproducibility

- Algorithm is deterministic given `(state_fips, n_districts, seed, resolution_level, input_data_hash)`. Seed is the single canonical seed; data hash is the SHA of the loaded census shapefile + population data. Record all five on every `district_run` row.
- Precompute pipeline is idempotent: rerunning produces byte-identical results. CI can spot-check this with one or two cells.
- Apportionment is fully deterministic; no seed needed.
- The single-seed choice is documented in the methodology writeup. Future multi-seed work is a non-breaking schema extension (`seed` is already on the row).

## Open questions / decisions to revisit

These didn't need answering up front but will at some point:

1. **Map rendering library.** d3-geo (clean, code-forward), react-simple-maps (convenient), mapbox-gl (interactive zoom/pan), or vanilla SVG. Decide at step 2.
2. **Polygon simplification level for the national overview.** Too detailed → big GeoJSON, slow render. Too simplified → ugly. Tune empirically at step 5.
3. **PostGIS or JSONB GeoJSON.** Starting with JSONB. If query patterns get hairy (spatial joins, neighbor lookups), upgrade. Should not block step 5.
4. **TIGER/Line vintage.** 2020 to match the census. Confirm we use the same vintage for tract geometry and population data.
5. **Apportionment edge case: what if cap < 50?** Not applicable (our floor is 435), but worth a guard so the API can't be called with nonsense.

## Future work (deferred)

- DC and territories support.
- Block-group resolution for state detail.
- Live seed-regeneration affordance.
- Multi-seed comparison view.
- Cross-demo composition with the voting-methods comparison: simulate a hypothetical House election under various methods, given a chosen districting.
- Alternative algorithms for comparison (shortest splitline, MCMC ensemble methods à la Mattingly/Duchin) — would significantly expand the portfolio depth but is its own demo's worth of work.
