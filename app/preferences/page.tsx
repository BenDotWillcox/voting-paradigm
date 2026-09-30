import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PreferenceElicitation } from "@/components/preferences/preference-elicitation";

export default function PreferencesPage() {
  return (
    <main className="container mx-auto max-w-4xl px-4 py-8">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to demos
      </Link>

      <header className="mb-8 space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">Preference modeling</Badge>
          <Badge variant="outline">Interactive · no LLM calls</Badge>
        </div>
        <div className="max-w-4xl space-y-3">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Preference elicitation · interaction prototype
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Where do you stand—and how sure are you?
          </h1>
          <p className="text-muted-foreground text-lg">
            Explore one choice at a time. Keep your preferred position,
            uncertainty, and the outcomes you could accept separate.
          </p>
          <p className="text-sm text-muted-foreground">
            This prototype records what you tell it. It does not yet infer
            preferences, recommend choices, or conduct an AI interview.
          </p>
        </div>
      </header>

      <PreferenceElicitation />

      <aside className="mt-8 border-t pt-6 text-sm">
        <h2 className="font-semibold">What has been measured?</h2>
        <p className="mt-2 text-muted-foreground">
          The reproducible 1,080-trial synthetic benchmark compares recovery of
          generated latent preference orderings. It does not establish human
          decision accuracy or validate this new spectrum interaction.
        </p>
        <a className="mt-2 inline-block font-medium underline underline-offset-4"
          href="https://github.com/BenDotWillcox/voting-paradigm/tree/main/eval/benchmarks/synthetic_v1">
          Read the benchmark, curves, and limitations
        </a>
      </aside>
    </main>
  );
}
