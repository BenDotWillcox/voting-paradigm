"use client";

import * as React from "react";
import { geoPath } from "d3-geo";
import { feature as topoFeature } from "topojson-client";
import type { FeatureCollection, Geometry } from "geojson";
import { Binary, Database, Focus, MapPinned, Orbit, Waypoints } from "lucide-react";

import { fetchDistrictPlan } from "@/lib/fetch-district-plan";
import type { StateFeature } from "@/lib/load-states-geojson";
import {
  STATE_DETAIL_VIEWBOX,
  stateFittedAlbers,
} from "@/lib/state-projection";
import type {
  CachedDistrictPlan,
  DistrictPlanFeatureProperties,
} from "@/types/districting";

interface AlgorithmPlaybackPanelProps {
  michigan: StateFeature;
  /** Compact summary plan: scalar metrics and centers, no tract geometry. */
  summary: CachedDistrictPlan;
  /** Tract-level topo asset, fetched lazily when the panel scrolls into view. */
  topoUrl: string | null;
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
  summary,
  topoUrl,
}: AlgorithmPlaybackPanelProps) {
  const [activeStep, setActiveStep] = React.useState(0);
  const [tractPlan, setTractPlan] = React.useState<CachedDistrictPlan | null>(
    null
  );
  const sectionRef = React.useRef<HTMLElement | null>(null);
  // Scalar metrics are identical between summary and tract artifacts; the
  // fetched plan only contributes geometry.
  const plan = summary;

  React.useEffect(() => {
    if (!topoUrl || tractPlan) return;
    const node = sectionRef.current;
    if (!node) return;

    let cancelled = false;
    const load = () => {
      fetchDistrictPlan(topoUrl)
        .then((fetched) => {
          if (!cancelled) setTractPlan(fetched);
        })
        .catch(() => {
          // Panel stays usable without the tract layer.
        });
    };

    if (typeof IntersectionObserver === "undefined") {
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
  }, [topoUrl, tractPlan]);

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
  const featureCollection = React.useMemo(() => {
    if (!tractPlan) return null;
    if (tractPlan.display_topology) {
      return topoFeature(
        tractPlan.display_topology,
        tractPlan.display_topology.objects.districts
      ) as FeatureCollection<Geometry, DistrictPlanFeatureProperties>;
    }
    return tractPlan.feature_collection ?? null;
  }, [tractPlan]);
  const tractFeatures = React.useMemo(
    () => featureCollection?.features ?? [],
    [featureCollection]
  );
  // Project every tract once. Step clicks only restyle the layer; without
  // this, each click re-derived ~3k SVG path strings from raw geometry.
  const tractPaths = React.useMemo(
    () =>
      tractFeatures.map((feature) => ({
        d: path(feature) ?? "",
        properties: feature.properties,
      })),
    [tractFeatures, path]
  );
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
  const centerPoints = React.useMemo(() => {
    const projectionMeta = plan.projection;
    if (!projectionMeta || !plan.centers) return [];

    return plan.centers
      .map((center, index) => {
        const lonLat = unprojectEquirectangular(
          center.x,
          center.y,
          projectionMeta.lon0,
          projectionMeta.lat0
        );
        const point = projection(lonLat);
        if (!point) return null;
        // Rounded to 0.01px so SSR and client markup agree (Math.cos can
        // drift in the last float digits between Node and the browser).
        const final: [number, number] = [
          roundCoord(point[0]),
          roundCoord(point[1]),
        ];
        const [dx, dy] = seedOffsets[index % seedOffsets.length];
        return {
          districtId: center.district_id,
          final,
          seed: [final[0] + dx, final[1] + dy] as [number, number],
          weight: center.weight,
        };
      })
      .filter((center) => center !== null);
  }, [plan.centers, plan.projection, projection]);

  const showTracts = activeStep >= 1;
  const showAssignments = activeStep >= 3;
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

          <svg
            viewBox={`0 0 ${STATE_DETAIL_VIEWBOX.width} ${STATE_DETAIL_VIEWBOX.height}`}
            className="mt-4 h-auto w-full"
            role="img"
            aria-label="Michigan districting algorithm walkthrough"
          >
            <path
              d={statePath}
              style={{ fill: "var(--muted)", stroke: "var(--border)" }}
              strokeWidth={1.2}
            />
            {showTracts && tractFeatures.length === 0 ? (
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
            {tractPaths.length > 0 ? (
              <TractLayer
                tracts={tractPaths}
                mode={
                  !showTracts
                    ? "hidden"
                    : activeStep === 1
                      ? "outline"
                      : showAssignments
                        ? "district"
                        : "population"
                }
                seats={plan.seats}
                maxPopulation={highlightedTract?.properties.population ?? 1}
              />
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
          </svg>

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
                  {highlightedTract.properties.name} with{" "}
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

interface TractLayerProps {
  tracts: Array<{ d: string; properties: DistrictPlanFeatureProperties }>;
  /**
   * hidden: step 1 (layer stays mounted so later steps don't pay a ~3k-node
   * remount); outline: step 2; population: step 3; district: steps 4-5.
   */
  mode: "hidden" | "outline" | "population" | "district";
  seats: number;
  maxPopulation: number;
}

/**
 * The ~3k tract paths. Each path carries its population and district fills
 * as CSS custom properties; the active `mode` on the wrapper <g> selects
 * which applies. A step click therefore changes one DOM attribute instead
 * of reconciling ~3k inline styles.
 */
function TractLayer({ tracts, mode, seats, maxPopulation }: TractLayerProps) {
  return (
    <g className="walkthrough-tracts" data-mode={mode}>
      <TractPaths tracts={tracts} seats={seats} maxPopulation={maxPopulation} />
    </g>
  );
}

const TRACT_LAYER_CSS = `
.walkthrough-tracts { opacity: 0.58; }
.walkthrough-tracts[data-mode="hidden"] { display: none; }
.walkthrough-tracts path { fill: var(--background); stroke: var(--background); stroke-width: 0.25; }
.walkthrough-tracts[data-mode="outline"] { opacity: 0.85; }
.walkthrough-tracts[data-mode="outline"] path { stroke: var(--border); stroke-width: 0.55; }
.walkthrough-tracts[data-mode="population"] path { fill: var(--tract-fill-population); }
.walkthrough-tracts[data-mode="district"] path { fill: var(--tract-fill-district); }
`;

const TractPaths = React.memo(function TractPaths({
  tracts,
  seats,
  maxPopulation,
}: Omit<TractLayerProps, "mode">) {
  return (
    <>
      <style>{TRACT_LAYER_CSS}</style>
      {tracts.map((tract) => (
        <path
          key={tract.properties.geoid}
          d={tract.d}
          style={
            {
              "--tract-fill-population": tractPopulationFill(
                tract.properties.population,
                maxPopulation
              ),
              "--tract-fill-district": districtColor(
                tract.properties.district_id,
                seats
              ),
            } as React.CSSProperties
          }
        >
          <title>
            {`${tract.properties.name}: ${tract.properties.population.toLocaleString()} people`}
          </title>
        </path>
      ))}
    </>
  );
});

function districtColor(districtId: number, seats: number): string {
  const hue = (districtId * 137.508) % 360;
  const lightness = seats > 24 ? 0.72 : 0.66;
  const chroma = seats > 24 ? 0.11 : 0.14;
  return `oklch(${lightness} ${chroma} ${hue.toFixed(1)})`;
}

function roundCoord(value: number): number {
  return Math.round(value * 100) / 100;
}

function tractPopulationFill(population: number, maxPopulation: number): string {
  const share = Math.max(0.08, Math.min(1, population / maxPopulation));
  return `oklch(${0.96 - share * 0.16} ${0.03 + share * 0.1} 222)`;
}

function unprojectEquirectangular(
  x: number,
  y: number,
  lon0: number,
  lat0: number
): [number, number] {
  const earthRadiusM = 6_371_000;
  const lat = lat0 + radiansToDegrees(y / earthRadiusM);
  const lon =
    lon0 +
    radiansToDegrees(
      x / (earthRadiusM * Math.cos(degreesToRadians(lat0)))
    );
  return [lon, lat];
}

function degreesToRadians(value: number): number {
  return (value * Math.PI) / 180;
}

function radiansToDegrees(value: number): number {
  return (value * 180) / Math.PI;
}
