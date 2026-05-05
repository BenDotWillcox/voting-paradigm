"use client";

import * as React from "react";
import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ApportionmentDto } from "@/types/districting";
import { US_STATES, getStateByFips } from "@/lib/us-states";

interface ApportionmentSummaryProps {
  apportionment: ApportionmentDto | null;
  /** The 435-baseline apportionment for "vs. current" deltas. */
  baseline: ApportionmentDto | null;
  /** True while a fresh apportionment is being fetched. */
  loading: boolean;
}

/**
 * Right-rail summary of the current apportionment:
 *  - top-line stats (total seats, average district size)
 *  - top-N states by seat count
 *  - count of state-level seat changes vs the 435 baseline
 *
 * Pure presentation. The parent owns the data fetch.
 */
export function ApportionmentSummary({
  apportionment,
  baseline,
  loading,
}: ApportionmentSummaryProps) {
  if (!apportionment) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Apportionment</CardTitle>
          <CardDescription>Loading…</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const { cap, apportionment: seats, total_apportionment_population } =
    apportionment;
  const avgDistrict = Math.round(total_apportionment_population / cap);

  // Top 5 states by seat count, ties broken alphabetically by name for stability.
  const topFive = [...Object.entries(seats)]
    .map(([fips, n]) => ({ fips, n, name: getStateByFips(fips)?.name ?? fips }))
    .sort((a, b) => b.n - a.n || a.name.localeCompare(b.name))
    .slice(0, 5);

  // Per-state delta vs baseline. Positive = gained seats, negative = lost.
  let changedStates = 0;
  let topGain: { fips: string; name: string; delta: number } | null = null;
  let topLoss: { fips: string; name: string; delta: number } | null = null;
  if (baseline) {
    for (const { fips, name } of US_STATES) {
      const delta = (seats[fips] ?? 0) - (baseline.apportionment[fips] ?? 0);
      if (delta !== 0) changedStates += 1;
      if (delta > 0 && (!topGain || delta > topGain.delta)) {
        topGain = { fips, name, delta };
      }
      if (delta < 0 && (!topLoss || delta < topLoss.delta)) {
        topLoss = { fips, name, delta };
      }
    }
  }

  return (
    <Card className={loading ? "opacity-70 transition-opacity" : "transition-opacity"}>
      <CardHeader>
        <CardTitle className="text-base">At cap = {cap.toLocaleString()}</CardTitle>
        <CardDescription>
          Method of Equal Proportions on 2020 census apportionment populations.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Total seats</dt>
          <dd className="text-right tabular-nums">{cap.toLocaleString()}</dd>
          <dt className="text-muted-foreground">Avg. district</dt>
          <dd className="text-right tabular-nums">
            {avgDistrict.toLocaleString()} ppl
          </dd>
          <dt className="text-muted-foreground">States covered</dt>
          <dd className="text-right tabular-nums">{apportionment.total_states}</dd>
          {baseline && cap !== baseline.cap && (
            <>
              <dt className="text-muted-foreground">States gaining/losing</dt>
              <dd className="text-right tabular-nums">{changedStates}</dd>
            </>
          )}
        </dl>

        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">
            Top 5 states
          </div>
          <ul className="space-y-1">
            {topFive.map(({ fips, name, n }) => (
              <li key={fips} className="flex items-center justify-between text-sm">
                <Link
                  href={`/districts/${fips}?cap=${cap}`}
                  className="hover:underline"
                >
                  {name}
                </Link>
                <span className="tabular-nums">{n}</span>
              </li>
            ))}
          </ul>
        </div>

        {baseline && cap !== baseline.cap && (topGain || topLoss) && (
          <div>
            <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">
              Biggest swings vs. {baseline.cap}
            </div>
            <ul className="space-y-1 text-sm">
              {topGain && (
                <li className="flex items-center justify-between">
                  <span>{topGain.name}</span>
                  <span className="tabular-nums text-emerald-600 dark:text-emerald-400">
                    +{topGain.delta}
                  </span>
                </li>
              )}
              {topLoss && (
                <li className="flex items-center justify-between">
                  <span>{topLoss.name}</span>
                  <span className="tabular-nums text-rose-600 dark:text-rose-400">
                    {topLoss.delta}
                  </span>
                </li>
              )}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
