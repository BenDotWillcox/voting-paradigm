"use client";

import { ChevronUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { isReference, type AtlasView } from "@/lib/methods/atlas";
import { atScaleTakeaway, countsClaim, numberWord } from "@/lib/methods/claims";
import { CRITERIA } from "@/lib/methods/gallery";
import { METHOD_META } from "@/lib/methods/instrument";
import { encodeProfile, specimenProfile } from "@/lib/methods/profile";
import { CHAPTERS, STEPS, type ExampleSlide, type SlideExample, type StepId } from "@/lib/methods/sections";
import { cn } from "@/lib/utils";
import {
  BALLOT_RULES,
  WALK_PRESET,
  ballotCopy,
  countCopy,
  headToHeadCopy as walkHeadToHead,
  votersCopy,
  type BallotKind,
} from "@/lib/methods/walkthrough";
import type {
  ProfileResolveResponse,
  SimulationSummary,
  Specimen,
  SpecimenRole,
  SpecimenSearch,
  UtilityProfile,
  VotingMethod,
} from "@/types/methods";

import { AtScale } from "./at-scale";
import { Atlas, AtlasPointBanner, type AtlasPoint } from "./atlas";
import { BallotsPanel } from "./ballots-panel";
import { Channels } from "./channels";
import { MethodTrace, type GalleryFailure } from "./method-trace";
import { ParadoxGallery } from "./paradox-gallery";
import { Playground } from "./playground";
import { ProfileEditor } from "./profile-editor";
import { StepDeck, StepFrame, type Step } from "./step-deck";
import { SpecimenBanner } from "./specimen-banner";
import { TournamentGraph } from "./tournament-graph";
import { useElectorate, type ElectorateStatus } from "./use-electorate";
import { VoterCounts } from "./voter-counts";
import { BallotView, CountView, HeadToHeadView, VotersView } from "./walkthrough";

export interface PresetOption {
  id: string;
  label: string;
  description: string;
  notes: Record<ExampleSlide, string>;
  profile: UtilityProfile;
  resolution: ProfileResolveResponse;
}

export interface SpecimenView {
  id: string;
  role: SpecimenRole;
}

/**
 * The methods instrument: chapters of steps (lib/methods/sections.ts), one
 * step on screen at a time, and a playground that pulls up from the bottom of
 * the screen. The steps and the playground share one electorate and its
 * count.
 */
export function MethodsInstrument({
  presets,
  examples: slideExamples,
  searches,
  simulation,
  initialProfile,
  initialResolution,
  initialSpecimen,
  initialStep,
  initialPlay,
  provenance,
}: {
  presets: PresetOption[];
  examples: Record<ExampleSlide, SlideExample[]>;
  searches: SpecimenSearch[];
  simulation: SimulationSummary;
  initialProfile: UtilityProfile;
  initialResolution: ProfileResolveResponse | null;
  initialSpecimen: SpecimenView | null;
  initialStep: StepId;
  initialPlay: boolean;
  provenance: { presetsHash: string; sourceHash: string };
}) {
  const electorate = useElectorate({ presets, initialProfile, initialResolution });
  const { profile, resolution, status, showing, key } = electorate;

  const specimens = useMemo(
    () =>
      new Map(
        searches.flatMap((search) =>
          search.specimen ? [[search.specimen.id, search] as const] : []
        )
      ),
    [searches]
  );

  const [stepIndex, setStepIndex] = useState(() => STEPS.indexOf(initialStep));
  const showStep = (id: StepId) => setStepIndex(STEPS.indexOf(id));
  const [method, setMethod] = useState<VotingMethod>(
    () => specimens.get(initialSpecimen?.id ?? "")?.specimen?.method ?? "irv"
  );
  const [voterType, setVoterType] = useState(0);
  const [specimenView, setSpecimenView] = useState<SpecimenView | null>(initialSpecimen);
  const [atlasPoint, setAtlasPoint] = useState<AtlasPoint | null>(null);
  const [playOpen, setPlayOpen] = useState(initialPlay);
  const [advanced, setAdvanced] = useState(false);

  const selectedType = Math.min(voterType, profile.rows.length - 1);
  const activeSearch = specimenView ? specimens.get(specimenView.id) : undefined;
  const defaultKey = encodeProfile(presets[0].profile);

  useEffect(() => {
    const url = new URL(window.location.href);
    for (const name of ["p", "s", "v", "step", "section", "play"]) url.searchParams.delete(name);
    if (stepIndex > 0) url.searchParams.set("step", STEPS[stepIndex]);
    if (specimenView) {
      url.searchParams.set("s", specimenView.id);
      url.searchParams.set("v", specimenView.role);
    } else if (key !== defaultKey) {
      url.searchParams.set("p", key);
    }
    if (playOpen) url.searchParams.set("play", "1");
    window.history.replaceState(null, "", url);
  }, [key, specimenView, stepIndex, playOpen, defaultKey]);

  function edit(next: UtilityProfile) {
    electorate.load(next);
    setSpecimenView(null);
    setAtlasPoint(null);
  }

  function openPreset(preset: PresetOption) {
    electorate.load(preset.profile, preset.resolution);
    setSpecimenView(null);
    setAtlasPoint(null);
    setVoterType(0);
  }

  function openExample(example: SlideExample) {
    const preset = presets.find((p) => p.id === example.presetId);
    if (!preset) return;
    openPreset(preset);
    if (example.voterType !== undefined) setVoterType(example.voterType);
  }

  function openSpecimen(specimen: Specimen, role?: SpecimenRole) {
    const shown = role ?? specimen.profiles[0].role;
    setAtlasPoint(null);
    setSpecimenView({ id: specimen.id, role: shown });
    electorate.load(specimenProfile(specimen, shown));
    setMethod(specimen.method);
    setVoterType(0);
  }

  function loadAtlasPoint(response: ProfileResolveResponse, point: AtlasPoint, view: AtlasView) {
    if (response.profile.ballot_type !== "utility") return;
    electorate.load(response.profile, response);
    setSpecimenView(null);
    setAtlasPoint(point);
    setVoterType(0);
    if (!isReference(view)) setMethod(view);
    setPlayOpen(true);
  }

  const winners = new Set(resolution.results.map((r) => r.winner));
  const selectedResult =
    resolution.results.find((r) => r.method === method) ?? resolution.results[0];
  const currentPreset = presets.find((preset) => encodeProfile(preset.profile) === key);
  const origin = activeSearch?.specimen
    ? `Specimen · ${METHOD_META[activeSearch.specimen.method].label}, ${specimenView?.role}`
    : atlasPoint
      ? `Atlas point · ${atlasPoint.layout}`
      : currentPreset
        ? null
        : "Your electorate";

  const summary = (
    <span aria-live="polite">
      {resolution.total_voters} voters
      <span className="text-mi-muted"> · </span>
      {winners.size} {winners.size === 1 ? "winner" : "different winners"}
      <span className="text-mi-muted"> · </span>
      {resolution.criteria.condorcet_winner
        ? `Condorcet winner ${resolution.criteria.condorcet_winner}`
        : "no Condorcet winner"}
      <StatusNote status={status} showing={showing} />
    </span>
  );

  const examples = (slide: ExampleSlide) => (
    <Examples
      slide={slide}
      examples={slideExamples[slide]}
      presets={presets}
      activeKey={key}
      selectedType={selectedType}
      origin={origin}
      status={<StatusNote status={status} showing={showing} />}
      onExample={openExample}
      onPlay={() => setPlayOpen(true)}
    />
  );

  const counts = (
    <div className={cn("transition-opacity", !showing && "opacity-55")}>
      <Channels resolution={resolution} selected={method} onSelect={setMethod} />
    </div>
  );
  // A method's smallest gallery failures. Opening one from the steps moves to
  // the gallery; the playground shows the specimen's banner where it is.
  const failuresOf = (method: VotingMethod): GalleryFailure[] =>
    searches.flatMap(({ method: searched, criterion, specimen }) =>
      searched === method && specimen
        ? [
            {
              criterion: criterionName(criterion),
              voters: specimen.voters,
              onOpen: () => {
                openSpecimen(specimen);
                if (!playOpen) showStep("gallery");
              },
            },
          ]
        : []
    );
  const trace = (
    <div className={cn("transition-opacity", !showing && "opacity-55")}>
      <h3 className="mb-3 text-sm font-medium text-mi-ink">
        How {METHOD_META[selectedResult.method].label.toLowerCase()} counted
      </h3>
      <MethodTrace result={selectedResult} resolution={resolution} failures={failuresOf(selectedResult.method)} />
    </div>
  );
  const ballots = (
    <BallotsPanel
      profile={profile}
      ballots={showing ? resolution.voter_ballots : null}
      selected={selectedType}
      onSelect={setVoterType}
    />
  );
  const tournament = (
    <TournamentGraph
      candidates={resolution.rankings.candidates}
      pairwise={resolution.pairwise}
      condorcetWinner={resolution.criteria.condorcet_winner}
    />
  );

  const countsCopy = countsClaim(resolution);
  const methodCount = numberWord(resolution.results.length);

  // Chapter 1 walks one preset whatever the playground holds, from its
  // stored count, so its steps never wait on the API
  const walk = presets.find((preset) => preset.id === WALK_PRESET) ?? presets[0];
  const ballotStep = (kind: BallotKind) => ({
    title: `${BALLOT_RULES[kind].name} ballot`,
    render: (number: string) => (
      <StepFrame number={number} {...ballotCopy(kind, walk.resolution)}>
        <BallotView kind={kind} profile={walk.profile} resolution={walk.resolution} />
      </StepFrame>
    ),
  });
  const countStep = (method: VotingMethod) => ({
    title: METHOD_META[method].label,
    render: (number: string) => (
      <StepFrame number={number} {...countCopy(method, walk.resolution)}>
        <CountView method={method} resolution={walk.resolution} failures={failuresOf(method)} />
      </StepFrame>
    ),
  });

  // Each step's content, by id; CHAPTERS sets their order and numbers
  const stepContent: Record<StepId, { title: string; render: (number: string) => React.ReactNode }> = {
    voters: {
      title: "The voters",
      render: (number) => (
        <StepFrame number={number} {...votersCopy(walk.resolution)}>
          <VotersView profile={walk.profile} />
        </StepFrame>
      ),
    },
    "ballot-single": ballotStep("single"),
    "count-plurality": countStep("plurality"),
    "ballot-ranked": ballotStep("ranked"),
    "count-irv": countStep("irv"),
    "count-borda": countStep("borda"),
    "head-to-head": {
      title: "Head to head",
      render: (number) => (
        <StepFrame number={number} {...walkHeadToHead(walk.resolution)}>
          <HeadToHeadView resolution={walk.resolution} />
        </StepFrame>
      ),
    },
    "count-ranked-pairs": countStep("ranked_pairs"),
    "ballot-approval": ballotStep("approval"),
    "count-approval": countStep("approval"),
    "ballot-score": ballotStep("score"),
    "count-score": countStep("score"),
    "ballot-quadratic": ballotStep("quadratic"),
    "count-quadratic": countStep("quadratic"),
    comparison: {
      title: "Seven counts",
      render: (number) => (
        <StepFrame
          number={number}
          transition={`One electorate, counted ${methodCount} ways.`}
          title={countsCopy.title}
          takeaway={countsCopy.takeaway}
          intro={
            <>
              Choose a method to see how it reached its winner, or{" "}
              <button
                type="button"
                onClick={() => showStep("voters")}
                className="underline decoration-mi-rule underline-offset-2 hover:decoration-mi-ink"
              >
                walk through each ballot and count
              </button>{" "}
              again.
            </>
          }
        >
          {examples("counts")}
          <div className="grid gap-6 lg:grid-cols-2">
            {counts}
            {trace}
          </div>
        </StepFrame>
      ),
    },
    gallery: {
      title: "Paradox gallery",
      render: (number) => (
        <StepFrame
          number={number}
          transition="So far, one electorate. Now the worst electorate we could find for each method."
          title="Every method fails a fairness test"
          takeaway="Each numbered ✗ is a real election, and the number is how few voters it takes."
        >
          {specimenView && activeSearch?.specimen ? (
            <div className="mb-5 space-y-2">
              <SpecimenBanner
                specimen={activeSearch.specimen}
                role={specimenView.role}
                maxVoters={activeSearch.max_voters}
                onRole={(role) => {
                  if (activeSearch.specimen) openSpecimen(activeSearch.specimen, role);
                }}
                onClose={() => setSpecimenView(null)}
              />
              <PlayButton onClick={() => setPlayOpen(true)}>Explore this electorate in the playground</PlayButton>
            </div>
          ) : null}
          <ParadoxGallery
            searches={searches}
            activeSpecimen={specimenView?.id ?? null}
            onOpen={(specimen) => openSpecimen(specimen)}
          />
        </StepFrame>
      ),
    },
    atlas: {
      title: "Atlas",
      render: (number) => (
        <StepFrame
          number={number}
          transition="Those were worst cases. Here is every electorate in a plane at once."
          title="Same candidates, same voters, different maps"
          takeaway="Each method carves the same plane of voters into a different map of winners."
        >
          <Atlas onLoadPoint={loadAtlasPoint} />
        </StepFrame>
      ),
    },
    "at-scale": {
      title: "At scale",
      render: (number) => (
        <StepFrame
          number={number}
          transition="And in typical elections?"
          title="In typical elections they still disagree"
          takeaway={atScaleTakeaway(simulation)}
        >
          <AtScale summary={simulation} />
        </StepFrame>
      ),
    },
  };
  const steps: Step[] = CHAPTERS.flatMap((chapter, at) =>
    chapter.steps.map((id, within) => ({
      id,
      chapter: at,
      title: stepContent[id].title,
      content: stepContent[id].render(`${at + 1}.${within + 1}`),
    }))
  );

  return (
    <div className="mx-auto max-w-6xl px-4 pt-6 pb-28 sm:pt-8">
      {/* The full title opens the first step; after it, the kicker alone
          keeps the page's name and leaves the screen to the steps */}
      <header className="max-w-3xl">
        <p className="font-mi-mono text-xs tracking-wide text-mi-muted">
          Voting methods · instrument
          {stepIndex > 0 ? <span className="text-mi-ink-2"> · Same voters, different winners</span> : null}
        </p>
        {stepIndex === 0 ? (
          <>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.02em] text-mi-ink sm:text-[2.75rem] sm:leading-[1.08]">
              Same voters, different winners.
            </h1>
            <p className="mt-3 text-base leading-relaxed text-mi-ink-2 sm:text-lg">
              Seven voting methods count the same voters and can elect different candidates. Every
              one of them, somewhere, breaks a rule most people take for basic fairness.
            </p>
          </>
        ) : null}
      </header>

      <div className={stepIndex === 0 ? "mt-6" : "mt-3"}>
        <StepDeck
          chapters={CHAPTERS.map((chapter) => chapter.title)}
          steps={steps}
          index={stepIndex}
          onIndex={setStepIndex}
          keys={!playOpen}
        />
      </div>

      <footer className="mt-10 border-t border-mi-rule pt-4">
        <details className="group">
          <summary className="cursor-pointer text-sm text-mi-ink-2 hover:text-mi-ink">
            Methods &amp; provenance
          </summary>
          <p className="mt-2 font-mi-mono text-xs leading-relaxed text-mi-muted">
            Ballots: {resolution.ballot_model ?? "ranked input"} (sincere voters; rules on the
            Ballots step). Presets, specimens and atlas layouts: public/data/methods (presets
            sha256 {provenance.presetsHash}…), built from source {provenance.sourceHash}…. Edits:
            POST /api/voting/profile/resolve. Ties: seeded random tiebreak, seed{" "}
            {resolution.tiebreak_seed}.
          </p>
        </details>
      </footer>

      <Playground
        open={playOpen}
        onOpenChange={setPlayOpen}
        advanced={advanced}
        onAdvancedChange={setAdvanced}
        status={summary}
        drawer={
          <ProfileEditor profile={profile} selected={selectedType} onSelect={setVoterType} onChange={edit} />
        }
      >
        <div className="mx-auto max-w-6xl space-y-5">
          {specimenView && activeSearch?.specimen ? (
            <SpecimenBanner
              specimen={activeSearch.specimen}
              role={specimenView.role}
              maxVoters={activeSearch.max_voters}
              onRole={(role) => {
                if (activeSearch.specimen) openSpecimen(activeSearch.specimen, role);
              }}
              onClose={() => setSpecimenView(null)}
            />
          ) : atlasPoint ? (
            <AtlasPointBanner
              point={atlasPoint}
              voters={resolution.total_voters}
              types={profile.rows.length}
              onBack={() => {
                setPlayOpen(false);
                showStep("atlas");
              }}
              onClose={() => setAtlasPoint(null)}
            />
          ) : null}

          <StartingPoints presets={presets} activeKey={key} origin={origin} onPreset={openPreset} />

          {/* Two columns when the space beside the drawer allows. In one
              column the counts come first, and the electorate panel steps
              aside while the drawer holds the same controls. */}
          <div className="flex flex-col gap-6 @4xl:grid @4xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] @4xl:items-start">
            <div className="contents @4xl:flex @4xl:flex-col @4xl:gap-6">
              {advanced ? null : (
                <Panel title="Electorate" className="order-1">
                  <VoterCounts
                    profile={profile}
                    selected={selectedType}
                    onSelect={setVoterType}
                    onChange={edit}
                  />
                  <p className="mt-2 text-xs leading-relaxed text-mi-muted">
                    Change how many voters hold each ranking. To move candidates on a voter&apos;s
                    scale, or add voter types and candidates, open Advanced controls.
                  </p>
                </Panel>
              )}
              <Panel title="Ballots" className="order-4">{ballots}</Panel>
              <Panel title="Head to head" className="order-5">{tournament}</Panel>
            </div>
            <div className="contents @4xl:flex @4xl:flex-col @4xl:gap-6">
              <Panel title="Seven counts" className="order-2">{counts}</Panel>
              <Panel title="How it counted" className="order-3">{trace}</Panel>
            </div>
          </div>
        </div>
      </Playground>
    </div>
  );
}

