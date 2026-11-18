import { z } from "zod";
import { journalRequestAllowed } from "@/lib/personal-journal-local";
import { correctEntry, getCheck, listEntries, lockEntry, recordVote } from "@/lib/personal-journal-store";
import { failed, forecast, nonblank, reply, requestData, revision } from "@/lib/personal-journal-service";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const vote = z.enum(["yes", "no"]);
const measureSchema = z.object({
  title: nonblank(300),
  sourceUrl: nonblank(2048).url().refine(value => /^https?:\/\//i.test(value)),
  text: nonblank(30000),
  yesMeaning: nonblank(3000),
  noMeaning: nonblank(3000),
  familiar: z.boolean(),
}).strict();
const packetRequest = z.object({ id: z.string().uuid(), measure: measureSchema }).strict();
const lockRequest = packetRequest.extend({ checkId: z.string().uuid().optional() });
const voteRequest = z.object({ id: z.string().uuid(), vote, reasoning: nonblank(10000), expectedRevision: revision.default(0) }).strict();
const correctionRequest = packetRequest.extend({
  expectedRevision: revision,
  expectedStatus: z.enum(["locked", "revealed"]),
  confirmVote: z.literal(true).optional(),
});
export async function GET(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    const [entries, check] = await Promise.all([listEntries(), getCheck()]);
    return reply({ entries, check });
  } catch (error) {
    return failed(error);
  }
}

export async function POST(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    const input = lockRequest.safeParse(await requestData(request));
    if (!input.success) return reply({ error: "Enter a title, source URL, measure text, both outcomes and your familiarity with the measure." }, 400);
    const { id, measure, checkId } = input.data;
    const entry = await lockEntry(id, measure, (packet, history, paired) => forecast(id, packet, history, paired), checkId);
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
    const { id, vote: choice, reasoning, expectedRevision } = input.data;
    return reply({ entry: await recordVote(id, choice, reasoning, expectedRevision) });
  } catch (error) {
    return failed(error);
  }
}

export async function PATCH(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    const input = correctionRequest.safeParse(await requestData(request));
    if (!input.success) return reply({ error: "Check the corrected measure fields and try again." }, 400);
    const { id, measure, expectedRevision, expectedStatus, confirmVote } = input.data;
    if (expectedStatus === "revealed" && !confirmVote) {
      return reply({ error: "Confirm that your saved vote and reasoning apply to the corrected measure." }, 400);
    }
    const entry = await correctEntry(id, expectedRevision, expectedStatus, measure, (packet, history, paired) => forecast(id, packet, history, paired));
    return reply({ entry });
  } catch (error) {
    return failed(error);
  }
}
