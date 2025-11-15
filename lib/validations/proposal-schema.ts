import { z } from "zod";

export const proposalMetricSchema = z.object({
  name: z.string().min(1, "Metric name is required"),
  unit: z.string().min(1, "Unit is required"),
  baselineVal: z.string().min(1, "Baseline value is required"),
  baselineYear: z.number().int().optional(),
  baselineSource: z.string().optional(),
  targetVal: z.string().min(1, "Target value is required"),
  deadline: z.string().min(1, "Deadline is required"),
});

export const proposalActionSchema = z.object({
  text: z.string().min(1, "Action text is required"),
});

export const proposalBudgetItemSchema = z.object({
  itemName: z.string().min(1, "Item name is required"),
  oneTimeUsd: z.number().int().min(0).default(0),
  annualUsd: z.number().int().min(0).default(0),
  confidence: z.number().min(0).max(1).default(0.5),
});

export const proposalTopicSchema = z.object({
  domainId: z.string().uuid("Invalid domain"),
  programId: z.string().uuid().optional(),
  isPrimary: z.boolean(),
});

export const proposalFormSchema = z.object({
  // Header
  title: z.string().min(1, "Title is required").max(60, "Title must be ≤60 characters"),
  summary: z.string().min(1, "Summary is required").max(280, "Summary must be ≤280 characters"),
  
  // Essentials
  problemPlain: z.string().min(1, "Problem description is required").max(1500, "Problem must be ≤~250 words"),
  implementingOrg: z.string().optional(),
  
  // Actions (3-7)
  actions: z.array(proposalActionSchema).min(3, "At least 3 actions required").max(7, "Maximum 7 actions allowed"),
  
  // Metrics
  metrics: z.array(proposalMetricSchema).min(1, "At least one metric is required"),
  
  // Scope (optional)
  scopeGeojson: z.string().optional(),
  populationEstimate: z.number().int().positive().optional(),
  populationSource: z.string().optional(),
  
  // Topics
  topics: z.array(proposalTopicSchema).min(1, "At least one topic is required"),
  
  // Budget
  budgetItems: z.array(proposalBudgetItemSchema).min(1, "At least one budget item is required"),
  fundingNotes: z.string().optional(),
  
  // Governance
  legalCitation: z.string().optional(),
  needsNewAuthority: z.boolean(),
  equityBeneficiaries: z.string().optional(),
  equityCostBearers: z.string().optional(),
  safeguardsRollbackTrigger: z.string().optional(),
  safeguardsRollbackSteps: z.string().optional(),
  sunsetDate: z.string().optional(),
  privacyNotes: z.string().optional(),
  retentionDays: z.number().int().positive().optional(),
  
  // Author
  authorId: z.string().uuid("Invalid author"),
});

export type ProposalFormData = z.infer<typeof proposalFormSchema>;
