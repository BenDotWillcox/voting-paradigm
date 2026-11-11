import { NextResponse } from "next/server";
import { ExpressivePreviewError } from "@/lib/expressive-api";
import { previewScalarBallot } from "@/lib/expressive-scalar-api";
import { scalarPreviewRequestSchema } from "@/lib/validations/expressive-scalar";

export const runtime = "nodejs";

/** Stateless evaluation of one authored scalar ballot. */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ message: "Send a valid rate ballot." }, { status: 400 });
  }
  const parsed = scalarPreviewRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ message: parsed.error.issues[0]?.message || "Check your rate ballot." }, { status: 422 });
  }
  try {
    return NextResponse.json(await previewScalarBallot(parsed.data));
  } catch (error) {
    if (error instanceof ExpressivePreviewError) {
      return NextResponse.json({ message: error.message }, { status: error.status });
    }
    return NextResponse.json({ message: "The curve could not be evaluated. Please try again." }, { status: 500 });
  }
}
