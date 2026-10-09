import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { geoCentroid } from "d3-geo";

import { loadStatesGeoJSON } from "@/lib/load-states-geojson";
import { US_STATES } from "@/lib/us-states";

/** One apportionment, as the essay's figures need it. */
export interface EssayApportionment {
  year: number;
  houseSize: number;
  method: string;
  reapportioned: boolean;
  /** National resident population at that census (null for 1787). */
  residentPopulation: number | null;
  /** National resident population per seat (null for 1787). */
  residentPerSeat: number | null;
  /** The Census Bureau's average apportionment population per representative (1910 on). */
  apportionmentPerSeat: number | null;
  stateSeats: Record<string, number>;
}

export interface EssayState {
  fips: string;
  abbr: string;
  name: string;
  /** 2020 apportionment population. */
  population: number;
  /** 2020 census resident population (= the at-large district's, if one seat). */
  residentPopulation: number;
  /** 2020 seats. */
  seats: number;
  /** Census Bureau's 2020 average apportionment population per seat. */
  averagePerSeat: number;
  /** One seat: the whole state is a single at-large district. */
  atLarge: boolean;
}

export interface EssayData {
  history: EssayApportionment[];
  states: EssayState[];
  /** State FIPS codes west to east (by centroid longitude). */
  westToEast: string[];
  /** 2020 apportionment population total. */
  totalPopulation: number;
}

interface HistoryFile {
  apportionments: Array<{
    census_year: number;
    house_size: number;
    method: string;
    reapportioned: boolean;
    resident_population: number | null;
    resident_per_seat: number | null;
    apportionment_per_seat: number | null;
    state_seats: Record<string, number>;
  }>;
}

interface StatesFile {
  states: Array<{
    fips: string;
    abbr: string;
    name: string;
    seats: number;
    apportionment_population: number;
    resident_population: number;
    average_per_seat: number;
    at_large: boolean;
  }>;
}

const ARTIFACTS = join(process.cwd(), "public", "data", "apportionment-story");

let cached: Promise<EssayData> | null = null;

/**
 * Everything the essay renders on the server, from the generated artifacts
 * (scripts/build_apportionment_story.py) and the state outlines. Cached per
 * server process; the page is static, so this runs at build time.
 */
export function loadEssayData(): Promise<EssayData> {
  cached ??= build();
  return cached;
}

async function build(): Promise<EssayData> {
  const [historyText, statesText, geo] = await Promise.all([
    readFile(join(ARTIFACTS, "history.json"), "utf-8"),
    readFile(join(ARTIFACTS, "states-2020.json"), "utf-8"),
    loadStatesGeoJSON(),
  ]);
  const historyFile = JSON.parse(historyText) as HistoryFile;
  const statesFile = JSON.parse(statesText) as StatesFile;

  const longitude = new Map<string, number>();
  for (const feature of geo.features) {
    longitude.set(String(feature.id ?? "").padStart(2, "0"), geoCentroid(feature)[0]);
  }
  const westToEast = [...US_STATES]
    .sort((a, b) => (longitude.get(a.fips) ?? 0) - (longitude.get(b.fips) ?? 0))
    .map((state) => state.fips);

  return {
    history: historyFile.apportionments.map((a) => ({
      year: a.census_year,
      houseSize: a.house_size,
      method: a.method,
      reapportioned: a.reapportioned,
      residentPopulation: a.resident_population,
      residentPerSeat: a.resident_per_seat,
      apportionmentPerSeat: a.apportionment_per_seat,
      stateSeats: a.state_seats,
    })),
    states: statesFile.states.map((state) => ({
      fips: state.fips,
      abbr: state.abbr,
      name: state.name,
      population: state.apportionment_population,
      residentPopulation: state.resident_population,
      seats: state.seats,
      averagePerSeat: state.average_per_seat,
      atLarge: state.at_large,
    })),
    westToEast,
    totalPopulation: statesFile.states.reduce(
      (sum, state) => sum + state.apportionment_population,
      0
    ),
  };
}
