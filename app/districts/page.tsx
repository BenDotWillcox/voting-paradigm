import { AlertCircle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { DistrictsExplorer } from "@/components/districting/districts-explorer";
import { getApportionment } from "@/lib/districting-api";
import { CAP_MIN, getNearestAnchor } from "@/lib/districting-cap-scale";
import { loadStatesGeoJSON } from "@/lib/load-states-geojson";

export const dynamic = "force-dynamic";

interface DistrictsPageProps {
  searchParams: Promise<{ cap?: string }>;
}

/**
 * Districting demo overview.
 *
 * Server component: pre-fetches the apportionment for the requested cap (or
 * the 435 default) and the 435 baseline used by the sidebar's "vs. current"
 * deltas, then hands both off to the client orchestrator. The us-atlas
 * topology is also loaded server-side so the SVG can render synchronously
 * on first paint.
 */
export default async function DistrictsPage({ searchParams }: DistrictsPageProps) {
  const { cap: capParam } = await searchParams;
  const initialCap = parseCapParam(capParam);

  try {
    const [states, baseline, initialApportionment] = await Promise.all([
      loadStatesGeoJSON(),
      getApportionment(CAP_MIN),
      initialCap === CAP_MIN ? null : getApportionment(initialCap),
    ]);

    const apportionment = initialApportionment ?? baseline;

    return (
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <header className="mb-8 space-y-3 max-w-3xl">
          <h1 className="text-3xl font-bold tracking-tight">
            Algorithmic districting
          </h1>
          <p className="text-muted-foreground">
            Pick one of five House sizes. Apportionment runs
            Method-of-Equal-Proportions on 2020 census populations and updates
            every state&rsquo;s seat count. The choices are the current{" "}
            <strong>435</strong> (1929 cap), <strong>574</strong> (Wyoming
            Rule), <strong>692</strong> (Cube Root Rule), an &ldquo;expanded&rdquo;{" "}
            <strong>1,000</strong>, and the constitutional <strong>11,037</strong>{" "}
            (Article I §2 ratio of one representative per 30,000 people).
          </p>
          <p className="text-xs text-muted-foreground">
            Step 2 of the build: UI shell with apportionment-driven seat
            counts. Real district polygons drawn by the balanced power-diagram
            algorithm follow in the next districting slice.
          </p>
        </header>

        <DistrictsExplorer
          initialApportionment={apportionment}
          baselineApportionment={baseline}
          initialCap={initialCap}
          states={states}
        />
      </div>
    );
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Unknown error reaching the API.";
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Algorithmic districting</h1>
        </div>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Districting API unavailable</AlertTitle>
          <AlertDescription>
            <p>Could not load the demo. The most common cause is that the Python API isn&rsquo;t running:</p>
            <code className="block mt-2 p-2 bg-muted rounded text-sm">
              npm run api:dev
            </code>
            <p className="mt-2 text-xs opacity-80">Underlying error: {message}</p>
          </AlertDescription>
        </Alert>
      </div>
    );
  }
}

function parseCapParam(raw: string | undefined): number {
  if (!raw) return CAP_MIN;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n)) return CAP_MIN;
  // Snap arbitrary or stale URL values to the nearest anchor so the picker
  // always has a selected item and we never request a cap we don't render.
  return getNearestAnchor(n).cap;
}
