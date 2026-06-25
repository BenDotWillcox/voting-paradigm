import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import { US_STATES } from "@/lib/us-states";

export interface AllocationStep {
  seatNumber: number;
  stateFips: string;
  stateName: string;
  population: number;
  previousSeats: number;
  newSeats: number;
  priority: number;
}

export interface PriorityCandidate {
  stateFips: string;
  stateName: string;
  population: number;
  currentSeats: number;
  nextSeats: number;
  priority: number;
}

export interface StatePriorityPoint {
  seats: number;
  priority: number;
}

export function priorityValue(population: number, currentSeats: number): number {
  if (currentSeats <= 0) return Number.POSITIVE_INFINITY;
  return population / Math.sqrt(currentSeats * (currentSeats + 1));
}

export function buildAllocationSequence(totalSeats: number): AllocationStep[] {
  const stateCount = US_STATES.length;
  if (totalSeats <= stateCount) return [];

  const seats = Object.fromEntries(US_STATES.map((state) => [state.fips, 1]));
  const steps: AllocationStep[] = [];

  for (let seatNumber = stateCount + 1; seatNumber <= totalSeats; seatNumber += 1) {
    const next = getNextCandidate(seats);
    steps.push({
      seatNumber,
      stateFips: next.stateFips,
      stateName: next.stateName,
      population: next.population,
      previousSeats: next.currentSeats,
      newSeats: next.nextSeats,
      priority: next.priority,
    });
    seats[next.stateFips] = next.nextSeats;
  }

  return steps;
}

export function getSeatCountsAfter(totalSeats: number): Record<string, number> {
  const seats = Object.fromEntries(US_STATES.map((state) => [state.fips, 1]));
  for (const step of buildAllocationSequence(totalSeats)) {
    seats[step.stateFips] = step.newSeats;
  }
  return seats;
}

export function getNextCandidates(
  totalSeats: number,
  count: number = 10
): PriorityCandidate[] {
  const seats = getSeatCountsAfter(totalSeats);
  return getAllCandidates(seats).slice(0, count);
}

export function getRecentAllocations(
  totalSeats: number,
  count: number = 10
): AllocationStep[] {
  return buildAllocationSequence(totalSeats).slice(-count).reverse();
}

export function getStateSeatLadder(
  stateFips: string,
  totalSeats: number
): AllocationStep[] {
  return buildAllocationSequence(totalSeats).filter(
    (step) => step.stateFips === stateFips
  );
}

export function buildStatePriorityCurve(
  stateFips: string,
  maxSeats: number
): StatePriorityPoint[] {
  const population = US_2020_APPORTIONMENT_POPULATIONS[stateFips] ?? 0;
  const limit = Math.max(1, maxSeats);
  return Array.from({ length: limit }, (_, index) => {
    const seats = index + 1;
    return {
      seats,
      priority: priorityValue(population, seats),
    };
  });
}

function getNextCandidate(seats: Record<string, number>): PriorityCandidate {
  return getAllCandidates(seats)[0];
}

function getAllCandidates(seats: Record<string, number>): PriorityCandidate[] {
  return US_STATES.map((state) => {
    const currentSeats = seats[state.fips] ?? 1;
    const population = US_2020_APPORTIONMENT_POPULATIONS[state.fips] ?? 0;
    return {
      stateFips: state.fips,
      stateName: state.name,
      population,
      currentSeats,
      nextSeats: currentSeats + 1,
      priority: priorityValue(population, currentSeats),
    };
  }).sort((a, b) => b.priority - a.priority || a.stateName.localeCompare(b.stateName));
}
