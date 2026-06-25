import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";
import { MethodsLab } from "@/components/methods/methods-lab";
import { fetchDemoScenarios, resolveDemoScenario } from "@/lib/methods-api";

export const dynamic = "force-dynamic";

export default async function MethodsPage() {
  try {
    const scenarios = await fetchDemoScenarios();
    const firstScenario = scenarios[0];
    if (!firstScenario) {
      throw new Error("No methods demo scenarios are configured.");
    }
    const initialResolution = await resolveDemoScenario(
      firstScenario.id,
      firstScenario.default_controls
    );

    return (
      <div className="container mx-auto max-w-7xl px-4 py-8">
        <div className="mb-8">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Voting methods lab
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
            Same electorate, different democracy.
          </h1>
          <p className="mt-3 max-w-3xl text-muted-foreground">
            Explore how plurality, approval, IRV, Borda, Ranked Pairs, score,
            and quadratic voting transform the same voter blocs into different
            winners, explanations, and failure modes.
          </p>
        </div>

        <MethodsLab
          scenarios={scenarios}
          initialResolution={initialResolution}
        />
      </div>
    );
  } catch {
    return (
      <div className="container mx-auto max-w-5xl px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Compare Voting Methods</h1>
        </div>

        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Python API Unavailable</AlertTitle>
          <AlertDescription>
            Could not connect to the voting API. Make sure the Python server is
            running:
            <code className="block mt-2 p-2 bg-muted rounded text-sm">
              npm run api:dev
            </code>
          </AlertDescription>
        </Alert>
      </div>
    );
  }
}
