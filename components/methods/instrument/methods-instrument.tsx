"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { resolveProfileAction } from "@/actions/methods-actions";
import { METHOD_META } from "@/lib/methods/instrument";
import { encodeProfile, totalVoters } from "@/lib/methods/profile";
import { cn } from "@/lib/utils";
import type { ProfileResolveResponse, UtilityProfile, VotingMethod } from "@/types/methods";

import { BallotsPanel } from "./ballots-panel";
import { Channels } from "./channels";
import { MethodTrace } from "./method-trace";
import { ProfileEditor } from "./profile-editor";
import { TournamentGraph } from "./tournament-graph";

export interface PresetOption {
  id: string;
  label: string;
  description: string;
  profile: UtilityProfile;
  resolution: ProfileResolveResponse;
}

type Status =
  | { kind: "ready" }
  | { kind: "counting" }
  | { kind: "empty" }
  | { kind: "offline"; message: string };

// Wait this long after the last edit before asking the API to count
const DEBOUNCE_MS = 250;

/**
 * The methods instrument: edit an electorate of voter types, see the ballots
 * each type casts in every format, and watch seven methods count them at
 * once. Presets resolve from static artifacts; edits are counted by the
 * Python API (POST /api/voting/profile/resolve), cached by profile so
 * returning to one is instant.
 */
