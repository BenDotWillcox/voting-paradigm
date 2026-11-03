# AGENTS.md

Guidance for Codex working in this repository. This is a living document — edit it when architecture changes, not the other way around.

## What this project is

**Nebula Civitas is a portfolio of demos exploring potential improvements to democratic voting.** Each demo isolates a specific friction that has blocked better voting practice from being adopted at scale, and shows how modern technology — AI agents, statistical preference modeling, optimization, network analysis — could plausibly dissolve it. The demos share infrastructure (one repo, one Next.js shell, one FastAPI service, one DB) but are conceptually independent: each is a self-contained answer to one objection against electoral reform.

The umbrella thesis: the gap between *what voting theory recommends* and *what real polities use* is technological as much as political. Better methods, better districts, better delegation, better preference articulation — none have spread because the practical machinery wasn't there. This project builds parts of that machinery as proofs of concept.

**This is a portfolio project**, not a product. The audience is AI/ML
engineers evaluating the author's work. Synthetic personas drive development
benchmarks; final preference evidence may include one explicitly labeled
personal case study and a separately approved small opt-in pilot. There are no
real elections, binding outcomes, production accounts, auth-hardening, crypto,
identity verification, or scale requirements. Optimization target:
*demonstrated judgment, clean architecture, and depth in AI engineering,
statistical modeling, and systems design.*

### The demos

Each demo is a top-level route in the web app and a domain package on the Python side. Demos can compose where it falls out naturally (e.g. an electorate produced by the districting demo can feed the methods comparison) but each must stand alone as a portfolio artifact.

| # | Demo | Route | Status | Core showcase |
|---|------|-------|--------|---------------|
| 1 | **Voting methods comparison** — same ballots, multiple resolution methods, side-by-side winners | `/methods` | Instrument, paradox gallery, atlas and simulation built | Voting theory rigor, electoral criteria, reproducibility |
| 2 | **Agent voting via preference models** — LLM-elicited preference posterior; agent casts a ballot under uncertainty | `/preferences` | In progress | Bayesian inference, embeddings, active learning, LLM orchestration |
| 3 | **Algorithmic districting** — fair, transparent district maps under explicit constraints | `/districts` | One page: the nine-chapter Michigan algorithm walkthrough, then the four-anchor block-plan explorer | Optimization, graph algorithms, geo data, fairness metrics |
| 4 | **Liquid democracy** — delegation graphs, transitive trust, topic-conditional delegates | `/delegation` | Planned | Network analysis, simulation, dynamics on graphs |

The list is open — additional demos can be added as peer packages without disturbing existing ones. New demos must justify themselves by isolating a *distinct* friction with a *distinct* technical showcase; otherwise they're noise.

### Explicitly out of scope

- Real elections, binding outcomes, cryptographic voting
- Real user accounts, identity verification, multi-tenancy
- Mobile apps, on-chain anything, production-grade ops
- A "grand unified" demo that ties everything together — let each speak for itself; cross-demo composition is opportunistic, not architectural

## Working with the user

- **Domain expertise:** the user knows voting theory deeply. Ask clarifying questions about electoral behavior rather than assuming. Cite criteria (Condorcet, monotonicity, IIA, etc.) when discussing trade-offs.
- **Reviews code before committing:** walk through logic when requested; don't bundle unrelated changes.
- **Python > TypeScript for numerical/ML work:** scipy, numpy, PyTorch ecosystem. TypeScript is for the web frontend only.
- **Git workflow:** feature branches + PRs. Never commit without asking.
- **Project review skills:** use the focused checklists under `.claude/skills/`
  for database, Server Action, voting-package, voting-method, and PR-review
  work.

## Architecture

Two processes. One web app, one Python service.

```
┌─────────────────────┐        ┌──────────────────────────────┐
│ Next.js 15 (App     │◄──────►│ FastAPI (Python 3.11)        │
│ Router) + React 18  │  HTTP  │ One service, one router/demo │
│ Routes: /methods,   │        │  /api/voting/...             │
│ /preferences,       │        │  /api/preferences/...        │
│ /districts (future),│        │  /api/districting/... (future)│
│ /delegation (future)│        │  /api/delegation/...  (future)│
│ Server Actions →    │        │  /api/personas/...    (future)│
│ Python API client   │        │  /api/agents/...      (future)│
└──────────┬──────────┘        └────────────┬─────────────────┘
           │                                │
           ▼                                ▼
    ┌──────────────────────────────────────────┐
    │ PostgreSQL (Drizzle ORM, single schema)  │
    │  - Next.js owns writes via Server Actions│
    │  - Python reads only (never writes DB)   │
    └──────────────────────────────────────────┘
```

**Why two processes, not one:**
- Next.js owns UI, routing, forms, auth boundary, and DB writes
- Python owns numerical modeling (scipy/numpy), voting resolution logic, LLM orchestration, and simulation
- The boundary forces clean contracts (Pydantic request/response models, typed TS clients) which doubles as portfolio signal

**Why one Python process, not two:** the previous split (`voting/api` on :8000, `preferences/api` on :8001) had no justification beyond accidental evolution. One FastAPI app with multiple routers is simpler to run, document, and demonstrate.

**Why Python never writes the DB:** single source of authority. Server Actions handle persistence; Python receives state and returns updated state, stateless per-call. This keeps the transactional story simple and makes Python endpoints trivially reproducible given an input state.

## Repository layout

```
.claude/skills/              Versioned project review checklists
app/                        Next.js App Router pages (incl. /methods demo explorer)
components/                 React components (domain subfolders + ui/ for shadcn)
actions/                    Server Actions — "use server", return ActionResult<T>
db/
  schema/                   Drizzle table definitions (one file per domain)
  queries/                  Pure DB functions — no revalidation, throw on error
  migrations/               Drizzle-generated SQL + journal (never hand-edit)
lib/
  *-api.ts                  Typed clients for the Python service (server-only)
  validations/              Zod schemas (form + JSONB boundary validation)
types/                      Shared TS types
voting/                     Python: pure voting methods + ballot types       [demo 1]
preferences/                Python: preference modeling                       [demo 2]
personas/                   Python: simulated voter generation               (future) [demo 2]
agents/                     Python: agent voting policies                    (future) [demo 2]
districting/                Python: redistricting algorithms                 (future) [demo 3]
delegation/                 Python: liquid democracy delegation graphs       (future) [demo 4]
eval/                       Python: synthetic + human-measure evaluation       [cross-demo]
api/                        Python: FastAPI app, one router per demo
prompts/                    Project scope + documentation
```

**Domain packages are import-isolated.** `voting/` does not import `preferences/`; `districting/` does not import `delegation/`. `api/` imports every domain but domains do not import `api/`. No circular deps; every package is testable without the HTTP layer.

**`voting/` is a foundational primitive, not a demo-specific package.** Other demo packages MAY import `voting/` (liquid democracy resolves delegated tallies; districting may simulate within-district elections; agent voting casts ballots that are tallied by voting methods). This is the only such cross-demo dependency that's allowed by default — everything else is independent.

**All other demo packages are mutually isolated.** `preferences/` does not import `districting/`; `delegation/` does not import `preferences/`. If a demo's *UI* wants to compose another demo's results, it does so at the API or Server Action layer, not by reaching into another demo's Python package. Shared types that genuinely belong to multiple demos (e.g. an `Electorate` definition) get lifted into a small, clearly-named shared package rather than living inside one demo's namespace.

## Data model

The schema grows per-demo. Each demo owns its own tables, namespaced by clear prefixes (`measure_*`, `preference_*`, future `district_*`, `delegation_*`). Cross-demo joins are allowed but go through small, deliberate shared tables (`user`, `electorate`) that genuinely belong to more than one demo.

### Shared (used by ≥2 demos)

- **`user`** — actors (simulated personas authored by one real user). Used everywhere voters appear.
- **`domain`, `program`** — two-level topic taxonomy. Used for measure filtering (demo 1) and will be reused for topic-conditional delegation (demo 4).
- **`electorate`** — a named simulated population with generation parameters and a seed. Reproducible. Used by demos 1, 2, 3, and 4 — different demos populate it from different sources (synthetic preference distributions, geo-grounded sampling, etc).

### Demos 1 + 2 (methods comparison + agent voting)

These two demos share the ballot-measure backbone because demo 2 is structurally "demo 1 + a preference-driven agent."

- **`ballot_measure`** — a question posed to voters. Imported (source = ballotpedia) or user-created (source = user). Structurally identical; only source/author differs. Has title, summary, ballot type, jurisdiction, options.
- **`measure_option`** — ordered choices for a measure (yes/no is 2 rows; candidate race is N rows).
- **`measure_topic`** — junction table linking measures to domains/programs for filtering.
- **`resolution_run`** — `(measure_id, electorate_id, method, seed, result_jsonb, computed_at)`. One measure can have many runs — same measure, same electorate, different methods = the side-by-side comparison that defines demo 1.
- **`preference_session`** — a user's preference elicitation session (state snapshot as JSONB). Demo 2.
- **`preference_response`** — audit trail, one row per answered question. Demo 2.

