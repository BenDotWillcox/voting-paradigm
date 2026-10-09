"use client";

import * as React from "react";

import { useElementWidth } from "@/components/story/chart";
import { SWEEP_START, SWEEP_STOP } from "@/lib/apportionment-sweep";
import { ROLES, districtLabel } from "@/lib/apportionment/persona";
import { INK } from "@/lib/story/palette";

import { NAMED_SIZES } from "./bigger-figure";
import { RUSH_STEPS, PersonFigure } from "./person-figure";
import { usePersona } from "./persona";
import { useStateFocus } from "./state-focus";
import { averageAt, seatsFor, sweepData } from "./state-swarm";

const about = (n: number) => (Math.round(n / 1000) * 1000).toLocaleString("en-US");

/**
 * The coda: the person from the opening, and how many people would share
 * their representative at each House size the essay stopped at, then their
 * state (or the country) at every size from 435 to 11,036.
 */
export function Coda() {
  const { focus } = useStateFocus();
  const { persona } = usePersona();
  const rows = NAMED_SIZES.map(({ size, label }) => ({
    size,
    label,
    people: focus ? focus.population / seatsFor(size)[focus.fips] : averageAt(size),
  }));
  const who =
    persona && focus
      ? `One ${persona.role.noun} in ${districtLabel(focus.name, persona.district)}`
      : focus
        ? `One person in ${focus.name}`
        : "One person, anywhere in the 50 states";
  const max = rows[0].people;

  return (
    <section id="coda" aria-labelledby="coda-heading" className="mx-auto mt-24 max-w-5xl px-4">
      <div className="grid items-center gap-10 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="flex justify-center text-story-ink">
          {persona ? (
            <PersonFigure
              roleId={persona.role.id}
              mode="assembled"
              arrived={3 + RUSH_STEPS}
              readableCategories={persona.readable.map((piece) => piece.category)}
              seed={persona.seed}
              className="h-64 w-auto sm:h-80"
              title={`${who}.`}
            />
          ) : (
            <PersonFigure
              roleId={ROLES[0].id}
              mode="plain"
              arrived={0}
              seed={1}
              className="h-64 w-auto text-story-muted sm:h-80"
              title="A person"
            />
          )}
        </div>
        <div className="font-story-serif text-story-ink">
          <h2 id="coda-heading" className="text-3xl leading-tight font-medium tracking-[-0.01em] sm:text-4xl">
            Back to one person.
          </h2>
          <p className="mt-4 text-lg leading-relaxed sm:text-xl">
            {who} {focus ? "lives in a state that averages" : "is one of"} about {about(rows[0].people)}{" "}
            people per House seat{focus ? "" : " on average"}, using the 2020 census. Here is that average in a
            bigger House:
          </p>
          <ol className="mt-6 space-y-3 font-sans">
            {rows.map((row, i) => (
              <li key={row.size} className="grid grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
                <span className="text-sm leading-tight">
                  <span className="font-semibold tabular-nums">{row.size.toLocaleString("en-US")} seats</span>
                  <span className="block text-xs text-story-muted">{row.label}</span>
                </span>
                <span className="flex items-center gap-2">
                  <span
                    className="h-3 shrink-0 rounded-sm"
                    style={{
                      width: `${Math.max(1, (row.people / max) * 50)}%`,
                      background: i === 0 ? "var(--gap-more-3)" : "var(--story-seat-focus)",
                    }}
                  />
                  <span className="text-sm whitespace-nowrap tabular-nums">about {about(row.people)}</span>
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-4 font-sans text-xs leading-relaxed text-story-muted">
            Averages: apportionment population divided by seats, not the population of any actual district.
            Figures cover the 50 states, the only places apportioned House seats; Washington, D.C., and the
            territories send nonvoting delegates.
          </p>
        </div>
      </div>

      <div className="mx-auto mt-16 max-w-3xl">
        <StateAtEverySize />
      </div>
    </section>
  );
}

/**
 * The reader's state (or the country) at every House size: people per seat
 * on log scales, a sawtooth for a state as it gains seats one at a time,
 * against the national average.
 */
function StateAtEverySize() {
  const { focus } = useStateFocus();
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const height = 260;
  const compact = width < 520;
  const plot = { left: compact ? 40 : 52, right: width - 12, top: 16, bottom: height - 30 };
  const lx = (size: number) =>
    plot.left + ((Math.log(size) - Math.log(SWEEP_START)) / (Math.log(SWEEP_STOP) - Math.log(SWEEP_START))) * (plot.right - plot.left);
  const [lo, hi] = [20_000, 1_200_000];
  const ly = (v: number) => plot.bottom - ((Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * (plot.bottom - plot.top);

  const line = React.useMemo(() => {
    if (width === 0) return { state: "", average: "" };
    const { order } = sweepData();
    const fips = focus?.fips ?? null;
    let seats = fips ? seatsFor(SWEEP_START)[fips] : 0;
    const state: string[] = [];
    const average: string[] = [];
    let lastX = -1;
    for (let size = SWEEP_START; size <= SWEEP_STOP; size++) {
      if (fips && size > SWEEP_START && order[size - 51] === fips) seats += 1;
      const px = lx(size);
      // One point per pixel column keeps the path small; a step drawn as
      // a vertical drop where the state gains a seat keeps the sawtooth.
      if (px - lastX < 1 && size !== SWEEP_STOP) continue;
      lastX = px;
      average.push(`${average.length ? "L" : "M"}${px.toFixed(1)},${ly(averageAt(size)).toFixed(1)}`);
      if (focus) state.push(`${state.length ? "L" : "M"}${px.toFixed(1)},${ly(focus.population / seats).toFixed(1)}`);
    }
    return { state: state.join(""), average: average.join("") };
    // lx and ly are derived from width.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus, width]);

  return (
    <figure ref={ref} className="font-sans">
      <figcaption className="mb-2 text-sm font-semibold text-story-ink">
        {focus ? `${focus.name} at every House size` : "The 50 states at every House size"}
        <span className="block text-xs font-normal text-story-muted">
          Average people per seat, 2020 census, from 435 to 11,036 seats (both scales logarithmic)
          {focus ? "; the dashed line is the national average" : ""}
        </span>
      </figcaption>
      {width > 0 ? (
        <svg width={width} height={height} role="img" aria-label={`People per seat ${focus ? `in ${focus.name}` : "on average"} at every House size from 435 to 11,036.`}>
          {[30_000, 100_000, 300_000, 1_000_000].map((tick) => (
            <g key={tick}>
              <line x1={plot.left} x2={plot.right} y1={ly(tick)} y2={ly(tick)} stroke={INK.grid} />
              <text x={plot.left - 6} y={ly(tick)} dy="0.32em" textAnchor="end" fontSize={11} fill={INK.muted}>
                {tick >= 1_000_000 ? "1M" : `${tick / 1000}k`}
              </text>
            </g>
          ))}
          {NAMED_SIZES.map(({ size }) => (
            <g key={size}>
              <line x1={lx(size)} x2={lx(size)} y1={plot.top} y2={plot.bottom + 4} stroke={INK.axis} />
              <text
                x={lx(size)}
                y={plot.bottom + 18}
                textAnchor={size === SWEEP_STOP ? "end" : size === SWEEP_START ? "start" : "middle"}
                fontSize={11}
                fill={INK.muted}
                className="tabular-nums"
              >
                {compact && size === 573 ? "" : size.toLocaleString("en-US")}
              </text>
            </g>
          ))}
          <path d={line.average} fill="none" stroke={focus ? INK.secondary : "var(--story-seat-focus)"} strokeWidth={focus ? 1.5 : 2.5} strokeDasharray={focus ? "4 4" : undefined} />
          {focus ? <path d={line.state} fill="none" stroke="var(--story-seat-focus)" strokeWidth={2} strokeLinejoin="round" /> : null}
        </svg>
      ) : (
        <div style={{ height }} />
      )}
    </figure>
  );
}
