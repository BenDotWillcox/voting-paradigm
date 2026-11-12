import { useId } from "react";
import { cn } from "@/lib/utils";
import { AppLink } from "./app-link";

type Props = {
  /** A short title: two words at most. */
  label: string;
  /** What the number counts, in full; shown on hover and focus. */
  hint: string;
  value: React.ReactNode;
  /** A short addition worth a second glance, such as a deadline. */
  badge?: string;
  /** Values over time, oldest first, drawn as a small line under the number. */
  trend?: number[];
  /** With `onSelect` the cell is a button that picks this stat; with `href` it is a link. */
  selected?: boolean;
  onSelect?: () => void;
  href?: string;
};

/**
 * A row of stats as one readout: a single panel divided into cells, so the
 * numbers read as a set and no cell is a mostly empty box. `columns` are the
 * grid classes for how many cells sit side by side at each width.
 */
export function StatStrip({ columns, children }: { columns: string; children: React.ReactNode }) {
  return <div className={cn("liquid-panel grid", columns)}>{children}</div>;
}

// A hairline on the right and under every cell divides the strip, however the
// cells wrap; at the strip's own edge it falls on the border.
const DIVIDERS = "shadow-[1px_0_0_var(--lq-line),0_1px_0_var(--lq-line)]";
const DIVIDERS_SELECTED =
  "shadow-[1px_0_0_var(--lq-line),0_1px_0_var(--lq-line),inset_0_-2px_0_var(--lq-violet)]";

/**
 * One cell of a StatStrip: a short name over its number, centred, so the
 * cell looks the same at any width. The fuller wording is a tooltip; a badge
 * on the top edge carries the one fact worth adding; a trend line under the
 * number shows how it has moved where there is a history to draw.
 */
export function StatCard({ label, hint, value, badge, trend, selected, onSelect, href }: Props) {
  const tip = useId();
  const body = (
    <>
      <span className="liquid-label">{label}</span>
      <span className="font-mono text-3xl font-semibold tabular-nums leading-none">{value}</span>
      {trend && trend.length > 1 && <Sparkline values={trend} />}
      {badge && (
        <span className="absolute -top-2.5 right-2 rounded-full border border-amber-400/60 bg-[#2a2310] px-2 py-0.5 font-mono text-[0.65rem] leading-tight text-amber-300">
          {badge}
        </span>
      )}
      <span
        id={tip}
        role="tooltip"
        // Under the cell and no wider than it, so it is never cut off by a
        // scrolling panel's edge and never widens one.
        className="pointer-events-none absolute inset-x-1 top-full z-10 mt-1.5 rounded-md border bg-popover px-2 py-1.5 text-center text-xs font-normal normal-case leading-snug tracking-normal text-popover-foreground opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
      >
        {hint}
      </span>
    </>
  );
  const classes = cn(
    "group relative flex min-w-0 flex-col items-center justify-center gap-2 px-3 py-4 text-center transition-colors first:rounded-l-[inherit] last:rounded-r-[inherit]",
    selected ? cn(DIVIDERS_SELECTED, "bg-primary/15") : DIVIDERS,
    (onSelect || href) &&
      "hover:bg-accent focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary",
    selected && "hover:bg-primary/20"
  );
  if (onSelect) {
    return (
      <button
        type="button"
        aria-pressed={selected}
        aria-describedby={tip}
        className={classes}
        onClick={onSelect}
      >
        {body}
      </button>
    );
  }
  if (href) {
    return (
      <AppLink href={href} aria-describedby={tip} className={classes}>
        {body}
      </AppLink>
    );
  }
  return (
    <div tabIndex={0} aria-describedby={tip} className={classes}>
      {body}
    </div>
  );
}

/** A bare line for the shape of a series; the large chart carries the detail. */
function Sparkline({ values }: { values: number[] }) {
  const width = 72;
  const height = 22;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const range = high - low || 1;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * (width - 6) + 3;
    const y = height - 4 - ((value - low) / range) * (height - 8);
    return [x, y] as const;
  });
  const [lastX, lastY] = points[points.length - 1];
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      className="shrink-0"
    >
      <polyline
        points={points.map(([x, y]) => `${x},${y}`).join(" ")}
        fill="none"
        stroke="var(--lq-violet)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r="3" fill="var(--lq-violet)" stroke="var(--background)" strokeWidth="1.5" />
    </svg>
  );
}
