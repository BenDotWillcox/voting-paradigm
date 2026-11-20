import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { StoryCity, StoryMeasures } from "./story-types";

export interface LiquidStoryData {
  measures: StoryMeasures;
  city: StoryCity;
}

const ARTIFACTS = join(process.cwd(), "public", "data", "liquid-story");

let cached: Promise<LiquidStoryData> | null = null;

/**
 * Everything the walkthrough renders, from the generated artifacts
 * (scripts/build_liquid_story.py, scripts/build_liquid_example_city.py).
 * Cached per server process; the page is static, so this runs at build time.
 */
export function loadLiquidStory(): Promise<LiquidStoryData> {
  cached ??= load();
  return cached;
}

async function load(): Promise<LiquidStoryData> {
  const [measures, city] = await Promise.all([
    readFile(join(ARTIFACTS, "measures.json"), "utf-8"),
    readFile(join(ARTIFACTS, "city.json"), "utf-8"),
  ]);
  return {
    measures: JSON.parse(measures) as StoryMeasures,
    city: JSON.parse(city) as StoryCity,
  };
}
