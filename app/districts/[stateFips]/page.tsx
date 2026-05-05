import Link from "next/link";
import { notFound } from "next/navigation";
import { AlertCircle, ArrowLeft } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { StateDetailMap } from "@/components/districting/state-detail-map";
import { getApportionment } from "@/lib/districting-api";
import { CAP_MIN, getNearestAnchor } from "@/lib/districting-cap-scale";
import { loadStatesGeoJSON } from "@/lib/load-states-geojson";
import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import { getStateByFips, isStateFips } from "@/lib/us-states";

export const dynamic = "force-dynamic";

interface StatePageProps {
  params: Promise<{ stateFips: string }>;
  searchParams: Promise<{ cap?: string }>;
}

export default async function StateDetailPage({
  params,
  searchParams,
}: StatePageProps) {
  const { stateFips } = await params;
  const { cap: capParam } = await searchParams;
  const cap = parseCapParam(capParam);

  if (!isStateFips(stateFips)) notFound();
  const state = getStateByFips(stateFips);
  if (!state) notFound();

  try {
    const [states, apportionment] = await Promise.all([
      loadStatesGeoJSON(),
      getApportionment(cap),
    ]);

    const seats = apportionment.apportionment[stateFips] ?? 0;
    const population = US_2020_APPORTIONMENT_POPULATIONS[stateFips] ?? 0;
    const avgDistrict = seats > 0 ? Math.round(population / seats) : null;
    const baselineSeats = await getApportionment(CAP_MIN).then(
      (r) => r.apportionment[stateFips] ?? 0
    );
    const delta = seats - baselineSeats;

    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Link
          href={`/districts?cap=${cap}`}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-6"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to national overview
        </Link>

        <header className="mb-8 space-y-2">
          <div className="flex items-baseline justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">
                {state.name}
              </h1>
              <p className="text-muted-foreground text-sm">
                FIPS {state.fips} &middot; {state.abbr}
              </p>
            </div>
            <Badge variant="secondary" className="text-sm">
              House cap {cap.toLocaleString()}
            </Badge>
          </div>
        </header>

        <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_18rem]">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">State outline</CardTitle>
              <CardDescription>
                Algorithmic district polygons land in step 4. For now, the
                state shape and its apportioned seat count.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <StateDetailMap states={states} stateFips={state.fips} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">At cap = {cap.toLocaleString()}</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Seats</dt>
                <dd className="text-right tabular-nums">{seats}</dd>
                <dt className="text-muted-foreground">2020 population</dt>
                <dd className="text-right tabular-nums">
                  {population.toLocaleString()}
                </dd>
                {avgDistrict !== null && (
                  <>
                    <dt className="text-muted-foreground">Avg. district</dt>
                    <dd className="text-right tabular-nums">
                      {avgDistrict.toLocaleString()} ppl
                    </dd>
                  </>
                )}
                {cap !== CAP_MIN && (
                  <>
                    <dt className="text-muted-foreground">vs. {CAP_MIN}</dt>
                    <dd
                      className={`text-right tabular-nums ${
                        delta > 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : delta < 0
                          ? "text-rose-600 dark:text-rose-400"
                          : ""
                      }`}
                    >
                      {delta > 0 ? `+${delta}` : delta}
                    </dd>
                  </>
                )}
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Unknown error reaching the API.";
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Link
          href="/districts"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-6"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to national overview
        </Link>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Districting API unavailable</AlertTitle>
          <AlertDescription>
            <p>Could not load this state. Most likely cause: the Python API isn&rsquo;t running.</p>
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
  return getNearestAnchor(n).cap;
}
