import { z } from "zod";
import { scalarPreviewRequestSchema } from "@/lib/validations/expressive-scalar";

const rate = z.number().finite().min(0).max(100);
const score = z.number().finite().min(0).max(1);
const count = z.number().int().min(0).max(100);
const vote = z.enum(["yes", "no"]);
const curveVote = z.enum(["yes", "no", "abstain"]);
const offeredRate = z.union([z.literal(4.55), z.literal(4.4)]);

export const scalarComparisonRequestSchema = z.object({
  ballot: scalarPreviewRequestSchema,
  binary_vote: vote,
}).strict();

const ballotSchema = z.object({
  ideal: rate,
  lower_half_width: z.number().finite().positive().max(100),
  upper_half_width: z.number().finite().positive().max(100),
  approval_min: rate,
  approval_max: rate,
}).strict().refine((ballot) => ballot.approval_min <= ballot.ideal && ballot.ideal <= ballot.approval_max);

const voterSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  ballot: ballotSchema,
  binary_vote: curveVote,
  curve_vote: curveVote,
  status_quo_score: score,
  proposal_score: score,
}).strict();

const pointSchema = z.object({
  rate,
  mean_score: score,
  approval_count: count,
  user_score: score,
  user_approved: z.boolean(),
  prefer_this: count,
  prefer_binary: count,
  indifferent: count,
}).strict();

export const scalarComparisonResponseSchema = z.object({
  model: z.literal("scalar-comparison-v4"),
  status_quo: z.literal(4.55),
  proposal: z.literal(4.4),
  electorate_size: z.literal(100),
  candidate_step: z.literal(0.05),
  score_tie_tolerance: z.literal(1e-12),
  user_binary_vote: vote,
  user_curve_vote: curveVote,
  electorate: z.object({
    id: z.string().min(1),
    label: z.string().min(1),
    description: z.string().min(1),
    seed: z.number().int().nonnegative().safe(),
    voters: z.array(voterSchema).length(100),
  }).strict(),
  binary: z.object({
    yes: count,
    no: count,
    abstain: count,
    passed: z.boolean(),
    outcome_rate: offeredRate,
  }).strict(),
  pair: z.object({
    status_quo_mean: score,
    proposal_mean: score,
    winner_rates: z.array(offeredRate).min(1).max(2),
  }).strict(),
  winner_rates: z.array(rate).min(1).max(2001),
  max_mean_score: score,
  points: z.array(pointSchema).length(2001),
}).strict().superRefine((result, context) => {
  const fail = (message: string) => context.addIssue({ code: z.ZodIssueCode.custom, message });
  const close = (a: number, b: number) => Math.abs(a - b) <= result.score_tie_tolerance;
  const sameRates = (a: number[], b: number[]) => a.length === b.length && new Set(a).size === a.length && a.every((value) => b.includes(value));
  const derivedVote = (proposal: number, statusQuo: number) => close(proposal, statusQuo) ? "abstain" : proposal > statusQuo ? "yes" : "no";
  const { voters } = result.electorate;
  const { binary, pair, points } = result;
  // Array lengths are already schema errors; avoid indexing a malformed grid.
  if (voters.length !== result.electorate_size || points.length !== 2001) return;
  if (new Set(voters.map((voter) => voter.id)).size !== result.electorate_size) fail("Each voter must have a unique identity.");
  const users = voters.filter((voter) => voter.id === "you");
  if (users.length !== 1) fail("The electorate must contain exactly one submitted voter.");
  for (const voter of voters) {
    if (voter.curve_vote !== derivedVote(voter.proposal_score, voter.status_quo_score)) fail("A curve-derived answer disagrees with its two scores.");
    if (voter.id !== "you" && voter.binary_vote !== voter.curve_vote) fail("A synthetic voter's answer must follow their curve.");
  }
  for (const answer of ["yes", "no", "abstain"] as const) {
    if (binary[answer] !== voters.filter((voter) => voter.binary_vote === answer).length) fail("The binary tally must count the displayed voters.");
  }
  if (binary.yes + binary.no + binary.abstain !== result.electorate_size) fail("Electorate counts do not reconcile.");
  if (binary.passed !== (binary.yes > binary.no) || binary.outcome_rate !== (binary.passed ? result.proposal : result.status_quo)) fail("Binary outcome does not match its tally.");
  if (!close(pair.status_quo_mean, voters.reduce((total, voter) => total + voter.status_quo_score, 0) / result.electorate_size) ||
    !close(pair.proposal_mean, voters.reduce((total, voter) => total + voter.proposal_score, 0) / result.electorate_size)) fail("Pair averages must summarize the displayed voters.");
  const pairVote = derivedVote(pair.proposal_mean, pair.status_quo_mean);
  const pairWinners = pairVote === "abstain" ? [result.status_quo, result.proposal] : [pairVote === "yes" ? result.proposal : result.status_quo];
  if (!sameRates(pair.winner_rates, pairWinners)) fail("Pair winners do not match the average scores.");

  const user = users[0];
  if (user && (user.binary_vote !== result.user_binary_vote || user.curve_vote !== result.user_curve_vote)) fail("The submitted voter's answers must be preserved.");
  points.forEach((point, index) => {
    if (Math.abs(point.rate - index / 20) > 1e-10) fail("Candidate grid must run from 0 to 100 in 0.05-point increments.");
    if (point.prefer_this + point.prefer_binary + point.indifferent !== result.electorate_size) fail("Direct preference counts do not reconcile.");
    const approvedCount = voters.filter((voter) => point.rate >= voter.ballot.approval_min && point.rate <= voter.ballot.approval_max).length;
    if (point.approval_count !== approvedCount) fail("Approval counts must summarize the displayed intervals.");
    if (user) {
      const approved = point.rate >= user.ballot.approval_min && point.rate <= user.ballot.approval_max;
      if (point.user_approved !== approved || (!approved && point.user_score !== 0)) fail("User approval must match the submitted interval.");
    }
  });
  const maximum = Math.max(...points.map((point) => point.mean_score));
  const winners = points.filter((point) => close(point.mean_score, maximum)).map((point) => point.rate);
  if (!close(result.max_mean_score, maximum) || !sameRates(result.winner_rates, winners)) fail("All highest-scoring grid rates must be reported.");

  const quoPoint = points[Math.round(result.status_quo / result.candidate_step)];
  const proposalPoint = points[Math.round(result.proposal / result.candidate_step)];
  if (!close(quoPoint.mean_score, pair.status_quo_mean) || !close(proposalPoint.mean_score, pair.proposal_mean)) fail("Pair averages must agree with their candidate-grid entries.");
  if (user && (!close(quoPoint.user_score, user.status_quo_score) || !close(proposalPoint.user_score, user.proposal_score))) fail("User pair scores must agree with the candidate grid.");
  const binaryPoint = points[Math.round(binary.outcome_rate / result.candidate_step)];
  if (binaryPoint.prefer_this !== 0 || binaryPoint.prefer_binary !== 0 || binaryPoint.indifferent !== result.electorate_size) fail("Comparing the binary outcome to itself must leave every voter indifferent.");
});
