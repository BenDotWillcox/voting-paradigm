import Link from "next/link";
import { ArrowLeft, Network } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function LiquidPlaceholderPage() {
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
            <Network className="h-6 w-6" />
          </div>
          <Badge variant="outline">Planned</Badge>
        </div>

        <div className="max-w-3xl space-y-3">
          <h1 className="text-3xl font-bold tracking-tight">
            Liquid democracy
          </h1>
          <p className="text-lg text-muted-foreground">
            This demo will simulate topic-based delegation, transitive voting
            power, and concentration risks in a liquid democracy network.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Planned workflow</CardTitle>
            <CardDescription>
              The placeholder is live so navigation can show the full portfolio
              shape before the simulation is built.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-3 text-sm text-muted-foreground sm:grid-cols-3">
              <li className="rounded-md border p-3">
                Create voters, topics, and delegation edges.
              </li>
              <li className="rounded-md border p-3">
                Resolve transitive vote flow through the delegation graph.
              </li>
              <li className="rounded-md border p-3">
                Compare direct results against delegated outcomes.
              </li>
            </ul>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
