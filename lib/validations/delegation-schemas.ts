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

/** One vote: a single option, every option in order, or the approved options. */
export const choiceSchema = z.array(z.string().max(80)).max(12);
const ballotTypeSchema = z.enum(["single_choice", "ranked", "approval"]);
const methodSchema = z.enum(["plurality", "irv", "approval"]);

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
  viewer_votes: z.record(z.string().max(80), choiceSchema),
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

const optionSchema = z.object({
  id: z.string(),
  name: z.string(),
  note: z.string().nullable(),
});

const questionSchema = z.object({
  id: z.string(),
  label: z.string(),
  kind: z.string(),
  title: z.string(),
  summary: z.string(),
  ballot_type: ballotTypeSchema,
  method: methodSchema,
  wording: z.string(),
  fiscal: z.string(),
  placed_by: z.string(),
  argument_for: z.string(),
  argument_against: z.string(),
  site: z.array(z.number()).nullable(),
  options: z.array(optionSchema),
});

const personSchema = z.object({
  id: z.string(),
  name: z.string(),
  username: z.string(),
  home: z.string().nullable(),
  residences: z.array(z.string()),
  behaviour: z.string().nullable(),
  well_known_for: z.array(z.string()),
  location: z.array(z.number()).nullable(),
});

const statusSchema = z.enum(["open", "closed"]);

export const scenarioResponseSchema = z.object({
  scenario: z.string(),
  city: z.string(),
  provisional: z.array(z.string()),
  model: z.string(),
  seed: z.number(),
  threshold: z.number(),
  viewer: z.string(),
  live_judgments: z.boolean(),
  jurisdictions: z.array(z.object({ id: z.string(), name: z.string() })),
  persons: z.array(personSchema),
  categories: z.array(categorySchema),
  delegations: z.array(
    z.object({ delegator: z.string(), category: z.string(), delegate: z.string() })
  ),
  viewer_delegations: z.array(viewerDelegationSchema),
  viewer_changes: z.array(
    z.object({
      day: z.number(),
      category: z.string(),
      before: z.string().nullable(),
      after: z.string().nullable(),
    })
  ),
  ballot_papers: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      jurisdiction: z.string(),
      closes_in_days: z.number(),
      opens_in_days: z.number(),
      status: statusSchema,
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
  limited: z.boolean(),
  failures: z.array(z.string()),
});

// ---------------------------------------------------------------------------
// POST /resolve
// ---------------------------------------------------------------------------

const tallySchema = z.object({
  method: methodSchema,
  winners: z.array(z.string()),
  counts: z.record(z.number()),
  rounds: z.array(
    z.object({
      round: z.number(),
      counts: z.record(z.number()),
      eliminated: z.array(z.string()),
      exhausted: z.number(),
    })
  ),
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
  choice: choiceSchema.nullable(),
  resolver_votes_in_days: z.number().nullable(),
});

const questionResultSchema = z.object({
  question_id: z.string(),
  title: z.string(),
  ballot_type: ballotTypeSchema,
  cast_so_far: z.number(),
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
  status: statusSchema,
  closes_in_days: z.number(),
  viewer_eligible: z.boolean(),
  threshold: z.number(),
  tiebreak_seed: z.number(),
  unjudged_categories: z.array(z.string()),
  questions: z.array(questionResultSchema),
});

// ---------------------------------------------------------------------------
// GET /people/{person_id}
// ---------------------------------------------------------------------------

export const personIdSchema = z.string().min(1).max(40);

export const profileResponseSchema = z.object({
  person: personSchema,
  stats: z.object({
    votes_issued: z.number(),
    voted_personally: z.number(),
    delegated: z.number(),
    abstained: z.number(),
    delegation_rate: z.number().nullable(),
    categories_handed_over: z.number(),
    delegators: z.number(),
    categories_received: z.number(),
    votes_decided_for_others: z.number(),
    most_votes_held: z.number(),
    largest_share: z.number(),
  }),
  delegations: z.array(z.object({ category: z.string(), delegate: z.string() })),
  received: z.array(z.object({ delegator: z.string(), category: z.string() })),
  history: z.array(
    z.object({
      ballot_paper: z.string(),
      paper_title: z.string(),
      jurisdiction: z.string(),
      closed_days_ago: z.number(),
      question_id: z.string(),
      label: z.string(),
      title: z.string(),
      summary: z.string(),
      ballot_type: ballotTypeSchema,
      issued: z.boolean(),
      how: z.enum(["voted", "delegated", "abstained"]),
      category: z.string().nullable(),
      chain: z.array(z.string()),
      resolver: z.string(),
      choice: choiceSchema.nullable(),
      votes_for_others: z.number(),
      share: z.number(),
      winners: z.array(z.string()),
    })
  ),
});
