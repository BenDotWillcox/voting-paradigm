# CLAUDE.md

Guidance for Claude Code working in this repository. This is a living document — edit it when architecture changes, not the other way around.

## What this project is

**Nebula Civitas is an experiment in a potential future voting paradigm where an AI agent uses a model of your preferences to vote in elections on your behalf.**

The thesis: modern voting methods (Ranked Pairs, Score, Quadratic) produce measurably better collective outcomes than plurality, but lose in practice because voters won't rank ten candidates and jurisdictions won't hand-tally complex ballots. Accurate preference models plus agent voting dissolve both objections — so the *better* methods become viable. This project demonstrates that claim empirically: same constituency, same preferences, different methods, visibly different (and arguably better) winners.

**This is a portfolio project**, not a product. The audience is AI/ML engineers evaluating the author's work. The "users" are simulated personas entered by the author. No real voters, no binding outcomes, no auth hardening, no crypto, no identity, no scale concerns. Optimization target: *demonstrated judgment, clean architecture, and depth in AI engineering, statistical modeling, and systems design.*

### Explicitly out of scope

- Real elections, binding outcomes, cryptographic voting
- Real user accounts, identity verification, multi-tenancy
- Subsidiarity algorithms and liquid-democracy delegation (interesting, but orthogonal — quadratic voting already lets voters express what matters to them)
- Mobile apps, on-chain anything, production-grade ops

## Working with the user

- **Domain expertise:** the user knows voting theory deeply. Ask clarifying questions about electoral behavior rather than assuming. Cite criteria (Condorcet, monotonicity, IIA, etc.) when discussing trade-offs.
- **Reviews code before committing:** walk through logic when requested; don't bundle unrelated changes.
- **Python > TypeScript for numerical/ML work:** scipy, numpy, PyTorch ecosystem. TypeScript is for the web frontend only.
- **Git workflow:** feature branches + PRs. Never commit without asking.

See `.claude/skills/` for project-specific review checklists (db-change, server-action, voting-method-correctness, voting-package-conventions, pr-reviewer).

## Architecture

Two processes. One web app, one Python service.

```
┌─────────────────────┐        ┌──────────────────────────────┐
│ Next.js 15 (App     │◄──────►│ FastAPI (Python 3.11)        │
│ Router) + React 18  │  HTTP  │ One service, multiple routers│
│                     │        │  /api/voting/...             │
│ Server Actions →    │        │  /api/preferences/...        │
│ Python API client   │        │  /api/personas/...  (future) │
│                     │        │  /api/agents/...    (future) │
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
voting/                     Python: pure voting methods + ballot types
preferences/                Python: preference modeling (Thurstone, future models)
personas/                   Python: simulated voter generation               (future)
agents/                     Python: agent voting policies                    (future)
eval/                       Python: model evaluation harness                 (future)
api/                        Python: FastAPI app, one router per domain
prompts/                    Project scope + documentation
.claude/skills/             Project-specific review/guardrail skills
```

**Domain packages are import-isolated.** `voting/` does not import `preferences/`. `api/` imports every domain but domains do not import `api/`. No circular deps; every package is testable without the HTTP layer.

## Data model (target state)

Current schema has proposals + a partially-built elections schema. Target state deletes proposals and introduces a ballot-measure model aligned with the thesis demo.

### Core tables

- **`user`** — actors (simulated personas authored by one real user)
- **`domain`, `program`** — two-level topic taxonomy (kept from original schema; reused for measure tagging and filtering)
- **`ballot_measure`** — a question posed to voters. Imported (source = ballotpedia) or user-created (source = user). Structurally identical; only source/author differs. Has title, summary, ballot type, jurisdiction, options.
- **`measure_option`** — ordered choices for a measure (yes/no is 2 rows; candidate race is N rows).
- **`measure_topic`** — junction table linking measures to domains/programs for filtering.
- **`electorate`** — a named simulated population with generation parameters and a seed. Reproducible.
- **`resolution_run`** — the thesis artifact. `(measure_id, electorate_id, method, seed, result_jsonb, computed_at)`. One measure can have many runs — same measure, same electorate, different methods = the side-by-side comparison.
- **`preference_session`** — a user's preference elicitation session (state snapshot as JSONB).
- **`preference_response`** — audit trail, one row per answered question.