export function MethodsInstrument({
  presets,
  initialProfile,
  provenance,
}: {
  presets: PresetOption[];
  initialProfile: UtilityProfile;
  provenance: { presetsHash: string; sourceHash: string };
}) {
  const cache = useRef(
    new Map(presets.map((preset) => [encodeProfile(preset.profile), preset.resolution]))
  );
  const [profile, setProfile] = useState(initialProfile);
  const [resolution, setResolution] = useState<ProfileResolveResponse>(
    () => cache.current.get(encodeProfile(initialProfile)) ?? presets[0].resolution
  );
  const [status, setStatus] = useState<Status>({ kind: "ready" });
  const [method, setMethod] = useState<VotingMethod>("irv");
  const [voterType, setVoterType] = useState(0);
  const latest = useRef(0);

  const key = useMemo(() => encodeProfile(profile), [profile]);
  const resolvedKey =
    resolution.profile.ballot_type === "utility" ? encodeProfile(resolution.profile) : "";
  const showing = resolvedKey === key;
  const activePreset = presets.find((preset) => encodeProfile(preset.profile) === key);
  const selectedType = Math.min(voterType, profile.rows.length - 1);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (activePreset?.id === presets[0].id) url.searchParams.delete("p");
    else url.searchParams.set("p", key);
    window.history.replaceState(null, "", url);
  }, [key, activePreset, presets]);

  useEffect(() => {
    const request = ++latest.current;
    if (totalVoters(profile) === 0) {
      setStatus({ kind: "empty" });
      return;
    }
    const cached = cache.current.get(key);
    if (cached) {
      setResolution(cached);
      setStatus({ kind: "ready" });
      return;
    }
    setStatus({ kind: "counting" });
    const timer = window.setTimeout(async () => {
      const result = await resolveProfileAction({ profile });
      if (request !== latest.current) return;
      if (result.isSuccess && result.data) {
        cache.current.set(key, result.data);
        setResolution(result.data);
        setStatus({ kind: "ready" });
      } else {
        setStatus({ kind: "offline", message: result.message });
      }
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [profile, key]);

  const winners = new Set(resolution.results.map((r) => r.winner));
  const selectedResult =
    resolution.results.find((r) => r.method === method) ?? resolution.results[0];

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:py-12">
      <header className="max-w-3xl">
        <p className="font-mi-mono text-xs tracking-wide text-mi-muted">Voting methods · instrument</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.02em] text-mi-ink sm:text-[2.75rem] sm:leading-[1.08]">
          Same voters, different winners.
        </h1>
        <p className="mt-3 text-base leading-relaxed text-mi-ink-2 sm:text-lg">
          Place each group of voters&apos; candidates on a scale. Every group then fills in
          five kinds of ballot, and seven counting methods read them. They often
          disagree.
        </p>
      </header>

      <div className="mt-6 flex flex-wrap items-center gap-2" role="group" aria-label="Presets">
        {presets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            aria-pressed={activePreset?.id === preset.id}
            title={preset.description}
            onClick={() => {
              setProfile(preset.profile);
              setVoterType(0);
            }}
            className={cn(
              "rounded-[3px] border px-3 py-1.5 text-sm",
              activePreset?.id === preset.id
                ? "border-mi-ink bg-mi-ink text-mi-surface"
                : "border-mi-rule bg-mi-surface text-mi-ink hover:border-mi-ink"
            )}
          >
            {preset.label}
            <span className="ml-2 font-mi-mono text-xs opacity-70">
              {totalVoters(preset.profile)}
            </span>
          </button>
        ))}
        {activePreset ? (
          <span className="text-sm text-mi-muted">{activePreset.description}</span>
        ) : null}
      </div>

      <p className="mt-6 font-mi-mono text-sm text-mi-ink" aria-live="polite">
        {resolution.total_voters} voters
        <span className="text-mi-muted"> · </span>
        {winners.size} {winners.size === 1 ? "winner" : "different winners"} across{" "}
        {resolution.results.length} methods
        <span className="text-mi-muted"> · </span>
        {resolution.criteria.condorcet_winner
          ? `Condorcet winner ${resolution.criteria.condorcet_winner}`
          : "no Condorcet winner"}
        <StatusNote status={status} showing={showing} />
      </p>

      <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
        <div className="space-y-6">
          <Panel title="Electorate">
            <ProfileEditor
              profile={profile}
              selected={selectedType}
              onSelect={setVoterType}
              onChange={setProfile}
            />
          </Panel>
          <Panel title="Ballots">
            <BallotsPanel
              profile={profile}
              ballots={showing ? resolution.voter_ballots : null}
              selected={selectedType}
              onSelect={setVoterType}
            />
          </Panel>
          <Panel title="Head to head">
            <TournamentGraph
              candidates={resolution.rankings.candidates}
              pairwise={resolution.pairwise}
              condorcetWinner={resolution.criteria.condorcet_winner}
            />
          </Panel>
        </div>
        <div className={cn("space-y-6 transition-opacity", !showing && "opacity-55")}>
          <Panel title="Seven counts">
            <Channels resolution={resolution} selected={method} onSelect={setMethod} />
          </Panel>
          <Panel title={`How ${METHOD_META[selectedResult.method].label.toLowerCase()} counted`}>
            <MethodTrace result={selectedResult} resolution={resolution} />
          </Panel>
        </div>
      </div>

      <footer className="mt-10 border-t border-mi-rule pt-4 font-mi-mono text-xs leading-relaxed text-mi-muted">
        Ballots: {resolution.ballot_model ?? "ranked input"} (sincere voters; rules in the Ballots
        panel). Presets: public/data/methods/presets.json (sha256 {provenance.presetsHash}…), built
        from source {provenance.sourceHash}…. Edits: POST /api/voting/profile/resolve. Ties: seeded
        random tiebreak, seed {resolution.tiebreak_seed}.
      </footer>
    </div>
  );
}

function StatusNote({ status, showing }: { status: Status; showing: boolean }) {
  if (status.kind === "counting") return <span className="text-mi-muted"> · counting…</span>;
  if (status.kind === "empty")
    return <span className="text-mi-ink"> · add at least one voter to count</span>;
  if (status.kind === "offline")
    return (
      <span className="text-mi-ink">
        {" "}
        · {status.message} Showing the last counted electorate; presets still work.
      </span>
    );
  return showing ? null : <span className="text-mi-muted"> · showing the last count</span>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[4px] border border-mi-rule bg-mi-surface">
      <h2 className="border-b border-mi-rule px-4 py-2.5 text-sm font-medium text-mi-ink">{title}</h2>
      <div className="p-4">{children}</div>
    </section>
  );
}
