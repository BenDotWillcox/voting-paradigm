import { serveBlockPlanAsset } from "@/lib/load-block-plans";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type AssetContext = { params: Promise<{ asset: string[] }> };

export async function GET(request: Request, context: AssetContext): Promise<Response> {
  return serveBlockPlanAsset(request, (await context.params).asset);
}

export async function HEAD(request: Request, context: AssetContext): Promise<Response> {
  return serveBlockPlanAsset(request, (await context.params).asset);
}
