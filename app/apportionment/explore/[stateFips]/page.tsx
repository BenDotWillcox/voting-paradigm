import { notFound, permanentRedirect } from "next/navigation";

import { getStateByFips, isStateFips, US_STATES } from "@/lib/us-states";

// The old per-state pages now live in the explorer's state panel.
export const dynamicParams = false;

export function generateStaticParams() {
  return US_STATES.map((state) => ({ stateFips: state.fips }));
}

export default async function StateRedirect({ params }: { params: Promise<{ stateFips: string }> }) {
  const { stateFips } = await params;
  const state = isStateFips(stateFips) ? getStateByFips(stateFips) : undefined;
  if (!state) notFound();
  permanentRedirect(`/apportionment/explore?state=${state.abbr.toLowerCase()}`);
}
