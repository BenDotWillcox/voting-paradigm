"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import { US_STATES } from "@/lib/us-states";

interface RepresentationMetricsProps {
  cap: number;
  apportionment: Record<string, number>;
  baselineApportionment: Record<string, number>;
  totalPopulation: number;
}

export function RepresentationMetrics({
  cap,
  apportionment,
  baselineApportionment,
  totalPopulation,
}: RepresentationMetricsProps) {
  const metrics = getMetrics(apportionment, totalPopulation);
  const baseline = getMetrics(baselineApportionment, totalPopulation);
  const statesGaining = US_STATES.filter(
    (state) =>
      (apportionment[state.fips] ?? 0) > (baselineApportionment[state.fips] ?? 0)
  ).length;

  return (
    <Card className="gap-1.5 py-2.5">
      <CardHeader className="px-2.5 pb-0">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-sm">Representation impact</CardTitle>
          <Badge variant="outline">{cap.toLocaleString()} seats</Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-1.5 px-2.5 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Average district"
          value={Math.round(metrics.averageDistrict).toLocaleString()}
          delta={baseline.averageDistrict - metrics.averageDistrict}
          deltaLabel="fewer people per member"
          mode="improvement"
        />
        <Metric
          label="Largest district"
          value={metrics.largestDistrict.toLocaleString()}
          delta={baseline.largestDistrict - metrics.largestDistrict}
          deltaLabel="lower ceiling"
          mode="improvement"
        />
        <Metric
          label="Representation gap"
          value={`${metrics.gapRatio.toFixed(2)}x`}
          delta={baseline.gapRatio - metrics.gapRatio}
          deltaLabel="closer to equal"
          decimals={2}
          mode="improvement"
        />
        <Metric
          label="States gaining"
          value={statesGaining.toLocaleString()}
          delta={statesGaining}
          deltaLabel="vs. 435 seats"
          mode="plain"
        />
      </CardContent>
    </Card>
  );
}

function Metric({
  decimals = 0,
  delta,
  deltaLabel,
  label,
  mode,
  value,
}: {
  decimals?: number;
  delta: number;
  deltaLabel: string;
  label: string;
  mode: "improvement" | "plain";
  value: string;
}) {
  const showDelta = Math.abs(delta) > 0.005;
  const formattedDelta =
    decimals > 0 ? delta.toFixed(decimals) : Math.round(delta).toLocaleString();
  const deltaText =
    mode === "improvement"
      ? `${formattedDelta} ${deltaLabel}`
      : `${formattedDelta} ${deltaLabel}`;

  return (
    <div className="rounded-md border p-1.5">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="text-base font-semibold tabular-nums">{value}</div>
      <div className="min-h-3 text-[11px] leading-tight text-muted-foreground">
        {showDelta ? deltaText : "Current baseline"}
      </div>
    </div>
  );
}

function getMetrics(
  apportionment: Record<string, number>,
  totalPopulation: number
) {
  const peoplePerSeat = US_STATES.map((state) => {
    const population = US_2020_APPORTIONMENT_POPULATIONS[state.fips] ?? 0;
    const seats = apportionment[state.fips] ?? 0;
    return seats > 0 ? population / seats : 0;
  }).filter((value) => value > 0);

  const largestDistrict = Math.round(Math.max(...peoplePerSeat));
  const smallestDistrict = Math.round(Math.min(...peoplePerSeat));

  return {
    averageDistrict: totalPopulation / Object.values(apportionment).reduce((a, b) => a + b, 0),
    largestDistrict,
    smallestDistrict,
    gapRatio: largestDistrict / smallestDistrict,
  };
}
