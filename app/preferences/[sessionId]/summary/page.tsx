import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getPreferenceSessionAction,
  getPreferenceSummaryAction,
} from "@/actions/preferences-actions";
import { ValuesRanking } from "@/components/preferences/values-ranking";
import { Button } from "@/components/ui/button";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ sessionId: string }>;
}

export default async function PreferenceSummaryPage({ params }: PageProps) {
  const { sessionId } = await params;

  const [sessionRes, summaryRes] = await Promise.all([
    getPreferenceSessionAction(sessionId),
    getPreferenceSummaryAction(sessionId),
  ]);

  if (!sessionRes.isSuccess || !sessionRes.data) notFound();
  if (!summaryRes.isSuccess || !summaryRes.data) {
    return (
      <div className="container mx-auto max-w-2xl py-10 space-y-4">
        <h1 className="text-2xl font-bold">Summary unavailable</h1>
        <p className="text-muted-foreground">{summaryRes.message}</p>
      </div>
    );
  }

  const session = sessionRes.data;
  const summary = summaryRes.data;

  return (
    <div className="container mx-auto max-w-3xl py-10 space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold">Your Values</h1>
        <p className="text-muted-foreground">
          Ranked by posterior mean utility. The faded band shows one posterior
          standard deviation — narrower bands mean higher confidence.
        </p>
        <p className="text-xs text-muted-foreground">
          Model: {summary.model_version} · Answered{" "}
          {summary.progress.n_answered} of {summary.progress.target_questions}{" "}
          questions ·{" "}
          {summary.progress.is_complete ? "Session complete" : "In progress"}
        </p>
      </div>

      <ValuesRanking values={summary.values} />

      <div className="flex gap-2">
        <Button variant="outline" asChild>
          <Link href="/preferences">Start another session</Link>
        </Button>
        {!session.progress.isComplete && (
          <Button asChild>
            <Link href={`/preferences/${sessionId}`}>Continue session</Link>
          </Button>
        )}
      </div>
    </div>
  );
}
