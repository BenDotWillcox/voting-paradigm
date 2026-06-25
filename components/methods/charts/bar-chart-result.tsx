"use client";

import {
  BarChart,
  Bar,
  Cell,
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
  candidateColors?: Record<string, string>;
}

export function BarChartResult({
  candidates,
  values,
  valueLabel,
  candidateColors,
}: BarChartResultProps) {
  const data = candidates
    .map((c) => ({
      name: c.name,
      id: c.id,
      value: values[c.id] ?? 0,
      fill: candidateColors?.[c.id] ?? "var(--color-other)",
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
        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
          {data.map((entry) => (
            <Cell key={entry.id} fill={entry.fill} />
          ))}
        </Bar>
      </BarChart>
    </ChartContainer>
  );
}
