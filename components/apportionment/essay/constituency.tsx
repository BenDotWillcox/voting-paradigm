"use client";

import * as React from "react";

import { districtLabel } from "@/lib/apportionment/persona";

import { usePersona } from "./persona";
import { useStateFocus } from "./state-focus";

/**
 * The population behind "one seat", with its sourcing made explicit:
 *
 * - district: an at-large state, where the district is the whole state, so
 *   its 2020 census resident population is the district's population;
 * - state-average: a multi-district state, where we only have the Census
 *   Bureau's state average per seat (never presented as a district count);
 * - national-average: no state chosen; the 2020 national average per seat.
 */
export interface Constituency {
  kind: "district" | "state-average" | "national-average";
  population: number;
  /** "Wyoming’s at-large congressional district", when kind = district. */
  districtName: string | null;
  stateName: string | null;
  source: string;
}

export function useConstituency(nationalAverage: number): Constituency {
  const { focus } = useStateFocus();
  const { persona } = usePersona();
  return React.useMemo(() => {
    if (!focus) {
      return {
        kind: "national-average",
        population: nationalAverage,
        districtName: null,
        stateName: null,
        source: "U.S. Census Bureau, 2020 apportionment (average apportionment population per representative)",
      };
    }
    if (focus.atLarge) {
      return {
        kind: "district",
        population: focus.residentPopulation,
        districtName: districtLabel(focus.name, null),
        stateName: focus.name,
        source: `U.S. Census Bureau, 2020 Census resident population of ${focus.name}, which is one at-large district`,
      };
    }
    return {
      kind: "state-average",
      population: focus.averagePerSeat,
      districtName: persona ? districtLabel(focus.name, persona.district) : null,
      stateName: focus.name,
      source: `U.S. Census Bureau, 2020 apportionment: ${focus.name}’s average apportionment population per representative (a state average, not a district count)`,
    };
  }, [focus, persona, nationalAverage]);
}

export const formatCount = (n: number) => Math.round(n).toLocaleString("en-US");

/** Step-card text that depends on the reader's state. */
export function ConstituencyText({
  part,
  nationalAverage,
}: {
  part: "first-person" | "final" | "final-labels";
  nationalAverage: number;
}) {
  const constituency = useConstituency(nationalAverage);
  const { persona } = usePersona();
  const { focus } = useStateFocus();

  if (part === "first-person") {
    return persona && focus ? (
      <>
        One {persona.role.noun} in {districtLabel(focus.name, persona.district)}.
      </>
    ) : (
      <>One person.</>
    );
  }

  const population = formatCount(constituency.population);
  if (part === "final") {
    if (constituency.kind === "district") {
      return (
        <>
          In {constituency.districtName}, {population} people share one member of the House.
        </>
      );
    }
    if (constituency.kind === "state-average") {
      return (
        <>
          Across {constituency.stateName}, each House seat represents an average of {population}{" "}
          people.
        </>
      );
    }
    return <>Across the country, each House seat represents an average of {population} people.</>;
  }

  return (
    <span className="block font-sans text-2xl font-semibold leading-tight tracking-tight text-story-ink sm:text-3xl">
      <span className="block">
        {population} people.
      </span>
      <span className="mt-1 block text-story-accent">One seat in the House.</span>
    </span>
  );
}
