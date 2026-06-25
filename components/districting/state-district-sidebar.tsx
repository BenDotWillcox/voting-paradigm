"use client";

import { LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { cn } from "@/lib/utils";
import { US_STATES } from "@/lib/us-states";

interface StateDistrictSidebarProps {
  activeFips: string;
}

export function StateDistrictSidebar({ activeFips }: StateDistrictSidebarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [, startTransition] = React.useTransition();
  const [pendingFips, setPendingFips] = React.useState<string | null>(null);
  const isLoadingState = pendingFips !== null;

  React.useEffect(() => {
    setPendingFips(null);
  }, [activeFips]);

  const navigateToState = React.useCallback(
    (event: React.MouseEvent<HTMLAnchorElement>, fips: string) => {
      if (
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey ||
        event.button !== 0
      ) {
        return;
      }

      if (fips === activeFips || isLoadingState) {
        event.preventDefault();
        return;
      }

      const params = new URLSearchParams(searchParams.toString());
      params.set("tab", "districting");
      params.set("state", fips);
      event.preventDefault();
      setPendingFips(fips);
      startTransition(() => {
        router.push(`/districts?${params.toString()}`, { scroll: false });
      });
    },
    [activeFips, isLoadingState, router, searchParams]
  );

  return (
    <aside className="grid h-full min-h-0 w-full grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-lg border bg-card">
      <div className="border-b p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">States</div>
            <div className="text-xs text-muted-foreground">
              Current 435-seat district plans
            </div>
          </div>
          {isLoadingState ? (
            <LoaderCircle
              className="mt-0.5 h-4 w-4 animate-spin text-muted-foreground"
              aria-label="Loading state"
            />
          ) : null}
        </div>
      </div>
      <div className="min-h-0 min-w-0 overflow-y-auto overflow-x-hidden">
        <nav className="w-full p-2">
          {US_STATES.map((state) => {
            const active = state.fips === activeFips;
            const pending = state.fips === pendingFips;
            return (
              <Link
                key={state.fips}
                href={`/districts?tab=districting&state=${state.fips}`}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                aria-disabled={active || isLoadingState}
                onClick={(event) => navigateToState(event, state.fips)}
                className={cn(
                  "grid w-full min-w-0 grid-cols-[minmax(0,1fr)_2.5rem] items-center gap-3 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted aria-disabled:opacity-60"
                )}
              >
                <span className="min-w-0 truncate">{state.name}</span>
                {pending ? (
                  <LoaderCircle className="ml-auto h-3.5 w-3.5 animate-spin opacity-80" />
                ) : (
                  <span
                    className={cn(
                      "text-right",
                      active ? "opacity-80" : "text-muted-foreground"
                    )}
                  >
                    {state.abbr}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
