import { z } from "zod";
import { journalRequestAllowed } from "@/lib/personal-journal-local";
import { chooseQuestion, failed, nonblank, reply, requestData, revision } from "@/lib/personal-journal-service";
import { respondToFollowUp, suggestFollowUp } from "@/lib/personal-journal-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const entry = z.object({ id: z.string().uuid(), expectedRevision: revision }).strict();
const response = entry.extend({ expectedPrompt: nonblank(2000) });
const followUpRequest = z.discriminatedUnion("action", [
  entry.extend({ action: z.literal("suggest") }),
  response.extend({ action: z.literal("skip") }),
  response.extend({ action: z.literal("answer"), answer: nonblank(10000) }),
]);

export async function POST(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    const input = followUpRequest.safeParse(await requestData(request));
    if (!input.success) return reply({ error: "Check the follow-up request and enter an answer before saving." }, 400);
    const action = input.data;
    const saved = action.action === "suggest"
      ? await suggestFollowUp(action.id, action.expectedRevision, chooseQuestion)
      : await respondToFollowUp(action.id, action.expectedRevision, action.expectedPrompt, action.action === "skip" ? null : action.answer);
    return reply({ entry: saved });
  } catch (error) {
    return failed(error);
  }
}
