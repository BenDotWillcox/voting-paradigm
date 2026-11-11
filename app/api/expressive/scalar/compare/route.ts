import { NextResponse } from "next/server";
import { ExpressivePreviewError } from "@/lib/expressive-api";
import { compareScalarBallots } from "@/lib/expressive-comparison-api";
import { scalarComparisonRequestSchema } from "@/lib/validations/expressive-comparison";

export const runtime = "nodejs";

/** Compare a submitted pair of ballots with a deterministic authored electorate. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ message: "Send valid comparison ballots." }, { status: 400 });
  }
  const parsed = scalarComparisonRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ message: parsed.error.issues[0]?.message || "Check your ballots." }, { status: 422 });
  }
  try {
    return NextResponse.json(await compareScalarBallots(parsed.data));
  } catch (error) {
    if (error instanceof ExpressivePreviewError) {
      return NextResponse.json({ message: error.message }, { status: error.status });
    }
    return NextResponse.json({ message: "The ballots could not be compared. Please try again." }, { status: 500 });
  }
}
