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
}

const TurnoutContext = React.createContext<TurnoutState | null>(null);

/**
 * The page's one control: mean citizen turnout. Every turnout-dependent
 * figure reads it, and every dial on the page sets it, so moving any dial
 * moves them all. It snaps to the recorded levels; nothing between them is
 * interpolated.
 */
export function TurnoutProvider({
  levels,
  swiss,
  children,
}: {
  levels: readonly number[];
  swiss: number;
  children: React.ReactNode;
}) {
  const [level, setLevel] = React.useState(swiss);
  const value = React.useMemo(
    () => ({ levels, swiss, level, key: levelKey(level), setLevel }),
    [levels, swiss, level]
  );
  return <TurnoutContext.Provider value={value}>{children}</TurnoutContext.Provider>;
}

export function useTurnout(): TurnoutState {
  const value = React.useContext(TurnoutContext);
  if (!value) throw new Error("useTurnout must be used inside <TurnoutProvider>");
  return value;
}

/**
 * The turnout dial: the recorded levels as one radio group, Swiss turnout
 * marked. Arrow keys step through the levels.
 */
export function TurnoutDial({ className, label = "Mean citizen turnout" }: { className?: string; label?: string }) {
  const { levels, swiss, level, setLevel } = useTurnout();
  const id = React.useId();
  const buttons = React.useRef<Array<HTMLButtonElement | null>>([]);

  const step = (index: number) => {
    const next = Math.max(0, Math.min(levels.length - 1, index));
    setLevel(levels[next]);
    buttons.current[next]?.focus();
  };

  return (
    <div className={cn("font-sans", className)}>
      <div id={id} className="mb-1.5 text-xs font-medium text-story-ink-2">
        {label}
      </div>
      <div
        role="radiogroup"
        aria-labelledby={id}
        className="flex w-full rounded-md bg-story-page p-0.5 ring-1 ring-story-rule"
        onKeyDown={(event) => {
          const index = levels.indexOf(level);
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
            step(levels.length - 1);
          }
        }}
      >
        {levels.map((value, index) => {
          const active = value === level;
          return (
            <button
              key={value}
              ref={(node) => {
                buttons.current[index] = node;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              aria-label={value === swiss ? `${value}, Swiss turnout` : String(value)}
              tabIndex={active ? 0 : -1}
              onClick={() => setLevel(value)}
              className={cn(
                "relative flex-1 rounded px-0.5 pt-1 pb-2 text-xs tabular-nums transition-colors",
                active
                  ? "bg-story-surface font-semibold text-story-ink shadow-sm ring-1 ring-story-rule"
                  : "text-story-muted hover:text-story-ink"
              )}
            >
              {value}
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
