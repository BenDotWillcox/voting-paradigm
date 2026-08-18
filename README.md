# Nebula Civitas

A portfolio of demos exploring potential improvements to democratic voting.

The gap between *what voting theory recommends* and *what real polities use* is technological as much as political. Better methods, better districts, better delegation, better preference articulation — none have spread because the practical machinery wasn't there. This project builds parts of that machinery as proofs of concept.

Synthetic personas drive development benchmarks. The final preference-model
evidence will add one explicitly labeled personal case study and may later add
a separately approved opt-in pilot. There are no real elections or binding
outcomes. The audience is engineers evaluating systems and ML work on a domain
the author cares about.

## The demos

| # | Demo | Route | Status | Core showcase |
|---|------|-------|--------|---------------|
| 1 | **Voting methods comparison** — same ballots, multiple resolution methods, side-by-side winners | `/methods` | Voting package complete; UI in progress | Voting theory rigor, electoral criteria, reproducibility |
| 2 | **Agent voting via preference models** — LLM-elicited preference posterior; agent casts a ballot under uncertainty | `/preferences` | In progress | Bayesian inference, embeddings, active learning, LLM orchestration |
| 3 | **Algorithmic districting** — fair, transparent district maps under explicit constraints | `/districts` | Apportionment slice live; district polygons planned | Optimization, graph algorithms, geo data, fairness metrics |
| 4 | **Liquid democracy** — delegation graphs, transitive trust, topic-conditional delegates | `/delegation` | Planned | Network analysis, simulation, dynamics on graphs |

Demos share infrastructure (one repo, one Next.js shell, one FastAPI service, one DB) but are conceptually independent — each is a self-contained answer to one objection against electoral reform.

## Architecture

Two processes. Next.js owns UI, routing, forms, and DB writes. A single FastAPI service owns numerical modeling, voting resolution, LLM orchestration, and simulation — with one router per demo.

```
Next.js 15 (App Router)  ◄── HTTP ──►  FastAPI (Python 3.11)
        │                                      │
        │  Server Actions (mutations only)     │  Stateless per call;
        │                                      │  reads DB, never writes
        ▼                                      ▼
              PostgreSQL (Drizzle ORM)
```

Python never writes the DB — Server Actions own persistence; Python receives state and returns updated state. This keeps the transactional story simple and makes Python endpoints trivially reproducible given an input state.

Domain packages (`voting/`, `preferences/`, future `districting/`, `delegation/`) are import-isolated from each other; `voting/` is the one foundational primitive other demos may depend on.

## Stack

- **Web:** Next.js 15 (App Router), React 18, TypeScript, Tailwind 4, shadcn/ui, React Hook Form + Zod
- **DB:** PostgreSQL via Drizzle ORM
- **API / numerics:** FastAPI, Pydantic, Python 3.11
- **ML / inference:** scipy, numpy, PyTorch + Pyro (variational inference), `sentence-transformers` for embeddings
- **Tests:** pytest for Python; voting package has 197 passing tests covering all 7 resolution methods

## Getting started

### Prerequisites

- Node.js 20+, npm
- Python 3.11
- PostgreSQL (local or hosted)

### Setup

```bash
# Install JS dependencies
npm install

# Set up Python venv and install dependencies
python -m venv venv
source venv/Scripts/activate     # Windows Git Bash
# or: source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

Create `.env.local` in the project root:

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/voting_paradigm
VOTING_API_URL=http://localhost:8000
```

Apply migrations:

```bash
npm run db:migrate
```

### Run everything

```bash
npm run dev:all      # Next.js on :3000, FastAPI on :8000
```

Or run them separately:

```bash
npm run dev          # Next.js only
npm run api:dev      # FastAPI only
```

### Tests

```bash
pytest                          # all Python tests
pytest voting/tests -v          # voting package only
npm run lint                    # Next.js + TypeScript checks

# Validate and hash the non-held-out preference-evaluation fixture
python -m eval.validate_fixture eval/fixtures/preference_eval_dev_v1.json

# Replay the synthetic session and write an allowlisted publication candidate
python -m eval.run_human_measure_eval
```

## Reproducibility

Every stochastic operation is seeded:

- Voting method tiebreaks take an injectable RNG; default is a seeded random tiebreak.
- Electorate generation seeds are stored on the row; regenerating the same `electorate_id` produces byte-identical voters.
- Resolution runs are cached by `(measure_id, electorate_id, method, seed)`.
- LLM calls use `temperature=0` and (where supported) the `seed` parameter; responses are cached on the full prompt.

Anyone clicking through a demo can rerun a result and get exactly the same output.

## Project status

