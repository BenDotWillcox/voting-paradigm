# CLAUDE.md

Guidance for Claude Code working in this repository. This is a living document — edit it when architecture changes, not the other way around.

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

**Classical baselines — fixed bank of 36 civic-value items (both implemented):**

- **Gaussian linear utility model** (`GaussianLinearUtilityModel`, renamed from `ThurstonePairwiseModel` — it isn't actually Thurstone Case V). Gaussian likelihood on continuous strength observations; closed-form Kalman-style posterior update. Fast, interpretable, native uncertainty.
- **Bradley-Terry + Laplace approximation** (`BradleyTerryLaplaceModel`). Logistic likelihood on signed strength, with `|strength|/10` as per-observation weight. MAP via Newton refit from the full evidence history (order-independent); posterior approximated as Gaussian around the MAP. The canonical classical pairwise-ranking baseline.

**Evidence contract (implemented).** All elicitation modalities normalize into typed `Evidence` (`preferences/types.py`): sources `pairwise | slider | free_text_extraction | correction | override`, a signed value in [-10, 10] over an item pair, and a confidence weight. Only pairwise/slider have likelihoods today; the other sources are declared contract, rejected with 422 at the API until their handlers land. LLM components may *produce* evidence; only deterministic model code may *apply* it. Ballot-level overrides are recorded for audit and never update the posterior; dimension-level corrections become evidence only after user confirmation.

**Vote preview mapping (decided, not yet built).** Fixed-bank models score ballot options via authored stance vectors (option utility = stance · posterior over value items), keeping all models comparable at the vote layer; the embedding model additionally scores option text natively.

**Primary human-measure showcase — previously unanswered civic decisions:**

- The participant and model receive the same versioned neutral packet.
- Political identity, partisan voting history, and demographic proxies are not
  model inputs.
- Every model freezes full option probabilities before the participant's
  answer enters evidence.
- Measures share one standardized fictional jurisdiction but remain legally and
  fiscally independent; preference evidence accumulates.
- Packets pass a contextual-sufficiency audit so known decision-relevant facts
  are stated and unresolved facts remain explicit unknowns.
- The model ladder compares fixed/adaptive structured baselines, a direct LLM,
  and an LLM-plus-explicit-posterior hybrid. An embedding/Bayesian-last-layer
  model remains a candidate hybrid representation, not an assumed winner.
- LLM comparisons expose structured-only, conversational-only, and combined
  evidence conditions. Predictions retain private supporting-evidence IDs and
  unsupported-assumption flags.
- Semantically equivalent prompts and option-order/label permutations measure
  sensitivity before the final LLM estimator is frozen. Repeated calls are
  diagnostics, not independent human observations.
- Primary outcomes are prequential log loss and high-confidence delegated
  error. Question efficiency, follow-up quality, and cross-format ballot
  fidelity are secondary.

Versioned file-backed contracts live in `eval/contracts.py`; the non-held-out
fixture is `eval/fixtures/preference_eval_dev_v1.json`, and
`python -m eval.run_human_measure_eval` runs the deterministic Phase 2 replay.
The Phase 3 authoring contract is
`eval/fixtures/preference_eval_bank_profile_v1.json`; validate and hash it by
running `python -m eval.validate_bank_profile` against that path.

**Phase 4A architecture (frozen):** the LLM is a provider-neutral elicitation
orchestrator, not the durable preference store. It may choose vetted questions,
clarify existing evidence, and inspect typed posterior uncertainty, candidate
scores, coverage, and conflicts. Only the explicit preference model may move
posterior state from eligible typed evidence; inferred conversational evidence
has zero weight until participant confirmation. Ballot semantic mapping and
prediction readout remain separate from preference storage. The direct LLM
predictor is mandatory as an experimental control, while the intended
candidate architecture is an LLM plus explicit posterior.

Primary held-out elicitation cannot inspect a target packet or ask a
target-specific follow-up after packet exposure. Prediction arms receive the
same neutral packet and evidence cutoff. The action policy is held constant:
select the top-probability option for single choice, emit a valid format-
specific prediction for rich ballots, display confidence, and allow the
participant to override or abstain. The model itself cannot abstain or defer;
confidence thresholds are diagnostics and a possible future user-controlled
authorization policy. The machine-readable contract is
`eval/fixtures/preference_eval_phase4_protocol_v1.json`; the rationale and
Phase 4A-4E sequence are in `eval/PHASE4_PROTOCOL.md`.

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
- **Case-study exposure:** Ben has seen the topic-level Phase 3A authoring
  briefs but remains blind to exact packet language, options, quantitative
  values, arguments, and uncertainties until presentation. Codex may author the
  bank and Claude may perform the disclosed participant-blinded AI content
  review; a human content review is required before an external pilot. Novel-
  tier analysis must carry the topic-exposure caveat.
- **Restricted Phase 3B artifacts:** exact batches, fixtures, retest variants,
  and detailed review logs remain in Git-ignored `eval/restricted_bank/`;
  retrieved source documents remain in `.cache/eval-authoring/sources/`.
  Claude reviews them locally. Do not stage or open a content PR before every
  predeclared blinded participant finishes initial presentations and retests.
  Only generated safe summaries and aggregate hashes may enter interim PRs.
  Reviewer chat/status updates must also remain aggregate-only: do not name a
  slot or measure in connection with a finding, even without quoting prose.
- **Constructed authoring grounds:** content-bearing Phase 3B authoring uses
  the v2 trace/evidence/batch family. Every constructed measure declares an
  explicit structured assumption, and every source and assumption must bind
  to at least one exact participant-text trace.
- **Delegation claims:** sincere-choice prediction evaluates the substrate for
  future delegated voting, not real-world willingness to delegate or refrain
  from overriding the model.

### Active learning loop

Question selection evolves in three stages, each a shippable step:

1. **Max-variance pair selection** (implemented, default policy — `preferences/acquisition.py`). Pick the pair `(a, b)` with highest posterior std of `u_a − u_b`; deterministic lexicographic tie-break. The `random` policy remains as the eval baseline.
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
- **Demo 2 — synthetic preference models:** held-out pairwise log-likelihood,
  Kendall τ, Brier score, calibration, and questions-to-convergence curves.
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
- `eval/` harness skeleton: seeded held-out splits, deterministic trials, demo 2 preference-model metrics first (results JSON gitignored under `eval/results/`)
- Human-measure Phase 1: strict versioned contracts, an eight-domain
  development fixture, canonical content hashes, and leakage-boundary tests
- Human-measure Phase 2: leakage-safe model adapter boundary, synthetic
  prequential replay, option and delegated-risk metrics, and an allowlisted
  publication-candidate serializer
- Human-measure Phase 3A: frozen Meridian/Harborview jurisdiction, exact
  48-slot source/tier/format matrix, packet/source/neutrality policy, seeded
  wave-order policy, balanced retest target, and final-bank profile validator

**Next:**
- Seed-plumb all stochastic operations for the reproducibility invariant
- Extend `eval/` with one baseline metric for demos 1/3/4 as they mature
- Add a top-level navigation surfacing the demo set (`/methods`, `/preferences`, future `/districts`, `/delegation`)

### Demo 1: Voting methods comparison

**Done:**
- Voting package: plurality, approval, IRV, Borda, Ranked Pairs, Score, Quadratic — all with injectable tiebreak, abstention support, typed result classes, full test coverage. Review changes with `.claude/skills/voting-package-conventions/` and `.claude/skills/voting-method-correctness/`.
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
- Preferences package: question bank + elicitation engine + pytest suite
- Typed `Evidence` contract (pairwise/slider implemented; free-text/correction/override declared, 422 until built); legacy `responses`/`thurstone_v1` states upgrade transparently in `preferences/serialization.py`
- `GaussianLinearUtilityModel` (renamed from `ThurstonePairwiseModel`, docstrings corrected) + `BradleyTerryLaplaceModel`; model registry with `model_for_version` state routing
- Max-variance acquisition (default) + random baseline in `preferences/acquisition.py`
- Fixed-bank eval harness: 4 authored synthetic personas + seeded Dirichlet-mixture persona generator (`eval/personas.py`), three response models as the misspecification axis (`gaussian_gap` matches the Gaussian likelihood, `logistic_choice` matches BT, `sloppy` matches neither — `eval/response_models.py`), held-out pair splits, log-likelihood/accuracy/Brier/Kendall-τ/calibration curves, models × policies comparison (`python -m eval.run_preference_eval --response-model ...`), grid sweeps for notebooks (`eval/sweeps.py`)
- API: `/sessions/evidence` endpoint (replaces `/sessions/respond`), model + selection-policy params on session start
- TS hygiene: Zod-validated JSONB boundaries (`lib/validations/preferences-schemas.ts`); `startPreferenceSession` race fixed via server-generated UUID + single insert
- Human-measure evaluation contracts (`eval/contracts.py`): standardized
  jurisdiction and packet versions, rich ballot responses, evidence cutoffs,
  prediction snapshots, dynamic ontology versions, and evaluation runs
- Eight-domain non-held-out fixture plus deterministic validator/manifest
  command documented in `eval/README.md`
- Deterministic human-measure session runner with zero-evidence,
  post-onboarding, post-wave, and immediate pre-answer snapshots
- Uniform-prior baseline, scripted test double, primary log-loss and
  risk/coverage metrics, stable/tentative slices, and unsupported-delegation
  accounting
- Aggregate-only public artifact serializer with planted-sensitive-data tests
- Phase 3 bank-authoring profile and validator: frozen fictional jurisdiction,
  32/16 real/constructed split, 16/16/16 intended tiers, 38/9/1 ballot mix,
  source and political-cue boundaries, contextual-sufficiency and cold-review
  gates, and 12-item retest target
- Phase 3B authoring infrastructure: source-content hashes and exact adapted-
  text traces, six-measure domain batches, deterministic 48-measure assembly,
  a hash-locked Claude review prompt, restricted disposition logs, and
  nonrevealing aggregate summaries
- Phase 3B bank content: all eight domain batches and all 48 exact measures
  structurally validated and approved by the locked participant-independent
  Claude review; restricted content remains ignored and only the eight
  generated safe summaries are tracked
- Phase 3C infrastructure: deterministic six-wave and option-order plan,
  7-14 day run-boundary enforcement with retest-independence checks, a locked
  retest-review prompt and aggregate summary, final review-ledger assembly,
  and a final execution-bundle manifest
- Phase 3C retest content: round one was correctly rejected because all twelve
  alternates were near-verbatim, and round two was rejected because mechanical
  rewrites damaged modality, qualifier binding, technical language, and prose.
  Direct review found nine manually authored version-3 packets approval-ready
  and requested three targeted passage repairs. Version 4 preserves those nine
  packet hashes, changes one participant-facing field in each of three packets,
  and is approved at all twelve exact packet hashes. The final restricted
  review ledger and execution-bundle manifest bind the approved 48-measure
  fixture, registry version 4, and presentation plan version 4; every prior
  round remains in the restricted audit trail

**Next, in order:**
1. Implement the Phase 4B provider-neutral interviewer tool surface, the
   missing deterministic fixed-sequence selector, and deterministic test
   doubles under the Phase 4A contract
2. Add confirmed conversational evidence with evidence IDs and unsupported-
   assumption flags, then fixed/expanding ontology variants
3. Add `prediction_snapshot.v2` plus a compatible run contract without
   mutating v1, then implement authored semantic mapping, direct LLM control,
   and hybrid probability readouts on common evidence cutoffs
4. Add prompt, option-order/label, and stochastic robustness diagnostics;
   freeze inputs, models, prompts, seeds, weights, and metrics before Ben's
   held-out case study
5. Build separate blind evaluation and future-facing showcase modes
6. Schedule and execute the six blinded waves and 7-14 day retests only after
   the remaining model/evaluation freeze is complete
7. *(Deferred)* LLM-generated vote rationales
8. *(Deferred)* LLM-generated personas

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
