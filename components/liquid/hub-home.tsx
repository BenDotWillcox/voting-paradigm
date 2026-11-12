"use client";

import { useMemo, useState } from "react";
import { AppLink as Link } from "./app-link";
import { ArrowRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { useAccount } from "./account-provider";
import { AppSheet } from "./app-window";
import { AddDelegateSheet, ManageDelegationSheet } from "./delegation-sheets";
import { HubGraph, type HubSelection, type IncomingEdge } from "./hub-graph";
import { closing, personName, profileHref } from "./people";
import { PersonLine, ProfileButton } from "./person-bits";
import { StatCard, StatStrip } from "./stat-card";
import { needsViewer } from "./votes";

/**
 * The hub: the viewer at the centre of their delegations. Categories other
 * people hand them come in from the left; categories they hand on go out to
 * the right, and those can be changed here.
 */
export function HubHome() {
  const { scenario, directory, delegations, openVotes, votes } = useAccount();
  const [selected, setSelected] = useState<HubSelection>(null);
  const [adding, setAdding] = useState(false);

  const incoming = useMemo<IncomingEdge[]>(
    () =>
      scenario.delegations
        .filter((entry) => entry.delegate === scenario.viewer)
        .map((entry) => ({
          person: entry.delegator,
          category:
            directory.categoryText.get(entry.category) ?? entry.category,
        })),
    [scenario.delegations, scenario.viewer, directory.categoryText],
  );

  const waiting =
    openVotes?.filter(
      (entry) =>
        needsViewer(entry, directory.viewer) && !votes[entry.question.id],
    ) ?? [];
  const sent =
    openVotes?.filter(
      (entry) =>
        entry.result.receipt &&
        entry.result.receipt.resolver !== directory.viewer,
    ) ?? [];
  const reached = openVotes?.reduce(
    (sum, entry) => sum + entry.result.inbox.votes_for_others,
    0,
  );

  const readouts = [
    {
      label: "Awaited Votes",
      hint: "Number of votes waiting on you",
      value: openVotes ? waiting.length : "–",
      // The one addition worth making: how soon the first of them closes.
      badge: waiting[0]
        ? closing(waiting[0].paper.closes_in_days).replace("Closes in ", "")
        : undefined,
      href: "/liquid/votes",
    },
    {
      label: "Votes Delegated",
      hint: "Number of votes waiting on your delegates",
      value: openVotes ? sent.length : "–",
      href: "/liquid/votes?show=sent",
    },
    {
      label: "Votes Received",
      hint: "Number of other people's votes that have reached you",
      value: reached ?? "–",
      href: "/liquid/votes",
    },
    {
      label: "Delegates",
      hint: "Number of categories you hand to someone else",
      value: delegations.length,
      href: profileHref(directory, directory.viewer),
    },
    {
      label: "Delegators",
      hint: "Number of categories other people hand to you",
      value: incoming.length,
      href: profileHref(directory, directory.viewer),
    },
  ];

  const inbound =
    selected?.side === "in" ? incoming[selected.index] : undefined;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <p className="liquid-label">Hub</p>
          <h2 className="text-2xl font-semibold tracking-tight">
            Where your votes go
          </h2>
          <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Every vote issued to you is checked against the categories you have
            handed over. A match goes to that delegate; anything else stays with
            you. Other people&apos;s votes reach you when they trust you with a
            category.
          </p>
        </div>
        <Button onClick={() => setAdding(true)}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add a delegate
        </Button>
      </div>

      <StatStrip columns="grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        {readouts.map((readout) => (
          <StatCard key={readout.label} {...readout} />
        ))}
      </StatStrip>

      <section aria-label="Delegation graph">
        <HubGraph
          directory={directory}
          owner={directory.viewer}
          incoming={incoming}
          outgoing={delegations.map((held) => ({
            category: held.category,
            delegate: held.delegate,
            flagged: !held.judged || held.warnings.length > 0,
          }))}
          selected={selected}
          onSelect={setSelected}
          onAdd={() => setAdding(true)}
        />
      </section>

      <ManageDelegationSheet
        index={selected?.side === "out" ? selected.index : null}
        onClose={() => setSelected(null)}
      />
      <AddDelegateSheet open={adding} onClose={() => setAdding(false)} />

      <AppSheet open={inbound !== undefined} onClose={() => setSelected(null)}>
        {inbound && (
          <div className="space-y-5">
            <div className="space-y-1.5 pr-6">
              <p className="liquid-label">Handed to you</p>
              <SheetTitle className="text-lg">{inbound.category}</SheetTitle>
              <SheetDescription>
                {personName(directory, inbound.person)} trusts you with this.
                When a vote issued to them fits it, the decision comes to you,
                unless you hand it on.
              </SheetDescription>
            </div>
            <div className="liquid-panel flex items-center justify-between gap-3 p-3">
              <PersonLine directory={directory} id={inbound.person} />
              <ProfileButton directory={directory} id={inbound.person} />
            </div>
            <InboundVotes person={inbound.person} />
          </div>
        )}
      </AppSheet>
    </div>
  );
}

/** The open votes on which this person's vote currently ends with the viewer. */
function InboundVotes({ person }: { person: string }) {
  const { openVotes } = useAccount();
  const reaching = (openVotes ?? []).filter((entry) =>
    entry.result.inbox.held.some((held) => held.voter === person),
  );
  return (
    <div className="space-y-2">
      <p className="liquid-label">
        Their open votes with you · {reaching.length}
      </p>
      {reaching.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          None right now. Either no open vote fits the category, or you have
          handed it on.
        </p>
      ) : (
        <ul className="space-y-1">
          {reaching.map((entry) => (
            <li key={entry.question.id}>
              <Link
                href={`/liquid/votes/${entry.question.id}`}
                className="flex items-center justify-between gap-3 rounded-lg p-2 text-sm hover:bg-accent"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {entry.question.title}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {closing(entry.paper.closes_in_days)}
                  </span>
                </span>
                <ArrowRight
                  className="h-4 w-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
