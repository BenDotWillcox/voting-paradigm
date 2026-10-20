"use client";

import * as React from "react";
import { Minus, Plus } from "lucide-react";

import { EnvelopeChart, SizeStrip } from "@/components/apportionment/essay/bigger-figure";
import { useStateFocus } from "@/components/apportionment/essay/state-focus";
import { StateTileMap } from "@/components/apportionment/essay/state-map";
import { StateSwarm } from "@/components/apportionment/essay/state-swarm";
import { useElementWidth } from "@/components/story/chart";
import { NumberTicker } from "@/components/story/number-ticker";
import {
  COST_PER_MEMBER,
  NAMED_SIZES,
  SWEEP_START,
  SWEEP_STOP,
  averageAt,
  clampSize,
  seatsFor,
  spreadAt,
} from "@/lib/apportionment/house-sizes";
import { cn } from "@/lib/utils";

import { NextSeat } from "./next-seat";
import { SizeControl } from "./size-control";
import { StatePanel } from "./state-panel";

/**
 * The essay's companion: any House size from 435 to 11,036, with the same
 * figures and vocabulary as the essay's Act IV. The size lives in `?size=`;
 * the reader's state is the essay's (`?state=` and storage).
 */
export function SizeExplorer({ initialSize }: { initialSize: number }) {
  const [size, setSizeState] = React.useState(initialSize);
  const setSize = React.useCallback((next: number) => setSizeState(clampSize(next)), []);

  // Mirror the size to the URL, so a reload or a shared link keeps it.
  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      const url = new URL(window.location.href);
      if (size === SWEEP_START) url.searchParams.delete("size");
      else url.searchParams.set("size", String(size));
      url.searchParams.delete("cap");
      window.history.replaceState(window.history.state, "", url);
    }, 200);
    return () => window.clearTimeout(timer);
  }, [size]);

  // Phones: once the size control scrolls away, a bar at the bottom keeps
  // the size in hand.
  const controlRef = React.useRef<HTMLDivElement | null>(null);
  const [controlHidden, setControlHidden] = React.useState(false);
  React.useEffect(() => {
    const node = controlRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) =>
      setControlHidden(!entry.isIntersecting && entry.boundingClientRect.top < 0)
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="grid gap-x-10 gap-y-8 lg:grid-cols-[21rem_minmax(0,1fr)]">
      {/* The size and its numbers stay in view beside every figure. */}
      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <div ref={controlRef} className="rounded-xl bg-story-surface p-4 ring-1 ring-story-rule">
          <SizeControl size={size} onChange={setSize} />
        </div>
        <Metrics size={size} />
      </aside>

      <div className="min-w-0 space-y-12">
        <StatesFigure size={size} />
        <div className="rounded-xl bg-story-surface p-4 ring-1 ring-story-rule sm:p-5">
          <StatePanel size={size} />
        </div>
        <NextSeat size={size} onAdd={() => setSize(size + 1)} />
        <EverySize size={size} onPick={setSize} />
        <section aria-labelledby="named-sizes-title">
          <h2 id="named-sizes-title" className="font-story-serif text-2xl font-medium text-story-ink">
            Against the essay’s sizes
          </h2>
          <p className="mt-1 mb-3 font-sans text-sm text-story-ink-2">
            Both gaps at each size the essay stopped at
            {NAMED_SIZES.some((entry) => entry.size === size) ? "" : ", with yours in order"}.
          </p>
          <NamedSizesTable size={size} />
        </section>
      </div>
      <MiniControl
        size={size}
        onChange={setSize}
        visible={controlHidden}
        onOpen={() => controlRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
      />
    </div>
  );
}

/** The comparison table, with short headings where the page is narrow. */
function NamedSizesTable({ size }: { size: number }) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  return (
    <div ref={ref}>
      <SizeStrip area={{ left: 0, width }} current={size} compact={width > 0 && width < 560} inline everyRow />
    </div>
  );
}

