"use client";

import * as React from "react";

import { fetchDistrictPlan } from "@/lib/fetch-district-plan";
import type { StateFeature } from "@/lib/load-states-geojson";
import type { CachedDistrictPlan } from "@/types/districting";

import { DistrictPlanMap } from "./district-plan-map";

interface DistrictPlanMapLoaderProps {
  state: StateFeature;
  /** Compact dissolved-district plan, server-loaded. Renders immediately. */
  summary: CachedDistrictPlan;
  /** Tract-level topo asset to stream in for hover detail, if generated. */
  topoUrl: string | null;
}

/**
 * Renders the dissolved district map instantly from the small summary,
 * then upgrades in place to tract-level hover detail once the topo asset
 * finishes downloading in the background.
 */
export function DistrictPlanMapLoader({
  state,
  summary,
  topoUrl,
}: DistrictPlanMapLoaderProps) {
  const [detail, setDetail] = React.useState<{
    url: string;
    plan: CachedDistrictPlan;
  } | null>(null);

  React.useEffect(() => {
    if (!topoUrl) return;
    let cancelled = false;
    fetchDistrictPlan(topoUrl)
      .then((plan) => {
        if (!cancelled) setDetail({ url: topoUrl, plan });
      })
      .catch(() => {
        // Detail layer is an enhancement; the summary map stays up.
      });
    return () => {
      cancelled = true;
    };
  }, [topoUrl]);

  const detailPlan = detail?.url === topoUrl ? detail.plan : null;
  const loadingDetail = topoUrl !== null && detailPlan === null;

  return (
    <div className="space-y-2">
      <DistrictPlanMap state={state} plan={detailPlan ?? summary} />
      <p
        className="text-[11px] leading-snug text-muted-foreground"
        role="status"
        aria-live="polite"
      >
        {loadingDetail
          ? "Streaming tract-level detail…"
          : detailPlan
            ? "Tract-level detail loaded. Hover a tract for its assignment."
            : "District outlines shown. Tract-level detail not generated for this plan."}
      </p>
    </div>
  );
}
