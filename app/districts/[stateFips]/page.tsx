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
import { StatePriorityChart } from "@/components/districting/state-priority-chart";
import { StateSeatLadder } from "@/components/districting/state-seat-ladder";
import {
  buildStatePriorityCurve,
  getNextCandidates,
  getStateSeatLadder,
} from "@/lib/apportionment-sequence";
import { getApportionment } from "@/lib/districting-api";
import { CAP_MIN } from "@/lib/districting-cap-scale";
import { US_2020_APPORTIONMENT_POPULATIONS } from "@/lib/us-state-populations";
import { getStateByFips, isStateFips } from "@/lib/us-states";

export const dynamic = "force-dynamic";

interface StatePageProps {
  params: Promise<{ stateFips: string }>;
}

export default async function StateDetailPage({
  params,
}: StatePageProps) {
  const { stateFips } = await params;
  const cap = CAP_MIN;

  if (!isStateFips(stateFips)) notFound();
  const state = getStateByFips(stateFips);
  if (!state) notFound();

  try {
    const apportionment = await getApportionment(cap);

    const seats = apportionment.apportionment[stateFips] ?? 0;
    const population = US_2020_APPORTIONMENT_POPULATIONS[stateFips] ?? 0;
    const avgDistrict = seats > 0 ? Math.round(population / seats) : null;
    const seatLadder = getStateSeatLadder(stateFips, cap);
    const priorityCurve = buildStatePriorityCurve(stateFips, Math.max(seats + 8, 12));
    const nextCandidate = getNextCandidates(cap, 50).find(
      (candidate) => candidate.stateFips === stateFips
    );

    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Link
          href="/districts"
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
              Current 435-seat House
            </Badge>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Priority curve</CardTitle>
                <CardDescription>
                  Each additional state seat lowers its priority for the next
                  seat. Higher priority wins the next national allocation.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <StatePriorityChart data={priorityCurve} stateName={state.name} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Seat ladder</CardTitle>
                <CardDescription>
                  The national seat numbers where {state.name} received each
                  representative after its guaranteed first seat.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <StateSeatLadder steps={seatLadder} />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Current apportionment</CardTitle>
              <CardDescription>
                Method of Equal Proportions at 435 seats.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Seats</dt>
                <dd className="text-right tabular-nums">{seats}</dd>
                <dt className="text-muted-foreground">Population</dt>
                <dd className="text-right tabular-nums">
                  {population.toLocaleString()}
                </dd>
                {avgDistrict !== null && (
                  <>
                    <dt className="text-muted-foreground">People / seat</dt>
                    <dd className="text-right tabular-nums">
                      {avgDistrict.toLocaleString()}
                    </dd>
                  </>
                )}
                {nextCandidate && (
                  <>
                    <dt className="text-muted-foreground">Next priority</dt>
                    <dd className="text-right tabular-nums">
                      {Math.round(nextCandidate.priority).toLocaleString()}
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
