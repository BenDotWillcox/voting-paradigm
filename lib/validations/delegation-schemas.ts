import { z } from "zod";

/**
 * Zod schemas for the liquid democracy routes (`/api/delegation`). They
 * mirror `api/schemas/delegation.py`: requests are checked before they leave
 * the server action, responses when they come back.
 */

export const MAX_VIEWER_DELEGATIONS = 12;
export const MAX_CATEGORY_LENGTH = 200;

const categoryTextSchema = z
  .string()
  .trim()
  .min(1, "Write a category first.")
  .max(MAX_CATEGORY_LENGTH, `Keep a category under ${MAX_CATEGORY_LENGTH} characters.`);

const personRefSchema = z.string().min(1, "Choose a person.").max(40);

export const viewerDelegationSchema = z.object({
  category: categoryTextSchema,
  delegate: personRefSchema,
});

const viewerDelegationsSchema = z
  .array(viewerDelegationSchema)
  .max(MAX_VIEWER_DELEGATIONS, `You can hand over at most ${MAX_VIEWER_DELEGATIONS} categories.`);

const thresholdSchema = z.number().min(0).max(1);

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------

export const validateDelegationRequestSchema = z.object({
  viewer_delegations: viewerDelegationsSchema,
  proposed: viewerDelegationSchema,
  threshold: thresholdSchema,
});

export const categoryJudgmentsRequestSchema = z.object({
  category: categoryTextSchema,
  held: z.array(categoryTextSchema).max(MAX_VIEWER_DELEGATIONS),
});

export const resolveBallotPaperRequestSchema = z.object({
  ballot_paper: z.string().min(1).max(80),
  viewer_delegations: viewerDelegationsSchema,
  viewer_votes: z.record(z.string().max(80), z.string().max(80)),
  threshold: thresholdSchema,
  tiebreak_seed: z.number().int().min(0).max(2 ** 31 - 1),
});

// ---------------------------------------------------------------------------
// GET /scenario
// ---------------------------------------------------------------------------

export const categorySchema = z.object({
  id: z.string(),
  text: z.string(),
  in_pool: z.boolean(),
  inside: z.array(z.string()),
});

const optionSchema = z.object({ id: z.string(), name: z.string() });

const questionSchema = z.object({
  id: z.string(),
  title: z.string(),
  summary: z.string(),
  options: z.array(optionSchema),
});

export const scenarioResponseSchema = z.object({
  scenario: z.string(),
  model: z.string(),
  seed: z.number(),
  threshold: z.number(),
  viewer: z.string(),
  live_judgments: z.boolean(),
  jurisdictions: z.array(z.object({ id: z.string(), name: z.string() })),
  persons: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      residences: z.array(z.string()),
      behaviour: z.string().nullable(),
      well_known_for: z.array(z.string()),
    })
  ),
  categories: z.array(categorySchema),
  delegations: z.array(
    z.object({ delegator: z.string(), category: z.string(), delegate: z.string() })
  ),
  ballot_papers: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      jurisdiction: z.string(),
      eligible_voters: z.number(),
      questions: z.array(questionSchema),
    })
  ),
});

// ---------------------------------------------------------------------------
// POST /delegations/validate
// ---------------------------------------------------------------------------

export const validateDelegationResponseSchema = z.object({
  accepted: z.boolean(),
  reason: z.string().nullable(),
  chain: z.array(z.string()).nullable(),
  category: categorySchema,
  judged: z.boolean(),
  warnings: z.array(
    z.object({ ballot_paper: z.string(), question_id: z.string(), title: z.string() })
  ),
});

// ---------------------------------------------------------------------------
// POST /judgments
// ---------------------------------------------------------------------------

const judgmentCountsSchema = z.object({
  recorded: z.number(),
  fetched: z.number(),
  missing: z.number(),
});

export const categoryJudgmentsResponseSchema = z.object({
  category: categorySchema,
  model: z.string(),
  live: z.boolean(),
  judgments: judgmentCountsSchema,
  nesting: judgmentCountsSchema,
  inside: z.array(z.string()),
  contains: z.array(z.string()),
  scores: z.array(
    z.object({
      ballot_paper: z.string(),
      question_id: z.string(),
      title: z.string(),
      probability: z.number().nullable(),
    })
  ),
  failures: z.array(z.string()),
});

// ---------------------------------------------------------------------------
// POST /resolve
// ---------------------------------------------------------------------------

const tallySchema = z.object({
  winners: z.array(z.string()),
  counts: z.record(z.number()),
  abstentions: z.number(),
  total_ballots: z.number(),
  tiebreak_applied: z.boolean(),
});

const receiptSchema = z.object({
  outcome: z.enum([
    "direct_vote",
    "no_delegations",
    "router_unavailable",
    "none_available",
    "delegated",
  ]),
  threshold: z.number(),
  scores: z.array(
    z.object({ category: z.string(), text: z.string(), probability: z.number() })
  ),
  category: z.string().nullable(),
  set_aside: z.array(z.string()),
  chain: z.array(z.string()),
  resolver: z.string(),
  kept_because: z.enum([
    "direct_vote",
    "no_delegations",
    "router_unavailable",
    "none_available",
    "loop",
  ]),
  loop: z.array(z.string()).nullable(),
  choice: z.string().nullable(),
});

const questionResultSchema = z.object({
  question_id: z.string(),
  title: z.string(),
  delegated: tallySchema,
  direct: tallySchema,
  winner_changed: z.boolean(),
  metrics: z.object({
    voters: z.number(),
    delegated_share: z.number(),
    largest_share: z.number(),
    largest_resolver: z.string().nullable(),
    gini: z.number(),
    chain_lengths: z.array(z.object({ hops: z.number(), votes: z.number() })),
    loops: z.array(z.array(z.string())),
  }),
  receipt: receiptSchema.nullable(),
  inbox: z.object({
    votes_for_others: z.number(),
    held: z.array(z.object({ voter: z.string(), home: z.string().nullable() })),
    answered: z.boolean(),
  }),
});

export const resolveBallotPaperResponseSchema = z.object({
  scenario: z.string(),
  model: z.string(),
  ballot_paper: z.string(),
  jurisdiction: z.string(),
  viewer_eligible: z.boolean(),
  threshold: z.number(),
  tiebreak_seed: z.number(),
  unjudged_categories: z.array(z.string()),
  questions: z.array(questionResultSchema),
});
