import Link from "next/link";
import { ArrowLeft, Bot, Lock, PlayCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { LocalElicitationLab } from "@/components/preferences/local-elicitation-lab";
import { PreferenceDemoLab } from "@/components/preferences/preference-demo-lab";

export const dynamic = "force-dynamic";

type DemoMode = "replay" | "live";

export default function PreferencesPage() {
  const configuredMode: DemoMode =
    process.env.PREFERENCE_DEMO_MODE === "live" ? "live" : "replay";
  const liveEnabled =
    configuredMode === "live" &&
    process.env.ENABLE_LIVE_PREFERENCE_LLM === "true" &&
    process.env.NODE_ENV !== "production";
  const walkthroughVideoSrc =
    process.env.NEXT_PUBLIC_PREFERENCE_WALKTHROUGH_SRC || null;

  return (
    <main className="container mx-auto max-w-7xl px-4 py-8">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to demos
      </Link>

      <header className="mb-8 space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">
            <Bot className="h-3 w-3" />
            Preference model
          </Badge>
          <Badge variant={liveEnabled ? "default" : "outline"}>
            {liveEnabled ? (
              <>
                <PlayCircle className="h-3 w-3" />
                Local live mode
              </>
            ) : (
              <>
                <Lock className="h-3 w-3" />
                Public replay mode
              </>
            )}
          </Badge>
        </div>
        <div className="max-w-4xl space-y-3">
          <p className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Agent voting via preference models
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            A GPT-OSS interviewer turns one voter&apos;s values into an
            auditable ballot.
          </h1>
          <p className="text-muted-foreground text-lg">
            This video-first demo shows the individual experience: a local
            open-weight agent asks follow-up questions, structured evidence
            updates a transparent model, and the model previews a vote on a
            transportation and climate ballot.
          </p>
        </div>
      </header>

      <PreferenceDemoLab
        configuredMode={configuredMode}
        liveEnabled={liveEnabled}
        walkthroughVideoSrc={walkthroughVideoSrc}
      />

      {process.env.NODE_ENV !== "production" && <LocalElicitationLab />}
    </main>
  );
}
