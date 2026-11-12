import { NextResponse } from "next/server";
import { resolveProfileAction } from "@/actions/methods-actions";

export const runtime = "nodejs";

/** Keep validation and Python calculation in the existing read-only action. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ isSuccess: false, message: "Send a valid electorate." }, { status: 400 });
  }
  return NextResponse.json(await resolveProfileAction(body));
}
