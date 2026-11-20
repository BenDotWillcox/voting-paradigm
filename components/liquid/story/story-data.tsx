"use client";

import * as React from "react";

import type { StoryCity, StoryExploratory, StoryMeasures, StoryResults } from "@/lib/liquid/story-types";

interface StoryData {
  measures: StoryMeasures;
  results: StoryResults;
  exploratory: StoryExploratory;
  city: StoryCity;
}

const StoryDataContext = React.createContext<StoryData | null>(null);

/**
 * The walkthrough's static data, handed to the client once. Figures read it
 * from here instead of taking it as props, so the city is serialized into
 * the page a single time however many figures draw it.
 */
export function StoryDataProvider({
  measures,
  results,
  exploratory,
  city,
  children,
}: StoryData & { children: React.ReactNode }) {
  const value = React.useMemo(
    () => ({ measures, results, exploratory, city }),
    [measures, results, exploratory, city]
  );
  return <StoryDataContext.Provider value={value}>{children}</StoryDataContext.Provider>;
}

export function useStoryData(): StoryData {
  const value = React.useContext(StoryDataContext);
  if (!value) throw new Error("useStoryData must be used inside <StoryDataProvider>");
  return value;
}
