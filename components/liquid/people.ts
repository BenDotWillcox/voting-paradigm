import type { DelegationPerson, DelegationScenario } from "@/types/delegation";
import { buildCategoryGroups, type CategoryGroups } from "./categories";

/** Lookups the liquid democracy pages need, built once from the scenario. */
export type Directory = {
  viewer: string;
  persons: Map<string, DelegationPerson>;
  byUsername: Map<string, DelegationPerson>;
  jurisdictions: Map<string, string>;
  categoryText: Map<string, string>;
  /** Wordings of the same category, counted together. */
  groups: CategoryGroups;
};

export function buildDirectory(scenario: DelegationScenario): Directory {
  return {
    viewer: scenario.viewer,
    persons: new Map(scenario.persons.map((person) => [person.id, person])),
    byUsername: new Map(scenario.persons.map((person) => [person.username, person])),
    jurisdictions: new Map(scenario.jurisdictions.map((place) => [place.id, place.name])),
    categoryText: new Map(scenario.categories.map((category) => [category.id, category.text])),
    groups: buildCategoryGroups(scenario),
  };
}

/** "You" for the viewer, otherwise the person's name. */
export function personName(directory: Directory, id: string): string {
  return directory.persons.get(id)?.name ?? id;
}

export function personHandle(directory: Directory, id: string): string {
  return `@${directory.persons.get(id)?.username ?? id}`;
}

/** The person's district, or that they live outside the city. */
export function personHome(directory: Directory, id: string): string {
  const home = directory.persons.get(id)?.home;
  if (!home) return "Lives outside the city";
  return directory.jurisdictions.get(home) ?? home;
}

export function profileHref(directory: Directory, id: string): string {
  return `/liquid/people/${directory.persons.get(id)?.username ?? id}`;
}

/** Up to two initials, for an avatar. */
export function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

const AVATAR_TONES = [
  "bg-indigo-100 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-200",
  "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  "bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-200",
  "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
  "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200",
];

/** A stable avatar colour per person, so the same face is the same colour everywhere. */
export function avatarTone(id: string): string {
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return AVATAR_TONES[hash % AVATAR_TONES.length];
}

/** Categories match when they are the same after trimming, case and spacing. */
export function categoryKey(text: string): string {
  return text.trim().replace(/\s+/g, " ").toLowerCase();
}

export function percent(share: number, digits = 0): string {
  return `${(share * 100).toFixed(digits)}%`;
}

function span(days: number): string {
  if (days === 1) return "1 day";
  if (days < 14) return `${days} days`;
  if (days < 60) return `${Math.round(days / 7)} weeks`;
  return `${Math.round(days / 30)} months`;
}

/** "Closes in 3 days" or "Closed 2 months ago", from a paper's day offset. */
export function closing(closesInDays: number): string {
  return closesInDays > 0 ? `Closes in ${span(closesInDays)}` : `Closed ${span(-closesInDays)} ago`;
}

export function ago(days: number): string {
  return `${span(days)} ago`;
}

/**
 * People whose name or username matches, best matches first: a username
 * that starts with the text, then a name that does, then a word of the name,
 * then anywhere. A leading @ is ignored. The viewer is left out.
 */
export function searchPeople(directory: Directory, query: string): DelegationPerson[] {
  const text = query.trim().toLowerCase().replace(/^@/, "");
  if (!text) return [];
  const rank = (person: DelegationPerson): number | null => {
    const name = person.name.toLowerCase();
    if (person.username.startsWith(text)) return 0;
    if (name.startsWith(text)) return 1;
    if (name.split(" ").some((part) => part.startsWith(text))) return 2;
    if (name.includes(text) || person.username.includes(text)) return 3;
    return null;
  };
  return [...directory.persons.values()]
    .filter((person) => person.id !== directory.viewer)
    .map((person) => ({ person, rank: rank(person) }))
    .filter((entry): entry is { person: DelegationPerson; rank: number } => entry.rank !== null)
    .sort((a, b) => a.rank - b.rank || a.person.name.localeCompare(b.person.name))
    .map((entry) => entry.person);
}
