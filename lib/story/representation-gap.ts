import { getSeatCountsAfter } from "@/lib/apportionment-sequence";
import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import { US_STATES } from "@/lib/us-states";

export interface StateRepresentation {
  fips: string;
  abbr: string;
  name: string;
  seats: number;
  population: number;
  /** People per representative in this state. */
  perSeat: number;
  /** perSeat relative to the national average: 0.1 = 10% larger districts. */
  deviation: number;
}

export interface HouseSizeSnapshot {
  cap: number;
  /** National people per representative. */
  average: number;
  states: StateRepresentation[];
  largest: StateRepresentation;
  smallest: StateRepresentation;
  /** Largest district size divided by smallest. */
  ratio: number;
}

const TOTAL_POPULATION = Object.values(US_2020_APPORTIONMENT_POPULATIONS).reduce(
  (sum, population) => sum + population,
  0
);

/**
 * District-size inequality across states at a given House size, from the
 * deterministic Method of Equal Proportions sequence and 2020 counts.
 */
export function houseSizeSnapshot(cap: number): HouseSizeSnapshot {
  const seatCounts = getSeatCountsAfter(cap);
  const average = TOTAL_POPULATION / cap;
  const states = US_STATES.map((state) => {
    const seats = seatCounts[state.fips] ?? 0;
    const population = US_2020_APPORTIONMENT_POPULATIONS[state.fips] ?? 0;
    const perSeat = population / seats;
    return {
      fips: state.fips,
      abbr: state.abbr,
      name: state.name,
      seats,
      population,
      perSeat,
      deviation: perSeat / average - 1,
    };
  });
  const byPerSeat = [...states].sort((a, b) => a.perSeat - b.perSeat);
  const smallest = byPerSeat[0];
  const largest = byPerSeat[byPerSeat.length - 1];
  return {
    cap,
    average,
    states,
    largest,
    smallest,
    ratio: largest.perSeat / smallest.perSeat,
  };
}
