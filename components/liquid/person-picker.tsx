"use client";

import { useMemo, useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { DelegationPerson } from "@/types/delegation";
import { personHome, type Directory } from "./people";

type Props = {
  id: string;
  directory: Directory;
  /** Id of the pool category being handed over, when the text matches one. */
  categoryId: string | null;
  value: string;
  onChange: (personId: string) => void;
};

/**
 * Search the network for a delegate. People who are well known for the
 * category being handed over are listed first.
 */
export function PersonPicker({ id, directory, categoryId, value, onChange }: Props) {
  const [open, setOpen] = useState(false);

  const groups = useMemo(() => {
    const everyone = [...directory.persons.values()].filter(
      (person) => person.id !== directory.viewer
    );
    const known = categoryId
      ? everyone.filter((person) => person.well_known_for.includes(categoryId))
      : [];
    const knownIds = new Set(known.map((person) => person.id));
    const byHome = new Map<string, DelegationPerson[]>();
    for (const person of everyone) {
      if (knownIds.has(person.id)) continue;
      const home = personHome(directory, person.id);
      byHome.set(home, [...(byHome.get(home) ?? []), person]);
    }
    return { known, byHome: [...byHome.entries()] };
  }, [directory, categoryId]);

  const selected = value ? directory.persons.get(value) : undefined;

  const item = (person: DelegationPerson) => (
    <CommandItem
      key={person.id}
      value={`${person.label} ${person.id}`}
      onSelect={() => {
        onChange(person.id);
        setOpen(false);
      }}
    >
      <Check
        className={cn("h-4 w-4", person.id === value ? "opacity-100" : "opacity-0")}
        aria-hidden="true"
      />
      <span className="flex-1">{person.label}</span>
      <span className="text-xs text-muted-foreground">{person.behaviour}</span>
    </CommandItem>
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          <span className={cn("truncate", !selected && "text-muted-foreground")}>
            {selected ? selected.label : "Choose a person"}
          </span>
          <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(26rem,calc(100vw-2rem))] p-0" align="start">
        <Command>
          <CommandInput placeholder="Search 260 people" />
          <CommandList>
            <CommandEmpty>Nobody by that name.</CommandEmpty>
            {groups.known.length > 0 && (
              <CommandGroup heading="Well known for this category">
                {groups.known.map(item)}
              </CommandGroup>
            )}
            {groups.byHome.map(([home, people]) => (
              <CommandGroup key={home} heading={home}>
                {people.map(item)}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
