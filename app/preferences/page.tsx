import Link from "next/link";
import { ArrowLeft, Bot } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function PreferencesPlaceholderPage() {
  return (
    <main className="container mx-auto max-w-4xl px-4 py-12">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to demos
      </Link>

      <section className="space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-lg bg-muted p-2">
            <Bot className="h-6 w-6" />
          </div>
          <Badge variant="secondary">In progress</Badge>
        </div>

        <div className="max-w-3xl space-y-3">
          <h1 className="text-3xl font-bold tracking-tight">
            Agent voting via preference models
          </h1>
          <p className="text-lg text-muted-foreground">
            This demo will show how pairwise elicitation can build a preference
            model, let an agent cast a ballot from that model, and flag
            decisions where the model needs more input.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Planned workflow</CardTitle>
            <CardDescription>
              The placeholder is live so the portfolio can expose the full demo
              sequence while implementation continues.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-3 text-sm text-muted-foreground sm:grid-cols-3">
              <li className="rounded-md border p-3">
                Elicit preferences with pairwise civic choices.
              </li>
              <li className="rounded-md border p-3">
                Fit a model that captures tradeoffs and uncertainty.
              </li>
              <li className="rounded-md border p-3">
                Cast and audit simulated ballots from the learned model.
              </li>
            </ul>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
