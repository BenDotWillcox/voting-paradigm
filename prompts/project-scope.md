# Project Scope: Subsidiarity‑First Liquid Democracy (MVP)

> **Bar‑stool abstract:** We’re building a better way to make public decisions. On every issue, you can (1) vote yourself, (2) delegate by topic to someone you trust, or (3) let an optional AI helper recommend or cast a vote only when it’s confident it matches your preferences. Decisions default to the local level, the process is auditable, and individual ballots remain private. This MVP is a **local-only prototype** with simulated personas.

---

## 0) Quick Facts

- **Goal:** Prototype a cryptography‑ready, liquid‑delegation civic system that’s simple enough to test locally.
- **MVP Stack:** Next.js (App Router) + Supabase Postgres + Drizzle ORM. Local only; no real users, no PII.
- **Data Focus:** Short, structured proposals with verifiable fields (metrics, basic budget, scope).
- **Voting Methods (for later phases):**
  - **Multi‑option:** Condorcet with a fixed completion rule (**Ranked Pairs**).
  - **Boolean:** **Approval** (approve/disapprove).
  - **Continuous space:** Pre‑vote **synthesis** of a small representative menu; 1D medians when appropriate.
- **Delegation:** Topic‑scoped (Domain/Program). Basic in MVP; time‑decay/inbound caps later.
- **AI Agents:** Off by default in MVP. Phase‑1 adds opt‑in recommendations with confidence thresholds.
- **Privacy/Security:** MVP uses pseudonymous local users; cryptographic protocols (zk/threshold) are Phase‑2 targets.

---

## 1) Problem & Why Now (ultra‑short)

- **Plurality (FPTP)** drives spoilers and polarization → use **Condorcet + completion** for multi‑option choices; **Approval** for yes/no.
- **Representation gap** (one human ≈ 770k people) → **topic‑scoped delegation** + optional AI assistance to reduce effort.
- **Over‑centralization** → **jurisdiction resolver** that prefers local decisions (subsidiarity).
- **Opacity** → **open processes & logs** while keeping **ballots private**.

**Why now:** ubiquitous connectivity, modern cryptography (zk/MPC), and practical AI assistants make this workable at human scale.

---

## 2) MVP Boundaries (what we _are_ and _aren’t_ building)

### In scope (MVP)

- Proposal **creation form** that forces clarity (title, summary, problem, actions, metrics, scope, basic budget).
- **Topics:** human‑governed **Domains/Programs**; no auto‑tagging yet.
- **Local database** with a **minimal schema** (see §4).
- Simulated **personas** as `app_user` rows.
- A basic **dashboard** to list proposals and view details.
- **No real voting** yet (stub the tally step).

### Out of scope (for now)

- Cryptographic voting protocols (commit–reveal, threshold decryption, zk proofs).
- Identity/eligibility beyond fake personas.
- Delegation caps, time‑decay, or concentration dashboards.
- Attachments/evidence upload, PostGIS, RLS policies.

---

## 3) Proposal Intake (form blueprint)

**Header**

- **Title** ≤ 60 chars
- **Summary** ≤ 280 chars (plain English)

**Essentials**

- **Problem (≤ ~250 words)**
- **Actions** (3–7 concise bullets, verb‑first)
- **Metrics (SMART):** name, unit, baseline (value/year/source), target, deadline
- **Scope (optional):** GeoJSON text (keep minimal in MVP), population estimate + source

**Budget (MVP)**

- **Line items** (name, one‑time $, annual $, confidence 0–1)
- Roll‑up totals on the proposal row

**Governance stubs**

- **Legal citation** (free text) and `needsNewAuthority` flag
- **Equity beneficiaries/cost bearers** (free text)
- **Safeguards:** rollback trigger/steps, optional sunset, privacy notes

**Why this structure?**

- Keeps proposals short & verifiable; produces machine‑readable rows for later automation (dedupe, feasibility checks).

---

## 4) Minimal Data Model (Drizzle / Postgres)

