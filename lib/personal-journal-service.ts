import { NextResponse } from "next/server";
import { z } from "zod";
import { isJournalLoopbackHost } from "@/lib/personal-journal-local";
import { JournalStoreError } from "@/lib/personal-journal-store";
import type { JournalEntry, JournalForecastSet, JournalMeasure, JournalPrediction, JournalQuestion } from "@/lib/personal-journal-types";

type Completed = Extract<JournalEntry, { status: "revealed" }>;
export const nonblank = (limit: number) => z.string().trim().min(1).max(limit);
export const revision = z.number().int().nonnegative().safe();

export function reply(body: unknown, status = 200) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "private, no-store" } });
}

export function failed(error: unknown) {
  if (error instanceof JournalStoreError) return reply({ error: error.message }, error.status);
  return reply({ error: "The private journal could not complete this request. Please retry." }, 500);
}

export async function requestData(request: Request) {
  if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
    throw new JournalStoreError(415, "Send the journal entry as JSON.");
  }
  try {
    return await request.json();
  } catch {
    throw new JournalStoreError(400, "The journal request contains invalid JSON.");
  }
}

function pastDecision(entry: Completed) {
  const { id, measure, vote, reasoning, followUp } = entry;
  return {
    id, measure, vote, reasoning,
    ...(followUp?.status === "answered" && {
      clarification: { question: followUp.question.prompt, kind: followUp.question.kind, answer: followUp.answer },
    }),
  };
}

async function localModel<T>(operation: "forecast" | "paired" | "profile" | "question", payload: unknown, schema: z.ZodType<T>): Promise<T> {
  const base = new URL(process.env.PERSONAL_JOURNAL_API_ORIGIN ?? "http://127.0.0.1:8035");
  if (!isJournalLoopbackHost(base.host) || base.protocol !== "http:" || base.username || base.password) {
    throw new JournalStoreError(503, "The journal requires a local forecast service.");
  }
  const token = process.env.PERSONAL_JOURNAL_API_TOKEN;
  if (!token) throw new JournalStoreError(503, "Start the private journal using npm run journal.");
  try {
    const response = await fetch(new URL(`/api/preferences/journal/${operation}`, base), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Journal-Token": token },
      body: JSON.stringify(payload),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(120_000),
    });
    if (response.ok) {
      const result = schema.safeParse(await response.json());
      if (result.success) return result.data;
    }
  } catch {
    // Local provider errors can contain participant text.
  }
  throw new JournalStoreError(503, "The local preference service is unavailable. Please retry.");
}

const predictionSchema = z.object({
  choice: z.enum(["yes", "no"]), probabilityYes: z.number().min(0).max(1),
  model: nonblank(256), explanation: nonblank(4000), historyCount: z.number().int().nonnegative(),
}).strict();

const pairedSchema = z.object({
  reasoning: predictionSchema.extend({ model: z.literal("reasoning-examples-v1") }),
  baseline: predictionSchema.extend({ model: z.literal("outcome-wording-v1") }),
  withoutReasoning: predictionSchema.extend({ model: z.literal("reasoning-examples-v1-without-reasoning") }),
}).strict();

export function forecast(id: string, measure: JournalMeasure, history: Completed[], paired = false): Promise<JournalPrediction | JournalForecastSet> {
  const request = { id, measure, history: history.map(pastDecision) };
  return paired ? localModel("paired", request, pairedSchema) : localModel("forecast", request, predictionSchema);
}

const profileSchema = z.object({
  model: nonblank(256), evidenceCount: z.number().int().nonnegative(),
  facets: z.array(z.object({ label: nonblank(1000), evidenceIds: z.array(z.string().uuid()).min(1) })),
});

export async function preferenceProfile(entries: JournalEntry[]) {
  const history = entries.filter((entry): entry is Completed => entry.status === "revealed")
    .sort((a, b) => a.votedAt.localeCompare(b.votedAt) || a.id.localeCompare(b.id));
  const profile = await localModel("profile", { history: history.map(pastDecision) }, profileSchema);
  const sources = new Set(history.map(entry => entry.id));
  if (profile.evidenceCount !== history.length || profile.facets.some(facet => facet.evidenceIds.some(id => !sources.has(id)))) {
    throw new JournalStoreError(502, "The profile could not be matched to its journal entries.");
  }
  return profile;
}

const questionSchema = z.object({ question: z.object({
  prompt: nonblank(2000), trigger: z.enum(["miss", "uncertain"]),
  kind: z.enum(["contrast", "counterfactual", "weight"]), referenceId: z.string().uuid().nullish(),
}).nullable() });

export async function chooseQuestion(entry: Completed, history: Completed[]): Promise<JournalQuestion | null> {
  const target = { ...pastDecision(entry), prediction: entry.prediction };
  const { question } = await localModel("question", { target, history: history.map(pastDecision) }, questionSchema);
  if (!question) return null;
  const { prompt, trigger, kind, referenceId } = question;
  if (referenceId && !history.some(source => source.id === referenceId)) {
    throw new JournalStoreError(502, "The comparison measure could not be found in the forecast history.");
  }
  return { prompt, trigger, kind, ...(referenceId && { referenceId }) };
}
