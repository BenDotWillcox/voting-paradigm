import type { Metadata } from "next";
import Link from "next/link";
import { ProfileView } from "@/components/liquid/profile-view";
import { getDelegationScenario, getPersonProfile } from "@/lib/delegation-api";
import type { PersonProfile } from "@/types/delegation";

export const metadata: Metadata = { title: "Profile · Liquid democracy" };

/** The profile behind a username; null when there is no such person or no service. */
async function loadProfile(username: string): Promise<PersonProfile | null> {
  try {
    const scenario = await getDelegationScenario();
    const person = scenario.persons.find((entry) => entry.username === username);
    return person ? await getPersonProfile(person.id) : null;
  } catch (error) {
    console.error("Error loading a liquid democracy profile:", error);
    return null;
  }
}

export default async function LiquidProfilePage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;
  const profile = await loadProfile(decodeURIComponent(username));

  if (!profile) {
    return (
      <div className="space-y-3 text-sm">
        <p>Nobody in this city goes by that username.</p>
        <Link href="/liquid" className="underline underline-offset-4">
          Back to your delegations
        </Link>
      </div>
    );
  }
  return <ProfileView profile={profile} />;
}