This is an active, in-progress portfolio project. Demo 1 (voting methods) has a
complete Python package and a live comparison UI backed by curated scenarios.
Demo 2 (agent voting) has Gaussian and Bradley-Terry preference models,
fixed-sequence/random/max-variance acquisition, a fixed-bank synthetic
harness, and the versioned contracts, eight-domain development fixture,
deterministic prequential runner, primary metrics, and allowlisted artifact
boundary for the future standardized human-measure evaluation. Its Phase 3
authoring profile now freezes the
fictional jurisdiction, exact 48-slot bank matrix, source and neutrality
requirements, contextual-sufficiency review, packet-blind Claude review path,
presentation-order policy, and linked retest target before packet drafting.
Phase 3B infrastructure adds exact source captures and adapted-text traces,
six-measure domain batches, deterministic final-fixture assembly, a locked
Claude review prompt, restricted disposition logs, and participant-safe
aggregate review summaries. All eight domain batches and all 48 measures are
participant-independently approved at their exact hashes. Exact packets and
review logs stay outside Git under `eval/restricted_bank/` until all
predeclared blinded presentations and retests are complete; only the eight
batch summaries and one retest aggregate review summary are tracked. Retest
variants, the final
review-provenance ledger, and final bundle freeze remain restricted. The 12
authored variants and deterministic plan pass the Phase 3C structural gate.
Locked review rejected the near-verbatim first registry and the mechanically
rewritten second registry. Direct review found nine version-3 packets
approval-ready and requested three targeted passage repairs. Version 4 carries
those nine packet hashes forward unchanged, revises exactly one field in each
of three packets, and is approved at all 12 exact packet hashes. The final
review-provenance ledger and execution-bundle manifest bind the approved
48-measure fixture, registry version 4, and presentation plan version 4.
Phase 3C also provides per-presentation option-order seeds and run validation
for wave order, retest independence, and the 7-14 day interval. The frozen
bundle is ready for blinded case-study scheduling; the six waves and retests
have not yet been executed.
Phase 4A now freezes the provider-neutral preference-system architecture:
the LLM is a tool-using elicitation orchestrator, an explicit posterior owns
durable preference state, a direct LLM predictor remains a required control,
and primary elicitation cannot inspect held-out target packets. Its public
six-arm comparison profile binds to the Phase 3A bank profile without loading
restricted content. Phase 4B adds the non-adaptive fixed-sequence baseline and
the provider-neutral, target-blind interviewer boundary: typed read-only tools,
vetted-question/evidence-linked actions, deterministic test doubles, complete
version/hash/seed/cutoff audit records, and content-addressed caching that does
not persist raw private conversation. It intentionally includes no live model
provider. Phase 4C adds the fixed-ontology evidence lifecycle:
private raw messages, hash-bound zero-weight proposals, independent
participant accept/edit/reject decisions, append-only corrections, durable
evidence IDs, and replayable structured/conversation/combined views at
identical cutoffs. Typed confirmation and correction provenance prevent
client-state bypasses and cross-condition correction leakage. It uses a
deterministic extractor test double. The second Phase 4C slice adds a separate
participant-governed expanding-ontology ledger: missing-dimension proposals
remain zero-weight, exact and possible duplicates are reviewed, participant
decisions alone admit or map dimensions, correction-stable support controls
shrinkage, evidence-condition binding prevents conversational leakage into
structured-only replay, and confirmed merge/prune events preserve the full
history. Seed dimensions cannot be merged or pruned. Its provider boundary is
still a test double and its policy thresholds are not yet the final experiment
freeze.
Phase 4D adds separate `prediction_snapshot.v2` and
`evaluation_run.v2` contracts without changing their frozen v1 counterparts.
Every prediction binds the exact packet, eligible evidence and conversation
prefix, posterior and ontology state where applicable, component artifacts,
and pre-answer cutoff. A normalized option distribution remains separate from
the complete single-choice, ranking, approval, score, or quadratic action.
Same-checkpoint comparisons must use one cutoff, and identical fixed/expanding
active inputs on the same stack cannot silently diverge. The two classical
baselines now replay their posteriors through a fixture-bound authored stance
map, one uncertainty-aware probability coupling, and one deterministic rich-
ballot policy; a public development map exercises all five ballot formats.
Provider-neutral direct-LLM and fixed/expanding hybrid readouts now consume
the same evidence cutoffs through content-addressed requests and private
caches. Hybrids receive recomputed option-level posterior summaries, while the
expanding arm additionally receives only active participant-admitted
dimensions. The final restricted map, prompt/order robustness diagnostics,
and a live provider remain later Phase 4 work.
Public aggregate artifacts still require explicit release review.
Demo 3 (algorithmic districting) currently ships the apportionment slice;
district polygon generation comes next. The ballot-measure, electorate, and
resolution-run tables are internal reproducibility scaffolding for future
persisted demos, not a current user-facing CRUD/feed product.

For deeper architectural context — invariants, layering rules, per-demo technical surfaces, the build queue — see [CLAUDE.md](CLAUDE.md).

## Repository layout

```
app/                Next.js App Router pages (one route per demo)
components/         React components (domain folders + ui/ for shadcn)
actions/            Server Actions — return ActionResult<T>
db/                 Drizzle schema, queries, migrations
lib/                Typed Python API clients, Zod validations
voting/             Python: pure voting methods + ballot types       [demo 1]
preferences/        Python: preference modeling                      [demo 2]
eval/               Python: synthetic + prequential human-measure evaluation
districting/        Python: redistricting algorithms       (planned) [demo 3]
delegation/         Python: liquid-democracy delegation    (planned) [demo 4]
api/                Python: FastAPI app, one router per demo
.claude/skills/     Project-specific review/guardrail skills
```

## License

Not yet specified — this is a personal portfolio project.
