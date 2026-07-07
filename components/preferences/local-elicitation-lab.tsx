import { FlaskConical } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { StartSessionForm } from "@/components/preferences/start-session-form";
import { getActiveSessions } from "@/db/queries/preferences-queries";
import { getAllUsers } from "@/db/queries/users-queries";

/**
 * Dev-only entry point for the DB-backed classical elicitation flow
 * (fixed-bank pairwise sliders -> Bayesian posterior -> values ranking).
 * Rendered by /preferences only outside production; requires local Postgres
 * and the Python API. Degrades to a hint instead of crashing the curated
 * demo when either is missing.
 */
export async function LocalElicitationLab() {
  let users: { id: string; name: string }[] = [];
  let sessions: {
    id: string;
    userId: string;
    status: string;
    nQuestions: number;
    targetQuestions: number;
  }[] = [];
  let dbError: string | null = null;

  try {
    const [userRows, sessionRows] = await Promise.all([
      getAllUsers(),
      getActiveSessions(),
    ]);
    users = userRows.map((u) => ({ id: u.id, name: u.handle }));
    sessions = sessionRows.map((s) => ({
      id: s.id,
      userId: s.userId,
      status: s.status,
      nQuestions: s.nQuestions,
      targetQuestions: s.targetQuestions,
    }));
  } catch (error) {
    console.error("LocalElicitationLab query error:", error);
    dbError = "Database not reachable — is Postgres running?";
  }

  return (
    <section className="mt-10 rounded-xl border border-dashed p-6">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge variant="outline">
          <FlaskConical className="h-3 w-3" />
          Local lab
        </Badge>
        <span className="text-sm font-medium">
          Classical elicitation session
        </span>
      </div>
      <p className="mb-6 max-w-3xl text-sm text-muted-foreground">
        Runs the research flow behind this demo end-to-end: pairwise slider
        questions over the fixed 36-item civic-value bank, max-variance
        question selection, and a live Bayesian posterior served by the Python
        API. Sessions persist to Postgres. This section is only rendered in
        local development.
      </p>
      {dbError ? (
        <p className="text-sm text-destructive">{dbError}</p>
      ) : users.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No personas found — insert a row into <code>app_user</code> to start
          a session.
        </p>
      ) : (
        <div className="max-w-md">
          <StartSessionForm users={users} existingSessions={sessions} />
        </div>
      )}
    </section>
  );
}
