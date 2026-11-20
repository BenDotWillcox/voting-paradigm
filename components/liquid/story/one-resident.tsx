"use client";

import * as React from "react";

import { useElementWidth } from "@/components/story/chart";
import { StoryFigure } from "@/components/story/story-figure";
import { pct, resident } from "@/lib/liquid/format";
import { topicLabel, type BallotCode } from "@/lib/liquid/story-types";
import { INK } from "@/lib/story/palette";

import { BallotLegend, ballotLook, tally } from "./city-dots";
import { useSetting } from "./setting";
import { useStoryData } from "./story-data";

const PANELS = [
  { key: "direct", title: "Voting themself" },
  { key: "liquid", title: "Liquid delegation" },
] as const;

/**
 * §2: the two measures on one resident. Each panel holds their 160 scored
 * questions, a row per topic: fidelity is the share of blue dots, overhead
 * the share of filled ones (questions they decide themself). Under the
 * everyone-votes setting it shows the same resident voting on everything.
 */
export function OneResident() {
  const { city } = useStoryData();
  const { everyone } = useSetting();
  const { typical, level } = city.mechanism;
  const perTopic = city.design.evaluation_per_topic;
  const strips = everyone ? city.everyone.typical_strips : typical.strips;

  const panels = PANELS.map(({ key, title }) => {
    const strip = strips[key];
    const counts = tally(strip);
    return { key, title, strip, counts };
  });

  return (
    <StoryFigure
      title={
        everyone
          ? `${resident(typical.voter)}'s ${typical.questions.length} scored questions, with everyone voting`
          : `${resident(typical.voter)}'s ${typical.questions.length} scored questions at Swiss turnout (${level})`
      }
      subtitle={
        everyone
          ? "They vote on every question themselves. Under liquid delegation they hand every topic to someone else."
          : `They vote on about ${pct(typical.turnout, 0)} of questions themselves. Under liquid delegation they hand every topic to someone else.`
      }
      source={`Primary city 1, recomputed with the frozen code${everyone ? " (the everyone-votes setting, exploratory)" : ""}`}
      note="Fidelity counts a ballot against them the same as no ballot. A later section returns to that choice."
      table={{
        caption: `${resident(typical.voter)}'s ballots, counted`,
        columns: [
          { key: "arrangement", label: "Arrangement" },
          { key: "match", label: "Matches them", numeric: true },
          { key: "contrary", label: "Against them", numeric: true },
          { key: "none", label: "No ballot", numeric: true },
          { key: "own", label: "Decided themself", numeric: true },
        ],
        rows: panels.map(({ title, counts }) => ({
          arrangement: title,
          match: counts.match,
          contrary: counts.contrary,
          none: counts.none,
          own: counts.own,
        })),
      }}
    >
      <div className="grid gap-6 md:grid-cols-2">
        {panels.map(({ key, title, strip, counts }) => (
          <div key={key}>
            <div className="mb-2 font-sans text-sm font-semibold text-story-ink">{title}</div>
            <QuestionGrid strip={strip} topics={typical.questions} labels={city.topics} perTopic={perTopic} />
            <dl className="mt-3 grid grid-cols-2 gap-3 font-sans text-xs">
              <div>
                <dt className="text-story-muted">Fidelity</dt>
                <dd className="text-lg font-semibold text-story-ink tabular-nums">{pct(counts.match / strip.length)}</dd>
                <dd className="text-story-ink-2">
                  {counts.match} of {strip.length} match
                </dd>
              </div>
              <div>
                <dt className="text-story-muted">Overhead</dt>
                <dd className="text-lg font-semibold text-story-ink tabular-nums">{pct(counts.own / strip.length, 0)}</dd>
                <dd className="text-story-ink-2">
                  decides {counts.own === strip.length ? "all" : counts.own} of {strip.length}
                </dd>
              </div>
            </dl>
          </div>
        ))}
      </div>
      <BallotLegend className="mt-4" />
    </StoryFigure>
  );
}

/** One resident's questions: a row per topic, its questions in order. */
function QuestionGrid({
  strip,
  topics,
  labels,
  perTopic,
}: {
  strip: string;
  topics: number[];
  labels: string[];
  perTopic: number;
}) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const rows = React.useMemo(() => {
    const byTopic: Array<Array<BallotCode>> = labels.map(() => []);
    topics.forEach((topic, question) => byTopic[topic].push(strip[question] as BallotCode));
    return byTopic;
  }, [strip, topics, labels]);
  const spacing = width > 0 ? Math.min(14, width / perTopic) : 0;
  const outer = spacing * 0.4;
  const ring = Math.max(1.2, outer * 0.42);
  const height = spacing * labels.length;

  return (
    <div ref={ref}>
      {width > 0 ? (
        <svg width={perTopic * spacing} height={height} role="img" aria-label="One resident's ballots by topic" className="block">
          {rows.map((codes, topic) => (
            <g key={topic}>
              <title>{topicLabel(labels[topic])}</title>
              {codes.map((code, index) => {
                const look = ballotLook(code);
                return (
                  <circle
                    key={index}
                    cx={index * spacing + spacing / 2}
                    cy={topic * spacing + spacing / 2}
                    r={outer - ring / 2}
                    strokeWidth={ring}
                    style={{ fill: look.ring ? "transparent" : look.color, stroke: look.color }}
                  />
                );
              })}
            </g>
          ))}
        </svg>
      ) : (
        <div style={{ height: 112 }} />
      )}
      <div className="mt-1 font-sans text-[0.7rem] text-story-muted" style={{ color: INK.muted }}>
        A row per topic, {perTopic} questions each
      </div>
    </div>
  );
}
