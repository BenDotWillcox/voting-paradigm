"use client";

import * as React from "react";

import { cn } from "@/lib/utils";
import { levelKey, type LevelKey } from "@/lib/liquid/story-types";

interface TurnoutState {
  levels: readonly number[];
  swiss: number;
  level: number;
  key: LevelKey;
  setLevel: (level: number) => void;
  /** Set when the level is held fixed: the note a dial shows in its place. */
  fixed: React.ReactNode | null;
  /**
   * Whether figures show the everyone-votes reference point (exploratory)
   * instead of a turnout level: held fixed, or picked on the dial where the
   * provider offers that stop.
   */
  everyone: boolean;
  /** Whether the dial offers "everyone votes" as a stop. */
  everyoneStop: boolean;
  /** Moves the dial to the everyone-votes stop, where it is offered. */
  selectEveryone: () => void;
}

const TurnoutContext = React.createContext<TurnoutState | null>(null);

/**
 * The page's one control: mean citizen turnout. Every turnout-dependent
 * figure reads it, and every dial on the page sets it, so moving any dial
 * moves them all. It snaps to the recorded levels; nothing between them is
 * interpolated.
 *
 * With `fixed`, the level stays at Swiss turnout and every dial inside shows
 * that note instead, so a stretch of the page can be read at one turnout
 * before the reader is handed the dial. With `everyone` as well, figures
 * that support it show the everyone-votes reference point instead (see
 * `useSetting`), so the story can show the idea before turnout enters.
 *
 * With `everyoneStop`, the dial also offers "everyone votes" as a stop, and
 * starts there. Such a provider shares the turnout levels with the provider
 * around it, so moving a dial anywhere on the page still moves every other;
 * the everyone stop applies only inside it, where the figures support it.
 */
export function TurnoutProvider({
  levels,
  swiss,
  fixed = null,
  everyone = false,
  everyoneStop = false,
  children,
}: {
  levels: readonly number[];
  swiss: number;
  fixed?: React.ReactNode;
  everyone?: boolean;
  everyoneStop?: boolean;
  children: React.ReactNode;
}) {
  const parent = React.useContext(TurnoutContext);
  const [ownLevel, setOwnLevel] = React.useState(swiss);
  const shared = everyoneStop && parent && !parent.fixed ? parent : null;
  const level = shared ? shared.level : ownLevel;
  const setBase = shared ? shared.setLevel : setOwnLevel;
  const [atEveryone, setAtEveryone] = React.useState(everyoneStop);

  // A dial elsewhere that moves the shared level moves this stretch off the everyone stop
  const seen = React.useRef(level);
  React.useEffect(() => {
    if (seen.current === level) return;
    seen.current = level;
    setAtEveryone(false);
  }, [level]);

  const setLevel = React.useCallback(
    (next: number) => {
      setAtEveryone(false);
      setBase(next);
    },
    [setBase]
  );
  const selectEveryone = React.useCallback(() => setAtEveryone(true), []);
  const showsEveryone = everyone || (everyoneStop && atEveryone);
  const value = React.useMemo(
    () => ({
      levels,
      swiss,
      level,
      key: levelKey(level),
      setLevel,
      fixed,
      everyone: showsEveryone,
      everyoneStop,
      selectEveryone,
    }),
    [levels, swiss, level, setLevel, fixed, showsEveryone, everyoneStop, selectEveryone]
  );
  if (everyone && !fixed) throw new Error("the everyone-votes setting is held fixed: give it a note");
  return <TurnoutContext.Provider value={value}>{children}</TurnoutContext.Provider>;
}

export function useTurnout(): TurnoutState {
  const value = React.useContext(TurnoutContext);
  if (!value) throw new Error("useTurnout must be used inside <TurnoutProvider>");
  return value;
}

/** A stop on the dial: a recorded turnout level, or everyone voting. */
type Stop = number | "everyone";

/**
 * The turnout dial: the recorded levels as one radio group, Swiss turnout
 * marked, and "All" after them where everyone votes is offered. Arrow keys
 * step through the stops.
 */
export function TurnoutDial({ className, label = "Mean citizen turnout" }: { className?: string; label?: string }) {
  const { levels, swiss, level, setLevel, fixed, everyone, everyoneStop, selectEveryone } = useTurnout();
  const id = React.useId();
  const buttons = React.useRef<Array<HTMLButtonElement | null>>([]);

  if (fixed) {
    return <p className={cn("font-sans text-xs text-story-muted", className)}>{fixed}</p>;
  }

  const stops: Stop[] = everyoneStop ? [...levels, "everyone"] : [...levels];
  const current: Stop = everyoneStop && everyone ? "everyone" : level;
  const choose = (stop: Stop) => (stop === "everyone" ? selectEveryone() : setLevel(stop));
  const step = (index: number) => {
    const next = Math.max(0, Math.min(stops.length - 1, index));
    choose(stops[next]);
    buttons.current[next]?.focus();
  };

  return (
    <div className={cn("font-sans", className)}>
      <div id={id} className="mb-1.5 text-xs font-medium text-story-ink-2">
        {label}
        {everyoneStop ? <span className="font-normal text-story-muted"> · All: everyone votes</span> : null}
      </div>
      <div
        role="radiogroup"
        aria-labelledby={id}
        className="flex w-full rounded-md bg-story-page p-0.5 ring-1 ring-story-rule"
        onKeyDown={(event) => {
          const index = stops.indexOf(current);
          if (event.key === "ArrowRight" || event.key === "ArrowUp") {
            event.preventDefault();
            step(index + 1);
          } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
            event.preventDefault();
            step(index - 1);
          } else if (event.key === "Home") {
            event.preventDefault();
            step(0);
          } else if (event.key === "End") {
            event.preventDefault();
            step(stops.length - 1);
          }
        }}
      >
        {stops.map((value, index) => {
          const active = value === current;
          return (
            <button
              key={value}
              ref={(node) => {
                buttons.current[index] = node;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              aria-label={
                value === "everyone"
                  ? "Everyone votes (exploratory)"
                  : value === swiss
                    ? `${value}, Swiss turnout`
                    : String(value)
              }
              tabIndex={active ? 0 : -1}
              onClick={() => choose(value)}
              className={cn(
                "relative flex-1 rounded px-0.5 pt-1 pb-2 text-xs tabular-nums transition-colors",
                active
                  ? "bg-story-surface font-semibold text-story-ink shadow-sm ring-1 ring-story-rule"
                  : "text-story-muted hover:text-story-ink"
              )}
            >
              {value === "everyone" ? "All" : value}
              {value === swiss ? (
                <span
                  aria-hidden="true"
                  className="absolute inset-x-0 bottom-0.5 text-center text-[0.55rem] leading-none tracking-wide text-story-accent"
                >
                  CH
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