```ts
// Core tables (UUID PKs; defaults use gen_random_uuid())
app_user(id, handle, created_at, updated_at)

domain(id, name, active)
program(id, domain_id -> domain.id, name, active, UNIQUE(domain_id, name))

proposal(
  id, author_id -> app_user.id, status, title, summary, problem_plain,
  implementing_org, scope_geojson, population_estimate, population_source,
  budget_one_time_usd, budget_annual_usd, funding_notes,
  legal_citation, needs_new_authority,
  equity_beneficiaries, equity_cost_bearers,
  safeguards_rollback_trigger, safeguards_rollback_steps, sunset_date,
  privacy_notes, retention_days, created_at, updated_at
)

proposal_topic(proposal_id -> proposal.id, domain_id -> domain.id, program_id -> program.id?, is_primary)
proposal_metric(id, proposal_id -> proposal.id, name, unit, baseline_val, baseline_year, baseline_source, target_val, deadline)
proposal_action(id, proposal_id -> proposal.id, ordinal, text)
proposal_budget_item(id, proposal_id -> proposal.id, item_name, one_time_usd, annual_usd, confidence)
```

> See `db/schema.ts` in the repo; the Drizzle tables match this shape.

---

## 5) Local Dev Setup

**Environment**

```
DATABASE_URL=postgres://postgres:postgres@localhost:54322/postgres?sslmode=disable
```

**drizzle.config.ts**

```ts
import { config } from "dotenv";
import { defineConfig } from "drizzle-kit";
config({ path: ".env.local" });

export default defineConfig({
  schema: "./db/schema/index.ts",
  out: "./db/migrations",
  dialect: "postgresql",
  dbCredentials: { url: process.env.DATABASE_URL! },
});
```

**Scripts**

```json
{
  "scripts": {
    "db:gen": "drizzle-kit generate",
    "db:push": "drizzle-kit push",
    "db:studio": "drizzle-kit studio",
    "db:seed": "tsx db/seed.ts"
  }
}
```

**Seed personas + sample proposal**  
Creates `alice`, `bob`, a `Transportation > Vision Zero` topic, and a “Safe Crosswalks” sample proposal with metrics and budget items. (See `db/seed.ts`)

---

## 6) Voting Mechanisms Package

A core package within the repo for experimenting with and simulating different voting methods. The design separates **ballot types** (how voters express preferences) from **resolution methods** (how ballots are tallied to determine outcomes).

### Ballot Types

- **Binary (Yes/No):** Approve or reject a single proposal
- **Single Choice (1 of N):** Select one option from multiple candidates/proposals
- **Approval:** Approve any number of options (no ranking)
- **Score/Range:** Rate each option on a numeric scale (e.g., 0–5)
- **Ranked:** Order options by preference (full or partial ranking)

### Resolution Methods

- **Plurality (FPTP):** Highest vote count wins (single choice ballots)
- **Approval Tally:** Highest approval count wins
- **Score Tally:** Highest average/sum score wins
- **Instant Runoff (IRV):** Eliminate lowest-ranked, redistribute until majority
- **Borda Count:** Points based on rank position
- **Condorcet Methods:** Pairwise comparison; Ranked Pairs for cycle resolution
- **Quadratic Voting:** Voters allocate credits; cost scales quadratically

### Implementation Phases

**Phase A — Core Voting Library**
- Define ballot type interfaces and resolution method functions
- Pure TypeScript with no database dependencies
- Unit tests for each method with known election scenarios

**Phase B — Simulated Elections**
- Create simulated voter populations with preference distributions
- Run elections across ballot/method combinations
- Visualize results and compare method behaviors

**Phase C — Simulated Users**
- Generate user personas with defined preference profiles
- Simulate strategic vs sincere voting behavior
- Model delegation chains and their effects

**Phase D — AI Agent Voting**
- Train agents to learn user preferences from past votes
- Agent recommends or casts votes on user's behalf
- Confidence thresholds and override mechanisms
- Measure agent accuracy in maximizing user utility

---

## 7) Roadmap (phased)

### Phase 0 — MVP (this doc)

- Local Supabase, Drizzle models, minimal CRUD UI
- Proposal form with validation; list + detail pages
- Simulated users only

