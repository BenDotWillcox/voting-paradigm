# AGENTS.md

Guidance for Codex working in this repository. This is a living document — edit it when architecture changes, not the other way around.

## What this project is

**Nebula Civitas is a portfolio of demos exploring potential improvements to democratic voting.** Each demo isolates a specific friction that has blocked better voting practice from being adopted at scale, and shows how modern technology — AI agents, statistical preference modeling, optimization, network analysis — could plausibly dissolve it. The demos share infrastructure (one repo, one Next.js shell, one FastAPI service, one DB) but are conceptually independent: each is a self-contained answer to one objection against electoral reform.

The umbrella thesis: the gap between *what voting theory recommends* and *what real polities use* is technological as much as political. Better methods, better districts, better delegation, better preference articulation — none have spread because the practical machinery wasn't there. This project builds parts of that machinery as proofs of concept.

**This is a portfolio project**, not a product. The audience is AI/ML engineers evaluating the author's work. The "users" are simulated personas authored by one real user. No real voters, no binding outcomes, no auth hardening, no crypto, no identity, no scale concerns. Optimization target: *demonstrated judgment, clean architecture, and depth in AI engineering, statistical modeling, and systems design.*

### The demos

Each demo is a top-level route in the web app and a domain package on the Python side. Demos can compose where it falls out naturally (e.g. an electorate produced by the districting demo can feed the methods comparison) but each must stand alone as a portfolio artifact.

| # | Demo | Route | Status | Core showcase |
|---|------|-------|--------|---------------|
| 1 | **Voting methods comparison** — same ballots, multiple resolution methods, side-by-side winners | `/methods` | Voting package complete; UI in progress | Voting theory rigor, electoral criteria, reproducibility |
| 2 | **Agent voting via preference models** — LLM-elicited preference posterior; agent casts a ballot under uncertainty | `/preferences` | In progress | Bayesian inference, embeddings, active learning, LLM orchestration |
| 3 | **Algorithmic districting** — fair, transparent district maps under explicit constraints | `/districts` | Apportionment slice live; district polygons planned | Optimization, graph algorithms, geo data, fairness metrics |
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

See `.Codex/skills/` for project-specific review checklists (db-change, server-action, voting-method-correctness, voting-package-conventions, pr-reviewer).

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
eval/                       Python: model evaluation harness                 (future) [cross-demo]
api/                        Python: FastAPI app, one router per demo
prompts/                    Project scope + documentation
.Codex/skills/             Project-specific review/guardrail skills
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

Each demo has its own AI/ML/systems story. The depth lives here. Demo 1 (voting methods) is mostly about correctness and rigor — its conventions are documented in `.Codex/skills/voting-method-correctness.md` and `.Codex/skills/voting-package-conventions.md`. Demos 2–4 are detailed below.

## Demo 2: Agent voting via preference models

### Preference models (two families, compared on what each is for)

**Classical baselines — fixed bank of ~30 civic-value items:**

