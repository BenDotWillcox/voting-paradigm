"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Lock,
  Play,
  RefreshCcw,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Video,
  Vote,
  Workflow,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  ballotOptions,
  computeAgentVote,
  createInitialPreferenceState,
  getPreferenceDimension,
  normalizeSignals,
  recomputePreferenceState,
  replayTurns,
  type AgentVote,
  type BallotOption,
  type PreferenceDemoState,
  type PreferenceDimensionId,
  type PreferenceEstimate,
  type PreferenceMessage,
  type PreferenceSignal,
} from "@/lib/preferences-demo";

type DemoMode = "replay" | "live";

interface PreferenceDemoLabProps {
  configuredMode: DemoMode;
  liveEnabled: boolean;
  walkthroughVideoSrc?: string | null;
}

type PreferenceChatApiResponse = {
  mode: "live" | "disabled" | "error";
  reason?: string;
  assistantMessage: string;
  signals: PreferenceSignal[];
};

const STORAGE_KEY = "nebula-preference-demo-state-v1";

export function PreferenceDemoLab({
  configuredMode,
  liveEnabled,
  walkthroughVideoSrc,
}: PreferenceDemoLabProps) {
  const [state, setState] = useState<PreferenceDemoState>(() =>
    createInitialPreferenceState()
  );
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [hasHydrated, setHasHydrated] = useState(false);
  const [isPending, startTransition] = useTransition();

  const isLiveUsable = configuredMode === "live" && liveEnabled;
  const selectedOption = ballotOptions.find(
    (option) => option.id === state.vote.selectedOptionId
  );
  const replayComplete = state.replayStep >= replayTurns.length;

  useEffect(() => {
    setState(loadStoredState());
    setHasHydrated(true);
  }, []);

  useEffect(() => {
    if (!hasHydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Some restricted preview/browser contexts disable storage.
    }
  }, [hasHydrated, state]);

  function updateState(nextState: PreferenceDemoState) {
    setState(recomputePreferenceState(nextState));
  }

  function advanceReplay() {
    const nextTurn = replayTurns[state.replayStep];
    if (!nextTurn) return;
    setError(null);
    updateState({
      ...state,
      messages: [...state.messages, ...nextTurn.messages],
      signals: normalizeSignals([...state.signals, ...nextTurn.signals]),
      replayStep: state.replayStep + 1,
    });
  }

  function resetDemo() {
    const initialState = createInitialPreferenceState();
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Replay remains usable without persistent browser storage.
    }
    setDraft("");
    setError(null);
    setState(initialState);
  }

  function setOverride(optionId: string | null) {
    updateState({
      ...state,
      overrideOptionId: state.overrideOptionId === optionId ? null : optionId,
      vote: computeAgentVote(state.estimates, optionId),
    });
  }

  function submitLiveMessage() {
    const content = draft.trim();
    if (!content || !isLiveUsable) return;

    const userMessage: PreferenceMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content,
    };
    const messages = [...state.messages, userMessage];
    setDraft("");
    setError(null);

    updateState({
      ...state,
      messages,
    });

    startTransition(async () => {
      try {
        const response = await fetch("/api/preferences/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages,
            estimates: state.estimates,
          }),
        });
        const body = (await response.json()) as PreferenceChatApiResponse;
        const assistantMessage: PreferenceMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: body.assistantMessage,
        };

        if (!response.ok || body.mode !== "live") {
          setError(body.assistantMessage);
          updateState({
            ...state,
            messages: [...messages, assistantMessage],
          });
          return;
        }

        updateState({
          ...state,
          messages: [...messages, assistantMessage],
          signals: normalizeSignals([...state.signals, ...body.signals]),
        });
      } catch (caught) {
        const message =
          caught instanceof Error
            ? caught.message
            : "The local GPT-OSS interviewer could not be reached.";
        setError(message);
      }
    });
  }

  return (
    <div className="space-y-8">
      <section className="grid gap-5 lg:grid-cols-[1.25fr_0.75fr]">
        <WalkthroughPanel videoSrc={walkthroughVideoSrc} />
        <SecurityPanel
          configuredMode={configuredMode}
          liveEnabled={liveEnabled}
        />
      </section>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(20rem,0.95fr)]">
        <ChatPanel
          messages={state.messages}
          configuredMode={configuredMode}
          isLiveUsable={isLiveUsable}
          replayComplete={replayComplete}
          replayStep={state.replayStep}
          draft={draft}
          isPending={isPending}
          error={error}
          onDraftChange={setDraft}
          onAdvanceReplay={advanceReplay}
          onReset={resetDemo}
          onSubmitLiveMessage={submitLiveMessage}
        />

        <ModelPanel
          estimates={state.estimates}
          signals={state.signals}
        />
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(22rem,0.9fr)]">
        <BallotPanel
          options={ballotOptions}
          vote={state.vote}
          overrideOptionId={state.overrideOptionId}
          onOverride={setOverride}
        />
        <VotePanel
          vote={state.vote}
          selectedOption={selectedOption}
          overrideOptionId={state.overrideOptionId}
        />
      </section>
    </div>
  );
}