### Demo 3 (districting) — schema TBD

Anticipated: tables for jurisdictions, units (e.g. census blocks), proposed district maps, and run records of districting algorithms with their parameters and fairness metrics. Geo data lives in PostGIS columns or referenced shapefiles — to be decided when demo 3 is scoped.

### Demo 4 (liquid democracy) — schema TBD

Anticipated: a delegation graph (edges with topic + weight), per-topic effective vote weights, and snapshots of the resolved graph at the time of each `resolution_run`. Reuses `user` and `ballot_measure`; the resolution-run cache key extends to include the delegation snapshot id.

### Schema vocabulary

- **Measure ≠ election.** A measure is the *question*. Resolving it under a specific method with a specific electorate is a `resolution_run`. "Election" is overloaded and not used in schema names.
- **Ballot type** (the shape of a voter's input: single_choice / approval / ranked / score / quadratic) is stored on the measure; it constrains what ballots voters can cast.
- **Resolution method** (how ballots tally: plurality / IRV / Borda / Ranked Pairs / Score / Approval / Quadratic) is chosen per run, not per measure — a single ranked-choice measure can be resolved by IRV *and* Borda *and* Ranked Pairs for comparison.

## Per-demo technical surface

Each demo has its own AI/ML/systems story. The depth lives here. Demo 1 (voting
methods) is mostly about correctness and rigor; its conventions are enforced in
the voting package tests and module documentation. Demos 2–4 are detailed
below.

## Demo 2: Agent voting via preference models

### Preference-model tracks

**Implemented structured baselines — fixed bank of 36 civic-value items:**

- **Gaussian linear utility model.** Gaussian likelihood on continuous strength
  observations; closed-form Kalman-style posterior update. Fast,
  interpretable, and uncertainty-native.
- **Bradley-Terry + Laplace approximation.** Logistic likelihood on signed
  strength, with `|strength|/10` as per-observation weight. The posterior is
  approximated as Gaussian around the MAP.

**Primary human-measure showcase — previously unanswered civic decisions:**

- The participant and model receive the same versioned neutral packet.
- Political identity, partisan voting history, and demographic proxies are not
  model inputs.
- Every model freezes full option probabilities before the participant's
  answer enters evidence.
- Measures share one standardized fictional jurisdiction but remain legally and
  fiscally independent; preference evidence accumulates.
- The model ladder compares fixed/adaptive structured baselines, a direct LLM,
  and an LLM-plus-explicit-posterior hybrid. An embedding/Bayesian-last-layer
  model remains a candidate hybrid representation, not an assumed winner.
- Primary outcomes are prequential log loss and high-confidence delegated
  error. Question efficiency, follow-up quality, and cross-format ballot
  fidelity are secondary.

See `eval/README.md` for the source-level contract,
`eval/fixtures/preference_eval_dev_v1.json` for the non-held-out fixture, and
`python -m eval.run_human_measure_eval` for the deterministic Phase 2 replay.

**Phase 4A architecture (frozen):** the LLM is a provider-neutral elicitation
orchestrator, not the durable preference store. It may select vetted questions,
clarify existing evidence, and inspect typed posterior metrics; only the
explicit preference model may update posterior state from eligible typed
evidence. The ballot semantic mapper and prediction readout are separate from
preference storage. A direct LLM predictor is mandatory as an experimental
control, while the intended candidate architecture is an LLM plus explicit
posterior. Inferred conversational evidence has zero weight until participant
confirmation.

Primary held-out elicitation cannot inspect a target ballot or ask a
target-specific question after exposure. All predictors receive the same
neutral packet and evidence cutoff. The action rule is held constant: select
the top-probability option for single choice, emit a valid format-specific
prediction for rich ballots, display confidence, and permit participant
override or abstention. Model abstention/deferral is not allowed; confidence
thresholds are diagnostics and a future user-controlled authorization policy.
The machine-readable contract is
`eval/fixtures/preference_eval_phase4_protocol_v1.json`.

### The comparison story

- **Synthetic track:** Gaussian and Bradley-Terry models plus acquisition
  policies are evaluated against seeded personas with known latent utilities.
- **Human track:** all prediction models receive the same realized evidence
  stream and predict the same standardized measure bank.
- **Acquisition claims:** synthetic comparisons come first. A single person's
  unanswered counterfactual questions cannot establish that one interactive
  policy beat another.
- **LLM claims:** a direct LLM baseline is mandatory so the hybrid must
  demonstrate value beyond prompting an LLM with the transcript.

### Active learning loop

Question selection evolves in three stages, each a shippable step:

1. **Max-variance pair selection** (ships with rename). Pick the pair `(a, b)` with highest posterior std of `u_a − u_b`. Already supported by `get_uncertainty()`. Closes the active-learning loop immediately.
2. **Expected information gain / BALD** (follow-up). Pick the pair whose expected posterior update most reduces total entropy. Tractable under Gaussian/Laplace posteriors.
3. **LLM-generated items targeted at high-variance directions** (dynamic-items mode). Acquisition function picks a *direction* in embedding space with high posterior variance of `w`; LLM generates a new civic-value item whose embedding aligns with that direction; user answers; posterior tightens.

### Uncertainty-aware agent voting

The agent consults the posterior when casting a simulated ballot and always
selects the top-probability option in the evaluation. A small margin is shown
as low confidence rather than converted into model abstention. Targeted
elicitation may reduce uncertainty before a future target is exposed, or in a
separately reported consultation mode; it is not a target-specific escape hatch
in the primary held-out prediction.

### Deferred within demo 2 (do not build yet)

- **LLM-generated vote rationales** — demo polish, low priority.
- **LLM-generated personas** — wait until eval harness demands more electorate diversity.
- **MCMC inference for comparison against VI** — future work note.

All LLM calls live in Python. One framework for prompts, Pydantic output schemas, numerical code, and inference.

## Demo 3: Algorithmic districting (planned)

**Friction it dissolves:** districts gerrymandered to entrench incumbents or favor a party erode the legitimacy of even theoretically-good voting methods. Hand-drawn maps are politically unaccountable; the technology to generate transparent, constraint-driven maps now exists and isn't being used.

**Anticipated technical surface — to be confirmed when scoping starts:**

- **Optimization core.** Frame redistricting as constraint satisfaction: equal population (within ε), contiguity, compactness (Polsby-Popper or similar), respect for political/geographic boundaries, and a fairness target (efficiency gap, partisan-symmetry, or competitiveness). Likely solvers: integer/mixed-integer programming for small jurisdictions; Markov-chain-based ensemble methods (the Mattingly / Duchin school) for the realistic case where exact optimization is intractable.
- **Graph layer.** Census units (blocks or block groups) form a planar graph; districts are connected partitions. Recombination ("ReCom") moves are graph operations.
- **Geo data.** Real shapefiles (TIGER/Line) for at least one demo jurisdiction. PostGIS or in-memory GeoPandas — decide at scoping.
- **Fairness metrics surface.** The portfolio payoff is making the trade-offs *visible*: same units, different fairness objectives, visibly different maps, with metric tables next to each.
- **Reproducibility.** Same seed + same parameters = same map. Ensemble runs report distributional summaries, not single draws.

**Scope locked in.** Specific algorithm: Cohen-Addad / Klein / Young **balanced power diagrams** (arXiv 1710.03358). Full design — interaction model, schema, precompute strategy, build sequence — is in [`prompts/demo-3-districting.md`](prompts/demo-3-districting.md). Headline decisions: 2020 census, tract resolution, House-size range **[435, 11036]** with anchors at the Wyoming Rule (573), Cube Root Rule (692), and the Article I §2 limit of one representative per 30,000 (11,036, the largest House the Constitution allows). Anchor values are computed from 2020 apportionment populations (`apportionment.analysis.house_size_rules`), not typed. Single canonical seed, 50 states only (DC + territories deferred). Precompute per-state results across the apportionment range; runtime path is apportionment (live, sub-ms) plus DB lookup of cached district maps.

**Initial block-resolution prototype:** the Kansas benchmark uses whole 2020 census blocks, permitting tract splits, and postprocesses point-based assignments with `districting/connectivity.py`. Shared-edge adjacency requires disjoint interiors and positive-length shared boundaries; corner contacts are excluded, and zero-population/water blocks are retained. Component repair and boundary-block rebalancing enforce graph connectivity, followed by independent graph and dissolved-polygon validation. The corrected plan is no longer an exact power diagram. Continuous power-cell convexity does not guarantee whole-tract or whole-block contiguity; population balance is generally approximate for indivisible units, and local rebalancing does not guarantee global optimality or preserved compactness. Source/code hashes, final assignments, and move audits accompany the benchmark; initial centers alone cannot reproduce the corrected plan. See [`prompts/kansas-connectivity-benchmark.md`](prompts/kansas-connectivity-benchmark.md). The subsequent national rollout and app integration are described below.

**Reusable graph and anchor benchmarks:** `scripts/district_block_graph_cache.py` keys the offline adjacency cache by source archive hash, ordered GEOIDs, builder hash, topology rule, schema, and Shapely/GEOS versions. Cache hits read compressed NPZ integer arrays and JSON with pickle disabled, validating checksums and graph structure; invalid entries are rebuilt atomically. The benchmark caller verifies and re-extracts the source archive before lookup. `scripts/run_kansas_anchor_suite.py` prepares the graph separately, then runs `scripts/benchmark_kansas_anchors.py` serially in fresh processes for House sizes 435 / 574 / 692 / 1,000 / 11,037, which apportion Kansas 4 / 5 / 6 / 9 / 98 districts. Source, seed, solver settings, and postprocessing settings remain fixed across the suite. Reports distinguish cold graph creation, warm cache loading, solver convergence, rebalancing termination, and map export; population deviations use the fractional resident-population ideal rather than an integer-truncated target. The anchor report is [`prompts/kansas-anchor-benchmark.md`](prompts/kansas-anchor-benchmark.md); individual saved run statuses determine completion.

**Remaining-state block batch:** `scripts/run_state_block_suite.py` queues the other 49 states at House sizes **435 / 574 / 692 / 1,000**, excluding 11,037. Equal state seat counts share one plan (177 distinct state/count jobs). `scripts/district_block_sources.py` verifies official 2020 resident totals and block counts independently of apportionment, records source hashes, and safely acquires/extracts each archive. `scripts/benchmark_state_blocks.py` checks topology before solving, checkpoints progress, and supports validated resume. The user chose strict shared-edge connectivity: disconnected source graphs and unsupported antimeridian topology are reported as exceptions, with no artificial connections. `scripts/state_block_map_export.py` verifies compressed map copies before removing generated raw GeoJSON. Source archives, graphs, assignments, reports, and compressed maps remain cached; regenerable extractions may be removed after a state finishes. Up to two states run concurrently, so wall timings include contention and should not be compared as isolated Kansas benchmarks. The local queue manifest and inspection page are under `.cache/state-block-benchmark/suite-through-1000/`; a queued or running job is not a completed district plan.

**Polygon-part connectivity:** new general-state runs build a separate `scripts/district_block_part_graph.py` cache with one vertex per source polygon part and explicit part-to-block ownership. `districting/part_connectivity.py` keeps assignments/populations at whole-block granularity, permits zero-population topology repairs, and guards both donor and recipient during subsequent balancing. Common block ownership never creates a geometric edge. Local repair may stall without proving infeasibility; independent unsimplified polygon validation remains mandatory. Legacy block graphs and historical benchmark artifacts remain preserved. `scripts/correct_state_block_parts.py` applies the topology repair to saved failed assignments in a **new** output directory, hashes the original files before/after, measures correction separately from the original solve, and regenerates strict map exports. Maryland K19 and Virginia K26 are the regression cases; see `prompts/maryland-virginia-geometry-diagnosis.md` and the correction report linked there.

**Explicit island connections (Rhode Island prototype):** `scripts/benchmark_rhode_island_water.py` runs K2/K3 in new `policies/island-water-v1/` outputs while preserving the original strict exceptions, source archive, national manifest, and connectivity-only witness. `scripts/district_block_island_links.py` builds a deterministic forest of nearest boundary connections between disconnected source polygon-part components, attaching undersized components to eligible larger components without root-to-root links. The current adapter is explicitly limited to Rhode Island. Eligibility uses 99% of the ideal district population for that K; this classifies islands only and does not set solver convergence or claim a final balance guarantee. All water blocks remain included, so distances are between census-coverage boundaries rather than shorelines. Connections name exact source parts, block GEOIDs, endpoints, distances, and provenance; common multipart ownership still creates no edges. The solver and repair use the augmented graph. The optional water-policy map export independently verifies full polygon components and same-district link endpoints, retains physical `strict_validation` separately from `connectivity_validation`, and draws dashed connection lines without modifying source polygons. Default general-state exports remain strictly shared-edge connected. This policy does not automatically resolve larger island systems or antimeridian geography.

**Population-aware island connections (Hawaii prototype):** `scripts/hawaii_population_links.py` evaluates assignments of smaller populated components to original district-sized roots and mergers of those roots. A rational integer-seat allocation must meet the explicit 1% optimistic group-population budget before distance is considered; it is not a guarantee or acceptance threshold for final whole-block balance. The bounded search retains the most compatible original root groups, then chooses the shortest of its deterministic constrained-Kruskal forests. Aggregates of small islands are not promoted into protected roots. Zero-population components remain covered, candidate lines crossing another source component's interior are excluded, and endpoints are verified against unchanged polygon parts. Per-pair local candidate geometry and spherical endpoint lengths replace Rhode Island's narrow local distance assumption, without claiming certified geodesic minima. `scripts/benchmark_hawaii_water.py` runs K2/K3/K4 serially in new `policies/hawaii-water-v1/` directories, preserving strict artifacts and source hashes. These anchors require one augmented source component; separate feasible root groups at higher counts would need explicit per-group solves. Existing solver and independent water-policy polygon validation are reused. Physical connectivity, policy connectivity, population quality, and timing remain separate outcomes.

**Optimizer scaling and failure handling:** the inner balanced-power solve subtracts per-unit constant costs and normalizes geometry and population mass, then returns weights in the original squared coordinate units. Zero-population outliers remain assigned but do not set the objective's scale. Unsuccessful or nonfinite SciPy outputs raise `DistrictingOptimizationError`; center convergence and population balance are still independent metrics. `scripts/benchmark_hawaii_optimizer.py` records a fresh K2 correction under `corrections/hawaii-optimizer-v1/`, preserving the entire original Hawaii water-policy output tree, strict results, source archive, and reports. The water-connection hash, seed, iteration budgets, and connectivity postprocessing remain fixed; normalization and the increased line-search allowance are explicit numerical changes. These offline attempts retain their original provenance; the final catalog selects the accepted plans for the block demo.

**Recorded geographic exceptions:** optional policies supplement physical polygon-part adjacency with explicitly recorded endpoint connections; they never alter source polygons or assign foreign-state territory. Physical and policy connectivity are audited separately, and a link contributes only when both endpoint blocks belong to the same district. `scripts/kentucky_exclave_links.py` verifies the preserved Kentucky Bend diagnosis and selects its recorded exclave edge for K6/K8/K9/K14. That line crosses Missouri land as well as Mississippi River water, so it is labeled an **exclave connection**, distinct from the Rhode Island/Hawaii water policy. `scripts/benchmark_kentucky_exclave.py` uses the fixed optimizer and part-aware repair, with independent unsimplified polygon-plus-link validation. `scripts/run_kentucky_exclave_suite.py` runs fresh processes serially in `policies/kentucky-exclave-v1/`, refusing existing attempts and preserving original strict results. Its comparison is [`prompts/kentucky-exclave-benchmark.md`](prompts/kentucky-exclave-benchmark.md); strict preflight exceptions are not solved-plan baselines.

**New York mixed connections:** `scripts/new_york_recorded_links.py` pins the saved source and diagnostic evidence for Liberty Island's water connection and the New York portion of Ellis Island's exclave connection. Ellis's line crosses New Jersey land as well as water; these kinds remain distinct in the records and maps. Both zero-population blocks attach to the same New York water-block anchor. `scripts/state_block_map_export.py` accepts opt-in `recorded_connections` with per-link kind and geographic evidence, independently validating full polygon connectivity and endpoint ownership. Existing strict, water-only, and exclave-only interfaces retain their meanings. `scripts/run_new_york_link_suite.py` runs K26/K35/K42/K61 serially under `policies/new-york-links-v1/`, preserving strict and diagnostic artifacts and refusing prior attempts. After K26's inner optimizer reached its iteration cap, `scripts/run_new_york_remaining_plans.py` owns only the three unstarted first attempts with unchanged code/settings and a separate manifest; it neither retries K26 nor overwrites the stopped original suite. `scripts/summarize_new_york_links.py` independently checks saved populations, assignments, exports, and provenance for the comparison, keeping numerical failures distinct from accepted plans. These connections do not imply a bridge, travel route, or physical shared edge.

**Controlled inner-budget experiment:** `scripts/benchmark_new_york_budget.py` runs New York K26 under `corrections/new-york-inner-budget-v1/`, preserving the failed mixed-policy tree and its original source hashes. Only the inner iteration limit changes from 300 to 1,000; the seed, tolerances, outer budget, link records, and connectivity repair remain fixed. `scripts/district_optimizer_trace.py` observes existing objective evaluations and accepted iterations through temporary wrappers, adding no objective calls or numerical stopping rules. It records per-pass normalized objective improvement, population diagnostics reconstructed from the existing gradient, iteration counts, and timing in an append-only JSONL file. Objective values are comparable only within a balancing pass. Diagnostic assignments are distinct from the final public-weight assignments and repaired plan; runtime includes tracing overhead. `scripts/summarize_new_york_budget.py` verifies the experiment and presents its traces without treating a budget-limited attempt as a completed district map.

**New York budget anchor extension:** `scripts/run_new_york_budget_anchors.py` owns the separate serial K35/K42/K61 experiments in `corrections/new-york-inner-budget-anchors-v1/`. Each fresh process uses `scripts/benchmark_new_york_budget_anchors.py` and its own preserved 300-iteration baseline; only the inner limit changes to 1,000. The original numerical code, failed policy suite, and completed K26 experiment remain immutable. The launcher refuses duplicate attempts and verifies exited children, terminal reports, settings, artifacts, and preservation before advancing. `scripts/summarize_new_york_budget_anchors.py` compares independently verified outcomes and includes K26 only as a saved reference. Successful inner solves, outer-center convergence, final population balance, physical connectivity, and connectivity under recorded links remain separate findings.

**Florida recorded water plans:** `scripts/diagnose_florida_topology.py` verifies the exact part graph and source populations: main Florida/Keys coverage plus a six-block Dry Tortugas component with 11 residents. `scripts/florida_recorded_links.py` pins the diagnosis, exact boundary candidate and attributed geographic evidence, reruns the unchanged population-aware selector at the actual district count, and adds one recorded water edge without modifying polygons or populations. `scripts/run_florida_water_suite.py` owns serial fresh K28/K37/K45/K65 attempts under `policies/florida-water-v1/`, each using 1,000 inner iterations, the fixed seed, 80 outer iterations and part-aware repair. It preserves the original strict source-topology exception and diagnosis, refuses duplicate attempts, validates terminal reports and stops on operational ambiguity. `scripts/summarize_florida_water.py` independently reconciles populations, compressed maps, endpoint ownership, graph/polygon connectivity, runtime and peak memory. Strict preflight is not a solved-plan baseline; physical connectivity and connectivity with the recorded water link remain distinct. See `prompts/florida-topology-diagnosis.md` and the generated Florida comparison.

**Alaska longitude handling and recorded water plans:** `scripts/alaska_geometry.py` verifies the source and translates positive-longitude whole blocks by −360° into one continuous Alaska frame, preserving original coordinates and part ownership. `scripts/alaska_recorded_links.py` independently verifies the saved diagnosis and selects the same 49 recorded water edges for K1/K2, using the existing population rule's exact single-group specialization when at most one district-sized root exists. It rejects multiple roots; this is not a general replacement for the population grouping search. `scripts/run_alaska_water_suite.py` owns fresh serial attempts in `policies/alaska-water-v1/`: K1 assigns all blocks directly without an optimizer, and K2 uses the unchanged internal-point equirectangular model with 1,000 inner iterations and part-aware repair. Original strict results and diagnostics remain preserved. The national manifest's original K2 exception references K1's preflight report; it is not a separate strict solver attempt. `scripts/alaska_map_export.py` independently validates full polygon coverage and same-district connection endpoints, exports continuous and wrapped coordinates with seam reconstruction checks, and retains the original NAD83 datum. Display seam cuts do not create physical graph components; no WGS84 datum conversion is implied. The viewer draws recorded links and loads county blocks on demand. Physical connectivity, policy connectivity, population balance and convergence remain distinct. See `prompts/alaska-topology-diagnosis.md` and the generated Alaska water benchmark comparison.

**Cached donor connectivity and West Virginia continuation:** `districting/connectivity.py` uses iterative articulation-point caches for connected unit districts, invalidating both donor and recipient after every accepted transfer. `cache_connectivity=False` retains the unchanged traversal reference; candidate ordering, objective, move budgets, and polygon-part guards remain identical. Incompatible post-part-repair unit graphs fall back to traversal. Multipart whole-block removal still requires the separate exact part checks. `scripts/run_west_virginia_cached_balance.py` compares fresh 100-move traversal/cached processes against the preserved diagnostic trace before admitting a larger continuation from the original K3 endpoint. It checkpoints every 500 moves, caps additional moves at 10,000, preserves historical evidence, and independently validates strict polygons and coverage before accepting a new map. Correction time excludes the original numerical solve; cache equivalence, runtime, connectivity, and population quality remain separate findings. The comparison is generated by `scripts/summarize_west_virginia_cached_balance.py` under `corrections/west-virginia-cached-balance-v1/` and `prompts/west-virginia-cached-balance-benchmark.md`.

**Final block-plan anchor catalog:** `scripts/finalize_state_block_catalog.py` joins explicit historical baseline and correction/policy selections for all 50 states at House sizes 435 / 574 / 692 / 1,000 (200 state-anchor combinations, 181 distinct state/count plans). It independently reconciles apportionment with exact rational priorities and uses `scripts/final_state_plan_validation.py` to reread Census DBF populations, verify every assignment and compressed payload, and check full exported polygon connectivity and recorded-link endpoint ownership. Historical source-coverage and graph audits are checked but not rebuilt. It writes a new `final-anchors-vN/` inventory and `prompts/state-block-final-catalog.md/.json`; historical attempts stay read-only. Physical connectivity, policy connectivity, population quality, legacy inner-solver warnings, outer caps, and correction-only runtime remain separate fields. The catalog supplies only the four computed anchors. The block demo uses a separate manifest contract from the preserved historical tract summaries/topology, with explicit anchor selection, recorded links, Alaska longitude frames, lazy county detail, and truthful convergence labels.

## Demo 4: Liquid democracy (planned)

**Friction it dissolves:** direct democracy doesn't scale (voters can't research every issue) and representative democracy alienates (one elected agent represents your views on everything). Liquid democracy lets each voter delegate per-topic to whomever they trust, with delegation transitive and revocable. The technology — a maintained delegation graph and a vote-flow algorithm — is straightforward; what's missing is a credible demonstration that it produces sensible outcomes and resists pathologies (cycles, super-delegate concentration, low-participation collapse).