### Schema vocabulary

- **Measure ≠ election.** A measure is the *question*. Resolving it under a specific method with a specific electorate is a `resolution_run`. "Election" is overloaded and not used in schema names.
- **Ballot type** (the shape of a voter's input: single_choice / approval / ranked / score / quadratic) is stored on the measure; it constrains what ballots voters can cast.
- **Resolution method** (how ballots tally: plurality / IRV / Borda / Ranked Pairs / Score / Approval / Quadratic) is chosen per run, not per measure — a single ranked-choice measure can be resolved by IRV *and* Borda *and* Ranked Pairs for comparison.

## AI engineering surface

### Preference models (two families, compared on what each is for)

**Classical baselines — fixed bank of ~30 civic-value items:**

- **Gaussian linear utility model** (renamed from `ThurstonePairwiseModel` — it isn't actually Thurstone Case V). Gaussian likelihood on continuous strength observations; closed-form Kalman-style posterior update. Fast, interpretable, native uncertainty. This is the existing code, with docstring corrections.
- **Bradley-Terry + Laplace approximation**. Logistic likelihood on signed strength, with `|strength|/10` as per-observation weight. Posterior approximated as Gaussian around the MAP. The canonical classical pairwise-ranking baseline.

**Primary showcase — dynamic items:**

- **Embedding + Bayesian last layer**. Items embedded with a pretrained `sentence-transformers` model (start: `all-MiniLM-L6-v2`, 384-dim). Posterior is over the user's weight vector `w ∈ ℝ³⁸⁴`; utility of any item `u_i = w · e_i`. Variational inference via **Pyro** (PyTorch-based; one framework for embeddings + inference). Supports LLM-generated items mid-session with zero state-shape changes.

### The comparison story

- **Fixed-bank subtask:** all three models are scored head-to-head on the same data (log-likelihood on held-out pairs, Kendall τ on held-out rankings, calibration, sample efficiency).
- **Dynamic-items subtask:** only the embedding model works. The portfolio payoff is cold-start accuracy — predicting preference for an item the user was never asked about.

MCMC comparison is deferred to future work; VI alone is sufficient for the thesis demo.

### Active learning loop

Question selection evolves in three stages, each a shippable step:

1. **Max-variance pair selection** (ships with rename). Pick the pair `(a, b)` with highest posterior std of `u_a − u_b`. Already supported by `get_uncertainty()`. Closes the active-learning loop immediately.
2. **Expected information gain / BALD** (follow-up). Pick the pair whose expected posterior update most reduces total entropy. Tractable under Gaussian/Laplace posteriors.
3. **LLM-generated items targeted at high-variance directions** (dynamic-items mode). Acquisition function picks a *direction* in embedding space with high posterior variance of `w`; LLM generates a new civic-value item whose embedding aligns with that direction; user answers; posterior tightens.

### Uncertainty-aware agent voting

Agent consults the posterior when casting a simulated ballot. If the margin between top candidates is within the posterior's noise envelope for the relevant utility differences, the agent flags low confidence and recommends targeted elicitation (looping back into stage 3 above). This is the link between model, agent, and question generator that makes the thesis concrete.

### Evaluation harness (`eval/`)

Proper ML evaluation, reproducible seeds, held-out splits. Per component:

- **Preference models:** held-out pairwise log-likelihood, Kendall τ on ranking, Brier score + reliability diagram for calibration, questions-to-convergence curves, cold-start accuracy (embedding model only).
- **Agent vote alignment:** precision/recall of agent's vote vs the user's stated preference on a held-out set of measures.
- **Voting methods:** social welfare metrics (e.g., Borda-score of winner, Condorcet efficiency across simulated elections), and sensitivity of outcome to method choice given a fixed electorate.

### Deferred (do not build yet)

- **LLM-generated vote rationales** — demo polish, low priority.
- **LLM-generated personas** — wait until eval harness demands more electorate diversity.
- **MCMC inference for comparison against VI** — future work note.

All LLM calls live in Python. One framework for prompts, Pydantic output schemas, numerical code, and inference.

## Reproducibility (first-class invariant)

The thesis demo must be verifiable by anyone who clicks. Every stochastic operation is seeded:

- **Voting method tiebreaks** — each method takes an injectable tiebreak; default is `random_tiebreak(seed)`, not unseeded `random.choice`.
- **Electorate generation** — sampling from preference distributions uses a seed stored on the `electorate` row. Regenerating the same electorate_id produces byte-identical voters.
- **Resolution runs** — `(measure_id, electorate_id, method, seed)` is the cache key. Given the tuple, the result is deterministic.
- **LLM calls** — `temperature=0` for rationales and structured outputs; use the `seed` parameter where supported (OpenAI). Cache responses keyed on the full prompt.
- **Preference model inference** — RNG for MCMC / variational fits is seeded and recorded.

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

**Done:**
- Voting package: plurality, approval, IRV, Borda, Ranked Pairs, Score, Quadratic — all with injectable tiebreak, abstention support, typed result classes, full test coverage
- Preferences package: Thurstone v1 model + question bank + elicitation engine + pytest suite
- Web shell: Next.js App Router, Drizzle schema for elections/preferences (to be refactored)
- Proposals removed: tables, queries, actions, components, and form deleted; migration `0004_optimal_mystique.sql` drops the 5 proposal tables + enum
- Unified API: single FastAPI process at `api/` with `/api/voting/*` and `/api/preferences/*` routers on :8000; consolidated `requirements.txt`; `npm run dev:all` runs web + api concurrently
- Ballot-measure schema: tables `ballot_measure`, `measure_option`, `measure_topic`, `electorate`, `resolution_run` (cache key `(measure_id, electorate_id, method, seed)`); enums `ballot_type`, `measure_status`, `measure_source`. Migration `0005_green_mandrill.sql` drops the old `election*` tables/enums and creates the new ones. Schema only — no queries/actions/UI persisting yet.
- User-facing rename: demo route `/elections` → `/methods` (and `lib/elections-api.ts`, `components/elections/`, `actions/elections-actions.ts`, `types/elections.ts`, `lib/elections/` all renamed to `methods`). TS types `ElectionMethod`/`ElectionScenario`/`ElectionDemo` → `VotingMethod`/`MethodScenario`/`MethodDemo`. Voting-result type names (`ElectionResult`, `IRVResult`, etc.) kept — they are the canonical voting-theory term.

**In progress (this branch):**
- Ballot measure feed UI, preferences elicitation flow, methods comparison explorer

**Next, in order:**

1. Add `ballot_measure` queries/actions and wire `/ballots/new` form to persist
2. Zod-validate JSONB boundaries in preferences actions
3. Fix `startPreferenceSession` race via client-generated UUID (pattern #2)
4. Seed-plumb all stochastic operations for the reproducibility invariant
5. Rename `ThurstonePairwiseModel` → `GaussianLinearUtilityModel`, fix docstrings; ship max-variance question selection
6. Build `eval/` harness skeleton with held-out splits and one baseline metric per component
7. Implement `BradleyTerryLaplaceModel` on the fixed bank; run the three-way evaluation (current code counts as model #1)
8. Implement `EmbeddingPreferenceModel` — pretrained sentence-transformers + Pyro SVI over user weight vector
9. Wire LLM-generated dynamic items into elicitation flow; acquisition function over embedding directions
10. Uncertainty-aware agent voting + elicitation loopback on low-confidence margins
11. *(Deferred)* LLM-generated vote rationales
12. *(Deferred)* LLM-generated personas
