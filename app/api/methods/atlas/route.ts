import { NextResponse } from "next/server";
import { resolveAtlasAction } from "@/actions/methods-actions";

export const runtime = "nodejs";

/** Map a candidate layout through the existing validated Python action. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ isSuccess: false, message: "Send a valid layout." }, { status: 400 });
  }
  return NextResponse.json(await resolveAtlasAction(body));
}
