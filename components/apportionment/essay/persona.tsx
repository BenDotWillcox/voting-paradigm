"use client";

import * as React from "react";

import { generatePersona, type Persona } from "@/lib/apportionment/persona";

import { useStateFocus } from "./state-focus";

/**
 * idle: waiting for Begin. shuffle: cycling occupations. assemble: pieces
 * arriving. complete: the finished person (also where Skip and reduced
 * motion land).
 */
export type PersonaPhase = "idle" | "shuffle" | "assemble" | "complete";

/**
 * Where the finished person is drawn while they travel from the intro's
 * stage into the crowd (see PersonHandoff): on the stage, in flight (a
 * floating overlay), or in the crowd's canvas. null when no handoff is
 * running, in which case both places draw the person themselves.
 */
export type PersonPlace = "stage" | "flight" | "crowd" | null;

interface PersonaValue {
  /** The reader's fictional person, once a state is chosen. */
  persona: Persona | null;
  phase: PersonaPhase;
  setPhase: (phase: PersonaPhase) => void;
  personAt: PersonPlace;
  setPersonAt: (place: PersonPlace) => void;
}

const PersonaContext = React.createContext<PersonaValue | null>(null);
const SEED_KEY = "nebula-civitas.apportionment.visitor-seed";

/**
 * Holds the person for the rest of the essay. The seed is created once per
 * visitor and stored, so the same visitor and state always get the same
 * person: scrolling back, resizing, or replaying never replaces them.
 */
export function PersonaProvider({ children }: { children: React.ReactNode }) {
  const { focus } = useStateFocus();
  const [seed, setSeed] = React.useState<number | null>(null);
  const [phase, setPhase] = React.useState<PersonaPhase>("idle");
  const [personAt, setPersonAt] = React.useState<PersonPlace>(null);

  React.useEffect(() => setSeed(readOrCreateSeed()), []);

  const persona = React.useMemo(
    () => (focus && seed !== null ? generatePersona(seed, focus.fips, focus.seats) : null),
    [focus, seed]
  );

  // A different state is a different person: start their story over.
  const personaKey = persona ? `${persona.seed}:${persona.stateFips}` : null;
  React.useEffect(() => setPhase("idle"), [personaKey]);

  const value = React.useMemo(
    () => ({ persona, phase, setPhase, personAt, setPersonAt }),
    [persona, phase, personAt]
  );
  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>;
}

export function usePersona(): PersonaValue {
  const value = React.useContext(PersonaContext);
  if (!value) throw new Error("usePersona must be used inside PersonaProvider");
  return value;
}

function readOrCreateSeed(): number {
  try {
    const stored = window.localStorage.getItem(SEED_KEY);
    if (stored && /^\d+$/.test(stored)) return Number(stored);
    const created = crypto.getRandomValues(new Uint32Array(1))[0];
    window.localStorage.setItem(SEED_KEY, String(created));
    return created;
  } catch {
    // No storage (private mode): stable for this page view only.
    return 20_200;
  }
}
