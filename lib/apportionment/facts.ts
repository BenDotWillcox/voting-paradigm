import factsFile from "@/data/apportionment/facts.json";

export type FactStatus = "verified" | "derived" | "unverified";

export interface FactSource {
  title: string;
  publisher?: string;
  url: string;
  locator?: string;
}

export interface Fact {
  id: string;
  status: FactStatus;
  claim: string;
  quote?: string;
  derivation?: string;
  note?: string;
  sources: FactSource[];
}

const FACTS = new Map<string, Fact>(
  (factsFile.facts as Fact[]).map((fact) => [fact.id, fact])
);

/**
 * The fact register entry the essay is citing. Throws (failing the build)
 * for unknown ids and for `unverified` facts, which the essay may not use.
 * See data/apportionment/facts.json.
 */
export function citableFact(id: string): Fact {
  const fact = FACTS.get(id);
  if (!fact) {
    throw new Error(`Unknown apportionment fact "${id}"`);
  }
  if (fact.status === "unverified") {
    throw new Error(`Fact "${id}" is unverified and cannot be cited in the essay`);
  }
  return fact;
}

/** Every entry the essay may cite (verified or derived), in register order. */
export function citableFacts(): Fact[] {
  return [...FACTS.values()].filter((fact) => fact.status !== "unverified");
}