function WalkthroughPanel({ videoSrc }: { videoSrc?: string | null }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Video className="h-5 w-5" />
              Video-first showcase
            </CardTitle>
            <CardDescription>
              Public visitors can watch the walkthrough and inspect a safe replay.
            </CardDescription>
          </div>
          <Badge variant="secondary">Portfolio mode</Badge>
        </div>
      </CardHeader>
      <CardContent>
        {videoSrc ? (
          <video
            className="aspect-video w-full rounded-md border bg-muted object-cover"
            controls
            src={videoSrc}
          />
        ) : (
          <div className="flex aspect-video w-full items-center justify-center rounded-md border bg-[linear-gradient(135deg,oklch(0.97_0.02_220),oklch(0.92_0.04_145))] p-6 text-center">
            <div className="max-w-md space-y-3">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-background/90 shadow-sm">
                <Play className="h-5 w-5" />
              </div>
              <div>
                <p className="font-medium">Recorded walkthrough slot</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  The replay below mirrors the story used for the recording
                  without exposing a live model endpoint.
                </p>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SecurityPanel({
  configuredMode,
  liveEnabled,
}: {
  configuredMode: DemoMode;
  liveEnabled: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" />
          Public-safe by default
        </CardTitle>
        <CardDescription>
          The deployed version does not operate as an LLM proxy.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 text-sm">
          <StatusRow
            label="Page mode"
            value={configuredMode === "live" ? "Live local" : "Replay"}
            active={configuredMode === "replay"}
          />
          <StatusRow
            label="LLM route"
            value={liveEnabled ? "Enabled locally" : "Disabled"}
            active={!liveEnabled}
          />
          <StatusRow
            label="State"
            value="Browser session"
            active
          />
        </div>
        <div className="rounded-md border bg-muted/35 p-3 text-sm text-muted-foreground">
          Live GPT-OSS calls require both local env flags and a localhost Ollama
          endpoint. Production mode refuses live calls even if a route is present.
        </div>
        <div className="grid grid-cols-[auto_1fr] gap-3 rounded-md border p-3 text-sm">
          <Workflow className="mt-0.5 h-4 w-4 text-primary" />
          <p className="text-muted-foreground">
            Chat evidence flows into deterministic scoring; the model vote can
            be audited or overridden.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusRow({
  label,
  value,
  active,
}: {
  label: string;
  value: string;
  active: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border p-2">
      <span className="text-muted-foreground">{label}</span>
      <Badge variant={active ? "secondary" : "outline"}>{value}</Badge>
    </div>
  );
}

function ChatPanel({
  messages,
  configuredMode,
  isLiveUsable,
  replayComplete,
  replayStep,
  draft,
  isPending,
  error,
  onDraftChange,
  onAdvanceReplay,
  onReset,
  onSubmitLiveMessage,
}: {
  messages: PreferenceMessage[];
  configuredMode: DemoMode;
  isLiveUsable: boolean;
  replayComplete: boolean;
  replayStep: number;
  draft: string;
  isPending: boolean;
  error: string | null;
  onDraftChange: (value: string) => void;
  onAdvanceReplay: () => void;
  onReset: () => void;
  onSubmitLiveMessage: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              GPT-OSS interview
            </CardTitle>
            <CardDescription>
              The conversation produces structured preference evidence.
            </CardDescription>
          </div>
          <Badge variant={isLiveUsable ? "default" : "secondary"}>
            {isLiveUsable ? "Live local" : "Static replay"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Preference chat unavailable</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="h-[28rem] overflow-y-auto rounded-md border bg-muted/20 p-3">
          <div className="space-y-3">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>
        </div>

        {isLiveUsable ? (
          <div className="space-y-3">
            <Textarea
              value={draft}
              onChange={(event) => onDraftChange(event.target.value)}
              placeholder="Tell the model what matters to you on this ballot."
              className="min-h-24 resize-none"
              disabled={isPending}
            />
            <div className="flex flex-wrap justify-between gap-2">
              <Button
                variant="outline"
                onClick={onReset}
                disabled={isPending}
                data-testid="preference-live-reset"
              >
                <RefreshCcw className="h-4 w-4" />
                Reset
              </Button>
              <Button
                onClick={onSubmitLiveMessage}
                disabled={isPending || !draft.trim()}
                data-testid="preference-live-send"
              >
                <Send className="h-4 w-4" />
                {isPending ? "Sending" : "Send"}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Replay step {Math.min(replayStep, replayTurns.length)} of{" "}
              {replayTurns.length}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={onReset}
                data-testid="preference-replay-reset"
              >
                <RefreshCcw className="h-4 w-4" />
                Reset
              </Button>
              <Button
                onClick={onAdvanceReplay}
                disabled={replayComplete}
                data-testid="preference-advance-replay"
              >
                <Play className="h-4 w-4" />
                {replayComplete ? "Replay complete" : "Advance replay"}
              </Button>
            </div>
          </div>
        )}

        {configuredMode === "live" && !isLiveUsable && (
          <div className="grid grid-cols-[auto_1fr] gap-2 rounded-md border bg-muted/35 p-3 text-sm text-muted-foreground">
            <Lock className="mt-0.5 h-4 w-4" />
            <p>
              Live mode is configured, but the public-safe gate has disabled
              local model calls in this runtime.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MessageBubble({ message }: { message: PreferenceMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-md border px-3 py-2 text-sm leading-6",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-background text-foreground"
        )}
      >
        {message.content}
      </div>
    </div>
  );
}

function ModelPanel({
  estimates,
  signals,
}: {
  estimates: PreferenceEstimate[];
  signals: PreferenceSignal[];
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <SlidersHorizontal className="h-5 w-5" />
              Preference model
            </CardTitle>
            <CardDescription>
              Value weights update from structured chat evidence.
            </CardDescription>
          </div>
          <Badge variant="outline">{signals.length} signals</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3">
          {estimates.map((estimate) => (
            <DimensionRow key={estimate.dimensionId} estimate={estimate} />
          ))}
        </div>
        <EvidenceList signals={signals} />
      </CardContent>
    </Card>
  );
}

function DimensionRow({ estimate }: { estimate: PreferenceEstimate }) {
  const dimension = getPreferenceDimension(estimate.dimensionId);
  if (!dimension) return null;
  const position = ((estimate.value + 1) / 2) * 100;
  const confidencePct = estimate.confidence * 100;

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: dimension.color }}
            />
            <p className="font-medium">{dimension.label}</p>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {dimension.description}
          </p>
        </div>
        <div className="text-right text-xs tabular-nums text-muted-foreground">
          <div>{estimate.value.toFixed(2)}</div>
          <div>{Math.round(confidencePct)}% sure</div>
        </div>
      </div>
      <div className="space-y-1">
        <div className="relative h-2 rounded-full bg-muted">
          <div
            className="absolute inset-y-0 w-1 rounded-full bg-foreground"
            style={{ left: `calc(${position}% - 2px)` }}
          />
        </div>
        <div className="flex justify-between gap-3 text-[11px] text-muted-foreground">
          <span>{dimension.lowAnchor}</span>
          <span className="text-right">{dimension.highAnchor}</span>
        </div>
      </div>
      <Progress value={confidencePct} className="h-1.5" />
    </div>
  );
}

function EvidenceList({ signals }: { signals: PreferenceSignal[] }) {
  const latestSignals = signals.slice(-5).reverse();
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-sm font-medium">Latest evidence</p>
        <Badge variant="secondary">{latestSignals.length}</Badge>
      </div>
      {latestSignals.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No preference evidence has been extracted yet.
        </p>
      ) : (
        <div className="space-y-2">
          {latestSignals.map((signal, index) => {
            const dimension = getPreferenceDimension(signal.dimensionId);
            return (
              <div
                key={`${signal.dimensionId}-${signal.evidence}-${index}`}
                className="grid grid-cols-[auto_1fr_auto] items-start gap-2 rounded-md bg-background p-2 text-sm"
              >
                <span
                  className="mt-1 h-2 w-2 rounded-full"
                  style={{ backgroundColor: dimension?.color }}
                />
                <div>
                  <p className="font-medium">
                    {dimension?.shortLabel ?? signal.dimensionId}{" "}
                    {signal.direction > 0 ? "+" : "-"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {signal.evidence}
                  </p>
                </div>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {Math.round(signal.confidence * 100)}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function BallotPanel({
  options,
  vote,
  overrideOptionId,
  onOverride,
}: {
  options: BallotOption[];
  vote: AgentVote;
  overrideOptionId: string | null;
  onOverride: (optionId: string | null) => void;
}) {
  const scoreByOption = new Map(
    vote.scores.map((score) => [score.optionId, score])
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Vote className="h-5 w-5" />
              Transportation and climate ballot
            </CardTitle>
            <CardDescription>
              The same learned preferences score every option.
            </CardDescription>
          </div>
          <Badge variant="outline">Curated ballot</Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {options.map((option) => {
          const score = scoreByOption.get(option.id);
          const selected = vote.selectedOptionId === option.id;
          const overridden = overrideOptionId === option.id;
          return (
            <div
              key={option.id}
              className={cn(
                "flex h-full flex-col rounded-md border p-4 transition",
                selected && "border-primary bg-muted/35 ring-2 ring-primary/10"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{option.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {option.summary}
                  </p>
                </div>
                {selected && (
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                )}
              </div>
              <div className="mt-3 space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Model score</span>
                  <span className="tabular-nums">
                    {Math.round(score?.normalizedScore ?? 0)}
                  </span>
                </div>
                <Progress value={score?.normalizedScore ?? 0} />
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {score?.matchedDimensions.slice(0, 4).map((dimensionId) => {
                  const dimension = getPreferenceDimension(dimensionId);
                  return (
                    <Badge key={dimensionId} variant="secondary">
                      {dimension?.shortLabel ?? dimensionId}
                    </Badge>
                  );
                })}
              </div>
              <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                {option.tradeoffs.map((tradeoff) => (
                  <li key={tradeoff} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" />
                    <span>{tradeoff}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-auto pt-4">
                <Button
                  variant={overridden ? "default" : "outline"}
                  size="sm"
                  onClick={() => onOverride(option.id)}
                  className="w-full"
                  data-testid={`preference-override-${option.id}`}
                >
                  {overridden ? "Override selected" : "Override to this"}
                </Button>
              </div>
            </div>
          );
        })}
        {overrideOptionId && (
          <div className="md:col-span-2">
            <Button variant="ghost" onClick={() => onOverride(null)}>
              Clear override
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function VotePanel({
  vote,
  selectedOption,
  overrideOptionId,
}: {
  vote: AgentVote;
  selectedOption?: BallotOption;
  overrideOptionId: string | null;
}) {
  const uncertainLabels = useMemo(
    () =>
      vote.uncertainDimensions
        .map((dimensionId) => getPreferenceDimension(dimensionId)?.shortLabel)
        .filter(Boolean),
    [vote.uncertainDimensions]
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Agent vote preview</CardTitle>
            <CardDescription>
              Final ballot intent remains reviewable before submission.
            </CardDescription>
          </div>
          <Badge variant={overrideOptionId ? "default" : "secondary"}>
            {overrideOptionId ? "User override" : "Model vote"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="rounded-md border bg-muted/35 p-4">
          <p className="text-sm text-muted-foreground">Selected option</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">
            {selectedOption?.title ?? "No option selected"}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {vote.rationale}
          </p>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span>Vote confidence</span>
            <span className="tabular-nums">
              {Math.round(vote.confidence * 100)}%
            </span>
          </div>
          <Progress value={vote.confidence * 100} className="h-2.5" />
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Ranked scorecard</p>
          {vote.scores.map((score, index) => {
            const option = ballotOptions.find(
              (candidate) => candidate.id === score.optionId
            );
            return (
              <div
                key={score.optionId}
                className="grid grid-cols-[1.5rem_minmax(0,1fr)_3rem] items-center gap-2 text-sm"
              >
                <span className="text-xs text-muted-foreground">
                  #{index + 1}
                </span>
                <div className="min-w-0">
                  <div className="truncate">{option?.title}</div>
                  <Progress value={score.normalizedScore} className="mt-1 h-1.5" />
                </div>
                <span className="text-right text-xs tabular-nums text-muted-foreground">
                  {Math.round(score.normalizedScore)}
                </span>
              </div>
            );
          })}
        </div>

        <div className="rounded-md border p-3 text-sm">
          <p className="mb-2 font-medium">Uncertainty watchlist</p>
          {uncertainLabels.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {uncertainLabels.map((label) => (
                <Badge key={label} variant="outline">
                  {label}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground">
              No high-impact uncertainty is blocking the current vote.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function loadStoredState(): PreferenceDemoState {
  if (typeof window === "undefined") {
    return createInitialPreferenceState();
  }

  const initialState = createInitialPreferenceState();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return initialState;

    const parsed = JSON.parse(raw) as Partial<PreferenceDemoState>;
    if (!Array.isArray(parsed.messages) || !Array.isArray(parsed.signals)) {
      return initialState;
    }

    return recomputePreferenceState({
      ...initialState,
      messages: parsed.messages,
      signals: normalizeSignals(parsed.signals),
      overrideOptionId: parsed.overrideOptionId ?? null,
      replayStep:
        typeof parsed.replayStep === "number"
          ? Math.min(Math.max(parsed.replayStep, 0), replayTurns.length)
          : 0,
    });
  } catch {
    return initialState;
  }
}

export function getDimensionLabel(dimensionId: PreferenceDimensionId) {
  return getPreferenceDimension(dimensionId)?.label ?? dimensionId;
}
