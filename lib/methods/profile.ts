/**
 * Editing, encoding and reading the methods instrument's electorate: voter
 * types with utilities from 0 (worst) to 100 (best). Display and bookkeeping
 * only: every count of an election happens in Python
 * (POST /api/voting/profile/resolve), which also turns utilities into ballots.
 */

import type {
  RankedProfile,
  Specimen,
  SpecimenRole,
  UtilityProfile,
  UtilityRow,
} from "@/types/methods";

import {
  CANDIDATE_IDS,
  MAX_CANDIDATES,
  MIN_CANDIDATES,
  candidatesFor,
} from "./candidates";

export const UTILITY_SCALE = 100;
/** The API's ceiling on voters in one profile. */
export const MAX_VOTERS = 10_000;
/** The editor's ceiling on one row's count. */
export const MAX_ROW_COUNT = 999;

export function totalVoters(profile: { rows: { count: number }[] }): number {
  return profile.rows.reduce((sum, row) => sum + row.count, 0);
}

/** A row's ranking: highest utility first, equal utilities in candidate order. */
export function rankingOf(candidates: string[], row: UtilityRow): string[] {
  return [...candidates].sort(
    (a, b) =>
      (row.utilities[b] ?? 0) - (row.utilities[a] ?? 0) ||
      candidates.indexOf(a) - candidates.indexOf(b)
  );
}

/** Utilities that space a ranking evenly from 100 down to 0. */
export function evenlySpaced(ranking: string[]): Record<string, number> {
  const steps = Math.max(ranking.length - 1, 1);
  return Object.fromEntries(
    ranking.map((id, i) => [id, Math.round((UTILITY_SCALE * (steps - i)) / steps)])
  );
}

/**
 * A ranked profile as voter types, each ranking spaced evenly. Gallery
 * specimens load this way, so their rated counts assume even spacing.
 */
export function fromRanked(profile: RankedProfile): UtilityProfile {
  return {
    ballot_type: "utility",
    candidates: [...profile.candidates],
    rows: profile.rows.map((row) => ({ count: row.count, utilities: evenlySpaced(row.ranking) })),
  };
}

/**
 * URL form and cache key: rows joined by ".", each a count, ":", and one
 * utility per candidate in candidate order, e.g. "6:100,50,0.4:0,100,50".
 * Candidates are the first N letters unless a prefix names them ("AC|..."),
 * as in a specimen after a candidate withdraws. scripts/build_methods_artifacts.py
 * (instrument_key) builds the same keys for the static specimen resolutions.
 */
export function encodeProfile(profile: UtilityProfile): string {
  const first: string[] = candidatesFor(profile.candidates.length);
  const standard = profile.candidates.every((id, i) => id === first[i]);
  const prefix = standard ? "" : `${profile.candidates.join("")}|`;
  return (
    prefix +
    profile.rows
      .map((row) => `${row.count}:${profile.candidates.map((id) => row.utilities[id] ?? 0).join(",")}`)
      .join(".")
  );
}

/**
 * Parse the URL form; null when it is not a valid profile. Also accepts the
 * earlier ranked form ("6ABC.4BCA"), spacing each ranking evenly.
 */
export function decodeProfile(text: string | null | undefined): UtilityProfile | null {
  if (!text) return null;
  if (!text.includes(":")) return decodeRanked(text);
  const [prefix, body] = text.includes("|") ? text.split("|", 2) : [null, text];
  const named = prefix === null ? null : prefix.split("");
  if (named && (!/^[A-E]+$/.test(prefix ?? "") || new Set(named).size !== named.length)) return null;
  const rows: UtilityRow[] = [];
  let size: number | null = null;
  for (const part of body.split(".")) {
    const match = /^(\d{1,3}):(\d{1,3}(?:,\d{1,3})*)$/.exec(part);
    if (!match) return null;
    const values = match[2].split(",").map(Number);
    size ??= values.length;
    if (values.length !== size || values.some((v) => v > UTILITY_SCALE)) return null;
    const candidates: string[] = named ?? candidatesFor(values.length);
    if (candidates.length !== size) return null;
    rows.push({
      count: Number(match[1]),
      utilities: Object.fromEntries(candidates.map((id, i) => [id, values[i]])),
    });
  }
  // Two candidates are allowed here: a specimen can lose one
  if (size === null || size < 2 || size > MAX_CANDIDATES) return null;
  const profile: UtilityProfile = {
    ballot_type: "utility",
    candidates: named ?? candidatesFor(size),
    rows,
  };
  return totalVoters(profile) <= MAX_VOTERS ? profile : null;
}

