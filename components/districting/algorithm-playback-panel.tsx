"use client";

import * as React from "react";
import { geoPath } from "d3-geo";
import { feature as topoFeature } from "topojson-client";
import type { FeatureCollection, Geometry } from "geojson";
import { Binary, Database, Focus, MapPinned, Orbit, Waypoints } from "lucide-react";

import {
  districtColor,
  projectPlanCenters,
  tractName,
} from "@/lib/district-plans";
import { fetchDistrictPlanLayer } from "@/lib/fetch-district-plan";
import type { StateFeature } from "@/lib/load-states-geojson";
import {
  STATE_DETAIL_VIEWBOX,
  stateFittedAlbers,
} from "@/lib/state-projection";
import type { DistrictPlan, TractProperties } from "@/types/districting";

import { TractCanvasFigure, type TractFeature } from "./tract-canvas";

interface AlgorithmPlaybackPanelProps {
  michigan: StateFeature;
  /** Plan metrics and centers; tract geometry is fetched when scrolled near. */
  plan: DistrictPlan;
}

const steps = [
  {
    icon: Binary,
    label: "Apportionment target",
    body: "Michigan's House seat count gives the solver the number of centers and the target population per district.",
  },
  {
    icon: Database,
    label: "Census tracts",
    body: "Zoom into one tract: the solver reads its boundary, centroid, tract ID, and census population.",
  },
  {
    icon: Focus,
    label: "Seed centers",
    body: "Place initial district centers with population-weighted k-means++.",
  },
  {
    icon: Orbit,
    label: "Assign + rebalance",
    body: "Assign tracts to the best center, then adjust center weights when a district is over or under target.",
  },
  {
    icon: Waypoints,
    label: "Stable plan",
    body: "Move centers to population-weighted centroids and repeat until assignments and populations settle.",
  },
];

const seedOffsets: Array<[number, number]> = [
  [-18, 10],
  [14, -12],
  [22, 8],
  [-12, -18],
  [10, 18],
  [-24, -6],
  [16, 14],
  [-10, 20],
  [20, -16],
  [-16, -12],
  [8, -22],
  [-22, 16],
  [24, 0],
];

