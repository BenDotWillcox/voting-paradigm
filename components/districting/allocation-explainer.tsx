"use client";

import Link from "next/link";
import { useAutoAnimate } from "@formkit/auto-animate/react";
import type { AutoAnimationPlugin } from "@formkit/auto-animate";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  getNextCandidates,
  getRecentAllocations,
  type AllocationStep,
  type PriorityCandidate,
} from "@/lib/apportionment-sequence";
import { CAP_MIN } from "@/lib/districting-cap-scale";

interface AllocationExplainerProps {
  cap: number;
}

const VISIBLE_NEXT_CANDIDATES = 7;

export function AllocationExplainer({ cap }: AllocationExplainerProps) {
  const [queueParent] = useAutoAnimate(queueAnimationPlugin);
  const recent = getRecentAllocations(cap, 8);
  const lastAwarded = recent[0] ?? null;
  const nextCandidates = getNextCandidates(cap, VISIBLE_NEXT_CANDIDATES);
  const queueItems: QueueFlowItem[] = [
    {
      id: lastAwarded
        ? calloutKey(lastAwarded.stateFips, lastAwarded.previousSeats)
        : "floor",
      kind: "awarded",
      label: `Seat ${cap.toLocaleString()}`,
      step: lastAwarded,
      emptyLabel:
        cap === CAP_MIN ? "Current House floor reached" : "No awarded seat",
    },
    ...nextCandidates.map((candidate, index) => ({
      id: calloutKey(candidate.stateFips, candidate.currentSeats),
      kind: index === 0 ? ("next" as const) : ("queued" as const),
      label: `Seat ${(cap + index + 1).toLocaleString()}`,
      candidate,
      rank: index + 1,
    })),
  ];

  return (
    <Card className="gap-2 py-2.5">
      <CardHeader className="px-2.5">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-sm">Priority queue</CardTitle>
          <Badge variant="secondary">Huntington-Hill</Badge>
        </div>
        <CardDescription className="text-xs">
          Each added seat goes to the state with the highest priority score.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 px-2.5">
        <div className="rounded-md border bg-muted/30 p-1.5">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Priority formula
          </div>
          <div className="mt-0.5 font-mono text-[11px]">
            population / sqrt(seats * (seats + 1))
          </div>
        </div>

        <div>
          <div className="mb-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
            Seat flow
          </div>
          <ol ref={queueParent} className="space-y-0.5">
            {queueItems.map((item) => (
              <QueueItem key={item.id} item={item} />
            ))}
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}

type QueueFlowItem = {
  id: string;
  kind: "awarded" | "next" | "queued";
  candidate?: PriorityCandidate;
  emptyLabel?: string;
  label?: string;
  rank?: number;
  step?: AllocationStep | null;
};

function QueueItem({ item }: { item: QueueFlowItem }) {
  const { candidate, emptyLabel, label, rank, step } = item;
  const stateFips = step?.stateFips ?? candidate?.stateFips;
  const stateName = step?.stateName ?? candidate?.stateName;
  const previousSeats = step?.previousSeats ?? candidate?.currentSeats;
  const newSeats = step?.newSeats ?? candidate?.nextSeats;
  const priority = step?.priority ?? candidate?.priority;
  const isAwarded = item.kind === "awarded";
  const isNext = item.kind === "next";
  const eyebrow = isAwarded
    ? "Last awarded"
    : isNext
      ? "Next if one seat is added"
      : "";

  return (
    <li
      className={
        `allocation-flow-item list-none rounded-md border ${
          isAwarded
            ? "allocation-award-card border-emerald-600/50 bg-emerald-500/10"
            : "allocation-queue-card"
        }`
      }
    >
      <div className="allocation-flow-shell">
        <div className="allocation-flow-rank text-xs tabular-nums text-muted-foreground">
          {isAwarded ? "" : rank}
        </div>
        <div className="min-w-0">
          <div
            className={`allocation-flow-eyebrow allocation-callout-copy text-xs uppercase tracking-wide text-muted-foreground ${
              eyebrow ? "" : "allocation-flow-eyebrow-empty"
            }`}
          >
            {eyebrow}
          </div>
          {stateFips &&
          stateName &&
          previousSeats !== undefined &&
          newSeats !== undefined &&
          priority !== undefined ? (
            <>
              <div className="allocation-flow-main flex items-center justify-between gap-3">
                <Link
                  href={`/districts/${stateFips}`}
                  className="font-semibold hover:underline"
                >
                  {stateName}
                </Link>
                {label && (
                  <span className="allocation-flow-seat-label text-xs text-muted-foreground">
                    {label}
                  </span>
                )}
              </div>
              <div className="allocation-flow-detail allocation-callout-copy text-sm text-muted-foreground">
                {previousSeats} to {newSeats} seats
              </div>
              <div className="allocation-flow-priority">
                <PriorityText priority={priority} />
              </div>
            </>
          ) : (
            <div className="mt-1 text-sm text-muted-foreground">{emptyLabel}</div>
          )}
        </div>
      </div>
    </li>
  );
}

function PriorityText({ priority }: { priority: number }) {
  return (
    <div className="mt-1 text-xs tabular-nums text-muted-foreground">
      Priority {Math.round(priority).toLocaleString()}
    </div>
  );
}

function calloutKey(stateFips: string, currentSeats: number): string {
  return `${stateFips}-${currentSeats}`;
}

const queueAnimationPlugin: AutoAnimationPlugin = (
  el,
  action,
  oldCoords,
  newCoords
) => {
  if (action === "add") {
    return new KeyframeEffect(
      el,
      [
        { opacity: 0, transform: "translateY(0.35rem)", offset: 0 },
        { opacity: 0, transform: "translateY(0.35rem)", offset: 0.72 },
        { opacity: 1, transform: "translateY(0)", offset: 1 },
      ],
      {
        duration: 940,
        easing: "cubic-bezier(0.16, 1, 0.3, 1)",
      }
    );
  }

  if (action !== "remain" || !oldCoords || !newCoords) {
    return new KeyframeEffect(el, [{ opacity: 1 }, { opacity: 1 }], {
      duration: 1,
      easing: "linear",
    });
  }

  const deltaX = oldCoords.left - newCoords.left;
  const deltaY = oldCoords.top - newCoords.top;
  const startFrame: Keyframe = {
    transform: `translate(${deltaX}px, ${deltaY}px)`,
  };
  const endFrame: Keyframe = {
    transform: "translate(0, 0)",
  };

  if (Math.round(oldCoords.height) !== Math.round(newCoords.height)) {
    startFrame.height = `${oldCoords.height}px`;
    startFrame.minHeight = `${oldCoords.height}px`;
    endFrame.height = `${newCoords.height}px`;
    endFrame.minHeight = `${newCoords.height}px`;
  }

  return new KeyframeEffect(
    el,
    [startFrame, endFrame],
    {
      duration: 940,
      easing: "cubic-bezier(0.16, 1, 0.3, 1)",
    }
  );
};
