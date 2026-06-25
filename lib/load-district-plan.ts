import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { CachedDistrictPlan } from "@/types/districting";

/**
 * Load the compact per-state summary artifact: full plan metrics plus
 * dissolved per-district outlines. A few hundred KB, so it is safe to
 * read per-request and embed in the server-rendered payload.
 */
export async function loadDistrictPlanSummary(
  stateFips: string,
  cap: number,
  seats: number
): Promise<CachedDistrictPlan | null> {
  const path = join(
    process.cwd(),
    "public",
    "data",
    "districting-summary",
    stateFips,
    `cap-${cap}-seats-${seats}.summary.json`
  );
  return readPlanFile(path);
}

/**
 * Public URL of the tract-level topo artifact, or null if it has not been
 * generated. The browser fetches this lazily for tract-level hover detail;
 * it is never embedded in the page payload.
 */
export async function getDistrictPlanTopoUrl(
  stateFips: string,
  cap: number,
  seats: number
): Promise<string | null> {
  const fileName = `cap-${cap}-seats-${seats}.topo.json`;
  return `/data/districting-topo/${stateFips}/${fileName}`;
}

async function readPlanFile(path: string): Promise<CachedDistrictPlan | null> {
  try {
    const buf = await readFile(path, "utf-8");
    return JSON.parse(buf) as CachedDistrictPlan;
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code === "ENOENT") return null;
    throw err;
  }
}