function decodeRanked(text: string): UtilityProfile | null {
  const rows: { count: number; ranking: string[] }[] = [];
  let size: number | null = null;
  for (const part of text.split(".")) {
    const match = /^(\d{1,3})([A-E]+)$/.exec(part);
    if (!match) return null;
    const ranking = match[2].split("");
    size ??= ranking.length;
    if (ranking.length !== size) return null;
    rows.push({ count: Number(match[1]), ranking });
  }
  if (size === null || size < MIN_CANDIDATES || size > MAX_CANDIDATES) return null;
  const candidates: string[] = candidatesFor(size);
  const complete = rows.every(
    (row) => new Set(row.ranking).size === size && row.ranking.every((id) => candidates.includes(id))
  );
  return complete ? fromRanked({ ballot_type: "ranked", candidates, rows }) : null;
}

// ---------------------------------------------------------------------------
// Edits. Each returns a new profile; rows keep the order the reader sees.
// ---------------------------------------------------------------------------

export function setRowCount(profile: UtilityProfile, row: number, count: number): UtilityProfile {
  const clamped = Math.max(0, Math.min(MAX_ROW_COUNT, Math.round(count)));
  return {
    ...profile,
    rows: profile.rows.map((r, i) => (i === row ? { ...r, count: clamped } : r)),
  };
}

export function setUtility(
  profile: UtilityProfile,
  row: number,
  candidate: string,
  value: number
): UtilityProfile {
  const clamped = Math.max(0, Math.min(UTILITY_SCALE, Math.round(value)));
  return {
    ...profile,
    rows: profile.rows.map((r, i) =>
      i === row ? { ...r, utilities: { ...r.utilities, [candidate]: clamped } } : r
    ),
  };
}

/** Add one voter whose evenly spaced ranking no row uses yet. */
export function addRow(profile: UtilityProfile): UtilityProfile {
  const used = new Set(profile.rows.map((r) => rankingOf(profile.candidates, r).join("")));
  const fresh =
    permutations(profile.candidates).find((p) => !used.has(p.join(""))) ?? profile.candidates;
  return { ...profile, rows: [...profile.rows, { count: 1, utilities: evenlySpaced(fresh) }] };
}

export function removeRow(profile: UtilityProfile, row: number): UtilityProfile {
  return { ...profile, rows: profile.rows.filter((_, i) => i !== row) };
}

/** Add the next candidate at utility 0 for every voter type. */
export function addCandidate(profile: UtilityProfile): UtilityProfile {
  const next = CANDIDATE_IDS.find((id) => !profile.candidates.includes(id));
  if (profile.candidates.length >= MAX_CANDIDATES || next === undefined) return profile;
  return {
    ballot_type: "utility",
    candidates: [...profile.candidates, next],
    rows: profile.rows.map((r) => ({ ...r, utilities: { ...r.utilities, [next]: 0 } })),
  };
}

/** Remove the last candidate; every voter type keeps the rest of its utilities. */
export function removeCandidate(profile: UtilityProfile): UtilityProfile {
  const size = profile.candidates.length;
  if (size <= MIN_CANDIDATES) return profile;
  const last = profile.candidates[size - 1];
  return {
    ballot_type: "utility",
    candidates: profile.candidates.slice(0, -1),
    rows: profile.rows.map((r) => {
      const rest = { ...r.utilities };
      delete rest[last];
      return { ...r, utilities: rest };
    }),
  };
}

function permutations(items: string[]): string[][] {
  if (items.length <= 1) return [items];
  return items.flatMap((item, index) =>
    permutations([...items.slice(0, index), ...items.slice(index + 1)]).map((rest) => [
      item,
      ...rest,
    ])
  );
}

/** How many voters rank each candidate at each position (0 = first). */
export function positionCounts(profile: RankedProfile): Record<string, number[]> {
  const counts: Record<string, number[]> = Object.fromEntries(
    profile.candidates.map((id) => [id, profile.candidates.map(() => 0)])
  );
  for (const row of profile.rows) {
    row.ranking.forEach((id, position) => {
      counts[id][position] += row.count;
    });
  }
  return counts;
}

/** Utility shown as a 0–10 number with one decimal place. */
export function formatUtility(value: number): string {
  return (value / 10).toFixed(value % 10 === 0 ? 0 : 1);
}

/**
 * A gallery specimen's profile as the instrument shows it: utility specimens
 * as found, ranked ones as evenly spaced voter types.
 */
export function specimenProfile(specimen: Specimen, role: SpecimenRole): UtilityProfile {
  const profile = specimen.profiles.find((p) => p.role === role) ?? specimen.profiles[0];
  if (profile.ballot_type === "utility") {
    return {
      ballot_type: "utility",
      candidates: [...profile.candidates],
      rows: profile.rows.map(([count, utilities]) => ({
        count,
        utilities: Object.fromEntries(profile.candidates.map((id, i) => [id, utilities[i]])),
      })),
    };
  }
  return fromRanked({
    ballot_type: "ranked",
    candidates: profile.candidates,
    rows: profile.rows.map(([count, ranking]) => ({ count, ranking })),
  });
}
