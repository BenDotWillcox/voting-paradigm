import type { DelegationPerson, DelegationScenario } from "@/types/delegation";

/** Lookups the liquid democracy page needs, built once from the scenario. */
export type Directory = {
  viewer: string;
  persons: Map<string, DelegationPerson>;
  jurisdictions: Map<string, string>;
  categoryText: Map<string, string>;
};

export function buildDirectory(scenario: DelegationScenario): Directory {
  return {
    viewer: scenario.viewer,
    persons: new Map(scenario.persons.map((person) => [person.id, person])),
    jurisdictions: new Map(scenario.jurisdictions.map((place) => [place.id, place.name])),
    categoryText: new Map(scenario.categories.map((category) => [category.id, category.text])),
  };
}

/** "You" for the viewer, otherwise the person's label. */
export function personName(directory: Directory, id: string): string {
  if (id === directory.viewer) return "You";
  return directory.persons.get(id)?.label ?? id;
}

/** The person's district, or where they stand if they live outside the city. */
export function personHome(directory: Directory, id: string): string {
  const person = directory.persons.get(id);
  if (!person) return "";
  const district = person.residences.find((place) => place !== "city");
  if (district) return directory.jurisdictions.get(district) ?? district;
  return person.residences.length > 0 ? "The city" : "Lives outside the city";
}

/** Categories match when they are the same after trimming, case and spacing. */
export function categoryKey(text: string): string {
  return text.trim().replace(/\s+/g, " ").toLowerCase();
}

export function percent(share: number, digits = 0): string {
  return `${(share * 100).toFixed(digits)}%`;
}
