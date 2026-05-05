"use client";

import type { ValueSummaryDto } from "@/lib/preferences-api";

interface ValuesRankingProps {
  values: ValueSummaryDto[];
}

/**
 * Displays ranked values with posterior mean as the bar length and
 * posterior std as an uncertainty whisker.
 */
export function ValuesRanking({ values }: ValuesRankingProps) {
  if (values.length === 0) {
    return (
      <p className="text-muted-foreground">No values computed yet.</p>
    );
  }

  const means = values.map((v) => v.mean);
  const minMean = Math.min(...means);
  const maxMean = Math.max(...means);
  const range = Math.max(1e-6, maxMean - minMean);

  return (
    <div className="space-y-3">
      {values.map((v) => {
        // Normalize mean to [0, 100] for bar width.
        const norm = (v.mean - minMean) / range;
        const pct = Math.max(2, Math.min(100, norm * 100));
        const stdPct = Math.min(20, (v.std / range) * 100);
        // Whisker, clamped so it never escapes the track.
        const whiskerLeft = Math.max(0, Math.min(100, pct - stdPct));
        const whiskerRight = Math.max(0, Math.min(100, pct + stdPct));
        const whiskerWidth = Math.max(0, whiskerRight - whiskerLeft);
        return (
          <div key={v.item_id} className="rounded-lg border p-3">
            <div className="flex items-baseline justify-between gap-2">
              <div className="flex items-baseline gap-2">
                <span className="text-xs text-muted-foreground tabular-nums w-6">
                  #{v.rank}
                </span>
                <span className="font-medium">{v.text}</span>
                {v.domain && (
                  <span className="text-xs text-muted-foreground">
                    ({v.domain})
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground tabular-nums">
                μ={v.mean.toFixed(2)} · σ={v.std.toFixed(2)}
              </div>
            </div>

            <div className="relative mt-2 h-2 w-full rounded-full bg-muted">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-primary"
                style={{ width: `${pct}%` }}
              />
              {/* Uncertainty whisker */}
              <div
                className="absolute inset-y-0 rounded-full bg-primary/30"
                style={{
                  left: `${Math.max(0, pct - stdPct)}%`,
                  width: `${Math.min(100, stdPct * 2)}%`,
                }}
              />
            </div>

            {v.description && (
              <p className="mt-2 text-sm text-muted-foreground">
                {v.description}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
