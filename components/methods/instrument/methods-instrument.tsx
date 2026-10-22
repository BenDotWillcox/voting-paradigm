"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { resolveProfileAction } from "@/actions/methods-actions";
import { isReference, type AtlasView } from "@/lib/methods/atlas";
import { METHOD_META } from "@/lib/methods/instrument";
import { encodeProfile, specimenProfile, totalVoters } from "@/lib/methods/profile";
import { TOUR } from "@/lib/methods/tour";
import { cn } from "@/lib/utils";
import type {
  ProfileResolveResponse,
  Specimen,
  SpecimenRole,
  SpecimenSearch,
  UtilityProfile,
  VotingMethod,
} from "@/types/methods";

import { Atlas, AtlasPointBanner, type AtlasPoint } from "./atlas";
import { BallotsPanel } from "./ballots-panel";
import { Channels } from "./channels";
import { MethodTrace } from "./method-trace";
import { ParadoxGallery } from "./paradox-gallery";
import { ProfileEditor } from "./profile-editor";
import { SpecimenBanner } from "./specimen-banner";
import { TourBar } from "./tour-bar";
import { TournamentGraph } from "./tournament-graph";

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

type Status =
  | { kind: "ready" }
  | { kind: "counting" }
  | { kind: "empty" }
  | { kind: "offline"; message: string };

// Wait this long after the last edit before asking the API to count
const DEBOUNCE_MS = 250;
// Every gallery specimen, resolved at build time (scripts/build_methods_artifacts.py)
const SPECIMEN_RESOLUTIONS = "/data/methods/specimen-resolutions.json";

/**
 * The methods instrument: edit an electorate of voter types, see the ballots
 * each type casts in every format, and watch seven methods count them at
 * once. A tour, a gallery of minimal specimens and the atlas's spatial maps
 * load electorates into it. Presets and specimens resolve from static
 * artifacts; edits are counted by the Python API
 * (POST /api/voting/profile/resolve), cached by profile.
 */