- **Gaussian linear utility model** (renamed from `ThurstonePairwiseModel` — it isn't actually Thurstone Case V). Gaussian likelihood on continuous strength observations; closed-form Kalman-style posterior update. Fast, interpretable, native uncertainty. This is the existing code, with docstring corrections.
- **Bradley-Terry + Laplace approximation**. Logistic likelihood on signed strength, with `|strength|/10` as per-observation weight. Posterior approximated as Gaussian around the MAP. The canonical classical pairwise-ranking baseline.

**Primary showcase — dynamic items:**

- **Embedding + Bayesian last layer**. Items embedded with a pretrained `sentence-transformers` model (start: `all-MiniLM-L6-v2`, 384-dim). Posterior is over the user's weight vector `w ∈ ℝ³⁸⁴`; utility of any item `u_i = w · e_i`. Variational inference via **Pyro** (PyTorch-based; one framework for embeddings + inference). Supports LLM-generated items mid-session with zero state-shape changes.

### The comparison story

- **Fixed-bank subtask:** all three models are scored head-to-head on the same data (log-likelihood on held-out pairs, Kendall τ on held-out rankings, calibration, sample efficiency).
- **Dynamic-items subtask:** only the embedding model works. The portfolio payoff is cold-start accuracy — predicting preference for an item the user was never asked about.

MCMC comparison is deferred to future work; VI alone is sufficient for this demo.

### Active learning loop

Question selection evolves in three stages, each a shippable step:

1. **Max-variance pair selection** (ships with rename). Pick the pair `(a, b)` with highest posterior std of `u_a − u_b`. Already supported by `get_uncertainty()`. Closes the active-learning loop immediately.
2. **Expected information gain / BALD** (follow-up). Pick the pair whose expected posterior update most reduces total entropy. Tractable under Gaussian/Laplace posteriors.
3. **LLM-generated items targeted at high-variance directions** (dynamic-items mode). Acquisition function picks a *direction* in embedding space with high posterior variance of `w`; LLM generates a new civic-value item whose embedding aligns with that direction; user answers; posterior tightens.

### Uncertainty-aware agent voting

Agent consults the posterior when casting a simulated ballot. If the margin between top candidates is within the posterior's noise envelope for the relevant utility differences, the agent flags low confidence and recommends targeted elicitation (looping back into stage 3 above). This is the link between model, agent, and question generator that makes the thesis concrete.

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

**Scope locked in.** Specific algorithm: Cohen-Addad / Klein / Young **balanced power diagrams** (arXiv 1710.03358). Full design — interaction model, schema, precompute strategy, build sequence — is in [`prompts/demo-3-districting.md`](prompts/demo-3-districting.md). Headline decisions: 2020 census, tract resolution, House-size slider over **[435, 11037]** (logarithmic scale) with anchors at Wyoming Rule (~574), Cube Root Rule (~692), and Article I §2 1-per-30K ratio (11,037 — the constitutional minimum-district-size that the 1929 cap abandoned). Single canonical seed, 50 states only (DC + territories deferred). Precompute per-state results across the apportionment range; runtime path is apportionment (live, sub-ms) plus DB lookup of cached district maps.

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
- **Demo 2 — preference models:** held-out pairwise log-likelihood, Kendall τ on ranking, Brier score + reliability diagram for calibration, questions-to-convergence curves, cold-start accuracy (embedding model only).
- **Demo 2 — agent vote alignment:** precision/recall of agent's vote vs the user's stated preference on a held-out set of measures.
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

**Next:**
- Seed-plumb all stochastic operations for the reproducibility invariant
- Build `eval/` harness skeleton with held-out splits and one baseline metric per demo
- Add a top-level navigation surfacing the demo set (`/methods`, `/preferences`, future `/districts`, `/delegation`)

### Demo 1: Voting methods comparison

**Done:**
- Voting package: plurality, approval, IRV, Borda, Ranked Pairs, Score, Quadratic — all with injectable tiebreak, abstention support, typed result classes, full test coverage
- Ballot-measure schema: tables `ballot_measure`, `measure_option`, `measure_topic`, `electorate`, `resolution_run` (cache key `(measure_id, electorate_id, method, seed)`); enums `ballot_type`, `measure_status`, `measure_source`. Migration `0005_green_mandrill.sql`. Schema only — no queries/actions/UI persisting yet.
- User-facing rename: demo route `/elections` → `/methods`; corresponding `lib/`, `components/`, `actions/`, `types/` renames. TS types `ElectionMethod`/`ElectionScenario`/`ElectionDemo` → `VotingMethod`/`MethodScenario`/`MethodDemo`. Voting-result type names (`ElectionResult`, `IRVResult`, etc.) kept — they are the canonical voting-theory term.

**In progress (this branch):**
- Portfolio-facing methods comparison explorer
- Demo 3 districting shell with apportionment-driven seat counts

**Next:**
1. Replace curated method scenarios with persisted `resolution_run` rows when the demo needs saved runs
2. Add ballot-measure queries/actions only when a portfolio demo has a concrete persisted workflow for them

### Demo 2: Agent voting via preference models

**Done:**
- Preferences package: Thurstone-named v1 model (actually a Gaussian linear utility model — to rename) + question bank + elicitation engine + pytest suite

**In progress (this branch):**
- Preferences elicitation flow UI

**Next, in order:**
1. Zod-validate JSONB boundaries in preferences actions
2. Fix `startPreferenceSession` race via client-generated UUID
3. Rename `ThurstonePairwiseModel` → `GaussianLinearUtilityModel`, fix docstrings; ship max-variance question selection
4. Implement `BradleyTerryLaplaceModel` on the fixed bank; run the three-way evaluation (current code counts as model #1)
5. Implement `EmbeddingPreferenceModel` — pretrained sentence-transformers + Pyro SVI over user weight vector
6. Wire LLM-generated dynamic items into elicitation flow; acquisition function over embedding directions
7. Uncertainty-aware agent voting + elicitation loopback on low-confidence margins
8. *(Deferred)* LLM-generated vote rationales
9. *(Deferred)* LLM-generated personas

### Demo 3: Algorithmic districting

**Status:** Apportionment + map shell implemented. Design doc at [`prompts/demo-3-districting.md`](prompts/demo-3-districting.md). The current slice ships Method-of-Equal-Proportions apportionment, a FastAPI route, a national/state map UI, and tests. Real district polygons, metrics, and precomputed district maps are still planned.

**Next, in order:**
1. Add methodology writeup page explaining the algorithm, constraints, seed policy, and limits of geometric fairness.
2. Precompute pipeline for one state end-to-end.
3. Scale precompute to all 50 states across cap range [435, 1000].
4. State detail page with real district polygons + metrics (Polsby-Popper, population deviation, edge count).
5. *(Deferred)* Live seed regeneration, block-group resolution, DC/territories, cross-demo composition with methods.

### Demo 4: Liquid democracy

**Status:** Not started. Scope before building. Open questions in the demo 4 section above.

The most interesting cross-demo synthesis is "delegate recommendations driven by demo 2's preference posterior" — flag for design attention when both demos are mature.
