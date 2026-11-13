"use client";

import { useEffect, useId, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Ban,
  Loader2,
  Pencil,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import {
  MAX_CATEGORY_LENGTH,
  MAX_VIEWER_DELEGATIONS,
} from "@/lib/validations/delegation-schemas";
import { AppSheet } from "./app-window";
import {
  useAccount,
  type DelegationCheck,
  type HeldDelegation,
} from "./account-provider";
import { otherWordings, suggestCategories } from "./categories";
import { categoryKey, personName, type Directory } from "./people";
import { Chain, PersonLine, ProfileButton } from "./person-bits";
import { PersonSearch } from "./person-search";

function PanelHeader({ children }: { children: React.ReactNode }) {
  return <div className="space-y-1.5 pr-6">{children}</div>;
}

function PanelFooter({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-wrap justify-end gap-2 pt-2", className)}>
      {children}
    </div>
  );
}

/** What the service said about a delegation: nesting, missing judgments, loops. */
export function DelegationNotes({
  held,
  others,
  live,
}: {
  held: HeldDelegation;
  /** The viewer's other delegations, to say which broader one this sits inside. */
  others: HeldDelegation[];
  live: boolean;
}) {
  const { directory } = useAccount();
  const heldKeys = new Set(others.map((entry) => categoryKey(entry.category)));
  const broader = held.inside
    .map((id) => directory.categoryText.get(id))
    .filter(
      (text): text is string =>
        text !== undefined && heldKeys.has(categoryKey(text)),
    );
  if (broader.length === 0 && held.judged && held.warnings.length === 0)
    return null;
  return (
    <div className="space-y-2 text-sm">
      {broader.length > 0 && (
        <p className="text-muted-foreground">
          Sits inside “{broader.join("”, “")}”, which you also hand over. When a
          question fits both, this narrower one wins.
        </p>
      )}
      {held.warnings.length > 0 && (
        <div className="space-y-1 rounded-md border border-amber-500/50 bg-amber-500/5 p-3">
          <p className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            Comes back to you on {held.warnings.length} open{" "}
            {held.warnings.length === 1 ? "question" : "questions"}
          </p>
          <p className="text-muted-foreground">
            On these the chain leads back to you. The delegation is allowed; on
            a loop everyone keeps their own decision.
          </p>
          <ul className="list-disc pl-5 text-muted-foreground">
            {held.warnings.map((warning) => (
              <li key={`${warning.ballot_paper}-${warning.question_id}`}>
                {warning.title}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!held.judged && (
        <p className="rounded-md border border-amber-500/50 bg-amber-500/5 p-3">
          {live
            ? "The decision model could not judge this category right now."
            : "This wording is new, and this deployment replays recorded judgments rather than asking the decision model."}{" "}
          Without a judgment the rule fails closed: you keep every open vote
          while you hold this category.
        </p>
      )}
    </div>
  );
}

function Rejected({
  directory,
  check,
}: {
  directory: Directory;
  check: Exclude<DelegationCheck, { status: "ok" }>;
}) {
  return (
    <div className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
      <p className="flex items-center gap-2 font-medium">
        <Ban className="h-4 w-4" aria-hidden="true" />
        {check.status === "rejected" && check.chain
          ? "This would close a loop"
          : "Not possible"}
      </p>
      {check.status === "rejected" && check.chain ? (
        <>
          <p className="text-muted-foreground">
            The same category would come straight back to you, so no question in
            it could ever reach someone who decides.
          </p>
          <Chain directory={directory} chain={check.chain} />
        </>
      ) : (
        <p className="text-muted-foreground">
          {check.status === "rejected" ? check.reason : check.message}
        </p>
      )}
    </div>
  );
}

function CategoryField({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { directory } = useAccount();
  const typed = categoryKey(value);
  const written = directory.groups.byKey.get(typed);
  // What other people already write that matches, unless this is exactly it
  const similar = suggestCategories(directory.groups, value).filter(
    (group) => group !== written,
  );
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>Decisions about…</Label>
      <Input
        id={id}
        value={value}
        maxLength={MAX_CATEGORY_LENGTH}
        placeholder="in your own words, broad or narrow"
        autoComplete="off"
        onChange={(event) => onChange(event.target.value)}
      />
      {!typed && (
        <p className="text-xs text-muted-foreground">
          Anything from “all things taxes” to “the well-being of tree frogs in
          the Amazon”.
        </p>
      )}
      {written && (
        <p className="text-xs text-muted-foreground">
          {written.holders} {written.holders === 1 ? "person hands" : "people hand"}{" "}
          this over
          {otherWordings(written, value).length > 0 && (
            <>
              , counting those who write it as “
              {otherWordings(written, value).join("”, “")}”
            </>
          )}
          .
        </p>
      )}
      {typed && !written && similar.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Nobody else writes it this way. That is fine: each question is checked
          against your words.
        </p>
      )}
      {similar.length > 0 && (
        <div className="space-y-1">
          <p className="liquid-label">Others write</p>
          <ul className="space-y-1">
            {similar.map((group) => (
              <li key={group.id}>
                <button
                  type="button"
                  onClick={() => onChange(group.label)}
                  className="flex w-full items-baseline justify-between gap-3 rounded-md border border-transparent px-2 py-1.5 text-left text-sm hover:border-border hover:bg-accent"
                >
                  <span className="min-w-0">
                    <span className="font-medium">{group.label}</span>
                    {group.wordings.length > 1 && (
                      <span className="block text-xs text-muted-foreground">
                        also “{otherWordings(group, group.label).join("”, “")}”
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {group.holders} {group.holders === 1 ? "person" : "people"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Handover({
  directory,
  category,
  delegate,
}: {
  directory: Directory;
  category: string;
  delegate: string;
}) {
  return (
    <div className="liquid-panel space-y-2 p-3">
      <p className="text-sm">
        <span className="text-muted-foreground">Decisions about </span>
        <span className="font-medium">{category}</span>
        <span className="text-muted-foreground"> go to</span>
      </p>
      <PersonLine directory={directory} id={delegate} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// An existing delegation
// ---------------------------------------------------------------------------

type ManageStep =
  | { name: "view" }
  | { name: "category"; text: string }
  | { name: "delegate" }
  | { name: "confirm"; held: HeldDelegation }
  | { name: "remove" }
  | { name: "refused"; check: Exclude<DelegationCheck, { status: "ok" }> };

/** View one of the viewer's delegations, change its delegate or category, or remove it. */
export function ManageDelegationSheet({
  index,
  onClose,
}: {
  index: number | null;
  onClose: () => void;
}) {
  const { scenario, directory, delegations, check, replace, remove } =
    useAccount();
  const fieldId = useId();
  const [step, setStep] = useState<ManageStep>({ name: "view" });
  const [pending, setPending] = useState(false);
  const current = index === null ? undefined : delegations[index];

  useEffect(() => {
    setStep({ name: "view" });
    setPending(false);
  }, [index]);

  if (index === null || !current) return null;
  const others = delegations.filter((_, position) => position !== index);

  async function review(category: string, delegate: string) {
    if (!category.trim()) return;
    setPending(true);
    const result = await check(category, delegate, index ?? undefined);
    setPending(false);
    setStep(
      result.status === "ok"
        ? { name: "confirm", held: result.held }
        : { name: "refused", check: result },
    );
  }

  return (
    <AppSheet open onClose={onClose}>
      <div className="space-y-5">
        {step.name === "view" && (
          <>
            <PanelHeader>
              <SheetTitle className="text-lg">{current.category}</SheetTitle>
              <SheetDescription>
                Questions about this are decided for you by the person below,
                unless you vote yourself.
              </SheetDescription>
            </PanelHeader>
            <div className="space-y-3">
              <div className="liquid-panel flex items-center justify-between gap-3 p-3">
                <div className="min-w-0 text-sm">
                  <p className="text-xs text-muted-foreground">Category</p>
                  <p className="font-medium">{current.category}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setStep({ name: "category", text: current.category })
                  }
                >
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  Edit
                </Button>
              </div>
              <div className="liquid-panel flex items-center justify-between gap-3 p-3">
                <PersonLine directory={directory} id={current.delegate} />
                <span className="flex shrink-0 items-center gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setStep({ name: "delegate" })}
                  >
                    <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    Change
                  </Button>
                  <ProfileButton directory={directory} id={current.delegate} />
                </span>
              </div>
              <DelegationNotes
                held={current}
                others={others}
                live={scenario.live_judgments}
              />
            </div>
            <PanelFooter className="justify-start">
              <Button
                variant="ghost"
                className="text-destructive hover:text-destructive"
                onClick={() => setStep({ name: "remove" })}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                Remove
              </Button>
            </PanelFooter>
          </>
        )}

        {step.name === "category" && (
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void review(step.text, current.delegate);
            }}
          >
            <PanelHeader>
              <SheetTitle className="text-lg">Edit the category</SheetTitle>
              <SheetDescription>
                {personName(directory, current.delegate)} keeps it; only what it
                covers changes.
              </SheetDescription>
            </PanelHeader>
            <CategoryField
              id={fieldId}
              value={step.text}
              onChange={(text) => setStep({ name: "category", text })}
            />
            <PanelFooter className="gap-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setStep({ name: "view" })}
              >
                Back
              </Button>
              <Button
                type="submit"
                disabled={
                  pending ||
                  !step.text.trim() ||
                  categoryKey(step.text) === categoryKey(current.category)
                }
              >
                {pending && (
                  <Loader2
                    className="h-4 w-4 animate-spin"
                    aria-hidden="true"
                  />
                )}
                Review change
              </Button>
            </PanelFooter>
          </form>
        )}

        {step.name === "delegate" && (
          <div className="space-y-4">
            <PanelHeader>
              <SheetTitle className="text-lg">Change the delegate</SheetTitle>
              <SheetDescription>
                Who should decide questions about “{current.category}” for you?
              </SheetDescription>
            </PanelHeader>
            <PersonSearch
              directory={directory}
              categoryId={
                scenario.categories.find(
                  (entry) =>
                    categoryKey(entry.text) === categoryKey(current.category),
                )?.id
              }
              onPick={(person) => void review(current.category, person)}
            />
            <PanelFooter>
              <Button
                variant="ghost"
                disabled={pending}
                onClick={() => setStep({ name: "view" })}
              >
                {pending && (
                  <Loader2
                    className="h-4 w-4 animate-spin"
                    aria-hidden="true"
                  />
                )}
                Back
              </Button>
            </PanelFooter>
          </div>
        )}

        {step.name === "confirm" && (
          <div className="space-y-4">
            <PanelHeader>
              <SheetTitle className="text-lg">Confirm the change</SheetTitle>
              <SheetDescription>
                It takes effect at once on every open vote. Votes that have
                closed stay as they were.
              </SheetDescription>
            </PanelHeader>
            <div className="space-y-2">
              <div className="opacity-60">
                <Handover
                  directory={directory}
                  category={current.category}
                  delegate={current.delegate}
                />
              </div>
              <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <ArrowRight
                  className="h-3.5 w-3.5 rotate-90"
                  aria-hidden="true"
                />
                becomes
              </p>
              <Handover
                directory={directory}
                category={step.held.category}
                delegate={step.held.delegate}
              />
            </div>
            <DelegationNotes
              held={step.held}
              others={others}
              live={scenario.live_judgments}
            />
            <PanelFooter className="gap-2">
              <Button variant="ghost" onClick={() => setStep({ name: "view" })}>
                Cancel
              </Button>
              <Button
                onClick={() => {
                  replace(index, step.held);
                  onClose();
                }}
              >
                Confirm
              </Button>
            </PanelFooter>
          </div>
        )}

        {step.name === "remove" && (
          <div className="space-y-4">
            <PanelHeader>
              <SheetTitle className="text-lg">
                Remove this delegation?
              </SheetTitle>
              <SheetDescription>
                You will decide questions about “{current.category}” yourself
                again, starting with every open vote.
              </SheetDescription>
            </PanelHeader>
            <Handover
              directory={directory}
              category={current.category}
              delegate={current.delegate}
            />
            <PanelFooter className="gap-2">
              <Button variant="ghost" onClick={() => setStep({ name: "view" })}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  remove(index);
                  onClose();
                }}
              >
                Remove
              </Button>
            </PanelFooter>
          </div>
        )}

        {step.name === "refused" && (
          <div className="space-y-4">
            <PanelHeader>
              <SheetTitle className="text-lg">
                That change was refused
              </SheetTitle>
              <SheetDescription>Your delegation is unchanged.</SheetDescription>
            </PanelHeader>
            <Rejected directory={directory} check={step.check} />
            <PanelFooter>
              <Button
                variant="outline"
                onClick={() => setStep({ name: "view" })}
              >
                Back
              </Button>
            </PanelFooter>
          </div>
        )}
      </div>
    </AppSheet>
  );
}

// ---------------------------------------------------------------------------
// A new delegation
// ---------------------------------------------------------------------------

type AddStep =
  | { name: "person" }
  | { name: "category"; delegate: string; text: string }
  | { name: "confirm"; held: HeldDelegation }
  | {
      name: "refused";
      delegate: string;
      text: string;
      check: Exclude<DelegationCheck, { status: "ok" }>;
    };

/** Find a person, give them a category in the viewer's own words, confirm. */
export function AddDelegateSheet({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { scenario, directory, delegations, check, add } = useAccount();
  const fieldId = useId();
  const [step, setStep] = useState<AddStep>({ name: "person" });
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (open) {
      setStep({ name: "person" });
      setPending(false);
    }
  }, [open]);

  const full = delegations.length >= MAX_VIEWER_DELEGATIONS;

  async function review(delegate: string, text: string) {
    const existing = delegations.find(
      (held) => categoryKey(held.category) === categoryKey(text),
    );
    if (existing) {
      setStep({
        name: "refused",
        delegate,
        text,
        check: {
          status: "error",
          message: `You already hand “${existing.category}” to ${personName(directory, existing.delegate)}. A category has one delegate; change that one instead.`,
        },
      });
      return;
    }
    setPending(true);
    const result = await check(text, delegate);
    setPending(false);
    setStep(
      result.status === "ok"
        ? { name: "confirm", held: result.held }
        : { name: "refused", delegate, text, check: result },
    );
  }

  return (
    <AppSheet open={open} onClose={onClose}>
      <div className="space-y-5">
        {full ? (
          <>
            <PanelHeader>
              <SheetTitle className="text-lg">Add a delegate</SheetTitle>
              <SheetDescription>
                This demo stops at {MAX_VIEWER_DELEGATIONS} delegations. Remove
                one first.
              </SheetDescription>
            </PanelHeader>
            <PanelFooter>
              <Button variant="outline" onClick={onClose}>
                Close
              </Button>
            </PanelFooter>
          </>
        ) : (
          <>
            {step.name === "person" && (
              <div className="space-y-4">
                <PanelHeader>
                  <SheetTitle className="text-lg">Add a delegate</SheetTitle>
                  <SheetDescription>
                    Find someone you trust. They can live in any district, or
                    outside the city.
                  </SheetDescription>
                </PanelHeader>
                <PersonSearch
                  directory={directory}
                  onPick={(delegate) =>
                    setStep({ name: "category", delegate, text: "" })
                  }
                />
              </div>
            )}

            {step.name === "category" && (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (step.text.trim())
                    void review(step.delegate, step.text.trim());
                }}
              >
                <PanelHeader>
                  <SheetTitle className="text-lg">
                    What do you hand over?
                  </SheetTitle>
                  <SheetDescription>
                    Write the kind of decision you trust this person with. Each
                    question is checked against it when a vote opens.
                  </SheetDescription>
                </PanelHeader>
                <div className="liquid-panel p-3">
                  <PersonLine directory={directory} id={step.delegate} />
                </div>
                <CategoryField
                  id={fieldId}
                  value={step.text}
                  onChange={(text) => setStep({ ...step, text })}
                />
                <KnownFor
                  directory={directory}
                  delegate={step.delegate}
                  onPick={(text) => setStep({ ...step, text })}
                />
                <PanelFooter className="gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setStep({ name: "person" })}
                  >
                    Back
                  </Button>
                  <Button type="submit" disabled={pending || !step.text.trim()}>
                    {pending && (
                      <Loader2
                        className="h-4 w-4 animate-spin"
                        aria-hidden="true"
                      />
                    )}
                    Review
                  </Button>
                </PanelFooter>
              </form>
            )}

            {step.name === "confirm" && (
              <div className="space-y-4">
                <PanelHeader>
                  <SheetTitle className="text-lg">
                    Confirm the delegation
                  </SheetTitle>
                  <SheetDescription>
                    It takes effect at once on every open vote. You can still
                    vote yourself on any question.
                  </SheetDescription>
                </PanelHeader>
                <Handover
                  directory={directory}
                  category={step.held.category}
                  delegate={step.held.delegate}
                />
                <DelegationNotes
                  held={step.held}
                  others={delegations}
                  live={scenario.live_judgments}
                />
                <PanelFooter className="gap-2">
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setStep({
                        name: "category",
                        delegate: step.held.delegate,
                        text: step.held.category,
                      })
                    }
                  >
                    Back
                  </Button>
                  <Button
                    onClick={() => {
                      add(step.held);
                      onClose();
                    }}
                  >
                    Confirm
                  </Button>
                </PanelFooter>
              </div>
            )}

            {step.name === "refused" && (
              <div className="space-y-4">
                <PanelHeader>
                  <SheetTitle className="text-lg">
                    That delegation was refused
                  </SheetTitle>
                  <SheetDescription>Nothing was added.</SheetDescription>
                </PanelHeader>
                <Handover
                  directory={directory}
                  category={step.text}
                  delegate={step.delegate}
                />
                <Rejected directory={directory} check={step.check} />
                <PanelFooter>
                  <Button
                    variant="outline"
                    onClick={() =>
                      setStep({
                        name: "category",
                        delegate: step.delegate,
                        text: step.text,
                      })
                    }
                  >
                    Back
                  </Button>
                </PanelFooter>
              </div>
            )}
          </>
        )}
      </div>
    </AppSheet>
  );
}

/** What people already hand a person, or what they are well known for, as one-click suggestions. */
function KnownFor({
  directory,
  delegate,
  onPick,
}: {
  directory: Directory;
  delegate: string;
  onPick: (text: string) => void;
}) {
  // What other people already hand this person, wordings of one thing together
  const trusted = directory.groups.all
    .flatMap((group) => {
      const entry = group.trusted.find((item) => item.person === delegate);
      return entry ? [{ text: group.label, count: entry.delegators }] : [];
    })
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
  const known = (directory.persons.get(delegate)?.well_known_for ?? [])
    .map((id) => directory.groups.byCategory.get(id)?.label)
    .filter((text): text is string => text !== undefined)
    .filter((text) => !trusted.some((entry) => entry.text === text))
    .map((text) => ({ text, count: 0 }));
  const suggestions = [...trusted, ...known];
  if (suggestions.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted-foreground">
        {trusted.length > 0
          ? `People already hand ${personName(directory, delegate)}`
          : `${personName(directory, delegate)} is well known for`}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {suggestions.map(({ text, count }) => (
          <button
            key={text}
            type="button"
            onClick={() => onPick(text)}
            className="rounded-full border px-2.5 py-1 text-xs hover:bg-accent"
          >
            {text}
            {count > 0 && (
              <span className="ml-1.5 text-muted-foreground">{count}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
