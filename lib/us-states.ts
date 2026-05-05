/**
 * Reference table of the 50 US states, keyed by 2-character FIPS code.
 *
 * FIPS codes are the canonical identifier used everywhere on the Python side
 * (apportionment, future district_run rows) and match the `id` field on
 * features in us-atlas's TopoJSON (states-10m.json) — except us-atlas IDs are
 * the integer form ("6"), not zero-padded ("06"). Use `paddedFips()` when
 * looking up by id from a TopoJSON feature.
 *
 * DC and the territories are intentionally omitted: they receive no voting
 * House representation and are out of scope for v1 (see
 * prompts/demo-3-districting.md decision #5).
 */

export interface UsState {
  fips: string; // 2-char zero-padded, e.g. "06"
  abbr: string; // 2-char postal, e.g. "CA"
  name: string;
}

export const US_STATES: readonly UsState[] = [
  { fips: "01", abbr: "AL", name: "Alabama" },
  { fips: "02", abbr: "AK", name: "Alaska" },
  { fips: "04", abbr: "AZ", name: "Arizona" },
  { fips: "05", abbr: "AR", name: "Arkansas" },
  { fips: "06", abbr: "CA", name: "California" },
  { fips: "08", abbr: "CO", name: "Colorado" },
  { fips: "09", abbr: "CT", name: "Connecticut" },
  { fips: "10", abbr: "DE", name: "Delaware" },
  { fips: "12", abbr: "FL", name: "Florida" },
  { fips: "13", abbr: "GA", name: "Georgia" },
  { fips: "15", abbr: "HI", name: "Hawaii" },
  { fips: "16", abbr: "ID", name: "Idaho" },
  { fips: "17", abbr: "IL", name: "Illinois" },
  { fips: "18", abbr: "IN", name: "Indiana" },
  { fips: "19", abbr: "IA", name: "Iowa" },
  { fips: "20", abbr: "KS", name: "Kansas" },
  { fips: "21", abbr: "KY", name: "Kentucky" },
  { fips: "22", abbr: "LA", name: "Louisiana" },
  { fips: "23", abbr: "ME", name: "Maine" },
  { fips: "24", abbr: "MD", name: "Maryland" },
  { fips: "25", abbr: "MA", name: "Massachusetts" },
  { fips: "26", abbr: "MI", name: "Michigan" },
  { fips: "27", abbr: "MN", name: "Minnesota" },
  { fips: "28", abbr: "MS", name: "Mississippi" },
  { fips: "29", abbr: "MO", name: "Missouri" },
  { fips: "30", abbr: "MT", name: "Montana" },
  { fips: "31", abbr: "NE", name: "Nebraska" },
  { fips: "32", abbr: "NV", name: "Nevada" },
  { fips: "33", abbr: "NH", name: "New Hampshire" },
  { fips: "34", abbr: "NJ", name: "New Jersey" },
  { fips: "35", abbr: "NM", name: "New Mexico" },
  { fips: "36", abbr: "NY", name: "New York" },
  { fips: "37", abbr: "NC", name: "North Carolina" },
  { fips: "38", abbr: "ND", name: "North Dakota" },
  { fips: "39", abbr: "OH", name: "Ohio" },
  { fips: "40", abbr: "OK", name: "Oklahoma" },
  { fips: "41", abbr: "OR", name: "Oregon" },
  { fips: "42", abbr: "PA", name: "Pennsylvania" },
  { fips: "44", abbr: "RI", name: "Rhode Island" },
  { fips: "45", abbr: "SC", name: "South Carolina" },
  { fips: "46", abbr: "SD", name: "South Dakota" },
  { fips: "47", abbr: "TN", name: "Tennessee" },
  { fips: "48", abbr: "TX", name: "Texas" },
  { fips: "49", abbr: "UT", name: "Utah" },
  { fips: "50", abbr: "VT", name: "Vermont" },
  { fips: "51", abbr: "VA", name: "Virginia" },
  { fips: "53", abbr: "WA", name: "Washington" },
  { fips: "54", abbr: "WV", name: "West Virginia" },
  { fips: "55", abbr: "WI", name: "Wisconsin" },
  { fips: "56", abbr: "WY", name: "Wyoming" },
] as const;

const BY_FIPS: Map<string, UsState> = new Map(
  US_STATES.map((s) => [s.fips, s])
);

/** Look up a state by zero-padded 2-char FIPS code. Returns null if unknown. */
export function getStateByFips(fips: string): UsState | null {
  return BY_FIPS.get(fips) ?? null;
}

/**
 * Normalize a state id into the canonical 2-char zero-padded FIPS form.
 *
 * us-atlas TopoJSON encodes feature ids as numeric strings ("6"); the
 * Python API and this codebase use "06". Pads so they line up.
 */
export function paddedFips(id: string | number): string {
  return String(id).padStart(2, "0");
}

/** True if `fips` is one of the 50 states. False for DC, PR, and territories. */
export function isStateFips(fips: string): boolean {
  return BY_FIPS.has(fips);
}
