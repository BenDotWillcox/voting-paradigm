import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { PersonalBallotJournal } from "@/components/preferences/personal-ballot-journal";
import { isJournalLoopbackHost } from "@/lib/personal-journal-local";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Personal ballot journal",
  robots: { index: false, follow: false },
};

export default async function PersonalBallotJournalPage() {
  if (process.env.NODE_ENV !== "development" || process.env.PERSONAL_JOURNAL_LOCAL !== "1") notFound();
  if (!isJournalLoopbackHost((await headers()).get("host"))) notFound();

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-8 md:py-12">
      <Link href="/preferences" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground hover:underline">
        <ArrowLeft aria-hidden="true" className="size-4" /> Back to the preference demo
      </Link>
      <header className="my-8 max-w-3xl space-y-3">
        <h1 className="font-serif text-4xl tracking-tight sm:text-5xl">Personal ballot journal</h1>
        <p className="max-w-2xl leading-relaxed text-muted-foreground">
          Bring a yes/no measure, lock the model’s prediction, then cast your own vote to see how they compare.
          Your journal is saved on this computer.
        </p>
      </header>
      <PersonalBallotJournal />
    </main>
  );
}
