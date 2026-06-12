"use client";

import { useState } from "react";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Button } from "@/components/ui/button";
import { CandidateData, IRVRound } from "@/types/methods";

interface IRVRoundsChartProps {
  candidates: CandidateData[];
  rounds: IRVRound[];
  winners: string[];
  candidateColors?: Record<string, string>;
}

export function IRVRoundsChart({
  candidates,
  rounds,
  winners,
  candidateColors,
}: IRVRoundsChartProps) {
  const [currentRound, setCurrentRound] = useState(rounds.length - 1);
  const round = rounds[currentRound];
  if (!round) return null;

  const winnerSet = new Set(winners);

  // Build the set of all eliminated candidates up to (but not including) this round
  const eliminatedBefore = new Set<string>();
  for (let i = 0; i < currentRound; i++) {
    for (const cid of rounds[i].eliminated) {
      eliminatedBefore.add(cid);
    }
  }

  const data = candidates
    .map((c) => {
      const isEliminated = eliminatedBefore.has(c.id);
      const isEliminatedThisRound = round.eliminated.includes(c.id);
      const isWinner = winnerSet.has(c.id) && currentRound === rounds.length - 1;
      return {
        name: c.name,
        id: c.id,
        value: round.vote_counts[c.id] ?? 0,
        fill: isEliminated
          ? "hsl(var(--muted))"
          : isEliminatedThisRound
            ? candidateColors?.[c.id] ?? "hsl(var(--destructive))"
            : isWinner
              ? candidateColors?.[c.id] ?? "var(--color-winner)"
              : candidateColors?.[c.id] ?? "var(--color-active)",
      };
    })
    .filter((d) => !eliminatedBefore.has(d.id));

  const majorityLine = round.active_ballots / 2;

  const config: ChartConfig = {
    winner: { label: "Winner", color: "hsl(var(--chart-1))" },
    active: { label: "Active", color: "hsl(var(--chart-3))" },
  };

  // Compute narrative for this round
  const narrative = getRoundNarrative(round, currentRound, rounds.length, candidates);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        {rounds.map((_, i) => (
          <Button
            key={i}
            variant={i === currentRound ? "default" : "outline"}
            size="sm"
            onClick={() => setCurrentRound(i)}
          >
            Round {i + 1}
          </Button>
        ))}
      </div>

      <ChartContainer config={config} className="h-[300px] w-full">
        <BarChart data={data} layout="vertical" margin={{ left: 20 }}>
          <CartesianGrid horizontal={false} />
          <XAxis type="number" />
          <YAxis
            type="category"
            dataKey="name"
            width={140}
            tick={{ fontSize: 12 }}
          />
          <ChartTooltip
            content={
              <ChartTooltipContent
                formatter={(value) => (
                  <span>Votes: {Number(value).toLocaleString()}</span>
                )}
              />
            }
          />
          <ReferenceLine
            x={majorityLine}
            stroke="hsl(var(--chart-2))"
            strokeDasharray="5 5"
            label={{ value: "Majority", position: "top", fontSize: 11 }}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {data.map((entry) => (
              <Cell key={entry.id} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ChartContainer>

      <p className="text-sm text-muted-foreground">{narrative}</p>
    </div>
  );
}

function getRoundNarrative(
  round: IRVRound,
  roundIndex: number,
  totalRounds: number,
  candidates: CandidateData[]
): string {
  const nameMap = new Map(candidates.map((c) => [c.id, c.name]));
  const getName = (id: string) => nameMap.get(id) ?? id;

  if (roundIndex === totalRounds - 1 && round.eliminated.length === 0) {
    // Final round — winner found
    const entries = Object.entries(round.vote_counts).sort(
      ([, a], [, b]) => b - a
    );
    if (entries.length > 0) {
      return `${getName(entries[0][0])} wins with ${entries[0][1]} votes out of ${round.active_ballots} active ballots.`;
    }
    return "Final round.";
  }

  if (round.eliminated.length > 0) {
    const eliminated = round.eliminated.map(getName).join(", ");
    return `${eliminated} eliminated with the fewest votes. Their votes redistribute to remaining candidates.`;
  }

  return `Round ${round.round_number}: ${round.active_ballots} active ballots.`;
}
