"use client";

import { ChevronUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { isReference, type AtlasView } from "@/lib/methods/atlas";
import { METHOD_META } from "@/lib/methods/instrument";
import { encodeProfile, specimenProfile } from "@/lib/methods/profile";
import { SECTIONS, type SectionId } from "@/lib/methods/sections";
import { cn } from "@/lib/utils";
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
import { MethodTrace } from "./method-trace";
import { ParadoxGallery } from "./paradox-gallery";
import { Playground } from "./playground";
import { ProfileEditor } from "./profile-editor";
import { SlideDeck, SlideFrame, type Slide } from "./slide-deck";
import { SpecimenBanner } from "./specimen-banner";
import { TournamentGraph } from "./tournament-graph";
import { useElectorate, type ElectorateStatus } from "./use-electorate";
import { VoterCounts } from "./voter-counts";

export interface PresetOption {
  id: string;
  label: string;
  description: string;
  profile: UtilityProfile;
  resolution: ProfileResolveResponse;
}

export interface SpecimenView {
  id: string;
  role: SpecimenRole;
}

/**
 * The methods instrument: six sections as slides (ballots, the seven counts,
 * head to head, the paradox gallery, the atlas, and the simulation), and a
 * playground that pulls up from the bottom of the screen. The slides and the
 * playground share one electorate and its count.
 */
export function MethodsInstrument({
  presets,
  searches,
  simulation,
  initialProfile,
  initialResolution,
  initialSpecimen,
  initialSection,
  initialPlay,
  provenance,
}: {
  presets: PresetOption[];
  searches: SpecimenSearch[];
  simulation: SimulationSummary;
  initialProfile: UtilityProfile;
  initialResolution: ProfileResolveResponse | null;
  initialSpecimen: SpecimenView | null;
  initialSection: SectionId;
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

  const [section, setSection] = useState(() => SECTIONS.indexOf(initialSection));
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
    for (const name of ["p", "s", "v", "section", "play"]) url.searchParams.delete(name);
    if (section > 0) url.searchParams.set("section", SECTIONS[section]);
    if (specimenView) {
      url.searchParams.set("s", specimenView.id);
      url.searchParams.set("v", specimenView.role);
    } else if (key !== defaultKey) {
      url.searchParams.set("p", key);
    }
    if (playOpen) url.searchParams.set("play", "1");
    window.history.replaceState(null, "", url);
  }, [key, specimenView, section, playOpen, defaultKey]);

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

  const electorateBar = (
    <ElectorateBar
      presets={presets}
      activeKey={key}
      origin={origin}
      summary={summary}
      onPreset={openPreset}
      onPlay={() => setPlayOpen(true)}
    />
  );

  const counts = (
    <div className={cn("transition-opacity", !showing && "opacity-55")}>
      <Channels resolution={resolution} selected={method} onSelect={setMethod} />
    </div>
  );
  const trace = (
    <div className={cn("transition-opacity", !showing && "opacity-55")}>
      <h3 className="mb-3 text-sm font-medium text-mi-ink">
        How {METHOD_META[selectedResult.method].label.toLowerCase()} counted
      </h3>
      <MethodTrace result={selectedResult} resolution={resolution} />
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

  const slides: Slide[] = [
    {
      id: "ballots",
      title: "Ballots",
      content: (
        <SlideFrame
          number={1}
          title="Five ballots from one voter"
          intro="Each group of voters places the candidates on a scale from 0 to 10. The sincere-v1 model turns that placement into every kind of ballot the seven methods read."
        >
          {electorateBar}
          {ballots}
        </SlideFrame>
      ),
    },
    {
      id: "counts",
      title: "Seven counts",
      content: (
        <SlideFrame
          number={2}
          title="Same voters, different winners"
          intro="Seven methods count the same electorate. Choose one to see how it reached its winner."
        >
          {electorateBar}
          <div className="grid gap-6 lg:grid-cols-2">
            {counts}
            {trace}
          </div>
        </SlideFrame>
      ),
    },
    {
      id: "head-to-head",
      title: "Head to head",
      content: (
        <SlideFrame
          number={3}
          title="Head to head"
          intro="Every pair of candidates as a two-way race, decided by how many voters rank one above the other."
        >
          {electorateBar}
          <div className="max-w-xl">{tournament}</div>
        </SlideFrame>
      ),
    },
    {
      id: "paradoxes",
      title: "Paradoxes",
      content: (
        <SlideFrame
          number={4}
          title="Paradox gallery"
          intro="The smallest elections in which each method fails a fairness criterion, found by exhaustive search."
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
        </SlideFrame>
      ),
    },
    {
      id: "atlas",
      title: "Atlas",
      content: (
        <SlideFrame number={5} title="Atlas">
          <Atlas onLoadPoint={loadAtlasPoint} />
        </SlideFrame>
      ),
    },
    {
      id: "at-scale",
      title: "At scale",
      content: (
        <SlideFrame number={6} title="At scale">
          <AtScale summary={simulation} />
        </SlideFrame>
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-6xl px-4 pt-8 pb-28 sm:pt-12">
      <header className="max-w-3xl">
        <p className="font-mi-mono text-xs tracking-wide text-mi-muted">Voting methods · instrument</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.02em] text-mi-ink sm:text-[2.75rem] sm:leading-[1.08]">
          Same voters, different winners.
        </h1>
        <p className="mt-3 text-base leading-relaxed text-mi-ink-2 sm:text-lg">
          Seven ways to count the same voters, one section at a time: how voters fill in
          their ballots, how each method counts them, where majority rule breaks down, the
          smallest elections in which each method fails a fairness test, who wins where across
          a plane of voters, and how often the methods disagree.
        </p>
      </header>

      <div className="mt-8">
        <SlideDeck slides={slides} index={section} onIndex={setSection} />
      </div>

      <footer className="mt-10 border-t border-mi-rule pt-4 font-mi-mono text-xs leading-relaxed text-mi-muted">
        Ballots: {resolution.ballot_model ?? "ranked input"} (sincere voters; rules on the Ballots
        slide). Presets, specimens and atlas layouts: public/data/methods (presets sha256{" "}
        {provenance.presetsHash}…), built from source {provenance.sourceHash}…. Edits: POST
        /api/voting/profile/resolve. Ties: seeded random tiebreak, seed {resolution.tiebreak_seed}.
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
                setSection(SECTIONS.indexOf("atlas"));
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

/** What the slides are counting, with presets to switch to and the playground. */
function ElectorateBar({
  presets,
  activeKey,
  origin,
  summary,
  onPreset,
  onPlay,
}: {
  presets: PresetOption[];
  activeKey: string;
  origin: string | null;
  summary: React.ReactNode;
  onPreset: (preset: PresetOption) => void;
  onPlay: () => void;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-[3px] border border-mi-rule bg-mi-page px-3 py-2">
      <StartingPoints presets={presets} activeKey={activeKey} origin={origin} onPreset={onPreset} />
      <span className="font-mi-mono text-xs text-mi-ink-2">{summary}</span>
      <span className="ml-auto">
        <PlayButton onClick={onPlay}>Open in the playground</PlayButton>
      </span>
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