export function MethodsInstrument({
  presets,
  searches,
  initialProfile,
  initialResolution,
  initialSpecimen,
  provenance,
}: {
  presets: PresetOption[];
  searches: SpecimenSearch[];
  initialProfile: UtilityProfile;
  initialResolution: ProfileResolveResponse | null;
  initialSpecimen: SpecimenView | null;
  provenance: { presetsHash: string; sourceHash: string };
}) {
  const cache = useRef(
    new Map([
      ...presets.map((preset) => [encodeProfile(preset.profile), preset.resolution] as const),
      ...(initialResolution ? [[encodeProfile(initialProfile), initialResolution] as const] : []),
    ])
  );

  const specimens = useMemo(
    () =>
      new Map(
        searches.flatMap((search) =>
          search.specimen ? [[search.specimen.id, search] as const] : []
        )
      ),
    [searches]
  );

  const [profile, setProfile] = useState(initialProfile);
  const [resolution, setResolution] = useState<ProfileResolveResponse>(
    () => cache.current.get(encodeProfile(initialProfile)) ?? presets[0].resolution
  );
  const [status, setStatus] = useState<Status>({ kind: "ready" });
  const [method, setMethod] = useState<VotingMethod>(
    () => specimens.get(initialSpecimen?.id ?? "")?.specimen?.method ?? "irv"
  );
  const [voterType, setVoterType] = useState(0);
  const [specimenView, setSpecimenView] = useState<SpecimenView | null>(initialSpecimen);
  const [atlasPoint, setAtlasPoint] = useState<AtlasPoint | null>(null);
  const [tourStep, setTourStep] = useState<number | null>(() =>
    initialStep(initialSpecimen, encodeProfile(initialProfile), presets)
  );
  const [staticVersion, setStaticVersion] = useState(0);
  const latest = useRef(0);
  const banner = useRef<HTMLDivElement>(null);
  const atlasSection = useRef<HTMLDivElement>(null);
  const scrollToBanner = useRef(false);

  const key = useMemo(() => encodeProfile(profile), [profile]);
  const resolvedKey =
    resolution.profile.ballot_type === "utility" ? encodeProfile(resolution.profile) : "";
  const showing = resolvedKey === key;
  const selectedType = Math.min(voterType, profile.rows.length - 1);
  const activeSearch = specimenView ? specimens.get(specimenView.id) : undefined;

  // Specimens resolve from a static file, fetched once in the background
  useEffect(() => {
    let cancelled = false;
    fetch(SPECIMEN_RESOLUTIONS)
      .then((response) => (response.ok ? response.json() : null))
      .then((data: { resolutions?: Record<string, ProfileResolveResponse> } | null) => {
        if (cancelled || !data?.resolutions) return;
        for (const [k, v] of Object.entries(data.resolutions)) cache.current.set(k, v);
        setStaticVersion((version) => version + 1);
      })
      .catch(() => {
        // The API resolves specimens too; nothing to do
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.delete("p");
    url.searchParams.delete("s");
    url.searchParams.delete("v");
    if (specimenView) {
      url.searchParams.set("s", specimenView.id);
      url.searchParams.set("v", specimenView.role);
    } else if (key !== encodeProfile(presets[0].profile)) {
      url.searchParams.set("p", key);
    }
    window.history.replaceState(null, "", url);
  }, [key, specimenView, presets]);

  useEffect(() => {
    if ((specimenView || atlasPoint) && scrollToBanner.current) {
      scrollToBanner.current = false;
      banner.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [specimenView, atlasPoint]);

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
  }, [profile, key, staticVersion]);

  function openSpecimen(specimen: Specimen, role?: SpecimenRole) {
    const shown = role ?? specimen.profiles[0].role;
    setAtlasPoint(null);
    setSpecimenView({ id: specimen.id, role: shown });
    setProfile(specimenProfile(specimen, shown));
    setMethod(specimen.method);
    setVoterType(0);
  }

  function goToStep(step: number) {
    const target = TOUR[step].target;
    setTourStep(step);
    if (target.kind === "preset") {
      const preset = presets.find((p) => p.id === target.id);
      if (preset) {
        setSpecimenView(null);
        setAtlasPoint(null);
        setProfile(preset.profile);
        setVoterType(0);
      }
    } else if (target.kind === "specimen") {
      const specimen = specimens.get(target.id)?.specimen;
      if (specimen) openSpecimen(specimen, target.role);
    }
  }

  function loadAtlasPoint(response: ProfileResolveResponse, point: AtlasPoint, view: AtlasView) {
    if (response.profile.ballot_type !== "utility") return;
    // The point arrives counted; cache it so the instrument shows it at once
    cache.current.set(encodeProfile(response.profile), response);
    scrollToBanner.current = true;
    setSpecimenView(null);
    setTourStep(null);
    setAtlasPoint(point);
    setProfile(response.profile);
    setVoterType(0);
    if (!isReference(view)) setMethod(view);
  }

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

      <div className="mt-6">
        <TourBar step={tourStep} onStep={goToStep} />
      </div>

      {specimenView && activeSearch?.specimen ? (
        <div ref={banner} className="mt-6 scroll-mt-4">
          <SpecimenBanner
            specimen={activeSearch.specimen}
            role={specimenView.role}
            maxVoters={activeSearch.max_voters}
            onRole={(role) => {
              if (activeSearch.specimen) openSpecimen(activeSearch.specimen, role);
            }}
            onClose={() => {
              setSpecimenView(null);
              setTourStep(null);
            }}
          />
        </div>
      ) : atlasPoint ? (
        <div ref={banner} className="mt-6 scroll-mt-4">
          <AtlasPointBanner
            point={atlasPoint}
            voters={totalVoters(profile)}
            types={profile.rows.length}
            onBack={() => atlasSection.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
            onClose={() => setAtlasPoint(null)}
          />
        </div>
      ) : null}

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
              onChange={(next) => {
                setProfile(next);
                setSpecimenView(null);
                setAtlasPoint(null);
                setTourStep((step) => (step !== null && TOUR[step].target.kind === "free" ? step : null));
              }}
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

      <div className="mt-6">
        <Panel title="Paradox gallery">
          <ParadoxGallery
            searches={searches}
            activeSpecimen={specimenView?.id ?? null}
            onOpen={(specimen) => {
              scrollToBanner.current = true;
              setTourStep(null);
              openSpecimen(specimen);
            }}
          />
        </Panel>
      </div>

      <div ref={atlasSection} className="mt-6 scroll-mt-4">
        <Panel title="Atlas">
          <Atlas onLoadPoint={loadAtlasPoint} />
        </Panel>
      </div>

      <footer className="mt-10 border-t border-mi-rule pt-4 font-mi-mono text-xs leading-relaxed text-mi-muted">
        Ballots: {resolution.ballot_model ?? "ranked input"} (sincere voters; rules in the Ballots
        panel). Presets, specimens and atlas layouts: public/data/methods (presets sha256{" "}
        {provenance.presetsHash}…), built from source {provenance.sourceHash}…. Edits: POST
        /api/voting/profile/resolve. Ties: seeded random tiebreak, seed {resolution.tiebreak_seed}.
      </footer>
    </div>
  );
}

function initialStep(
  specimen: SpecimenView | null,
  key: string,
  presets: PresetOption[]
): number | null {
  const index = TOUR.findIndex(({ target }) =>
    specimen
      ? target.kind === "specimen" && target.id === specimen.id
      : target.kind === "preset" &&
        encodeProfile(presets.find((p) => p.id === target.id)?.profile ?? presets[0].profile) === key
  );
  return index === -1 ? null : index;
}

function StatusNote({ status, showing }: { status: Status; showing: boolean }) {
  if (status.kind === "counting") return <span className="text-mi-muted"> · counting…</span>;
  if (status.kind === "empty")
    return <span className="text-mi-ink"> · add at least one voter to count</span>;
  if (status.kind === "offline")
    return (
      <span className="text-mi-ink">
        {" "}
        · {status.message} Showing the last counted electorate; the tour and gallery still work.
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
