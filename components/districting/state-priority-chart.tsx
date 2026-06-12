"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { StatePriorityPoint } from "@/lib/apportionment-sequence";

interface StatePriorityChartProps {
  data: StatePriorityPoint[];
  stateName: string;
}

export function StatePriorityChart({
  data,
  stateName,
}: StatePriorityChartProps) {
  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 12, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="seats"
            tickLine={false}
            axisLine={false}
            label={{ value: "Current seats", position: "insideBottom", offset: -4 }}
          />
          <YAxis
            tickFormatter={(value) => Math.round(Number(value) / 1_000_000).toString()}
            tickLine={false}
            axisLine={false}
            width={44}
            label={{
              value: "Priority, millions",
              angle: -90,
              position: "insideLeft",
              offset: 4,
            }}
          />
          <Tooltip
            formatter={(value) => [
              Math.round(Number(value)).toLocaleString(),
              "Priority",
            ]}
            labelFormatter={(value) =>
              `${stateName} priority after ${Number(value).toLocaleString()} seat${
                Number(value) === 1 ? "" : "s"
              }`
            }
          />
          <Line
            type="monotone"
            dataKey="priority"
            stroke="var(--primary)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