### Phase 1 — Voting Mechanisms Package

- Implement core voting library (see §6 Phase A–B)
- Integrate with proposal system for mock elections

### Phase 2 — AI Assistance (opt‑in recommendations)

- Local preference store (per topic)
- Agent suggests rankings/approvals + **confidence**
- Pre‑commit preview; easy override; learning from overrides
- Builds on voting mechanisms package (§6 Phase D)

### Phase 3 — Voting Protocols & Delegation

- Topic‑scoped **delegation**; basic explorer of delegation graph
- Full integration of all ballot types and resolution methods

### Phase 4 — Privacy & Security

- Eligibility via verifiable credentials (zk‑eligibility POC)
- Commit–reveal or encrypted ballots + threshold tally
- Public proofs/commitments (ballot secrecy preserved)
- Incident response, audits, bug bounty

---

## 8) Multi‑Option & Continuous Policy Choices (design notes)

- Never vote over an “infinite” space directly. **Synthesize** a small, representative **menu** first (Pareto frontier points + Status Quo), then use **Condorcet** with **Ranked Pairs** to pick a winner.
- For single‑parameter choices with likely single‑peaked preferences (e.g., a rate/limit), consider the **median** mechanism.
- For boolean choices or mutually exclusive variants, run **Approval** first to filter, then Condorcet among finalists + Status Quo.

---

## 9) Principles & Non‑Goals

**Principles**

- **Subsidiarity‑first**: decide as locally as practical.
- **Plain language** by default; numbers beat adjectives.
- **Open processes** (code/specs/data) with **private ballots**.
- **Small, composable steps**; ship working slices early.

**Non‑Goals (MVP)**

- Perfect identity, cryptography, or fairness guarantees on day one.
- Production infra. This is a local prototype to validate UX and data.

---

## 10) Glossary (quick)

- **Approval voting:** Voters approve any number of options; highest approval wins.
- **Ballot type:** The format for expressing voter preferences (binary, single choice, ranked, scored, etc.).
- **Borda count:** Ranked voting where candidates receive points based on position (n-1 for 1st, n-2 for 2nd, etc.).
- **Condorcet method:** Candidate that would beat every other in head‑to‑head wins.
- **Delegation (topic‑scoped):** You pick a trusted person for specific Domains/Programs.
- **Instant Runoff (IRV):** Ranked voting with elimination rounds; lowest candidate eliminated and votes redistributed.
- **Plurality (FPTP):** First-past-the-post; candidate with most votes wins regardless of majority.
- **Quadratic voting:** Voters allocate credits across options; cost to add votes scales quadratically (1, 4, 9, 16...).
- **Ranked Pairs:** A Condorcet completion rule to resolve cycles deterministically.
- **Resolution method:** Algorithm that processes ballots to determine election outcome.
- **Score/Range voting:** Voters rate each option on a scale; highest average or sum wins.
- **Subsidiarity:** Make decisions at the lowest competent level.
- **Synthesis (menu):** Turning continuous policy spaces into a small, auditable set of concrete options before voting.

---

## 11) Next Steps (action list)

- [x] Push current Drizzle schema & run seeds
- [x] Build minimal form page (Zod + React Hook Form) → `proposals` + children
- [ ] List page with quick filters (Domain/Program/Status)
- [ ] Detail page with metrics table & budget roll‑up
- [ ] Add simple "verifiability score" badge (filled metrics + scope + budget)
- [x] Create `voting/` Python package with ballot type interfaces and core types
- [x] Implement plurality and approval ballot types + resolution methods with tests
- [x] Implement ranked choice ballot (dual list+dict representation) with IRV, Borda, and Condorcet/Ranked Pairs resolvers
- [x] Implement score ballot type (0-10) + score tally resolution method
- [ ] Implement quadratic voting ballot type + resolution method
- [ ] Build election simulation runner for comparing methods
- [ ] Create simulated voter populations with preference distributions

---

**Contact & Maintainer:** Benjamin Willcox (local prototype).  
**Status:** Active (MVP).  
**License:** TBD (private during prototype).
