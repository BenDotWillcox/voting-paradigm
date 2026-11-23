"use client";

import * as React from "react";

import { StoryFigure } from "@/components/story/story-figure";
import { pct } from "@/lib/liquid/format";
import { levelKey } from "@/lib/liquid/story-types";
import { INK, seriesColor } from "@/lib/story/palette";
import { cn } from "@/lib/utils";

import { ClaimLabel, type Claim } from "./claim-label";
import { ReplayButton, easeInOut, lerp, span, useScenePlayer } from "./stage";
import { useStoryData } from "./story-data";

/*
 * Part 3 of the story, "what we'd build" (prompts/demo-5-walkthrough.md,
 * items 24 and 25, "as proposed"): the fixes from parts 1 and 2 stacked on
 * the basic version, shown as one vote's path through the assembled
 * system. Each stage carries its label, its evidence and the break it
 * answers. Every number comes from the generated data.
 */

interface Stage {
  key: string;
  title: string;
  does: string;
  claim: Claim;
  evidence: string;
  answers?: { label: string; href: string };
}

const STEP = { move: 420, pause: 380 } as const;

export function DesignScene() {
  const { measures, results, exploratory } = useStoryData();
  const swiss = measures.protocol.swiss_marker;
  const grid = measures.protocol.turnout_grid;
  const highest = grid[grid.length - 1];
  const operating = results.router.operating;
  const fallback = exploratory.fallback;
  const bars = exploratory.agent_bars.levels[levelKey(swiss)];
  const handover = (l: number) => exploratory.handover.levels[levelKey(l)];
  const rises = (l: number) => handover(l).every((p, i, all) => i === 0 || p.fidelity > all[i - 1].fidelity);
  const lastRise = grid.filter(rises).slice(-1)[0];
  const leads = fallback.hypothesis_levels.map((l) => (100 * fallback.levels[levelKey(l)].h1.estimate).toFixed(1));

  const stages: Stage[] = [
    {
      key: "arrives",
      title: "A question arrives",
      does: "The basic version most proposals share: topics, a delegate for each one you hand over, and votes that travel on.",
      claim: "illustration",
      evidence: "How liquid delegation works in most proposals.",
    },
    {
      key: "router",
      title: "The router files it",
      does: "A decision model reads the question against the categories you wrote in your own words, and keeps it with you when unsure.",
      claim: "proposal",
      evidence: `Measured on the router benchmark: at threshold ${operating.threshold}, ${pct(operating.false_delegation_rate)} of the votes it sends go to the wrong category, and it keeps ${pct(operating.false_keep_rate)} that had a fitting one.`,
      answers: { label: "Strict categories", href: "#struggles" },
    },
    {
      key: "ceiling",
      title: "Your ceiling",
      does: "You keep a topic when voting on it yourself would match you more often than your delegate does.",
      claim: "proposal",
      evidence: `Exploratory: up to turnout ${lastRise} every topic handed over raises fidelity; at ${highest} every one lowers it.`,
      answers: { label: "Over-delegation at high turnout", href: "#struggles" },
    },
    {
      key: "chain",
      title: "Your delegate, and theirs",
      does: "The vote travels on until someone decides it. On a loop, everyone decides for themself.",
      claim: "design",
      evidence: "The loop rule is from the literature and ran in the frozen study: no vote on a loop is lost.",
      answers: { label: "Loops", href: "#breaks" },
    },
    {
      key: "fallback",
      title: "If no ballot comes back",
      does: "Your backup delegate casts it; failing that, your district representative.",
      claim: "proposal",
      evidence: `The representative as default was tested and ${fallback.outcome}: at ${fallback.hypothesis_levels.join(", ")} liquid with the default leads the representative by ${leads.join(", ")} points, with every city under the cap. The backup delegate is untested.`,
      answers: { label: "A delegate who does not vote", href: "#breaks" },
    },
    {
      key: "norecord",
      title: "If you have no record yet",
      does: "Your representative stands in, or a personal agent built from one interview casts your ballot.",
      claim: "proposal",
      evidence: `The agent must match you more than ${pct(bars.representative)} of the time to beat the representative at Swiss turnout. No accuracy is claimed.`,
      answers: { label: "Nobody to delegate to, and the initial history", href: "#breaks" },
    },
    {
      key: "tally",
      title: "The tally",
      does: "Each decider's ballot counts for everyone whose vote reached them.",
      claim: "illustration",
      evidence: "A plurality count of the ballots that reach the tally, as for every arrangement in the study.",
    },
  ];

  const duration = stages.length * (STEP.move + STEP.pause) + 300;
  const player = useScenePlayer(duration);
  const t = player.t;
  const list = React.useRef<HTMLOListElement | null>(null);
  const [centres, setCentres] = React.useState<number[]>([]);

  // Where each stage's marker sits on the rail, measured from the rendered cards
  React.useEffect(() => {
    const node = list.current;
    if (!node) return;
    const measure = () =>
      setCentres(
        Array.from(node.querySelectorAll<HTMLElement>("[data-stage]"), (card) => card.offsetTop + 18)
      );
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const slot = STEP.move + STEP.pause;
  const reached = (i: number) => t >= i * slot + STEP.move;
  const at = Math.min(stages.length - 1, Math.floor(t / slot));
  const within = easeInOut(span(t, at * slot, at * slot + STEP.move));
  const orbTop = centres.length
    ? at === 0
      ? centres[0]
      : lerp(centres[at - 1], centres[at], within)
    : 0;

  return (
    <StoryFigure
      title="The system we would build, one vote at a time"
      subtitle="The basic version with every fix from parts 1 and 2 in place. A vote passes down through each stage; every stage says what it is and what we know about it."
      source="eval/benchmarks/delegation_router_v1, delegation_handover_v1 and delegation_fallback_v1; eval/benchmarks/delegation_frontier_v1 (the agent's bars)"
      table={{
        caption: "The assembled system, stage by stage",
        columns: [
          { key: "stage", label: "Stage" },
          { key: "label", label: "Label" },
          { key: "evidence", label: "What we know" },
        ],
        rows: stages.map((s) => ({ stage: s.title, label: s.claim, evidence: s.evidence })),
      }}
    >
      <div ref={player.ref} className="font-sans">
        <ol ref={list} className="relative space-y-3 pl-8">
          <span aria-hidden="true" className="absolute top-4 bottom-4 left-[11px] w-0.5 rounded bg-story-rule" />
          {centres.length ? (
            <span
              aria-hidden="true"
              className="absolute left-[4px] h-4 w-4 rounded-full"
              style={{
                top: orbTop - 8,
                background: `radial-gradient(circle at 35% 35%, #fff 0 18%, ${seriesColor(0)} 45%)`,
                boxShadow: `0 0 10px 2px ${seriesColor(0)}`,
              }}
            />
          ) : null}
          {stages.map((s, i) => (
            <li
              key={s.key}
              data-stage
              className={cn(
                "rounded-lg p-3 ring-1 transition-[opacity,box-shadow] duration-300",
                reached(i) ? "opacity-100 ring-story-ink" : "opacity-40 ring-story-rule"
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-story-muted tabular-nums">{i + 1}</span>
                <span className="text-sm font-semibold text-story-ink">{s.title}</span>
                <ClaimLabel claim={s.claim} />
              </div>
              <p className="mt-1 text-sm text-story-ink-2">{s.does}</p>
              <p className="mt-1 text-xs text-story-muted">{s.evidence}</p>
              {s.answers ? (
                <p className="mt-1 text-xs text-story-ink-2">
                  Answers:{" "}
                  <a href={s.answers.href} className="underline underline-offset-4" style={{ color: INK.primary }}>
                    {s.answers.label}
                  </a>
                </p>
              ) : null}
            </li>
          ))}
        </ol>
        <ReplayButton player={player} className="mt-3" />
      </div>
    </StoryFigure>
  );
}
