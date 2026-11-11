"use client";

import { useId, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, Ban, Loader2, X } from "lucide-react";
import {
  getCategoryJudgmentsAction,
  validateDelegationAction,
} from "@/actions/delegation-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MAX_CATEGORY_LENGTH, MAX_VIEWER_DELEGATIONS } from "@/lib/validations/delegation-schemas";
import type { DelegationScenario, ValidateDelegationResponse } from "@/types/delegation";
import { categoryKey, personHome, personName, type Directory } from "./people";
import { PersonPicker } from "./person-picker";

/** A delegation the service has accepted, with what it said about it. */
export type HeldDelegation = {
  category: string;
  delegate: string;
  /** Ids of broader categories this one sits inside. */
  inside: string[];
  /** Whether every curated question has a recorded judgment for the category. */
  judged: boolean;
  warnings: ValidateDelegationResponse["warnings"];
};

type Feedback =
  | { kind: "error"; message: string }
  | { kind: "rejected"; category: string; delegate: string; reason: string; chain: string[] | null }
  | { kind: "accepted"; held: HeldDelegation };

const EXAMPLES = [
  // Handed to someone who lives outside the city.
  { label: "A broad category", category: "all things taxes", delegate: "out-16" },
  // Overrules the broad one on sales tax questions.
  { label: "A narrower one inside it", category: "sales tax rates", delegate: "d2-007" },
  // Allowed, with a warning: this person hands transport to the viewer.
  {
    label: "A loop on some questions",
    category: "bike lanes and cycling safety",
    delegate: "d2-022",
  },
  // Refused: the same category would come straight back.
  { label: "A loop on every question", category: "transportation and roads", delegate: "d2-022" },
];

type Props = {
  scenario: DelegationScenario;
  directory: Directory;
  delegations: HeldDelegation[];
  threshold: number;
  onAdd: (held: HeldDelegation) => void;
  onRemove: (index: number) => void;
};

