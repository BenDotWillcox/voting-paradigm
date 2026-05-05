// TypeScript types mirroring the Python districting package responses.
// Kept narrow on purpose: only what the API actually returns today.
// Step 3+ will add types for district maps, metrics, etc.

/** Apportionment for a single House size, as returned by the API. */
export interface ApportionmentDto {
  /** Total House size that was requested. Echoed for safety. */
  cap: number;
  /** State FIPS (2-char, with leading zeros) -> seats. Sums to `cap`. */
  apportionment: Record<string, number>;
  /** Always 50 in v1. Provided so the UI doesn't have to count keys. */
  total_states: number;
  /** 2020 census apportionment population summed across the 50 states. */
  total_apportionment_population: number;
}

/** A single anchor on the cap slider. */
export interface CapAnchor {
  /** The cap value the anchor sits at. */
  cap: number;
  /** Short label shown on the slider rail. */
  label: string;
  /** One-sentence tooltip explanation. */
  description: string;
}