/** The phone bar: a seat fewer, the size (back to the full control), a seat more. */
function MiniControl({
  size,
  onChange,
  visible,
  onOpen,
}: {
  size: number;
  onChange: (size: number) => void;
  visible: boolean;
  onOpen: () => void;
}) {
  return (
    <div
      aria-hidden={!visible}
      className={cn(
        "fixed inset-x-0 bottom-0 z-30 flex justify-center px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] transition-[translate,opacity] duration-300 lg:hidden",
        visible ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-4 opacity-0"
      )}
    >
      <div className="flex items-center gap-1 rounded-full bg-story-ink p-1 font-sans text-story-page shadow-lg">
        <button
          type="button"
          aria-label="One seat fewer"
          tabIndex={visible ? 0 : -1}
          disabled={size <= SWEEP_START}
          onClick={() => onChange(size - 1)}
          className="grid size-9 place-items-center rounded-full hover:bg-white/10 disabled:opacity-40"
        >
          <Minus className="size-4" aria-hidden="true" />
        </button>
        <button type="button" tabIndex={visible ? 0 : -1} onClick={onOpen} className="px-2 text-sm font-semibold tabular-nums">
          {size.toLocaleString("en-US")} seats
        </button>
        <button
          type="button"
          aria-label="One seat more"
          tabIndex={visible ? 0 : -1}
          disabled={size >= SWEEP_STOP}
          onClick={() => onChange(size + 1)}
          className="grid size-9 place-items-center rounded-full hover:bg-white/10 disabled:opacity-40"
        >
          <Plus className="size-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

/** "$914 million", "$2.10 billion", "$23.2 billion": as in the essay. */
function dollars(amount: number): string {
  if (amount < 1e9) return `$${Math.round(amount / 1e6).toLocaleString("en-US")} million`;
  return `$${(amount / 1e9).toFixed(amount < 1e10 ? 2 : 1)} billion`;
}

/** Both gaps and the cost at this size, each against today's House. */
function Metrics({ size }: { size: number }) {
  const { states } = useStateFocus();
  const nameOf = (fips: string) => states.find((state) => state.fips === fips)?.name ?? fips;
  const spread = spreadAt(size);
  const today = spreadAt(SWEEP_START);
  const average = averageAt(size);
  const shrink = Math.round((1 - SWEEP_START / size) * 100 + 1e-9);
  const changed = size !== SWEEP_START;

  return (
    <dl className="grid grid-cols-2 gap-3 font-sans">
      <Metric label="Average people per seat" note={changed ? `${shrink}% fewer than today` : "Today’s House"}>
        <NumberTicker value={Math.round(average)} />
      </Metric>
      <Metric
        label="Highest ÷ lowest state average"
        note={`${nameOf(spread.largest.fips)} ÷ ${nameOf(spread.smallest.fips)}${changed ? ` · today ${today.ratio.toFixed(2)}×` : ""}`}
      >
        <NumberTicker value={spread.ratio} decimals={2} suffix="×" />
      </Metric>
      <Metric
        label="Typical state’s gap"
        note={`Half the states are closer to the average${changed ? ` · today ±${(today.typical * 100).toFixed(1)}%` : ""}`}
      >
        ±<NumberTicker value={spread.typical * 100} decimals={1} suffix="%" />
      </Metric>
      <Metric
        label="Pay and allowances a year"
        note={changed ? `+${dollars((size - SWEEP_START) * COST_PER_MEMBER)} at today’s rates` : "At today’s rates"}
      >
        {dollars(size * COST_PER_MEMBER)}
      </Metric>
    </dl>
  );
}

function Metric({ label, note, children }: { label: string; note: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-story-surface px-3 py-2.5 ring-1 ring-story-rule">
      <dt className="text-xs leading-tight text-story-muted">{label}</dt>
      <dd className="mt-1 text-xl leading-tight font-semibold text-story-ink tabular-nums">{children}</dd>
      <dd className="mt-0.5 text-xs leading-snug text-story-ink-2">{note}</dd>
    </div>
  );
}

/** Every state at this size: the essay's dot chart, or the tile map. */
function StatesFigure({ size }: { size: number }) {
  const [view, setView] = React.useState<"dots" | "map">("dots");
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const height = width < 560 ? 280 : 380;
  const seats = React.useMemo(() => seatsFor(size), [size]);

  return (
    <section aria-labelledby="states-title">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="states-title" className="font-story-serif text-2xl font-medium text-story-ink">
          Every state at {size.toLocaleString("en-US")} seats
        </h2>
        <div role="group" aria-label="Show the states as" className="flex rounded-full bg-story-surface p-0.5 font-sans text-sm ring-1 ring-story-rule">
          {(
            [
              ["dots", "Dot chart"],
              ["map", "Map"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={view === key}
              onClick={() => setView(key)}
              className={cn(
                "rounded-full px-3 py-1 transition-colors",
                view === key ? "bg-story-ink text-story-page" : "text-story-ink-2 hover:text-story-ink"
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div ref={ref} className="mt-3">
        {view === "dots" ? (
          <>
            <div className="relative" style={{ height }}>
              {width > 0 ? (
                <StateSwarm
                  area={{ left: 0, width }}
                  height={height}
                  size={size}
                  relative
                  nationalAverage={averageAt(SWEEP_START)}
                  dim={false}
                  pickable
                />
              ) : null}
            </div>
            <p className="mt-1 font-sans text-sm text-story-ink-2">
              One dot per state: its average people per seat, above or below the national average at this size. The
              colors match the map. Click a dot to follow that state.
            </p>
          </>
        ) : (
          <StateTileMap seats={seats} nationalAverage={averageAt(size)} size={size} className="mx-auto max-w-xl" />
        )}
      </div>
    </section>
  );
}

/** The essay's envelope: every size at once, with this one marked; a click picks another. */
function EverySize({ size, onPick }: { size: number; onPick: (size: number) => void }) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const height = width < 560 ? 320 : 360;
  return (
    <section aria-labelledby="every-size-title">
      <h2 id="every-size-title" className="font-story-serif text-2xl font-medium text-story-ink">
        Every size from {SWEEP_START} to {SWEEP_STOP.toLocaleString("en-US")}
      </h2>
      <p className="mt-1 font-sans text-sm text-story-ink-2">
        The highest and lowest state averages at each size, and the band that holds half the states. Click or tap
        anywhere on the chart to jump to that size.
      </p>
      <div ref={ref} className="relative mt-3" style={{ height }}>
        {width > 0 ? (
          <EnvelopeChart
            area={{ left: 0, width }}
            height={height}
            reveal={1}
            marker={size}
            onPick={(picked) => onPick(picked)}
            pickHint="Click to choose this size"
          />
        ) : null}
      </div>
    </section>
  );
}
