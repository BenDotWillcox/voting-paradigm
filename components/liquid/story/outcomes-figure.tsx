"use client";

import { useElementWidth } from "@/components/story/chart";
import { StoryFigure } from "@/components/story/story-figure";
import { pct } from "@/lib/liquid/format";
import { ARRANGEMENT_LABEL, levelKey, topicLabel, type Arrangement } from "@/lib/liquid/story-types";
import { DIVERGING, INK, seriesColor } from "@/lib/story/palette";

import { DialChart, DialLegend, type DialSeries } from "./dial-chart";
import { useStoryData } from "./story-data";
import { TurnoutDial, useTurnout } from "./turnout";

const percent = (value: number) => `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
const COMPARED: readonly Arrangement[] = ["direct", "liquid", "proxy", "representative"];

/** §11: how often each arrangement's winner is the full-turnout winner, across the dial. */
export function OutcomesFigure() {
  const { measures } = useStoryData();
  const { levels } = useTurnout();
  const m = measures.levels;
  const value = (name: Arrangement) => levels.map((l) => 100 * (m[levelKey(l)][name].outcome_agreement ?? 0));
  const series: DialSeries[] = [
    { key: "direct", label: "Direct voting", color: INK.secondary, values: value("direct") },
    { key: "liquid", label: "Liquid delegation", color: seriesColor(0), values: value("liquid") },
    { key: "proxy", label: "Personal proxy", color: seriesColor(1), dashed: true, values: value("proxy") },
    { key: "representative", label: "District representative", color: seriesColor(1), values: value("representative") },
  ];
  return (
    <StoryFigure
      title="Individuals and outcomes: whose winner matches full turnout"
      subtitle={`The share of questions on which an arrangement's winner is the winner if everyone voted. Means over the ${measures.protocol.cities} primary cities.`}
      source="eval/benchmarks/delegation_frontier_v1/measures.csv"
      table={{
        caption: "Outcome agreement with full turnout per turnout level",
        columns: [
          { key: "level", label: "Turnout", numeric: true },
          ...COMPARED.map((name) => ({ key: name, label: ARRANGEMENT_LABEL[name], numeric: true })),
        ],
        rows: levels.map((l) => ({
          level: l,
          ...Object.fromEntries(COMPARED.map((name) => [name, pct(m[levelKey(l)][name].outcome_agreement ?? 0)])),
        })),
      }}
    >
      <DialLegend series={series} />
      <div className="mt-1">
        <DialChart
          series={series}
          yDomain={[70, 100]}
          yTicks={[70, 80, 90, 100]}
          yFormat={percent}
          yLabel="Questions"
          height={240}
          ariaLabel="Outcome agreement with full turnout across the turnout dial"
        />
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
    </StoryFigure>
  );
}

/**
 * The illustrative city's questions under each arrangement: where its winner
 * differs from full turnout's. The representative's misses are the
 * Ostrogorski-style cases: a council elected on bundled platforms losing the
 * issue-by-issue majority.
 */
export function OutcomeStrip() {
  const { city } = useStoryData();
  const { key, level } = useTurnout();
  const winners = city.levels[key].winners;
  const full = winners.full_turnout;
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const questions = full.length;
  const misses = (name: Arrangement) => Array.from(winners[name]).filter((w, q) => w !== full[q]).length;
  const labelWidth = width < 480 ? 0 : 180;
  const cell = width > 0 ? (width - labelWidth) / questions : 0;

  return (
    <StoryFigure
      title={`One city's ${questions} questions at turnout ${level}: where the winner differs from full turnout`}
      subtitle={`A council of ${city.design.districts} representatives loses the issue-by-issue majority on ${misses("representative")} of ${questions}; liquid on ${misses("liquid")}, direct voting on ${misses("direct")}.`}
      source="Primary city 1, recomputed with the frozen code"
      table={{
        caption: `Questions whose winner differs from full turnout at ${level}`,
        columns: [
          { key: "arrangement", label: "Arrangement" },
          { key: "misses", label: "Different winner", numeric: true },
        ],
        rows: COMPARED.map((name) => ({ arrangement: ARRANGEMENT_LABEL[name], misses: misses(name) })),
      }}
    >
      <div ref={ref} className="space-y-2 font-sans">
        {width > 0
          ? COMPARED.map((name) => (
              <div key={name} className={labelWidth ? "flex items-center" : ""}>
                <div className="text-xs text-story-ink-2" style={labelWidth ? { width: labelWidth } : undefined}>
                  {ARRANGEMENT_LABEL[name]} · {misses(name)}
                </div>
                <svg width={questions * cell} height={16} aria-hidden="true" className="block">
                  {Array.from(winners[name]).map((w, q) => (
                    <rect
                      key={q}
                      x={q * cell}
                      y={0}
                      width={Math.max(1, cell - 0.5)}
                      height={16}
                      fill={w === full[q] ? INK.grid : DIVERGING.negative}
                    >
                      <title>{`Question ${q + 1} (${topicLabel(city.topics[city.mechanism.typical.questions[q]])})`}</title>
                    </rect>
                  ))}
                </svg>
              </div>
            ))
          : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 font-sans text-xs text-story-ink-2">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: DIVERGING.negative }} /> Different winner
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: INK.grid }} /> Same winner
        </span>
      </div>
      <TurnoutDial className="mt-4 max-w-xl" />
    </StoryFigure>
  );
}
