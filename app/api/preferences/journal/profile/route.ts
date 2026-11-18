import { journalRequestAllowed } from "@/lib/personal-journal-local";
import { failed, preferenceProfile, reply } from "@/lib/personal-journal-service";
import { listEntries } from "@/lib/personal-journal-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!journalRequestAllowed(request)) return reply({ error: "Journal unavailable." }, 404);
  try {
    return reply(await preferenceProfile(await listEntries()));
  } catch (error) {
    return failed(error);
  }
}
