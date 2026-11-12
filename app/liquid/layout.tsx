import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AccountProvider } from "@/components/liquid/account-provider";
import { AppShell } from "@/components/liquid/app-shell";
import { getDelegationScenario } from "@/lib/delegation-api";
import type { DelegationScenario } from "@/types/delegation";

export const metadata: Metadata = {
  title: "Liquid democracy",
  description:
    "An account in a city that votes by liquid democracy: hand categories of decisions, in your own words, to people you trust, see whose votes reach you, and read anyone's record.",
};

// The network is rebuilt by the Python service on request, never at build time.
export const dynamic = "force-dynamic";

async function loadScenario(): Promise<DelegationScenario | null> {
  try {
    return await getDelegationScenario();
  } catch (error) {
    console.error("Error loading the liquid democracy scenario:", error);
    return null;
  }
}

export default async function LiquidLayout({ children }: { children: React.ReactNode }) {
  const scenario = await loadScenario();

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All demos
      </Link>
      <header className="mb-6 max-w-3xl space-y-2">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-700 dark:text-indigo-300">
          Demo 05 · Liquid democracy
        </p>
        <h1 className="text-3xl font-semibold tracking-tight">
          Keep the decisions you care about. Hand the rest to people you trust.
        </h1>
        <p className="leading-relaxed text-muted-foreground">
          Below is an account in a simulated city of 240 residents that votes this way. Use it
          as you would any app. The people, their delegations and the votes are made up; the
          routing is real.
        </p>
      </header>

      {scenario ? (
        <AccountProvider scenario={scenario}>
          <AppShell>{children}</AppShell>
        </AccountProvider>
      ) : (
        <div className="max-w-3xl rounded-lg border p-5 text-sm leading-relaxed text-muted-foreground">
          <p className="font-medium text-foreground">The delegation service is not reachable.</p>
          <p>
            This demo resolves every vote through the Python service, which is not answering
            right now. Please try again shortly.
          </p>
        </div>
      )}
    </main>
  );
}
