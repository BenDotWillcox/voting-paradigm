import type { DelegationScenario } from "@/types/delegation";

/** One way a category is written, and how many people hand it over in those words. */
export type Wording = { id: string; text: string; holders: number };

/**
 * Wordings the decision model judged to be the same thing. Only for reading
 * the network: a vote moves under the exact text its voter wrote.
 */
export type CategoryGroup = {
  id: string;
  /** The wording most people use, which names the group. */
  label: string;
  /** Most used first. */
  wordings: Wording[];
  /** People who hand over any of the wordings. */
  holders: number;
  /** Who they hand it to, most delegators first. */
  trusted: { person: string; delegators: number }[];
};

export type CategoryGroups = {
  all: CategoryGroup[];
  /** The group of a category in the network, by category id. */
  byCategory: Map<string, CategoryGroup>;
  /** The same, by the category's text as normalised by `categoryKey`. */
  byKey: Map<string, CategoryGroup>;
};

/** The same normalisation as people.ts, kept here to avoid a circular import. */
function key(text: string): string {
  return text.trim().replace(/\s+/g, " ").toLowerCase();
}

export function buildCategoryGroups(scenario: DelegationScenario): CategoryGroups {
  const order = new Map(scenario.categories.map((category, index) => [category.id, index]));
  const holders = new Map<string, number>();
  for (const delegation of scenario.delegations) {
    holders.set(delegation.category, (holders.get(delegation.category) ?? 0) + 1);
  }

  const byCategory = new Map<string, CategoryGroup>();
  const all: CategoryGroup[] = [];
  for (const category of scenario.categories) {
    if (byCategory.has(category.id)) continue;
    const members = [category.id, ...category.same_as].filter((id) => order.has(id));
    const wordings = members
      .map((id) => ({
        id,
        text: scenario.categories[order.get(id) ?? 0].text,
        holders: holders.get(id) ?? 0,
      }))
      .sort((a, b) => b.holders - a.holders || (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
    const group: CategoryGroup = {
      id: category.id,
      label: wordings[0].text,
      wordings,
      holders: wordings.reduce((sum, wording) => sum + wording.holders, 0),
      trusted: [],
    };
    all.push(group);
    for (const id of members) byCategory.set(id, group);
  }

  const delegators = new Map<CategoryGroup, Map<string, Set<string>>>();
  for (const delegation of scenario.delegations) {
    const group = byCategory.get(delegation.category);
    if (!group) continue;
    const people = delegators.get(group) ?? new Map<string, Set<string>>();
    delegators.set(group, people);
    people.set(
      delegation.delegate,
      (people.get(delegation.delegate) ?? new Set<string>()).add(delegation.delegator)
    );
  }
  for (const [group, people] of delegators) {
    group.trusted = [...people.entries()]
      .map(([person, from]) => ({ person, delegators: from.size }))
      .sort((a, b) => b.delegators - a.delegators || a.person.localeCompare(b.person));
  }

  const byKey = new Map<string, CategoryGroup>();
  for (const category of scenario.categories) {
    const group = byCategory.get(category.id);
    if (group) byKey.set(key(category.text), group);
  }
  return { all, byCategory, byKey };
}

/** Other wordings of a group, leaving one out, as quoted text. */
export function otherWordings(group: CategoryGroup, except: string): string[] {
  return group.wordings.filter((wording) => key(wording.text) !== key(except)).map((w) => w.text);
}

/**
 * Groups whose wordings match what someone is typing, most used first. A
 * match is every typed word appearing somewhere in a wording.
 */
export function suggestCategories(groups: CategoryGroups, query: string, limit = 5): CategoryGroup[] {
  const words = key(query).split(" ").filter(Boolean);
  if (words.length === 0) return [];
  return groups.all
    .filter(
      (group) =>
        group.holders > 0 &&
        group.wordings.some((wording) => {
          const text = key(wording.text);
          return words.every((word) => text.includes(word));
        })
    )
    .sort((a, b) => b.holders - a.holders)
    .slice(0, limit);
}

/**
 * What people hand to one person, with wordings of the same thing counted
 * together. `received` is each delegation to them as (delegator, category text).
 */
export function trustedWith(
  groups: CategoryGroups,
  received: { delegator: string; category: string }[]
): { label: string; people: string[]; wordings: { text: string; count: number }[] }[] {
  const rows = new Map<string, { group: CategoryGroup | null; entries: typeof received }>();
  for (const entry of received) {
    const group = groups.byKey.get(key(entry.category)) ?? null;
    const id = group ? group.id : `text:${key(entry.category)}`;
    const row = rows.get(id) ?? { group, entries: [] };
    rows.set(id, row);
    row.entries.push(entry);
  }
  return [...rows.values()]
    .map(({ group, entries }) => {
      const counts = new Map<string, number>();
      for (const entry of entries) counts.set(entry.category, (counts.get(entry.category) ?? 0) + 1);
      const wordings = [...counts.entries()]
        .map(([text, count]) => ({ text, count }))
        .sort((a, b) => b.count - a.count || a.text.localeCompare(b.text));
      return {
        // Named by what this person's own delegators mostly write
        label: wordings[0]?.text ?? group?.label ?? "",
        people: [...new Set(entries.map((entry) => entry.delegator))],
        wordings,
      };
    })
    .sort((a, b) => b.people.length - a.people.length || a.label.localeCompare(b.label));
}
