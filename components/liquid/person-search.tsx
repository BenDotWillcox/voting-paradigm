"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { searchPeople, type Directory } from "./people";
import { PersonLine } from "./person-bits";

type Props = {
  directory: Directory;
  /** Id of a pool category; people well known for it are suggested first. */
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
      const known = [...directory.persons.values()].filter(
        (person) =>
          person.id !== directory.viewer &&
          (categoryId
            ? person.well_known_for.includes(categoryId)
            : person.well_known_for.length > 0)
      );
      return { people: known.slice(0, SHOWN), total: known.length, suggested: true };
    }
    const matches = searchPeople(directory, query);
    return { people: matches.slice(0, SHOWN), total: matches.length, suggested: false };
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
        {suggested
          ? categoryId
            ? "Well known for this category"
            : "Well-known people"
          : total === 0
            ? "Nobody by that name or username"
            : total > SHOWN
              ? `${SHOWN} of ${total} · keep typing`
              : `${total} ${total === 1 ? "person" : "people"}`}
      </p>
      <ul className="space-y-1">
        {people.map((person) => (
          <li key={person.id}>
            <button
              type="button"
              onClick={() => onPick(person.id)}
              className="flex w-full items-center justify-between gap-3 rounded-md border border-transparent p-2 text-left text-sm hover:border-border hover:bg-accent"
            >
              <PersonLine directory={directory} id={person.id} />
              {person.well_known_for.length > 0 && (
                <span className="shrink-0 text-xs text-muted-foreground">
                  known for {person.well_known_for.length}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
