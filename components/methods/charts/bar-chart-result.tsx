"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { CandidateData } from "@/types/methods";

interface BarChartResultProps {
  candidates: CandidateData[];
  values: Record<string, number>;
  winners: string[];
  valueLabel: string;
}

export function BarChartResult({
  candidates,
  values,
  winners,
  valueLabel,
}: BarChartResultProps) {
  const winnerSet = new Set(winners);

  const data = candidates
    .map((c) => ({
      name: c.name,
      id: c.id,
      value: values[c.id] ?? 0,
      fill: winnerSet.has(c.id)
        ? "var(--color-winner)"
        : "var(--color-other)",
    }))
    .sort((a, b) => b.value - a.value);

  const config: ChartConfig = {
    winner: { label: "Winner", color: "hsl(var(--chart-1))" },
    other: { label: "Other", color: "hsl(var(--chart-3))" },
  };

  return (
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
                <span>
                  {valueLabel}: {Number(value).toLocaleString()}
                </span>
              )}
            />
          }
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ChartContainer>
  );
}
