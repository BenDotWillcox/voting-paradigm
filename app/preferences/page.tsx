import { getAllUsers } from "@/db/queries/users-queries";
import { listUserPreferenceSessionsAction } from "@/actions/preferences-actions";
import { StartSessionForm } from "@/components/preferences/start-session-form";

export const dynamic = "force-dynamic";

export default async function PreferencesLandingPage() {
  const users = await getAllUsers();

  // For v1 (no auth) we preload sessions for all users so we can surface
  // the "resume active session" affordance after they pick who they are.
  const sessionLists = await Promise.all(
    users.map(async (u) => {
      const res = await listUserPreferenceSessionsAction(u.id);
      if (!res.isSuccess || !res.data) return [];
      return res.data.map((s) => ({ ...s, userId: u.id }));
    })
  );
  const existingSessions = sessionLists.flat();

  return (
    <div className="container mx-auto max-w-2xl py-10 space-y-8">
      <div className="space-y-3">
        <h1 className="text-3xl font-bold">Discover Your Values</h1>
        <p className="text-muted-foreground">
          Answer a series of pairwise tradeoffs between civic values. A
          Bayesian model updates after each answer to build a personal map of
          what matters to you — with calibrated uncertainty. Takes ~5–10
          minutes for 25 questions.
        </p>
      </div>

      <div className="rounded-xl border bg-card p-6 shadow-sm">
        <StartSessionForm
          users={users.map((u) => ({ id: u.id, name: u.handle }))}
          existingSessions={existingSessions}
        />
      </div>

      <div className="text-sm text-muted-foreground space-y-2">
        <p className="font-medium">How it works:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            Each question asks you to pick between two civic values using a
            slider — the further you drag, the stronger the preference.
          </li>
          <li>
            We use a Thurstone pairwise model with a Laplace-approximated
            Gaussian posterior, so every answer refines a learned latent
            utility for each value.
          </li>
          <li>
            At the end you&apos;ll see your values ranked by posterior mean,
            with uncertainty bands from the posterior variance.
          </li>
        </ul>
      </div>
    </div>
  );
}