export function DelegationEditor({
  scenario,
  directory,
  delegations,
  threshold,
  onAdd,
  onRemove,
}: Props) {
  const formId = useId();
  const [category, setCategory] = useState("");
  const [delegate, setDelegate] = useState("");
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const poolByKey = useMemo(
    () => new Map(scenario.categories.map((entry) => [categoryKey(entry.text), entry])),
    [scenario.categories]
  );
  const typedCategoryId = poolByKey.get(categoryKey(category))?.id ?? null;

  const inbound = useMemo(
    () => scenario.delegations.filter((entry) => entry.delegate === scenario.viewer),
    [scenario.delegations, scenario.viewer]
  );

  const full = delegations.length >= MAX_VIEWER_DELEGATIONS;

  async function propose(categoryText: string, delegateId: string) {
    const text = categoryText.trim();
    if (!text) {
      setFeedback({ kind: "error", message: "Write a category first." });
      return;
    }
    if (!delegateId) {
      setFeedback({ kind: "error", message: "Choose a person." });
      return;
    }
    const existing = delegations.find(
      (held) => categoryKey(held.category) === categoryKey(text)
    );
    if (existing) {
      setFeedback({
        kind: "error",
        message: `You have already handed “${existing.category}” to ${personName(directory, existing.delegate)}. Remove it first; a category has one delegate.`,
      });
      return;
    }
    if (full) {
      setFeedback({
        kind: "error",
        message: `This demo stops at ${MAX_VIEWER_DELEGATIONS} categories. Remove one first.`,
      });
      return;
    }

    setPending(true);
    setFeedback(null);
    try {
      const checked = await validateDelegationAction({
        viewer_delegations: delegations.map((held) => ({
          category: held.category,
          delegate: held.delegate,
        })),
        proposed: { category: text, delegate: delegateId },
        threshold,
      });
      if (!checked.isSuccess || !checked.data) {
        setFeedback({ kind: "error", message: checked.message });
        return;
      }
      const result = checked.data;
      if (!result.accepted) {
        setFeedback({
          kind: "rejected",
          category: result.category.text,
          delegate: delegateId,
          reason: result.reason ?? "The delegation was refused.",
          chain: result.chain,
        });
        return;
      }

      let judged = result.judged;
      let inside = result.category.inside;
      if (!judged && scenario.live_judgments) {
        // A category nobody has written before: ask the decision model now.
        const judgments = await getCategoryJudgmentsAction({
          category: result.category.text,
          held: delegations.map((held) => held.category),
        });
        if (judgments.isSuccess && judgments.data) {
          judged = judgments.data.judgments.missing === 0;
          inside = judgments.data.category.inside;
        }
      }

      const held: HeldDelegation = {
        category: result.category.text,
        delegate: delegateId,
        inside,
        judged,
        warnings: result.warnings,
      };
      onAdd(held);
      setFeedback({ kind: "accepted", held });
      setCategory("");
      setDelegate("");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]">
      <div className="space-y-5">
        <form
          className="grid gap-4 rounded-lg border bg-card p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            void propose(category, delegate);
          }}
        >
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor={`${formId}-category`}>Decisions about…</Label>
            <Input
              id={`${formId}-category`}
              list={`${formId}-pool`}
              value={category}
              maxLength={MAX_CATEGORY_LENGTH}
              placeholder="pick one or write your own"
              autoComplete="off"
              onChange={(event) => setCategory(event.target.value)}
            />
            <datalist id={`${formId}-pool`}>
              {scenario.categories.map((entry) => (
                <option key={entry.id} value={entry.text} />
              ))}
            </datalist>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`${formId}-delegate`}>…go to</Label>
            <PersonPicker
              id={`${formId}-delegate`}
              directory={directory}
              categoryId={typedCategoryId}
              value={delegate}
              onChange={setDelegate}
            />
          </div>
          <Button type="submit" disabled={pending}>
            {pending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            Hand over
          </Button>
        </form>

        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Or try one of these:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((example) => (
              <Button
                key={example.label}
                type="button"
                variant="outline"
                size="sm"
                disabled={pending}
                onClick={() => void propose(example.category, example.delegate)}
              >
                {example.label}
              </Button>
            ))}
          </div>
        </div>

        <div aria-live="polite">
          {feedback?.kind === "error" && (
            <p className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
              {feedback.message}
            </p>
          )}
          {feedback?.kind === "rejected" && (
            <div className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
              <p className="flex items-center gap-2 font-medium">
                <Ban className="h-4 w-4" aria-hidden="true" />
                Refused: “{feedback.category}” to {personName(directory, feedback.delegate)}
              </p>
              {feedback.chain ? (
                <>
                  <p className="text-muted-foreground">
                    This would close a loop in the same category, so no question in it
                    could ever reach someone who decides:
                  </p>
                  <Chain directory={directory} chain={feedback.chain} />
                </>
              ) : (
                <p className="text-muted-foreground">{feedback.reason}</p>
              )}
            </div>
          )}
          {feedback?.kind === "accepted" && (
            <AcceptedNote
              directory={directory}
              held={feedback.held}
              live={scenario.live_judgments}
            />
          )}
        </div>
      </div>

      <div className="space-y-6">
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">What you have handed over</h3>
          {delegations.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing yet. With no delegations you keep every decision.
            </p>
          ) : (
            <ol className="space-y-2">
              {delegations.map((held, index) => (
                <li
                  key={categoryKey(held.category)}
                  className="flex items-start gap-3 rounded-md border bg-card p-3 text-sm"
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <p>
                      <span className="font-medium">{held.category}</span>
                      <ArrowRight
                        className="mx-1.5 inline h-3.5 w-3.5 text-muted-foreground"
                        aria-label="goes to"
                      />
                      {personName(directory, held.delegate)}
                      <span className="text-muted-foreground">
                        {" "}
                        · {personHome(directory, held.delegate)}
                      </span>
                    </p>
                    <HeldNotes directory={directory} held={held} delegations={delegations} />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    aria-label={`Take back ${held.category}`}
                    onClick={() => {
                      onRemove(index);
                      setFeedback(null);
                    }}
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </li>
              ))}
            </ol>
          )}
        </div>

        <div className="space-y-2">
          <h3 className="text-sm font-semibold">What others have handed to you</h3>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {inbound.map((entry) => (
              <li key={`${entry.delegator}-${entry.category}`}>
                <span className="text-foreground">{personName(directory, entry.delegator)}</span>{" "}
                · {directory.categoryText.get(entry.category) ?? entry.category}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

export function Chain({ directory, chain }: { directory: Directory; chain: string[] }) {
  return (
    <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
      {chain.map((id, index) => (
        <span key={`${id}-${index}`} className="inline-flex items-center gap-1.5">
          {index > 0 && (
            <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" aria-label="hands to" />
          )}
          <span className="rounded border bg-background px-1.5 py-0.5">
            {personName(directory, id)}
          </span>
        </span>
      ))}
    </p>
  );
}

function HeldNotes({
  directory,
  held,
  delegations,
}: {
  directory: Directory;
  held: HeldDelegation;
  delegations: HeldDelegation[];
}) {
  const heldKeys = new Set(delegations.map((entry) => categoryKey(entry.category)));
  const broader = held.inside
    .map((id) => directory.categoryText.get(id))
    .filter((text): text is string => text !== undefined && heldKeys.has(categoryKey(text)));
  return (
    <>
      {broader.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Sits inside “{broader.join("”, “")}”, so it overrules that one when both apply.
        </p>
      )}
      {!held.judged && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          No recorded judgments, so you keep every decision while you hold this.
        </p>
      )}
      {held.warnings.length > 0 && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          Comes back to you on {held.warnings.length} question
          {held.warnings.length === 1 ? "" : "s"}.
        </p>
      )}
    </>
  );
}

function AcceptedNote({
  directory,
  held,
  live,
}: {
  directory: Directory;
  held: HeldDelegation;
  live: boolean;
}) {
  const quiet = held.judged && held.warnings.length === 0;
  return (
    <div
      className={
        quiet
          ? "rounded-md border p-3 text-sm"
          : "space-y-2 rounded-md border border-amber-500/50 bg-amber-500/5 p-3 text-sm"
      }
    >
      <p className={quiet ? undefined : "flex items-center gap-2 font-medium"}>
        {!quiet && <AlertTriangle className="h-4 w-4" aria-hidden="true" />}
        Handed “{held.category}” to {personName(directory, held.delegate)}.
      </p>
      {held.warnings.length > 0 && (
        <div className="space-y-1 text-muted-foreground">
          <p>
            On these questions the chain leads back to you. The delegation stands; on a
            loop everyone keeps their own decision.
          </p>
          <ul className="list-disc pl-5">
            {held.warnings.map((warning) => (
              <li key={`${warning.ballot_paper}-${warning.question_id}`}>{warning.title}</li>
            ))}
          </ul>
        </div>
      )}
      {!held.judged && (
        <p className="text-muted-foreground">
          {live
            ? "The decision model could not be reached for this category."
            : "This category is new, and this deployment replays recorded judgments rather than asking the decision model."}{" "}
          Without a judgment the rule fails closed: you keep every decision until you
          take this category back.
        </p>
      )}
    </div>
  );
}