**Anticipated technical surface — to be confirmed when scoping starts:**

- **Graph data model.** Directed delegation edges with `(delegator, delegate, topic, weight)`. Topic taxonomy reuses `domain`/`program`. Cycles must be detected and broken (standard rule: voter's own vote takes precedence; cycles fall back to abstain or to a default delegate).
- **Vote-flow algorithm.** Given a delegation graph and a measure on a given topic, compute effective vote weights. This is a topic-conditional reachability + weight propagation problem.
- **Resolution.** Effective weights feed into `voting/` — every existing resolution method works on weighted ballots with minor adapter code. This is the natural cross-demo composition: liquid democracy is "demo 1 with a delegation layer in front."
- **Simulation surface.** Generate synthetic populations with varying delegation strategies (apathetic, expert-trusting, partisan, etc.) and show how outcomes differ from direct voting. Investigate pathologies: super-delegates, partisan cascades, participation cliffs.
- **AI angle.** A delegate-recommendation agent that, given a user's stated preferences (from demo 2's posterior!) and observed delegate voting records, suggests delegates per topic. This is the only natural cross-demo composition between demos 2 and 4 — and the most interesting portfolio synthesis.

**Open scoping questions:** Topic granularity — fixed taxonomy or learned topic embeddings? How realistic should the simulated populations be (synthetic strategies vs. data-grounded)? Is the demo focused on showing *outcomes differ* from direct democracy, or on *characterizing* the dynamics of the graph? Defer answering until demo 4 reaches the top of the build queue.

