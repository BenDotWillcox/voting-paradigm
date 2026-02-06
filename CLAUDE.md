# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working with the User

The user is highly knowledgeable about voting systems and electoral methods. When implementing voting-related features, ask clarifying questions about desired behavior rather than making assumptions. The user prefers to understand all code before committing, so explain implementation decisions and walk through logic when requested.

## Project Overview

Nebula Civitas is a subsidiarity-first liquid democracy prototype. Users can vote directly, delegate by topic, or (in future phases) use AI recommendations. This MVP focuses on proposal creation and viewing with simulated local users—no real voting or cryptography yet.

## Commands

```bash
npm run dev          # Start Next.js dev server (localhost:3000)
npm run build        # Production build
npm run lint         # ESLint
npm run db:generate  # Generate Drizzle migrations
npm run db:migrate   # Apply migrations
```

Database URL is loaded from `.env.local` (see `drizzle.config.ts`).

## Architecture

**Stack:** Next.js 15 (App Router) + React 18 + TypeScript + Tailwind CSS 4 + PostgreSQL + Drizzle ORM

**Key directories:**
- `app/` — Next.js pages and layouts
- `actions/` — Server Actions returning `ActionResult<T>` with `{ isSuccess, message, data }`
- `db/schema/` — Drizzle table definitions
- `db/queries/` — Database query functions
- `components/forms/` — Form components (proposal form is ~35KB)
- `components/ui/` — shadcn/ui component library (new-york style)
- `lib/validations/` — Zod schemas
- `prompts/` — Project documentation (project-scope.md has full MVP spec)

**Patterns:**
- All mutations use Server Actions with `"use server"` directive
- Forms use React Hook Form + Zod validation
- Path alias: `@/*` maps to project root
- Dark mode via class strategy

## Data Model

Seven tables centered on proposals:
- `users`, `domains`, `programs` — actors and topic taxonomy
- `proposals` — main records with scope, budget totals, governance fields
- `proposal_topics` — links proposals to domains/programs
- `proposal_metrics` — SMART metrics (baseline, target, deadline)
- `proposal_actions` — ordered action steps (3-7 required)
- `proposal_budget_items` — itemized budget with confidence scores

Proposals require: title (≤60 chars), summary (≤280 chars), problem description, 3-7 actions, at least one metric, and topic assignment.

## Domain Concepts

- **Domain/Program:** Two-level topic taxonomy for organizing proposals and scoping delegation
- **Subsidiarity:** Decisions default to the lowest competent jurisdiction level
- **SMART metrics:** Specific, Measurable, Achievable, Relevant, Time-bound proposal outcomes