export function AlgorithmPlaybackPanel({
  michigan,
  plan,
}: AlgorithmPlaybackPanelProps) {
  const [activeStep, setActiveStep] = React.useState(0);
  const [tracts, setTracts] = React.useState<TractFeature[] | null>(null);
  const sectionRef = React.useRef<HTMLElement | null>(null);

  const { state_fips: fips, cap, seats } = plan;
  // Tracts load when the panel nears the viewport, or immediately once a
  // step that needs them is selected.
  const needsTracts = activeStep >= 1;
  React.useEffect(() => {
    if (tracts) return;
    const node = sectionRef.current;
    if (!node) return;

    let cancelled = false;
    const load = () => {
      fetchDistrictPlanLayer(fips, cap, seats, "tracts")
        .then((topology) => {
          if (cancelled) return;
          const collection = topoFeature(
            topology,
            topology.objects.tracts
          ) as FeatureCollection<Geometry, TractProperties>;
          setTracts(collection.features);
        })
        .catch(() => {
          // Panel stays usable without the tract layer.
        });
    };

    if (needsTracts || typeof IntersectionObserver === "undefined") {
      load();
      return () => {
        cancelled = true;
      };
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          load();
          observer.disconnect();
        }
      },
      { rootMargin: "600px" }
    );
    observer.observe(node);
    return () => {
      cancelled = true;
      observer.disconnect();
    };
  }, [fips, cap, seats, tracts, needsTracts]);

  const projection = React.useMemo(
    () =>
      stateFittedAlbers(
        michigan,
        STATE_DETAIL_VIEWBOX.width,
        STATE_DETAIL_VIEWBOX.height
      ),
    [michigan]
  );
  const path = React.useMemo(() => geoPath(projection), [projection]);
  const tractFeatures = tracts ?? EMPTY_TRACTS;
  const statePath = React.useMemo(() => path(michigan) ?? "", [path, michigan]);
  const highlightedTract = React.useMemo(
    () =>
      [...tractFeatures].sort(
        (a, b) => b.properties.population - a.properties.population
      )[0] ?? null,
    [tractFeatures]
  );
  const highlightedTractCentroid = React.useMemo(
    () => (highlightedTract ? path.centroid(highlightedTract) : null),
    [highlightedTract, path]
  );
  const highlightedTractPath = React.useMemo(
    () => (highlightedTract ? path(highlightedTract) ?? "" : ""),
    [highlightedTract, path]
  );
  const centerPoints = React.useMemo(
    () =>
      // Illustrative seed positions: final centers offset by a fixed jitter.
      // Phase 3 of prompts/storytelling-redesign.md replaces this with the
      // solver's recorded iteration snapshots.
      projectPlanCenters(plan, projection).map((center, index) => {
        const [dx, dy] = seedOffsets[index % seedOffsets.length];
        return {
          districtId: center.districtId,
          final: center.point,
          seed: [center.point[0] + dx, center.point[1] + dy] as [number, number],
          weight: center.weight,
        };
      }),
    [plan, projection]
  );

  const showTracts = activeStep >= 1;
  const showAssignments = activeStep >= 3;
  const tractMode: TractMode = !showTracts
    ? "hidden"
    : activeStep === 1
      ? "outline"
      : showAssignments
        ? "district"
        : "population";
  const maxPopulation = highlightedTract?.properties.population ?? 1;
  const tractFill = React.useCallback(
    (tract: TractProperties) =>
      tractMode === "population"
        ? tractPopulationFill(tract.population, maxPopulation)
        : tractMode === "district"
          ? districtColor(tract.district_id, seats)
          : tractMode === "outline"
            ? "--background"
            : null,
    [tractMode, maxPopulation, seats]
  );
  const centerMode = activeStep >= 4 ? "final" : "seed";
  const populationDeviation =
    plan.target_population > 0
      ? (plan.max_population_imbalance / plan.target_population) * 100
      : 0;

  return (
    <section ref={sectionRef} className="rounded-lg border bg-card">
      <div className="grid gap-0 sm:grid-cols-[minmax(0,1fr)_13rem] md:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <MapPinned className="h-5 w-5 text-primary" />
            <h3 className="text-base font-semibold">
              Algorithm walkthrough: Michigan
            </h3>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            A compact loop of the balanced power-diagram process, starting from
            the same tract-level inputs used by the cached Michigan plan.
          </p>

          <div className="mt-4">
          <TractCanvasFigure
            tracts={tractFeatures}
            projection={projection}
            viewBox={STATE_DETAIL_VIEWBOX}
            fill={tractFill}
            stroke={
              tractMode === "outline"
                ? "--border"
                : tractMode === "hidden"
                  ? null
                  : "--background"
            }
            strokeWidth={tractMode === "outline" ? 0.55 : 0.25}
            opacity={tractMode === "outline" ? 0.85 : 0.58}
            ariaLabel="Michigan districting algorithm walkthrough"
            underlay={
              <path
                d={statePath}
                style={{ fill: "var(--muted)", stroke: "var(--border)" }}
                strokeWidth={1.2}
              />
            }
          >
            {showTracts && tracts === null ? (
              <text
                x={STATE_DETAIL_VIEWBOX.width / 2}
                y={STATE_DETAIL_VIEWBOX.height / 2}
                textAnchor="middle"
                style={{ fill: "var(--muted-foreground)" }}
                fontSize={18}
              >
                Loading tract geometry…
              </text>
            ) : null}
            {activeStep === 1 && highlightedTract && highlightedTractCentroid ? (
              <g aria-label="Highlighted census tract">
                <path
                  d={highlightedTractPath}
                  fill="oklch(0.78 0.16 145 / 0.78)"
                  style={{ stroke: "var(--foreground)" }}
                  strokeWidth={2.3}
                />
                <circle
                  cx={highlightedTractCentroid[0]}
                  cy={highlightedTractCentroid[1]}
                  r={5.25}
                  style={{ fill: "var(--foreground)" }}
                />
                <line
                  x1={highlightedTractCentroid[0] + 6}
                  y1={highlightedTractCentroid[1] - 6}
                  x2={430}
                  y2={96}
                  style={{ stroke: "var(--foreground)" }}
                  strokeOpacity={0.4}
                  strokeWidth={1.2}
                />
                <g transform="translate(430 34)">
                  <rect
                    width={330}
                    height={248}
                    rx={8}
                    style={{
                      fill: "var(--background)",
                      stroke: "var(--border)",
                    }}
                  />
                  <text
                    x={18}
                    y={32}
                    style={{ fill: "var(--foreground)" }}
                    fontSize={23}
                    fontWeight={700}
                  >
                    One census tract
                  </text>
                  <g
                    transform={`translate(164 102) scale(9) translate(${-highlightedTractCentroid[0]} ${-highlightedTractCentroid[1]})`}
                  >
                    <path
                      d={highlightedTractPath}
                      fill="oklch(0.78 0.16 145 / 0.74)"
                      style={{ stroke: "var(--foreground)" }}
                      strokeWidth={0.75}
                    />
                  </g>
                  <circle
                    cx={164}
                    cy={102}
                    r={5}
                    style={{ fill: "var(--foreground)" }}
                  />
                  <text
                    x={18}
                    y={176}
                    style={{ fill: "var(--muted-foreground)" }}
                    fontSize={17}
                    fontWeight={650}
                  >
                    boundary + centroid
                  </text>
                  <text
                    x={18}
                    y={207}
                    style={{ fill: "var(--foreground)" }}
                    fontSize={20}
                    fontWeight={700}
                  >
                    {highlightedTract.properties.population.toLocaleString()} people
                  </text>
                  <text
                    x={18}
                    y={231}
                    style={{ fill: "var(--muted-foreground)" }}
                    fontSize={15}
                  >
                    ID {highlightedTract.properties.geoid}
                  </text>
                </g>
              </g>
            ) : null}
            {activeStep === 0 ? (
              <g aria-label="Apportionment-derived center count">
                <text
                  x={44}
                  y={72}
                  style={{ fill: "var(--foreground)" }}
                  fontSize={52}
                  fontWeight={750}
                >
                  {plan.seats}
                </text>
                <text
                  x={44}
                  y={104}
                  style={{ fill: "var(--foreground)" }}
                  fontSize={17}
                  fontWeight={650}
                >
                  district centers needed
                </text>
                <text
                  x={44}
                  y={130}
                  style={{ fill: "var(--muted-foreground)" }}
                  fontSize={14}
                >
                  from the current {plan.cap}-seat House apportionment
                </text>
              </g>
            ) : null}
            {activeStep >= 2 ? (
              <g aria-label="District centers">
                {centerPoints.map((center) => {
                  const [cx, cy] = center[centerMode];
                  const districtPopulation =
                    plan.district_populations[String(center.districtId)] ?? 0;
                  const haloRadius =
                    activeStep === 3
                      ? 12 + Math.min(8, Math.abs(center.weight) / 160000)
                      : 10;

                  return (
                    <g key={center.districtId}>
                      {activeStep >= 3 ? (
                        <circle
                          cx={cx}
                          cy={cy}
                          r={haloRadius}
                          fill="none"
                          style={{ stroke: "var(--foreground)" }}
                          strokeOpacity={0.32}
                          strokeWidth={1.1}
                        />
                      ) : null}
                      <circle
                        cx={cx}
                        cy={cy}
                        r={5.25}
                        style={{
                          fill: "var(--background)",
                          stroke: "var(--foreground)",
                        }}
                        strokeWidth={1.4}
                      />
                      <circle
                        cx={cx}
                        cy={cy}
                        r={2.9}
                        fill={districtColor(center.districtId, plan.seats)}
                      >
                        <title>
                          {`District ${center.districtId + 1}: ${districtPopulation.toLocaleString()} people`}
                        </title>
                      </circle>
                    </g>
                  );
                })}
              </g>
            ) : null}
          </TractCanvasFigure>
          </div>

          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
            <div className="rounded-md border bg-background p-3">
              <div className="text-xs font-medium uppercase text-muted-foreground">
                Apportionment
              </div>
              <div className="mt-1 font-semibold">
                {plan.seats} seats / centers
              </div>
            </div>
            <div className="rounded-md border bg-background p-3">
              <div className="text-xs font-medium uppercase text-muted-foreground">
                Census tracts
              </div>
              <div className="mt-1 font-semibold">
                {(plan.unit_count ?? tractFeatures.length).toLocaleString()}{" "}
                population units
              </div>
            </div>
            <div className="rounded-md border bg-background p-3">
              <div className="text-xs font-medium uppercase text-muted-foreground">
                Stable when
              </div>
              <div className="mt-1 font-semibold">
                {plan.converged ? "Converged" : "Not converged"} after{" "}
                {plan.iterations} iterations
              </div>
            </div>
          </div>

          <div className="mt-3 rounded-md border bg-muted/35 p-3 text-sm text-muted-foreground">
            {activeStep === 0 ? (
              <>
                Michigan has {plan.total_population.toLocaleString()} people in
                the tract dataset. With {plan.seats} seats, the target district
                size is {plan.target_population.toLocaleString()} people.
              </>
            ) : activeStep === 1 ? (
              highlightedTract ? (
                <>
                  A tract is one census geography record, not a district. The
                  solver keeps it intact and uses its boundary, centroid, ID,
                  and population; this example is{" "}
                  {tractName(highlightedTract.properties.geoid)} with{" "}
                  {highlightedTract.properties.population.toLocaleString()}{" "}
                  people.
                </>
              ) : (
                <>
                  A tract is one census geography record, not a district. The
                  tract geometry is still streaming in; the example tract will
                  appear once it loads.
                </>
              )
            ) : activeStep === 2 ? (
              <>
                Seeding gives the solver {plan.seats} starting centers before
                any tract is assigned. Population weighting keeps the starts
                near where people actually live.
              </>
            ) : activeStep === 3 ? (
              <>
                Each iteration assigns every tract, checks each district against
                the {plan.target_population.toLocaleString()}-person target, and
                adjusts weights to pull populations back toward balance.
              </>
            ) : (
              <>
                Stability means the loop has settled: this cached plan converged
                in {plan.iterations} iterations with max deviation{" "}
                {populationDeviation.toFixed(2)}% from target.
              </>
            )}
          </div>
        </div>

        <div className="border-t p-4 sm:border-l sm:border-t-0 sm:p-5">
          <div className="space-y-3" aria-label="Algorithm slides">
            {steps.map((step, index) => {
              const Icon = step.icon;
              const active = index === activeStep;
              return (
                <button
                  type="button"
                  key={step.label}
                  aria-current={active ? "step" : undefined}
                  aria-pressed={active}
                  onClick={() => setActiveStep(index)}
                  className={`w-full rounded-md border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    active
                      ? "border-primary bg-primary/5"
                      : "bg-background hover:border-primary/50 hover:bg-muted/35"
                  }`}
                >
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Icon className="h-4 w-4 text-primary" />
                    <span className="flex h-5 w-5 items-center justify-center rounded-full border text-xs tabular-nums">
                      {index + 1}
                    </span>
                    <span>{step.label}</span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">{step.body}</p>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

type TractMode = "hidden" | "outline" | "population" | "district";

const EMPTY_TRACTS: TractFeature[] = [];

function tractPopulationFill(population: number, maxPopulation: number): string {
  const share = Math.max(0.08, Math.min(1, population / maxPopulation));
  return `oklch(${0.96 - share * 0.16} ${0.03 + share * 0.1} 222)`;
}
