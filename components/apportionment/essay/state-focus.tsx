"use client";

import * as React from "react";

import type { EssayState } from "@/lib/apportionment/essay-data";

interface StateFocusValue {
  states: readonly EssayState[];
  focus: EssayState | null;
  setFocus: (fips: string | null) => void;
}

const StateFocusContext = React.createContext<StateFocusValue | null>(null);
const STORAGE_KEY = "nebula-civitas.apportionment.state";

/**
 * The reader's chosen state, shared by every figure in the essay. Mirrored to
 * `?state=` (postal abbreviation, so links are shareable) and localStorage
 * (so it survives a reload). Read on the client after hydration; the static
 * page renders without a highlight first.
 */
export function StateFocusProvider({
  states,
  children,
}: {
  states: readonly EssayState[];
  children: React.ReactNode;
}) {
  const [focus, setFocusState] = React.useState<EssayState | null>(null);

  React.useEffect(() => {
    const byAbbr = (abbr: string | null) =>
      states.find((state) => state.abbr.toLowerCase() === abbr?.toLowerCase()) ?? null;
    const fromUrl = byAbbr(new URLSearchParams(window.location.search).get("state"));
    setFocusState(fromUrl ?? byAbbr(readStorage()));
  }, [states]);

  const setFocus = React.useCallback(
    (fips: string | null) => {
      const next = states.find((state) => state.fips === fips) ?? null;
      setFocusState(next);
      writeStorage(next?.abbr ?? null);
      const url = new URL(window.location.href);
      if (next) url.searchParams.set("state", next.abbr.toLowerCase());
      else url.searchParams.delete("state");
      window.history.replaceState(window.history.state, "", url);
    },
    [states]
  );

  const value = React.useMemo(() => ({ states, focus, setFocus }), [states, focus, setFocus]);
  return <StateFocusContext.Provider value={value}>{children}</StateFocusContext.Provider>;
}

export function useStateFocus(): StateFocusValue {
  const value = React.useContext(StateFocusContext);
  if (!value) throw new Error("useStateFocus must be used inside StateFocusProvider");
  return value;
}

function readStorage(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStorage(abbr: string | null): void {
  try {
    if (abbr) window.localStorage.setItem(STORAGE_KEY, abbr);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode); the URL still carries it.
  }
}
