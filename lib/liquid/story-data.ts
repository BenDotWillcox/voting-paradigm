import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { StoryCity, StoryExploratory, StoryMeasures, StoryResults } from "./story-types";

export interface LiquidStoryData {
  measures: StoryMeasures;
  results: StoryResults;
  exploratory: StoryExploratory;
  city: StoryCity;
}

const ARTIFACTS = join(process.cwd(), "public", "data", "liquid-story");

let cached: Promise<LiquidStoryData> | null = null;

/**
 * Everything the walkthrough renders, from the generated artifacts
 * (scripts/build_liquid_story.py, scripts/build_liquid_example_city.py).
 * Cached per server process; the page is static, so this runs at build time.
 * In development it reads the files every time, so a rebuilt artifact shows
 * without restarting the server.
 */
export function loadLiquidStory(): Promise<LiquidStoryData> {
  if (process.env.NODE_ENV === "development") return load();
  cached ??= load();
  return cached;
}

async function load(): Promise<LiquidStoryData> {
  const [measures, results, exploratory, city] = await Promise.all([
    readFile(join(ARTIFACTS, "measures.json"), "utf-8"),
    readFile(join(ARTIFACTS, "results.json"), "utf-8"),
    readFile(join(ARTIFACTS, "exploratory.json"), "utf-8"),
    readFile(join(ARTIFACTS, "city.json"), "utf-8"),
  ]);
  return {
    measures: JSON.parse(measures) as StoryMeasures,
    results: JSON.parse(results) as StoryResults,
    exploratory: JSON.parse(exploratory) as StoryExploratory,
    city: JSON.parse(city) as StoryCity,
  };
}
