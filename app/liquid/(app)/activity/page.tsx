import type { Metadata } from "next";
import { ActivityLog } from "@/components/liquid/activity-log";
import { getDelegationScenario, getPersonProfile } from "@/lib/delegation-api";
import type { PersonProfile } from "@/types/delegation";

export const metadata: Metadata = { title: "Activity · Liquid democracy" };

/** The viewer's own profile, which holds their dated changes and past votes. */
async function loadViewer(): Promise<PersonProfile | null> {
  try {
    const scenario = await getDelegationScenario();
    return await getPersonProfile(scenario.viewer);
  } catch (error) {
    console.error("Error loading the liquid democracy activity log:", error);
    return null;
  }
}

export default async function LiquidActivityPage() {
  const profile = await loadViewer();
  if (!profile) {
    return <p className="text-sm text-muted-foreground">Your activity could not be loaded.</p>;
  }
  return <ActivityLog profile={profile} />;
}