## Cross-demo: Evaluation harness (`eval/`)

Proper ML evaluation, reproducible seeds, held-out splits. Each demo contributes its own metrics:

- **Demo 1 — voting methods:** social welfare metrics (e.g., Borda-score of winner, Condorcet efficiency across simulated elections), and sensitivity of outcome to method choice given a fixed electorate.
- **Demo 2 — synthetic preference models:** held-out latent-direction log
  score, accuracy, one-coordinate binary Brier score, reliability, Kendall
  tau-b curves, and first-threshold-attainment summaries.
- **Demo 2 — human measure prediction:** prequential option log loss,
  high-confidence delegated error with risk/coverage, calibration,
  generalization gaps, test-retest stability, and secondary ballot-format
  fidelity.
- **Demo 3 — districting:** ensemble-based fairness comparisons (where does a proposed map sit in the distribution of ensemble maps?), efficiency gap, compactness scores.
- **Demo 4 — delegation dynamics:** participation rates, super-delegate concentration (Gini on effective weights), outcome divergence vs. direct democracy, robustness to delegation churn.

## Reproducibility (first-class invariant, applies to every demo)

Every demo must be verifiable by anyone who clicks. Every stochastic operation is seeded:

- **Voting method tiebreaks** — each method takes an injectable tiebreak; default is `random_tiebreak(seed)`, not unseeded `random.choice`.
- **Electorate generation** — sampling from preference distributions uses a seed stored on the `electorate` row. Regenerating the same electorate_id produces byte-identical voters.
- **Resolution runs** — `(measure_id, electorate_id, method, seed)` is the cache key. Given the tuple, the result is deterministic. Demos that introduce additional state (e.g. demo 4's delegation snapshot) extend the cache key accordingly.
- **LLM calls** — `temperature=0` for rationales and structured outputs; use the `seed` parameter where supported (OpenAI). Cache responses keyed on the full prompt.
- **Preference model inference** — RNG for MCMC / variational fits is seeded and recorded.
- **Districting ensembles (demo 3, when built)** — the MCMC chain seed and parameter set are part of every reported result; an ensemble run is identified by `(jurisdiction_id, params_hash, seed, n_steps)`.
- **Delegation-graph simulations (demo 4, when built)** — graph generation seed and any random delegation-strategy seeds are recorded on the run.

If a change breaks determinism (e.g., switching to an ungrounded LLM call), document the non-determinism explicitly and justify it.

## FastAPI quality bar

The API is visible in the portfolio; treat it as product surface.

- **Layering:** `api/routers/` (HTTP only, request/response validation) → `api/services/` (orchestration) → domain packages (`voting`, `preferences`, ...). Routers never contain domain logic.
- **Schemas:** Pydantic models for every request and response. No `dict[str, Any]` on public surfaces.
- **OpenAPI:** keep `/docs` curated — tag routes, write summaries, include example payloads. This is part of the portfolio.
- **Errors:** explicit HTTP codes with Pydantic error envelopes. No leaking `"Is the Python API running?"` strings to clients.
- **Testing:** pytest + `httpx.AsyncClient` for route tests; domain tests don't touch the HTTP layer.
- **Type completeness:** `mypy --strict` clean on `api/` and domain packages.

## Web app patterns

- **Server Actions** — all mutations. Return `ActionResult<T>` = `{ isSuccess, message, data? }`. Mutations call `revalidatePath`. Queries import from `db/queries/`; never call queries from client components.
- **"Not found" is not an error** — return `{ isSuccess: true, data: null }`, not `{ isSuccess: false }`. The action result envelope is for infra failures, not expected empty states.
- **Forms** — React Hook Form + Zod. Validate at form boundary AND at server action boundary (defense in depth).
- **JSONB columns** — always Zod-validate on read. Drizzle types JSONB as `unknown`; don't cast away with `as unknown as T`.
- **Path alias:** `@/*` maps to project root.
- **Style:** Tailwind CSS 4, shadcn/ui (new-york), dark mode via class strategy.

## Commands

```bash
# Web
npm run dev             # Next.js on :3000
npm run build
npm run lint
npm run db:generate     # drizzle-kit generate (inspect SQL before applying)
npm run db:migrate      # drizzle-kit migrate

# Python
source venv/Scripts/activate     # Windows Git Bash
pip install -r requirements.txt  # single consolidated requirements file
pytest                           # all tests across voting/, preferences/, api/, ...
npm run api:dev                  # starts FastAPI on :8000

# Run everything
npm run dev:all                  # web + api concurrently
```

Database URL from `.env.local` (see `drizzle.config.ts`). Python API URL from `VOTING_API_URL` (default `http://localhost:8000`).

## Build phases

Demos progress on independent tracks. Cross-cutting infra (shared schema, FastAPI shell, eval harness skeleton) is its own track.

### Cross-cutting infra

**Done:**
- Web shell: Next.js App Router, Drizzle schema scaffolding
- Proposals removed: tables, queries, actions, components, and form deleted; migration `0004_optimal_mystique.sql` drops the 5 proposal tables + enum
- Unified API: single FastAPI process at `api/` with `/api/voting/*` and `/api/preferences/*` routers on :8000; consolidated `requirements.txt`; `npm run dev:all` runs web + api concurrently
- `eval/` fixed-bank harness: seeded held-out splits, deterministic trials,
  synthetic personas, response-model robustness scenarios, and parameter
  sweeps
- Human-measure Phase 1: strict versioned contracts, an eight-domain
  development fixture, canonical content hashes, and leakage-boundary tests
- Human-measure Phase 2: leakage-safe model adapter boundary, synthetic
  prequential replay, option and delegated-risk metrics, and an allowlisted
  publication-candidate serializer

**Next:**
- Seed-plumb all stochastic operations for the reproducibility invariant
- Extend `eval/` with one baseline metric for demos 1/3/4 as they mature
- Add a top-level navigation surfacing the demo set (`/methods`, `/preferences`, future `/districts`, `/delegation`)

### Demo 1: Voting methods comparison

**Done:**
- Voting package: plurality, approval, IRV, Borda, Ranked Pairs, Score, Quadratic — all with injectable tiebreak, abstention support, typed result classes, full test coverage. Review changes with `.claude/skills/voting-package-conventions/` and `.claude/skills/voting-method-correctness/`.
- Ballot-measure schema: tables `ballot_measure`, `measure_option`, `measure_topic`, `electorate`, `resolution_run` (cache key `(measure_id, electorate_id, method, seed)`); enums `ballot_type`, `measure_status`, `measure_source`. Migration `0005_green_mandrill.sql`. Schema only — no queries/actions/UI persisting yet.
- User-facing rename: demo route `/elections` → `/methods`; corresponding `lib/`, `components/`, `actions/`, `types/` renames. TS types `ElectionMethod`/`ElectionScenario`/`ElectionDemo` → `VotingMethod`/`MethodScenario`/`MethodDemo`. Voting-result type names (`ElectionResult`, `IRVResult`, etc.) kept — they are the canonical voting-theory term.
- Instrument slice A (`prompts/demo-1-methods-instrument.md`): methods default to a seeded `random_tiebreak()`; Ranked Pairs orders equal-strength victories by a candidate priority drawn from the injected tiebreak, only when their order could change what locks, and sets `tiebreak_applied` only then (recording `tiebreak_priority`); canonical anonymous `RankedProfile`; single-profile criteria (`pairwise_counts`, `majority_winner`, `condorcet_winner`, `condorcet_loser`) in `voting/criteria/`.
- Instrument slice B: profile transformations in `voting/criteria/`; an exhaustive three-candidate paradox search in `voting/search/` (decisive outcomes from the reference methods, winner tables for consistency, `certify()`); `python scripts/build_methods_artifacts.py` writes certified minimal specimens for 4 ranked methods x 8 criteria, the tour presets, and a manifest to `public/data/methods/`.
- Instrument slice C: `POST /api/voting/profile/resolve` (router `api/routers/profiles.py`, schemas `api/schemas/voting.py`, service `api/services/profile_resolution.py`) resolves a ballot-type-tagged anonymous profile under plurality, IRV, Borda and Ranked Pairs, returning winners, decisiveness, every tie the seeded tiebreak settled, method traces, the pairwise matrix and single-profile criteria; typed client `resolveProfile` in `lib/methods-api.ts`.
- Instrument slice D: `/methods` is the instrument (`components/methods/instrument/`). The electorate is voter types on 0–10 utility tracks (order = ranking, spacing = intensity; `?p=` links); a ballots panel shows the five ballots each type casts; seven method channels grouped by ballot, with single-profile criteria; steppable traces with the lab's method descriptions (overclaims corrected); and a tournament graph. Ballot models live in `voting/ballot_models/` (`BallotModel` interface, `sincere-v1`, `UtilityProfile`); the endpoint accepts `"ballot_type": "utility"` profiles and runs all seven methods. Drafting-table identity (`.methods-instrument` tokens in `app/globals.css`, Instrument Sans + JetBrains Mono, a five-candidate palette validated for light and dark). Presets are voter types whose full endpoint responses live in `public/data/methods/presets.json`; edits go through `resolveProfileAction`, debounced and cached, with an offline fallback. IRV now iterates candidates in candidate order, so its rounds no longer depend on string hashing.
- Instrument slice E: the paradox gallery (four ranked methods × eight criteria) opens each certified specimen in the instrument with a before/after banner; cells no specimen settles carry a proof or citation (`lib/methods/gallery.ts`). A six-step tour (`lib/methods/tour.ts`) loads presets and specimens. `specimen-resolutions.json` holds every specimen profile resolved at build time, so the tour and gallery need no API; `?s=`/`?v=` links render on the server. `/methods/lab` redirects to `/methods` and the lab UI is removed (the Python `/api/elections` routes remain, unused by the web app).
- Instrument slice F: rated gallery rows. Approval, score and quadratic voting are searched over 18 voter types (each ranking with its middle candidate at 25, 50 or 75) whose ballots sincere-v1 casts (`voting/search/rated.py`, a matrix-total kernel tested against the reference methods; utility transformations with exact clones in `voting/criteria/utility_transformations.py`); `certify()` re-resolves every rated specimen, and specimens record `ballot_type` and `ballot_model`. The gallery shows all seven methods in two groups, with proofs for the rated passes and one open cell (quadratic participation); rated specimens load with their utilities as found. Quadratic totals now follow candidate order, so its traces and the built artifacts no longer depend on string hashing.
- Instrument slice G: the atlas, Yee's spatial diagrams for all seven methods, as a section of `/methods`. Each cell of a 64 × 64 grid is the same cloud of 95 voters (19 voter types on a sunflower spiral, spread 0.16) centered there, with utility linear in distance (`voting/spatial/`); the reference methods count every cell exactly as the instrument would, with identical ballots counted once. Condorcet, least-distance and disagreement reference maps; tie cells drawn lighter and counted apart in area shares. `POST /api/voting/atlas` recounts a dragged layout, `POST /api/voting/atlas/point` resolves one cell for the instrument, and five curated layouts ship in `public/data/methods/atlas.json`, with tests holding each caption's claims to that file.
- Instrument slice H: the methods simulation. `voting/spatial/sampling.py` draws seeded two-dimensional spatial elections (candidates, then voters, from one standard Gaussian) as utility profiles, and `voting/spatial/counting.py` (`ProfileCounter`, now shared with the atlas) counts them exactly as the instrument does. `python -m eval.run_methods_simulation` runs 10,000 elections each with 3, 4 and 5 candidates and 101 voters, seeded per election, and writes `eval/benchmarks/methods_simulation_v1/` (config, per-election rows, a summary with 95% Wilson intervals, provenance, README) plus `public/data/methods/simulation.json`. An "At scale" section on `/methods` shows Condorcet efficiency and pairwise disagreement, with a table view of every number.
- Instrument slice I: demo 1's home card (`components/home/methods-card.tsx`) in the instrument's drafting-table identity. The atlas's hub layout steps through the seven methods' maps on hover or focus (in view on touch screens; held on plurality under reduced motion) beside a list of D's outright share under each, read and downsampled from `atlas.json` on the server (`loadHomeCardAtlas`). The atlas's map renderer moved to `components/methods/instrument/map-canvas.tsx`, and the showcase cards share their motion hooks (`components/home/card-hooks.ts`).
- Instrument slice J (the 2026-10-23 revision): `/methods` is six slides in a horizontal scroll-snap carousel (`slide-deck.tsx`: Ballots, Seven counts, Head to head, Paradoxes, Atlas, At scale; arrows, dots, a tablist with arrow keys, swipe, `?section=` links), and "Try it yourself" pulls the instrument up as a bottom sheet (`playground.tsx`, `?play`; `?p=` links open it). The playground offers starting points and count steppers (`voter-counts.tsx`); the full editor sits in an Advanced controls drawer, right on large screens and bottom on phones, with the counts kept in view. The slides and the playground share one electorate (`use-electorate.ts`). The tour is retired; its cases return as slide examples in K and L.
- Narrative slices 1–4 (`prompts/demo-1-methods-narrative-proposal.md`): each slide's title is the claim its graph proves, with a takeaway and a transition; the counts and head-to-head claims are written from the shown electorate (`lib/methods/claims.ts`). Slides run Seven counts, Head to head, Ballots, Paradoxes, Atlas, At scale; the page opens on center squeeze; example chips with per-slide notes replace the electorate bar, each slide with its own examples: two authored presets join the two (a consensus, and three ballot shapes whose voter types share one ranking and differ only in strength). The footer is a closed "Methods & provenance" disclosure. Dense detail sits behind disclosures: each method's background and its smallest gallery failures (linked to their specimens), the gallery's search notes, and each atlas layout's secondary claims.
- Walkthrough slice 1 (`prompts/demo-1-methods-walkthrough-proposal.md`): `/methods` is four chapters of steps (`lib/methods/sections.ts`, `step-deck.tsx`): chapter tabs, a step counter, arrow keys outside controls, and `?step=` links (old `?section=` links resolve). From 1024px wide each step is sized to the window; the page title shows only on the first step. Steps 1.1 Ballots, 1.2 Head to head, 2.1 the comparison, 3.1 the gallery, 4.1 the atlas, 4.2 at scale hold the earlier slides until slices 2–4 replace them.
- Walkthrough slice 2: chapter 1 is 14 steps on the center-squeeze preset (`lib/methods/walkthrough.ts`, `walkthrough.tsx`): the voters on their 0–10 scales, each ballot for every group with its scale, each count with its trace, rule and a scoreboard of winners so far, and a head-to-head step defining Condorcet winner and loser before Ranked Pairs. Step copy is written from the preset's stored resolution; every step fits at 1280×720.
- Walkthrough slice 3: chapter 2 is a compact seven-count comparison of center squeeze and a step switching between center squeeze, consensus and the majority cycle beside the head-to-head graph; chapter 3 groups the eight criteria in plain words, tells three gallery specimens as before / change / after stories (`lib/methods/stories.ts`, counts loaded on the server), then shows the gallery, with an opened specimen in the table's place.
- Walkthrough slice 4: chapter 4 shows one simulated election in the plane (`public/data/methods/samples.json`, written by the artifact builder from `eval/methods_simulation.py` and tested against `elections.csv.gz`), the atlas on one screen, disagreement with one cell read aloud, and Condorcet efficiency. All 25 steps fit at 1280×720.
- Walkthrough revision: from 1024px wide `/methods` is a slide stage of a fixed design size (1240×700: the title row, a top-aligned chapter rail with the current chapter's numbered steps, one fixed step box, and previous/next naming their steps under it) scaled as a whole to the window; every step is laid out at the design size, so nothing moves between steps. Small screens keep a flowing deck with a chapter menu. Ballots, traces and the voters step draw larger on their steps.
- Design pass: a dark hero states the thesis from the center-squeeze preset's saved results (three method calls, three winners) above a dark sticky section nav. Each section opens on a tinted band (the Emerald Sapphire Daybreak pastels, surfaces only) with a large numeral and one small figure from its own data, its body carries a muted version of the same tone, and its parts carry numbered subheads (02.1, 03.1, ...). The code inspector (`lib/methods/code-listing.ts`, `code-view.tsx`) merges each method's stage excerpts into one listing in file order with folded gaps, keeps only the current stage's lines in color, slides a red marker to the driving line, scrolls the editor rather than the page, and annotates lines with values read from the saved trace. The playground no longer repeats the selected method's trace; "Trace this count" opens it in the inspector. On phones the method picker is one swipeable row, code wraps under its own indent, band figures are hidden, the turnout story drops its reserved height, and the disagreement matrix uses short labels. Candidate colors are unchanged; the palette rules are in `prompts/demo-1-methods-instrument.md`.

**In progress (this branch):**
- Demo 3 districting shell with apportionment-driven seat counts

**Next:**
1. Continue the `/methods` revision with slices K and L of `prompts/demo-1-methods-instrument.md`: each slide's explainer and examples.
2. Replace curated method scenarios with persisted `resolution_run` rows when the demo needs saved runs
3. Add ballot-measure queries/actions only when a portfolio demo has a concrete persisted workflow for them

### Demo 2: Agent voting via preference models

**Done:**
- Preferences question bank, elicitation engine, typed `Evidence`, and
  serialization upgrades
- `GaussianLinearUtilityModel` and `BradleyTerryLaplaceModel`
- Random and max-variance acquisition policies
- Fixed-bank synthetic model/acquisition evaluation
- Bounded synthetic reference benchmark: 1,080 trials across two models,
  three acquisition policies, and three response scenarios; full generated
  utilities/results, learning curves, endpoint spread, paired method differences,
  and latent-direction reliability in `eval/benchmarks/synthetic_v1/`, with
  numerical and figure provenance from `eval/run_synthetic_benchmark.py` and
  `eval/plot_synthetic_benchmark.py`. This is fixed-item latent-
  ordering evidence, not human ballot accuracy or production calibration.
- Pydantic contracts for standardized jurisdiction, measures, evidence,
  predictions, participant responses, ontology versions, and evaluation runs
- Eight-domain non-held-out development fixture plus deterministic manifest CLI
- Deterministic human-measure session runner with zero-evidence,
  post-onboarding, post-wave, and immediate pre-answer snapshots
- Uniform-prior baseline, scripted test double, primary log-loss and
  risk/coverage metrics, stable/tentative slices, and unsupported-delegation
  accounting
- Aggregate-only public artifact serializer with planted-sensitive-data tests
- Participant-blinded source capture, exact tracing, and locked independent
  review for the 48-measure bank, with eight participant-safe review summaries
- Phase 3C retest registry approved at all 12 exact hashes, with the final
  reviewer-provenance ledger, six-wave plan, and execution bundle frozen
- Phase 4A public architecture and six-arm comparison protocol frozen
- Phase 4B provider-neutral interviewer tools, constrained actions, exact
  caching/audit bindings, fixed-sequence baseline, and deterministic test
  doubles
- Phase 4C confirmed conversational evidence plus participant-governed fixed
  and expanding ontology lifecycles
- Phase 4D v2 prediction/run contract slice: exact input and component
  bindings, normalized option probabilities separated from complete rich-
  ballot actions, common-cutoff validation, and compatibility with the v1
  presentation/response execution surface
- Phase 4D classical readout slice: exact fixture/packet/ontology-bound
  authored stance maps, Gaussian and Bradley-Terry posterior replay, common
  uncertainty-aware probability coupling, deterministic five-format ballot
  actions, and a validated public development map
- Phase 4D provider readout slice: content-addressed provider-neutral direct-
  LLM and fixed/expanding hybrid requests, recomputed posterior projections,
  active admitted-dimension inputs, deterministic test doubles, private cache
  boundaries, and exact snapshot rebuild validation
- Phase 4 semantic-map review precommitment: packet-and-ontology-only inputs,
  coarse ordinal positions and primary/secondary importance, deterministic
  centered weights, restricted path-bound rationales, a locked independent-
  review prompt, final-map output confinement, exact approvals, run-level
  approved-mapper provenance, and participant-safe aggregate summaries

**Next, in order:**
1. Review and publish the synthetic reference benchmark and its reproducible
   curves. The metric-correction commit is `d47f605`.
2. Connect one real fixed-posterior-to-ballot user journey using public
   development material, then attach conversational evidence confirmation.
   Keep the illustrative web scoring distinct from the research posterior.
3. Before another paid qualification, declare and review any bounded-repair
   or scored-robustness amendment. These are proposals, not implemented rules.
   Preserve the existing no-winner outcome in
   `eval/review_summaries/qualification_attempt_receipt_v2.json`.
4. Finish deployment/model/evaluation freezing before the held-out case study;
   keep blind evaluation separate from target-aware companion consultation.
5. Execute the six blinded waves and 7-14 day retests only after that freeze.
   The 48-measure bank, retests, and semantic map are already reviewed.
6. *(Deferred)* LLM-generated vote rationales and personas

### Demo 3: Algorithmic districting

**Status:** Apportionment, national/state map UI, and cached tract-based plans are implemented. Design doc at [`prompts/demo-3-districting.md`](prompts/demo-3-districting.md). Kansas has a separate offline census-block benchmark with shared-edge repair, connectivity-preserving population rebalancing, independent validation, and lazy county-detail map exports; it does not replace the app's tract artifacts. Results and limits are recorded in [`prompts/kansas-connectivity-benchmark.md`](prompts/kansas-connectivity-benchmark.md).

**Next, in order:**
1. Add methodology writeup page explaining the algorithm, constraints, seed policy, and limits of geometric fairness.
2. Precompute pipeline for one state end-to-end.
3. Scale precompute to all 50 states across cap range [435, 1000].
4. State detail page with real district polygons + metrics (Polsby-Popper, population deviation, edge count).
5. *(Deferred)* Additional House-size block plans, live seed regeneration, DC/territories, cross-demo composition with methods.

### Demo 4: Liquid democracy

**Status:** Not started. Scope before building. Open questions in the demo 4 section above.

The most interesting cross-demo synthesis is "delegate recommendations driven by demo 2's preference posterior" — flag for design attention when both demos are mature.


## Current block explorer integration

`/districts` is the whole districting demo: the nine-chapter Michigan algorithm walkthrough (`prompts/demo-3-explainer.md`) first, then the four-anchor block explorer at `#explorer`. `/districts/explore` redirects there. Apportionment remains a separate demo at `/apportionment` and `/apportionment/explore`. The saved catalog covers 435 / 574 / 692 / 1,000; 574 is a saved benchmark size, not the current apportionment demo's computed 573-seat Wyoming Rule.

`data/districting-block-plans/` contains a small browser manifest, server asset allowlist, generated national outlines and county indexes. `lib/load-block-plans.ts` verifies accepted report/manifest hashes and each requested compressed payload before streaming it. `BLOCK_PLAN_CACHE_ROOT` may point to a preserved `.cache` directory outside this worktree; it is server-only and read-only. All requested paths come from the pinned allowlist and must stay within the applicable root. The default is the current checkout's `.cache`. Large county data is loaded only on demand, never by the national view. Alaska retains its continuous longitude frame; recorded water/exclave links stay separate from physical connectivity.

The original block numerical pipeline and immutable benchmark evidence remain in the preserved source checkout until separately ported/reviewed. Integrating saved plans does not rerun those algorithms. State border display geometry is derived from dissolved full outlines, then simplified for context; it does not change or revalidate district assignments.

State comparison layers are separate, display-only assets: 2020 tract population density (block populations divided by block land area, aggregated by tract), 2020 counties, and Census 119th Congressional District boundaries (2025 vintage). The shared state explorer loads county geometry for navigation and shows counties by default; other reference layers load when enabled. All layers share the computed plan's projection, including Alaska's continuous longitude frame. Keep computed outlines and enabled recorded connections above reference layers. Reference coastlines are cartographically generalized and must never become inputs to connectivity validation; density is a tract average, not the location of individual residents. Record source URLs, vintages and hashes when rebuilding comparison assets. The 119th Congress reference remains a 435-seat map at every computed House-size anchor.

All 50 states have land-focused display derivatives at all four anchors: hide original `ALAND20=0` block polygons, retain mixed land/water blocks, and preserve every saved assignment and population. These are the default national/state displays, with a full census extent toggle returning the original assets. This is land-focused, not an exact shoreline mask. Cyan derived water connections explain verified same-district paths through hidden source blocks; they are distinct from recorded policy links and never become solver inputs. Paths are checked at Polygon-part level, including multipart land endpoints and access to unchanged recorded endpoints, and must explain every display component. Do not infer these connections from generalized reference coastlines or nearest-island proximity. Density and on-demand block canvases clip to the derivative in land mode. Alaska keeps continuous longitudes. Michigan's original derivatives remain unchanged; `build_state_land_display.py` prepares additive fragments for other states and `publish_state_land_display.py` validates and publishes the complete set with byte-exact manifest/index backups. Never rerun solvers or regenerate blocks to change display geometry.

Michigan's state explorer uses a dedicated cleaned overview at all four anchors, superseding the earlier reuse of the coarse (`national`) derivative. A common state mask suppresses small enclosed water holes for overview display, allocating the restored display area by saved district ownership. Open channels, larger holes and holes containing land islands remain. District dividers are separate from the subdued coast layer, so shoreline detail does not acquire a bright district stroke. Inspection controls geometry: Districts and Counties use the simplified overview without loading fine polygons or blocks; Blocks loads fine boundaries and spatial block chunks. There is no independent overview/detail mode or Exit detail view. Districts/Counties permit 1–256× zoom; entering Blocks raises zoom to at least 7× and bounds it to 6–256×. Selection fits the chosen geography and updates its card without changing inspection or creating a selection-specific zoom floor. Leaving Blocks aborts requests and releases fine geometry/cache. Full census extent uses generalized national geometry outside Blocks; exact outlines require Blocks and full extent. Fill, clipping and hit testing use the selected coverage. Static district/connection paths and county centroids are memoized across movement. Generalization must not claim to restore ideal straight power-diagram edges or erase genuine connectivity-repair bends.

The national land view uses cleaned overviews with matching shared-divider and coast meshes for every state. District fills have no per-ring strokes; thin white state boundaries follow only top-level coast rings. Every enclosed shoreline stays subdued, including islands inside inland lakes: even-depth land rings are not automatically outer state borders. Coast classification runs offline using ring containment, independent of winding, without changing coordinates. Five bundled layers per anchor carry fills, classified coast, dividers, derived paths and original recorded links; layer plan identities, populations and coordinate frames must match before rendering. Full census extent restores the original national geometry. Alaska/Hawaii keep their separate inset projections. No county/block data is requested nationally.

Optional `nationalLandAnchors` provide lighter national-only fills and matched coast/divider meshes. `build_national_land_overview.py` derives them from existing land displays using jointly simplified shared boundary arcs, preserving original coordinate subsequences, district properties, polygon parts/holes and coordinate frames. Exterior source edges near neighboring states remain exact; rejected candidates explicitly retain original geometry. This does not repair pre-existing interstate display seams or revalidate saved-plan physical connectivity. Recorded and derived connection asset references are reused exactly. `--publish-prepared` validates complete four-anchor coverage, pinned base/runtime/assets and original topology, then adds the national descriptors with byte-exact metadata backups. Original state geometry, census extent, plans/proofs and block chunks remain unchanged.

National drawing preparation lives in `lib/block-national-render.ts`. Cache only successful complete SVG preparations, keyed by anchor, coverage mode, content-addressed assets, plan identities, coordinate frames and drawing dimensions. The shared LRU holds at most two views and an estimated 64 MiB of path strings/bookkeeping; decoded asset caches remain separate, so this is not a browser heap limit. Partial border-error maps must not enter that cache. Memoized district fills, meshes and connection layers stay stable during hover; only affected state controls and borders update. Keep opacity inherited per path, keyboard focus separate from pointer hover, and selection callbacks current. Anchor remounts still reset UI preferences while permitting reuse of the prepared drawing.

The Michigan explorer defaults to Districts inspection, independent of the selected data card. All three inspection choices remain available. Counties remain selectable after a county click, including neighboring counties outside the selected district. Only explicit Blocks inspection loads the spatial index and block geometry, using small spatial chunks whose full source bounds intersect the viewport. Chunks contain unique, whole, unchanged saved blocks, including spanning polygons and water blocks; the storage grid never clips geography or becomes a district boundary. County shares use the whole county's residents from the saved summary, not area or loaded block counts; zero-population blocks remain in the totals. Selecting a block updates its actual county and district context. Already available blocks remain inspectable while new coverage is loading.

Michigan's session cache shares overlapping in-flight requests and uses two concurrent loads. It distinguishes complete viewport coverage from trusted cached coverage that can remain visible during loading; a newly requested group appears together when complete. Cached subset zooms resolve without refetch or repeated geometry preparation. Prepared bounds/indexes and lazy paths keep stable identity; inactive chunks use a 64 MiB raw-JSON LRU budget, with active coverage retained even if it exceeds that soft total budget. Raw bytes are not a heap-memory bound. Anchor changes and leaving Blocks cancel and release the session. The canvas can transform the intersecting footprint of a valid previous frame during pan/zoom, while newly exposed regions show the base map and a loading indicator. Appearance or dimension changes must invalidate unsafe raster reuse; pending/error coverage must never be labeled complete. Counties and city points start on; density, congressional boundaries and derived/recorded connections start off. The desktop map scales to the viewport height while preserving its aspect ratio. At desktop widths of at least 1280px, the explorer uses a left plan-selection/geography sidebar, central map, and right display-settings sidebar. House sizes, state/district selection and county/block searches stay beside the map; opacity sliders appear for enabled reference layers and longer explanations stay under Sources and interpretation. Sidebars have bounded independent overflow. Smaller screens stack the same controls and keep display settings collapsible below the map. The responsive layout uses a single controls instance and preserves the map aspect ratio. Anchor changes reset Michigan's selection, cache and controls. City points cover 91 incorporated Michigan cities with at least 10,000 residents in the 2020 Census, using pinned official Gazetteer coordinates and Census population counts; points do not assign an entire city to a district.

`scripts/build_michigan_explorer.py` combines independently verified geometry and saved-block summaries into 21 immutable assets (four geometry layers plus one summary per plan, and one city collection). `scripts/build_michigan_spatial_blocks.py` follows it in `npm run prepare:block-plans`, adding the small-area block assets and optional `spatialIndex` references. A 0.125° storage grid is adaptively split to at most 256 blocks / 512 KiB raw per ordinary chunk; individual large blocks remain whole and can exceed that limit. Full-feature fingerprints, unique GEOIDs, county/district populations and before/after preservation hashes are reconciled for every anchor. Spatial publication only adds references/assets; earlier reports and accepted records remain intact. The spatial report is `data/districting-block-plans/michigan-spatial-blocks-report.json`; `scripts/audit_michigan_spatial_chunks.py` independently checks served payloads against saved county exports. No solver runs or saved-plan edits are involved. See `prompts/block-plan-main-integration.md` for historical and current validation. Geometry benchmarks use pinned real assets; their Node CPU and memory measurements must not be described as browser FPS, input latency or browser memory.

### Shared state explorer rollout

The all-state implementation is `StateBlockExplorer` with generic interaction, spatial cache and assignment-loading helpers. Michigan names remain compatibility exports for its existing tests. `manifest.stateExplorers` enables the shared component per state; older bundles retain the previous state-map fallback. Districts/Counties/Blocks inspection, retained block coverage during new loads, county switching and whole-county resident shares follow the Michigan behavior described above. The shared national/state dashboard places House-size and geography controls on the left and display controls on the right at desktop widths; one responsive instance of each control stacks on smaller screens. Preserve map aspect ratios and existing anchor remount keys when changing this layout. Counties and city/place points start on. Recorded policy links also start on when present, with separate water/exclave styling and endpoint inspection. Density, current congressional boundaries and derived water paths start off.

Blocks inspection also preflights the complete visible chunk set against an active-view target of 32 MiB raw JSON and 20,000 blocks. Dense views zoom closer before requesting geometry; every intersecting chunk is still included, rather than truncating counties or block lists. Apply this to entry, fits, county switches, pan and zoom, including the render when the async spatial index first arrives. Keep prior affordable coverage during camera correction and loading. An indivisible outlier that still exceeds the target at maximum zoom must show an explicit unavailable-area message and must not start the oversized load. This camera/request budget is separate from the cache's inactive-data budget and is not a browser heap guarantee. Saved polygons, assignments and Alaska coordinates are unchanged.

Michigan's validated land-focused assets remain unchanged. Generic state land geometry uses jointly simplified overview/fine polygons and separate coast/divider meshes. Each original census overview is retained as `censusOverview`; the coverage toggle must use it rather than the new land overview. Alaska's state geometry, spatial indexes and city points use the continuous longitude frame, including values below −180. Never substitute the wrapped national Alaska asset in this explorer. Exact geometry requires Blocks inspection and full census extent wherever a land derivative is available.

Outside Michigan, city/place points include incorporated places and census-designated places with at least 10,000 residents in the 2020 Census. Michigan retains its 91-city selection. Labels, coverage, Census source URLs and hashes live in `cityMetadata`; a point never assigns the entire place population to its district. County names remain neutral where the source does not identify borough/parish/independent-city labels.

`build_state_explorer_cities.py`, `build_state_explorer_geometry.py` and `build_state_explorer_blocks.py` produce independent fragments without changing the live manifest. Schema-2 spatial chunks share unchanged geometry between anchors; a small per-plan sidecar restores district IDs in the exact source-feature order. Validate plan/state/frame/chunk identity, geometry digest, assignment count/range and reconciled population before preparing or drawing blocks. Michigan schema-1 assets remain valid. Cache budgets count both geometry and assignment bytes. The single-worker block pass is resumable by completed state and freezes its four runtime sources while active; do not duplicate or edit an active run.

`publish_state_explorer.py --publish` is the final preparation step. It requires all 50 states, 181 accepted plan identities and exactly 200 anchor/state memberships, validates compressed/raw asset hashes, population summaries, sidecars, source/runtime preservation and original proofs, and saves exact manifest/index backups before adding `stateExplorers`. It never edits accepted plans or runs a solver. A successful publication report plus production build and browser checks are required before calling the rollout complete. While generation is pending, the existing preview remains authoritative.

The generated directory has roughly half a million assets. It is excluded from Tailwind class discovery and automatic NFT traversal, while final API tracing explicitly includes every generated gzip asset via 16 hash-prefix globs plus the metadata/catalog files. The guarded early-tracer hook is specific to Next 15.2.8 and must be reviewed/tested on upgrades; do not silently disable its guard or blanket-exclude generated assets from final route traces. Historical cache-backed assets and proofs retain the read-only `BLOCK_PLAN_CACHE_ROOT` mount contract. Final trace coverage and live asset-serving checks are separate from successful source compilation.

Deployments do not ship that directory. Git tracks only the manifest, build reports and final catalog; `npm run publish:block-plans` verifies every proof and payload against the index and uploads missing assets to Cloudflare R2 under their route keys. Setting `BLOCK_PLAN_ASSET_ORIGIN` at build time adds a `beforeFiles` rewrite from `/api/district-plans/*` to the bucket, and `loadBlockPlanManifest` falls back to the tracked manifest (still pinned to the catalog hash) when no server index exists. Leave the variable unset locally to keep the verified disk route.
