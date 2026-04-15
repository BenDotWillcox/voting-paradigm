"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  Cell,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import { CandidateData } from "@/types/methods";

interface QuadraticChartProps {
  candidates: CandidateData[];
  voteTotals: Record<string, number>;
  winners: string[];
  overallUtilization: number;
  avgVoterUtilization: number;
}

export function QuadraticChart({
  candidates,
  voteTotals,
  winners,
  overallUtilization,
  avgVoterUtilization,
}: QuadraticChartProps) {
  const winnerSet = new Set(winners);

  const data = candidates
    .map((c) => ({
      name: c.name,
      id: c.id,
      value: voteTotals[c.id] ?? 0,
    }))
    .sort((a, b) => b.value - a.value);

  const config: ChartConfig = {
    positive: { label: "Net Votes", color: "hsl(var(--chart-1))" },
    negative: { label: "Net Votes", color: "hsl(var(--destructive))" },
  };

  return (
    <div className="space-y-4">
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
                  <span>Net votes: {Number(value).toLocaleString()}</span>
                )}
              />
            }
          />
          <ReferenceLine x={0} stroke="hsl(var(--border))" />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {data.map((entry) => (
              <Cell
                key={entry.id}
                fill={
                  entry.value < 0
                    ? "hsl(var(--destructive))"
                    : winnerSet.has(entry.id)
                      ? "hsl(var(--chart-1))"
                      : "hsl(var(--chart-3))"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ChartContainer>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-muted-foreground mb-1">
            Overall Credit Utilization
          </p>
          <Progress value={overallUtilization * 100} className="h-2" />
          <p className="text-xs text-muted-foreground mt-1">
            {(overallUtilization * 100).toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-muted-foreground mb-1">
            Avg. Voter Utilization
          </p>
          <Progress value={avgVoterUtilization * 100} className="h-2" />
          <p className="text-xs text-muted-foreground mt-1">
            {(avgVoterUtilization * 100).toFixed(1)}%
          </p>
        </div>
      </div>
    </div>
  );
}
