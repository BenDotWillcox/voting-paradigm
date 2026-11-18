import { NextResponse } from "next/server";
import { z } from "zod";
import { isJournalLoopbackHost, journalRequestAllowed } from "@/lib/personal-journal-local";
import { JournalStoreError, listEntries, lockEntry, recordVote } from "@/lib/personal-journal-store";
import type { JournalEntry, JournalMeasure, JournalPrediction } from "@/lib/personal-journal-types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const nonblank = (limit: number) => z.string().trim().min(1).max(limit);
const vote = z.enum(["yes", "no"]);
const measureSchema = z.object({
  title: nonblank(300),
  sourceUrl: nonblank(2048).url().refine(value => /^https?:\/\//i.test(value)),
  text: nonblank(30000),
  yesMeaning: nonblank(3000),
  noMeaning: nonblank(3000),
  familiar: z.boolean(),
}).strict();
const lockRequest = z.object({ id: z.string().uuid(), measure: measureSchema }).strict();
const voteRequest = z.object({ id: z.string().uuid(), vote, reasoning: nonblank(10000) }).strict();
const predictionSchema = z.object({
  choice: vote,
  probabilityYes: z.number().min(0).max(1),
  model: nonblank(256),
  explanation: nonblank(4000),
  historyCount: z.number().int().nonnegative(),
}).strict();

function reply(body: unknown, status = 200) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "private, no-store" } });
}

function failed(error: unknown) {
  if (error instanceof JournalStoreError) return reply({ error: error.message }, error.status);
  return reply({ error: "The private journal could not complete this request. Your saved records are still available for retry." }, 500);
}

type CompletedEntry = Extract<JournalEntry, { status: "revealed" }>;

async function forecast(id: string, measure: JournalMeasure, history: CompletedEntry[]): Promise<JournalPrediction> {
  const base = new URL(process.env.PERSONAL_JOURNAL_API_ORIGIN ?? "http://127.0.0.1:8035");
  if (!isJournalLoopbackHost(base.host) || base.protocol !== "http:" || base.username || base.password) {
    throw new JournalStoreError(503, "The journal requires a local forecast service.");
  }
  const token = process.env.PERSONAL_JOURNAL_API_TOKEN;
  if (!token) throw new JournalStoreError(503, "Start the private journal using npm run journal.");
  try {
    const response = await fetch(new URL("/api/preferences/journal/forecast", base), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Journal-Token": token },
      body: JSON.stringify({
        id, measure,
        history: history.map(entry => ({ measure: entry.measure, vote: entry.vote, reasoning: entry.reasoning })),
      }),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(120_000),
    });
    if (response.ok) {
      const result = predictionSchema.safeParse(await response.json());
      if (result.success) return result.data;
    }
  } catch {
    // Never send provider errors, the packet or previous votes in an HTTP error body.
  }
  throw new JournalStoreError(503, "The forecast service could not lock a prediction. Check the local service and retry.");
}

async function requestData(request: Request) {
  if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
    throw new JournalStoreError(415, "Send the journal entry as JSON.");
  }
  try {
    return await request.json();
  } catch {
    throw new JournalStoreError(400, "The journal request contains invalid JSON.");
  }
}

export async function GET(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    return reply({ entries: await listEntries() });
  } catch (error) {
    return failed(error);
  }
}

export async function POST(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    const input = lockRequest.safeParse(await requestData(request));
    if (!input.success) return reply({ error: "Enter a title, source URL, measure text, both outcomes and your familiarity with the measure." }, 400);
    const { id, measure } = input.data;
    const entry = await lockEntry(id, measure, (packet, history) => forecast(id, packet, history));
    return reply({ entry });
  } catch (error) {
    return failed(error);
  }
}

export async function PUT(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    const input = voteRequest.safeParse(await requestData(request));
    if (!input.success) return reply({ error: "Select Yes or No and enter your reasoning before revealing the prediction." }, 400);
    const { id, vote: choice, reasoning } = input.data;
    return reply({ entry: await recordVote(id, choice, reasoning) });
  } catch (error) {
    return failed(error);
  }
}