/**
 * A slide's examples, and what to notice about the one showing. A preset that
 * is not among this slide's examples still shows, as an extra chip with its
 * note for this slide; an electorate from elsewhere (a specimen, an atlas
 * point, an edit) shows as its origin instead.
 */
function Examples({
  slide,
  examples,
  presets,
  activeKey,
  selectedType,
  origin,
  status,
  onExample,
  onPlay,
}: {
  slide: ExampleSlide;
  examples: SlideExample[];
  presets: PresetOption[];
  activeKey: string;
  selectedType: number;
  origin: string | null;
  status: React.ReactNode;
  onExample: (example: SlideExample) => void;
  onPlay: () => void;
}) {
  const active = presets.find((preset) => encodeProfile(preset.profile) === activeKey);
  const showing = examples.find(
    (example) =>
      example.presetId === active?.id &&
      (example.voterType === undefined || example.voterType === selectedType)
  );
  const extra: SlideExample | null =
    active && !examples.some((example) => example.presetId === active.id)
      ? { presetId: active.id, label: active.label, note: active.notes[slide] }
      : null;
  const chips = extra ? [...examples, extra] : examples;
  const pressed = showing ?? extra;
  const note =
    pressed?.note ??
    (active
      ? active.notes[slide]
      : "Loaded from elsewhere on the page or edited in the playground; choose an example to return.");

  return (
    <div className="mb-5 space-y-2">
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Examples">
        <span className="text-xs text-mi-muted">Examples</span>
        {chips.map((chip) => {
          const isPressed = chip === pressed;
          return (
            <button
              key={`${chip.presetId}-${chip.voterType ?? ""}`}
              type="button"
              aria-pressed={isPressed}
              onClick={() => onExample(chip)}
              className={cn(
                "rounded-[3px] border px-2.5 py-1 text-sm",
                isPressed ? "border-mi-ink bg-mi-ink text-mi-surface" : "border-mi-rule text-mi-ink hover:border-mi-ink"
              )}
            >
              {chip.label}
            </button>
          );
        })}
        {origin ? (
          <span className="rounded-[3px] border border-dashed border-mi-ink px-2.5 py-1 text-sm text-mi-ink">
            {origin}
          </span>
        ) : null}
      </div>
      <p className="max-w-3xl text-sm leading-relaxed text-mi-ink-2" aria-live="polite">
        {note}{" "}
        <button
          type="button"
          onClick={onPlay}
          className="whitespace-nowrap text-mi-muted underline decoration-mi-rule underline-offset-2 hover:text-mi-ink hover:decoration-mi-ink"
        >
          Explore it in the playground
        </button>
        {status}
      </p>
    </div>
  );
}

