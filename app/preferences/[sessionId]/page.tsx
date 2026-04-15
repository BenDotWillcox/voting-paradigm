import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { getPreferenceSessionAction } from "@/actions/preferences-actions";
import { ElicitationFlow } from "@/components/preferences/elicitation-flow";
import { Button } from "@/components/ui/button";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ sessionId: string }>;
}

export default async function PreferenceSessionPage({ params }: PageProps) {
  const { sessionId } = await params;
  const result = await getPreferenceSessionAction(sessionId);

  if (!result.isSuccess || !result.data) {
    notFound();
  }

  const session = result.data;

  if (session.progress.isComplete) {
    redirect(`/preferences/${sessionId}/summary`);
  }

  if (!session.question) {
    // Active but no question — data inconsistency. Offer recovery.
    return (
      <div className="container mx-auto max-w-2xl py-10 space-y-4">
        <h1 className="text-2xl font-bold">Session unavailable</h1>
        <p className="text-muted-foreground">
          This session has no pending question. Try starting a new one.
        </p>
        <Button asChild>
          <Link href="/preferences">Back to start</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-3xl py-10">
      <ElicitationFlow initial={session} />
    </div>
  );
}
