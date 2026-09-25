import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { DistrictPlan } from "@/types/districting";

import { districtPlanId } from "./district-plans";

/**
 * Load a cached plan's metrics and centers (`plan.json`, a few KB). Safe to
 * embed in a server-rendered payload; geometry layers are fetched by the
 * browser as static assets instead.
 */
export async function loadDistrictPlan(
  stateFips: string,
  cap: number,
  seats: number
): Promise<DistrictPlan | null> {
  const path = join(
    process.cwd(),
    "public",
    "data",
    "district-plans",
    stateFips,
    districtPlanId(cap, seats),
    "plan.json"
  );
  try {
    return JSON.parse(await readFile(path, "utf-8")) as DistrictPlan;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}
