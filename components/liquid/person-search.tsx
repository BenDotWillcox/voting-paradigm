"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { searchPeople, type Directory } from "./people";
import { PersonLine } from "./person-bits";

type Props = {
  directory: Directory;
  /** Id of a category in the network; the people most trusted with it are suggested first. */
  categoryId?: string | null;
  onPick: (personId: string) => void;
};

const SHOWN = 8;

/**
 * Find a person by name or by username. Names can repeat; the username is
 * what tells two people apart.
 */
export function PersonSearch({ directory, categoryId, onPick }: Props) {
  const [query, setQuery] = useState("");

  const { people, total, suggested } = useMemo(() => {
    if (!query.trim()) {
      // Counted across every wording of the category
      const group = categoryId ? directory.groups.byCategory.get(categoryId) : undefined;
      const trusted = (group?.trusted ?? [])
        .filter((entry) => entry.person !== directory.viewer)
        .flatMap((entry) => {
          const person = directory.persons.get(entry.person);
          return person ? [{ person, note: `${entry.delegators} hand them this` }] : [];
        });
      if (trusted.length > 0) {
        return { people: trusted.slice(0, SHOWN), total: trusted.length, suggested: "trusted" };
      }
      const known = [...directory.persons.values()]
        .filter((person) => person.id !== directory.viewer && person.well_known_for.length > 0)
        .map((person) => ({ person, note: `known for ${person.well_known_for.length}` }));
      return { people: known.slice(0, SHOWN), total: known.length, suggested: "known" };
    }
    const matches = searchPeople(directory, query).map((person) => ({
      person,
      note: person.well_known_for.length > 0 ? `known for ${person.well_known_for.length}` : null,
    }));
    return { people: matches.slice(0, SHOWN), total: matches.length, suggested: null };
  }, [query, directory, categoryId]);

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          autoFocus
          value={query}
          placeholder="Name or @username"
          aria-label="Search people by name or username"
          autoComplete="off"
          className="pl-9"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      <p className="liquid-label">
        {suggested === "trusted"
          ? "Most trusted with this category"
          : suggested === "known"
            ? "Well-known people"
          : total === 0
            ? "Nobody by that name or username"
            : total > SHOWN
              ? `${SHOWN} of ${total} · keep typing`
              : `${total} ${total === 1 ? "person" : "people"}`}
      </p>
      <ul className="space-y-1">
        {people.map(({ person, note }) => (
          <li key={person.id}>
            <button
              type="button"
              onClick={() => onPick(person.id)}
              className="flex w-full items-center justify-between gap-3 rounded-md border border-transparent p-2 text-left text-sm hover:border-border hover:bg-accent"
            >
              <PersonLine directory={directory} id={person.id} />
              {note && (
                <span className="shrink-0 text-xs text-muted-foreground">{note}</span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
