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
max-variance acquisition, a fixed-bank synthetic harness, and the versioned
contracts, eight-domain development fixture, deterministic prequential runner,
primary metrics, and allowlisted artifact boundary for the future standardized
human-measure evaluation. Its Phase 3 authoring profile now freezes the
fictional jurisdiction, exact 48-slot bank matrix, source and neutrality
requirements, contextual-sufficiency review, packet-blind Claude review path,
presentation-order policy, and linked retest target before packet drafting.
Phase 4 will add evidence-grounding and prompt/order robustness diagnostics.
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
