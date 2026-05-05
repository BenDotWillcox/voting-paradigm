import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertCircle } from "lucide-react";
import { MethodsExplorer } from "@/components/methods/methods-explorer";
import { fetchAllScenarioResults } from "@/lib/methods-api";

export const dynamic = "force-dynamic";

export default async function MethodsPage() {
  try {
    const demos = await fetchAllScenarioResults();

    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Compare Voting Methods</h1>
          <p className="text-muted-foreground mt-2">
            See how 7 different voting methods produce different winners from the
            same voter preferences. Each scenario is designed to highlight a
            unique property of the method.
          </p>
        </div>

        <MethodsExplorer demos={demos} />
      </div>
    );
  } catch {
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
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
