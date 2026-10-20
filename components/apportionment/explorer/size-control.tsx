"use client";

import * as React from "react";
import { Minus, Plus } from "lucide-react";

import { NAMED_SIZES, SWEEP_START, SWEEP_STOP, clampSize } from "@/lib/apportionment/house-sizes";
import { cn } from "@/lib/utils";

const LOG_START = Math.log(SWEEP_START);
const LOG_STOP = Math.log(SWEEP_STOP);
/** Slider positions: on a log scale, so 435 to 1,000 gets as much room as 1,000 to 2,300. */
const POSITIONS = 1000;
const toPosition = (size: number) => Math.round(((Math.log(size) - LOG_START) / (LOG_STOP - LOG_START)) * POSITIONS);
const fromPosition = (position: number) =>
  clampSize(Math.exp(LOG_START + (position / POSITIONS) * (LOG_STOP - LOG_START)));

/**
 * The House size: a log-scale slider for the sweep, a seat at a time with
 * the buttons, any exact size typed in, and the essay's named sizes as
 * shortcuts.
 */
export function SizeControl({ size, onChange }: { size: number; onChange: (size: number) => void }) {
  const named = NAMED_SIZES.find((entry) => entry.size === size);
  const listId = React.useId();
  const inputId = React.useId();
  // The typed size, committed on Enter or blur so half-typed numbers don't
  // move the figures.
  const [draft, setDraft] = React.useState<string | null>(null);
  const commit = () => {
    if (draft === null) return;
    const value = Number.parseInt(draft.replace(/[^\d]/g, ""), 10);
    if (Number.isFinite(value)) onChange(clampSize(value));
    setDraft(null);
  };

  return (
    <div className="font-sans">
      <label htmlFor={inputId} className="text-xs text-story-muted">
        House size
      </label>
      <div className="mt-1 flex items-center gap-2">
        <StepButton label="One seat fewer" disabled={size <= SWEEP_START} onClick={() => onChange(size - 1)}>
          <Minus className="size-4" aria-hidden="true" />
        </StepButton>
        <input
          id={inputId}
          inputMode="numeric"
          value={draft ?? size.toLocaleString("en-US")}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") commit();
            if (event.key === "Escape") setDraft(null);
          }}
          aria-describedby={`${inputId}-range`}
          className="w-28 min-w-0 rounded-md border border-transparent bg-transparent px-1 text-center text-3xl leading-tight font-semibold text-story-ink tabular-nums hover:border-story-rule focus:border-story-axis focus:outline-none"
        />
        <StepButton label="One seat more" disabled={size >= SWEEP_STOP} onClick={() => onChange(size + 1)}>
          <Plus className="size-4" aria-hidden="true" />
        </StepButton>
        <span className="text-sm text-story-muted">seats</span>
      </div>
      <p id={`${inputId}-range`} className="sr-only">
        From {SWEEP_START} to {SWEEP_STOP.toLocaleString("en-US")} seats.
      </p>

      <input
        type="range"
        min={0}
        max={POSITIONS}
        value={toPosition(size)}
        onChange={(event) => onChange(fromPosition(Number(event.target.value)))}
        list={listId}
        aria-label="House size, logarithmic scale"
        aria-valuetext={`${size.toLocaleString("en-US")} seats`}
        className="mt-3 w-full accent-[var(--story-accent)]"
      />
      <datalist id={listId}>
        {NAMED_SIZES.map((entry) => (
          <option key={entry.size} value={toPosition(entry.size)} />
        ))}
      </datalist>
      <div className="flex justify-between text-[11px] text-story-muted tabular-nums">
        <span>{SWEEP_START}</span>
        <span>{SWEEP_STOP.toLocaleString("en-US")}</span>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="The essay’s named sizes">
        {NAMED_SIZES.map((entry) => {
          const active = entry.size === size;
          return (
            <button
              key={entry.size}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(entry.size)}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs ring-1 transition-colors",
                active
                  ? "bg-story-ink text-story-page ring-story-ink"
                  : "bg-story-surface text-story-ink-2 ring-story-rule hover:text-story-ink hover:ring-story-axis"
              )}
            >
              <span className="font-semibold tabular-nums">{entry.size.toLocaleString("en-US")}</span>
              <span className={active ? "opacity-80" : "text-story-muted"}> · {entry.label}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-3 min-h-10 text-sm leading-snug text-story-ink-2" aria-live="polite">
        {named ? (
          <>
            <span className="font-semibold text-story-ink">{named.label}.</span> {named.rule}
          </>
        ) : (
          <>Drag the slider, type a size, or add one seat at a time to see which state gets it.</>
        )}
      </p>
    </div>
  );
}

function StepButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-8 shrink-0 place-items-center rounded-full bg-story-surface text-story-ink ring-1 ring-story-rule transition-colors hover:ring-story-axis disabled:opacity-40"
    >
      {children}
    </button>
  );
}