function StartingPoints({
  presets,
  activeKey,
  origin,
  onPreset,
}: {
  presets: PresetOption[];
  activeKey: string;
  origin: string | null;
  onPreset: (preset: PresetOption) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Electorate">
      <span className="text-xs text-mi-muted">Electorate</span>
      {presets.map((preset) => {
        const active = encodeProfile(preset.profile) === activeKey;
        return (
          <button
            key={preset.id}
            type="button"
            aria-pressed={active}
            title={preset.description}
            onClick={() => onPreset(preset)}
            className={cn(
              "rounded-[3px] border px-2.5 py-1 text-sm",
              active ? "border-mi-ink bg-mi-ink text-mi-surface" : "border-mi-rule text-mi-ink hover:border-mi-ink"
            )}
          >
            {preset.label}
          </button>
        );
      })}
      {origin ? (
        <span className="rounded-[3px] border border-dashed border-mi-ink px-2.5 py-1 text-sm text-mi-ink">
          {origin}
        </span>
      ) : null}
    </div>
  );
}

/** A criterion's name mid-sentence: Condorcet keeps its capital. */
function criterionName(id: string): string {
  const label = CRITERIA.find((criterion) => criterion.id === id)?.label ?? id;
  return label.startsWith("Condorcet") ? label : label.charAt(0).toLowerCase() + label.slice(1);
}

function PlayButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-[3px] border border-mi-ink px-2.5 py-1 text-sm text-mi-ink hover:bg-mi-wash focus-visible:outline-1 focus-visible:outline-mi-ink"
    >
      <ChevronUp className="size-3.5" aria-hidden />
      {children}
    </button>
  );
}

function StatusNote({ status, showing }: { status: ElectorateStatus; showing: boolean }) {
  if (status.kind === "counting") return <span className="text-mi-muted"> · counting…</span>;
  if (status.kind === "empty") return <span className="text-mi-ink"> · add at least one voter to count</span>;
  if (status.kind === "offline")
    return (
      <span className="text-mi-ink">
        {" "}
        · {status.message} Showing the last counted electorate; the sections still work.
      </span>
    );
  return showing ? null : <span className="text-mi-muted"> · showing the last count</span>;
}

function Panel({
  title,
  className,
  children,
}: {
  title: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("rounded-[4px] border border-mi-rule bg-mi-surface", className)}>
      <h3 className="border-b border-mi-rule px-4 py-2.5 text-sm font-medium text-mi-ink">{title}</h3>
      <div className="p-4">{children}</div>
    </section>
  );
}
