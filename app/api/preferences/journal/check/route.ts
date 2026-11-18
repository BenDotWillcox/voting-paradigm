import { z } from "zod";
import { journalRequestAllowed } from "@/lib/personal-journal-local";
import { failed, reply, requestData } from "@/lib/personal-journal-service";
import { startCheck } from "@/lib/personal-journal-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    if (!z.object({}).strict().safeParse(await requestData(request)).success) {
      return reply({ error: "Start the check using the current journal evidence." }, 400);
    }
    return reply({ check: await startCheck() });
  } catch (error) {
    return failed(error);
  }
}
