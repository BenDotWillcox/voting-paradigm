"use client";

import { StoryFigure } from "@/components/story/story-figure";
import { pointsLabel } from "@/lib/liquid/format";
import type { Interval } from "@/lib/liquid/story-types";
import { DIVERGING, SEQUENTIAL, seriesColor } from "@/lib/story/palette";
import { cn } from "@/lib/utils";

import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

/**
 * The declared chain from the district representative to liquid delegation
 * (decomposition.csv). Each step is a matched arm of the frozen benchmark; the
 * platform step is subtracted, the rest added, and they sum to the headline.
 */
export const LADDER = [
  {
    key: "platform_against_record",
    sign: -1,
    label: "Elect the representative by voting record, not platform",
  },
  { key: "cost_of_sharing", sign: 1, label: "Each voter picks their own of the three local candidates" },
  { key: "choice_by_non_voters", sign: 1, label: "…voters who rarely vote get to choose too" },
  {
    key: "city_wide_proxy_combined",
    sign: 1,
    label: "One personal proxy from the whole city",
    detail: "499 candidates, onward delegation, the acceptance level and own-rate attendance, together",
  },
  { key: "specialisation", sign: 1, label: "Eight topic delegates instead of one proxy" },
] as const;

interface Row {
  label: string;
  detail?: string;
  from: number;
  to: number;
  interval?: Interval;
  sign?: number;
  total?: boolean;
}

/** §7, the ladder: where liquid's lead over the representative comes from. */
export function LadderFigure() {
  const { results } = useStoryData();
  const { key, level } = useTurnout();
  const decomposition = results.levels[key].decomposition;
  const total = decomposition.h1;

  const rows: Row[] = [];
  let running = 0;
  for (const step of LADDER) {
    const interval = decomposition[step.key];
    const next = running + step.sign * interval.estimate;
    rows.push({ label: step.label, detail: "detail" in step ? step.detail : undefined, from: running, to: next, interval, sign: step.sign });
    running = next;
  }
  rows.push({ label: "Liquid delegation, against the representative", from: 0, to: total.estimate, interval: total, total: true });

  const values = rows.flatMap((r) => [r.from, r.to, ...(r.interval ? [r.from + (r.sign ?? 1) * r.interval.upper] : [])]);
  const lo = Math.min(0, ...values) - 0.01;
  const hi = Math.max(...values) + 0.01;
  const at = (value: number) => `${((value - lo) / (hi - lo)) * 100}%`;
  const ticks = Array.from({ length: 30 }, (_, i) => -0.1 + i * 0.02).filter((t) => t >= lo && t <= hi);

  return (
    <StoryFigure
      title={`Where liquid's lead comes from, at turnout ${level}`}
      subtitle={`The declared chain of matched arms from the district representative to liquid delegation. The steps add up to the lead: ${pointsLabel(100 * total.estimate)} points.`}
      source="eval/benchmarks/delegation_frontier_v1/decomposition.csv"
      note="Each step is the difference between two arrangements run on the same cities; whiskers are 95% t-intervals. The proxy step bundles several changes that no matched arm separates."
      table={{
        caption: `The ladder at turnout ${level}`,
        columns: [
          { key: "step", label: "Step" },
          { key: "points", label: "Points", numeric: true },
          { key: "interval", label: "95% interval", numeric: true },
        ],
        rows: rows.map((r) => ({
          step: r.label,
          points: pointsLabel(100 * (r.to - r.from)),
          interval: r.interval
            ? `${pointsLabel(100 * (r.sign ?? 1) * (r.sign === -1 ? r.interval.upper : r.interval.lower))} to ${pointsLabel(100 * (r.sign ?? 1) * (r.sign === -1 ? r.interval.lower : r.interval.upper))}`
            : "",
        })),
      }}
    >
      <div className="space-y-2 font-sans">
        {rows.map((row) => {
          const left = Math.min(row.from, row.to);
          const right = Math.max(row.from, row.to);
          const color = row.total ? seriesColor(0) : row.to < row.from ? DIVERGING.negative : SEQUENTIAL[300];
          const whisker = row.interval
            ? [row.from + (row.sign ?? 1) * row.interval.lower, row.from + (row.sign ?? 1) * row.interval.upper].sort(
                (a, b) => a - b
              )
            : null;
          return (
            <div key={row.label} className={cn("grid gap-x-4 gap-y-1 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]", row.total && "border-t border-story-rule pt-2")}>
              <div className="text-sm">
                <span className={cn("text-story-ink", row.total && "font-semibold")}>{row.label}</span>
                <span className="ml-2 text-story-ink-2 tabular-nums">{pointsLabel(100 * (row.to - row.from))}</span>
                {row.detail ? <div className="text-xs text-story-muted">{row.detail}</div> : null}
              </div>
              <div className="relative h-6">
                <div className="absolute inset-y-0 w-px bg-story-axis" style={{ left: at(0) }} />
                <div
                  className="absolute inset-y-1 rounded-sm"
                  style={{ left: at(left), width: `calc(${at(right)} - ${at(left)})`, background: color, minWidth: 2 }}
                />
                {whisker ? (
                  <div
                    className="absolute top-1/2 h-px bg-story-ink"
                    style={{ left: at(whisker[0]), width: `calc(${at(whisker[1])} - ${at(whisker[0])})` }}
                  />
                ) : null}
              </div>
            </div>
          );
        })}
        <div className="grid gap-x-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="hidden md:block" />
          <div className="relative h-5 text-[0.7rem] text-story-muted tabular-nums">
            {ticks.map((t) => (
              <span key={t} className="absolute -translate-x-1/2" style={{ left: at(t) }}>
                {pointsLabel(Math.round(100 * t))}
              </span>
            ))}
          </div>
        </div>
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
    </StoryFigure>
  );
}
