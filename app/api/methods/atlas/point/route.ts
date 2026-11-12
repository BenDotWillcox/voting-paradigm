import { NextResponse } from "next/server";
import { resolveAtlasPointAction } from "@/actions/methods-actions";

export const runtime = "nodejs";

/** Count one atlas electorate through the existing validated Python action. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ isSuccess: false, message: "Send a valid atlas point." }, { status: 400 });
  }
  return NextResponse.json(await resolveAtlasPointAction(body));
}
