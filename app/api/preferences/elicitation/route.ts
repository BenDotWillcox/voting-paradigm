import { NextResponse } from "next/server";
import {
  elicitationRequestSchema,
  elicitationResponseSchema,
} from "@/lib/validations/elicitation-schemas";

export const runtime = "nodejs";

const noStore = { "Cache-Control": "no-store" };

/** Validate an unsaved self-report: no inference or caller-selected upstream. */
export async function POST(request: Request) {
  const input = elicitationRequestSchema.safeParse(
    await request.json().catch(() => null)
  );
  if (!input.success) {
    return NextResponse.json(
      { error: "Send the spectrum bank version and up to four responses." },
      { status: 400, headers: noStore }
    );
  }

  const baseUrl = process.env.PREFERENCES_API_URL ||
    process.env.NEBULA_API_URL || "http://localhost:8000";
  try {
    const upstream = await fetch(`${baseUrl.replace(/\/$/, "")}/api/preferences/elicitation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input.data),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(15_000),
    });
    if (!upstream.ok) {
      const invalid = upstream.status === 400 || upstream.status === 422;
      return NextResponse.json(
        { error: invalid
          ? "These responses do not match this session. Restart to begin again."
          : "The session service is unavailable. Your accepted responses are unchanged." },
        { status: invalid ? 400 : 502, headers: noStore }
      );
    }
    const result = elicitationResponseSchema.safeParse(await upstream.json());
    if (
      !result.success ||
      result.data.bank_version !== input.data.bank_version ||
      JSON.stringify(result.data.responses) !== JSON.stringify(input.data.responses)
    ) {
      return NextResponse.json(
        { error: "The session service returned an incompatible result." },
        { status: 502, headers: noStore }
      );
    }
    return NextResponse.json(result.data, { headers: noStore });
  } catch {
    // Keep upstream bodies, infrastructure URLs, and answers out of errors/logs.
    return NextResponse.json(
      { error: "The session service could not be reached. Please try again." },
      { status: 503, headers: noStore }
    );
  }
}
