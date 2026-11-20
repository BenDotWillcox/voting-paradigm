"use client";

import * as React from "react";

import { getDelegationScenarioAction } from "@/actions/delegation-actions";
import { AccountProvider } from "@/components/liquid/account-provider";
import { AppShell } from "@/components/liquid/app-shell";
import { HubHome } from "@/components/liquid/hub-home";
import { RoutingTracer } from "@/components/liquid/routing-tracer";
import type { DelegationScenario } from "@/types/delegation";

type State =
  | { status: "loading" }
  | { status: "ready"; scenario: DelegationScenario }
  | { status: "unavailable" };

/**
 * The account app's hub, at the bottom of the walkthrough. The page is
 * static, so the scenario is loaded here, in the browser, from the Python
 * service; the app's other screens (/liquid/votes, ...) load it on the
 * server. The fallback is the app's own.
 */
export function AppSection() {
  const [state, setState] = React.useState<State>({ status: "loading" });

  React.useEffect(() => {
    let live = true;
    getDelegationScenarioAction()
      .then((result) => {
        if (!live) return;
        setState(result.isSuccess && result.data ? { status: "ready", scenario: result.data } : { status: "unavailable" });
      })
      .catch(() => live && setState({ status: "unavailable" }));
    return () => {
      live = false;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <div
        aria-busy="true"
        className="liquid-app dark flex min-h-[28rem] items-center justify-center rounded-2xl border text-sm text-muted-foreground"
      >
        Loading the account…
      </div>
    );
  }
  if (state.status === "unavailable") {
    return (
      <div className="max-w-3xl rounded-lg border p-5 text-sm leading-relaxed text-muted-foreground">
        <p className="font-medium text-foreground">The delegation service is not reachable.</p>
        <p>
          This demo resolves every vote through the Python service, which is not answering right now. Please try
          again shortly.
        </p>
      </div>
    );
  }
  return (
    <AccountProvider scenario={state.scenario}>
      <AppShell>
        <HubHome />
      </AppShell>
      <RoutingTracer />
    </AccountProvider>
  );
}
