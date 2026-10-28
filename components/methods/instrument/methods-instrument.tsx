"use client";

import { ArrowUpRight, Code2, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isReference, type AtlasView } from "@/lib/methods/atlas";
import type { CountSources } from "@/lib/methods/count-inspector";
import { CRITERIA } from "@/lib/methods/gallery";
import type { IRVSource } from "@/lib/methods/irv-inspector";
import { encodeProfile, specimenProfile, totalVoters } from "@/lib/methods/profile";
import { anchorForStep, DEMO_SECTIONS, isDemoAnchor, type DemoAnchor, type DemoSection } from "@/lib/methods/scroll-sections";
import type { ExampleSlide, StepId } from "@/lib/methods/sections";
import type { Story, StoryStep } from "@/lib/methods/stories";
import { WALK_PRESET } from "@/lib/methods/walkthrough";
import { cn } from "@/lib/utils";
import type { ProfileResolveResponse, SampleElection, SimulationSummary, Specimen, SpecimenRole, SpecimenSearch, UtilityProfile, VotingMethod } from "@/types/methods";
import { AtlasPointBanner, type AtlasPoint } from "./atlas";
import { BallotsPanel } from "./ballots-panel";
import { Channels } from "./channels";
import { MethodExplorer } from "./method-explorer";
import { MethodsHero } from "./methods-hero";
import { ProfileEditor } from "./profile-editor";
import { CONTAINER, SectionBand, TONES, type Tone } from "./section-band";
import { CodeFigure, EfficiencyFigure, PreferenceFigure, WinnersFigure } from "./section-figures";
import { SimulationEvidence } from "./simulation-evidence";
import { SpecimenBanner } from "./specimen-banner";
import { useElectorate } from "./use-electorate";
import { WhyItMatters } from "./why-it-matters";

export interface PresetOption {
  id: string; label: string; description: string;
  notes: Record<ExampleSlide, string>;
  profile: UtilityProfile;
  resolution: ProfileResolveResponse;
}
export interface SpecimenView { id: string; role: SpecimenRole }
const action = "inline-flex min-h-11 items-center justify-center gap-2 rounded-[4px] border border-mi-rule px-3 py-2 text-left text-sm font-medium text-mi-ink hover:bg-mi-wash focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink";

/** One scrolling argument: implementation, consequences, evidence, experiment. */
export function MethodsInstrument({ presets, stories, irvSource, countSources, samples, searches, simulation, initialProfile, initialResolution, initialSpecimen, initialAnchor, initialStory, initialReference, initialInspectorMethod, initialInspectorInput, initialRankedPairsCycle, provenance }: {
  presets: PresetOption[]; stories: Story[]; irvSource: IRVSource; countSources: CountSources;
  samples: SampleElection[]; searches: SpecimenSearch[]; simulation: SimulationSummary;
  initialProfile: UtilityProfile; initialResolution: ProfileResolveResponse | null;
  initialSpecimen: SpecimenView | null; initialAnchor: DemoAnchor; initialStory?: StoryStep; initialReference?: StepId;
  initialInspectorMethod: VotingMethod; initialInspectorInput: "reference" | "playground";
  initialRankedPairsCycle: boolean; provenance: { presetsHash: string; sourceHash: string };
}) {
  const electorate = useElectorate({ presets, initialProfile, initialResolution });
  const { profile, resolution, status, showing, key } = electorate;
  const ready = showing && status.kind === "ready";
  const [inspectorMethod, setInspectorMethod] = useState(initialInspectorMethod);
  const [inspectorInput, setInspectorInput] = useState(initialInspectorInput);
  const [rankedPairsCycle, setRankedPairsCycle] = useState(initialRankedPairsCycle);
  const [method, setMethod] = useState(() => searches.find((search) => search.specimen?.id === initialSpecimen?.id)?.specimen?.method ?? initialInspectorMethod);
  const [voterType, setVoterType] = useState(0);
  const [specimenView, setSpecimenView] = useState(initialSpecimen);
  const [atlasPoint, setAtlasPoint] = useState<AtlasPoint | null>(null);
  const [activeSection, setActiveSection] = useState<DemoSection>("implementation");
  const firstLocation = useRef(true);
  const specimens = useMemo(() => new Map(searches.flatMap((search) => search.specimen ? [[search.specimen.id, search] as const] : [])), [searches]);
  const activeSearch = specimenView ? specimens.get(specimenView.id) : undefined;
  const walk = presets.find((preset) => preset.id === WALK_PRESET) ?? presets[0];
  const cycle = presets.find((preset) => preset.id === "majority-cycle");
  const defaultKey = encodeProfile(presets[0].profile);
  const selectedType = Math.max(0, Math.min(voterType, profile.rows.length - 1));
  const selectedResult = resolution.results.find((result) => result.method === method) ?? resolution.results[0];
  const pendingMessage = status.kind === "empty" ? "Add at least one voter to count this electorate."
    : status.kind === "offline" ? "This electorate could not be counted. Try editing it or choosing a starting point."
    : "Counting your edited electorate in Python…";

  const jumpTo = useCallback((anchor: DemoAnchor, focus = true) => {
    const destination = document.getElementById(anchor);
    if (!destination) return;
    for (let parent: HTMLElement | null = destination; parent; parent = parent.parentElement) {
      if (parent instanceof HTMLDetailsElement) parent.open = true;
    }
    window.requestAnimationFrame(() => {
      destination.scrollIntoView({ block: "start", behavior: "instant" });
      if (focus) { destination.tabIndex = -1; destination.focus({ preventScroll: true }); }
    });
    const url = new URL(window.location.href);
    url.hash = anchor;
    window.history.replaceState(null, "", url);
  }, []);

  useEffect(() => {
    if (!firstLocation.current) return;
    firstLocation.current = false;
    const hash = window.location.hash.slice(1);
    const anchor = isDemoAnchor(hash) ? hash : initialAnchor;
    if (anchor !== "implementation") jumpTo(anchor, false);
  }, [initialAnchor, jumpTo]);

  useEffect(() => {
    const followHash = () => {
      const anchor = window.location.hash.slice(1);
      if (isDemoAnchor(anchor)) jumpTo(anchor, false);
    };
    window.addEventListener("hashchange", followHash);
    return () => window.removeEventListener("hashchange", followHash);
  }, [jumpTo]);

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (visible) setActiveSection(visible.target.id as DemoSection);
    }, { rootMargin: "-12% 0px -65% 0px" });
    DEMO_SECTIONS.forEach(({ id }) => { const element = document.getElementById(id); if (element) observer.observe(element); });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    for (const name of ["p", "s", "v", "step", "section", "play", "method", "input", "example"]) url.searchParams.delete(name);
    if (specimenView) { url.searchParams.set("s", specimenView.id); url.searchParams.set("v", specimenView.role); }
    else if (key !== defaultKey) url.searchParams.set("p", key);
    if (inspectorMethod !== "plurality") url.searchParams.set("method", inspectorMethod);
    if (inspectorInput === "playground") url.searchParams.set("input", "playground");
    if (!rankedPairsCycle) url.searchParams.set("example", "condorcet");
    window.history.replaceState(null, "", url);
  }, [key, specimenView, defaultKey, inspectorMethod, inspectorInput, rankedPairsCycle]);

  function edit(next: UtilityProfile) { electorate.load(next); setSpecimenView(null); setAtlasPoint(null); }
  function openPreset(preset: PresetOption) {
    electorate.load(preset.profile, preset.resolution);
    setSpecimenView(null); setAtlasPoint(null); setVoterType(0);
  }
  function openSpecimen(specimen: Specimen, role?: SpecimenRole, navigate = true) {
    const selected = role ?? specimen.profiles[0].role;
    electorate.load(specimenProfile(specimen, selected));
    setSpecimenView({ id: specimen.id, role: selected }); setAtlasPoint(null); setVoterType(0); setMethod(specimen.method);
    if (navigate) jumpTo("playground");
  }
  function openMethod(selected: VotingMethod) {
    setInspectorMethod(selected); setInspectorInput("reference"); setRankedPairsCycle(false); jumpTo("implementation");
  }
  function editInspector() {
    setMethod(inspectorMethod); setInspectorInput("playground"); jumpTo("playground");
  }
  function tracePlayground() {
    if (!ready) return;
    setInspectorInput("playground"); setInspectorMethod(selectedResult.method); jumpTo("implementation");
  }
  function loadAtlasPoint(response: ProfileResolveResponse, point: AtlasPoint, view: AtlasView) {
    if (response.profile.ballot_type !== "utility") return;
    electorate.load(response.profile, response); setSpecimenView(null); setAtlasPoint(point); setVoterType(0);
    if (!isReference(view)) setMethod(view);
    jumpTo("playground");
  }
  const reference = (step: StepId) => jumpTo(anchorForStep(step));

  return (
    <main className="pb-16">
      <MethodsHero label={walk.label} resolution={walk.resolution} simulation={simulation} criteria={CRITERIA.length} />
      <nav aria-label="Demo sections" className="mi-island relative z-20 border-t border-mi-rule md:sticky md:top-0">
        <div className={cn(CONTAINER, "grid grid-cols-2 md:grid-cols-4")}>
          {DEMO_SECTIONS.map(({ id, label }, index) => {
            const tone = TONES[(index + 1) as Tone];
            return <a key={id} href={`#${id}`} onClick={(event) => { event.preventDefault(); jumpTo(id); }} aria-current={activeSection === id ? "location" : undefined} className={cn("-mt-px flex min-h-12 min-w-0 items-center gap-2.5 border-t-[3px] px-2 text-sm font-medium motion-safe:transition-colors focus-visible:outline-2 focus-visible:-outline-offset-4 focus-visible:outline-mi-ink sm:px-3 sm:text-base", activeSection === id ? cn(tone.rule, "text-mi-ink") : "border-transparent text-mi-ink-2 hover:text-mi-ink")}><span className={cn("font-mi-mono text-sm font-normal", tone.text)} aria-hidden>0{index + 1}</span>{label}</a>;
          })}
        </div>
      </nav>
      <section id="implementation" aria-labelledby="implementation-title" className={cn("scroll-mt-14", TONES[1].body)}>
        <SectionBand tone={1} number="01" id="implementation-title" title="Explore the implementation." description="Pick a voting rule. Follow its Python code alongside the count it produces." figure={<CodeFigure source={countSources.plurality} resolution={walk.resolution} />} />
        <div className={cn(CONTAINER, "pb-16 pt-8 sm:pb-24 sm:pt-10")}>
          <MethodExplorer method={inspectorMethod} onMethod={setInspectorMethod} reference={walk.resolution} cycle={cycle?.resolution} useCycle={rankedPairsCycle} onCycle={setRankedPairsCycle} input={inspectorInput} onInput={setInspectorInput} playground={ready ? resolution : undefined} playgroundKey={key} pendingMessage={pendingMessage} onEdit={editInspector} sources={countSources} failures={[]} onReference={reference} />
        </div>
      </section>
      <section id="why-it-matters" aria-labelledby="why-title" className={cn("scroll-mt-14", TONES[2].body)}>
        <SectionBand tone={2} number="02" id="why-title" title="Why it matters." description="A counting rule decides which parts of people’s preferences shape the outcome. Change the rule, and the consequences can change with it." figure={<WinnersFigure label={walk.label} resolution={walk.resolution} />} />
        <div className={cn(CONTAINER, "pb-16 pt-10 sm:pb-24 sm:pt-14")}>
          <WhyItMatters presets={presets} stories={stories} irvSource={irvSource} searches={searches} onMethod={openMethod} onSpecimen={openSpecimen} initialExample={initialStory} initialReference={initialReference} />
        </div>
      </section>
      <section id="simulation" aria-labelledby="simulation-title" className={cn("scroll-mt-14", TONES[3].body)}>
        <SectionBand tone={3} number="03" id="simulation-title" title="From an example to evidence." description="Counterexamples reveal what can happen. Seeded simulations explore how often it happens under a specified model." figure={<EfficiencyFigure simulation={simulation} />} />
        <div className={cn(CONTAINER, "pb-16 pt-10 sm:pb-24 sm:pt-14")}>
          <SimulationEvidence simulation={simulation} samples={samples} onAtlasPoint={loadAtlasPoint} onImplementation={() => jumpTo("implementation")} />
        </div>
      </section>
      <section id="playground" aria-labelledby="playground-title" className={cn("scroll-mt-14", TONES[4].body)}>
        <SectionBand tone={4} number="04" id="playground-title" title="Build your own electorate." description="Change the voters, their preferences, or the candidates. The Python package counts every method on the same electorate." figure={<PreferenceFigure label={walk.label} profile={walk.profile} />} />
        <div className={cn(CONTAINER, "space-y-5 pb-16 pt-10 sm:pb-24 sm:pt-14 [&_.text-xs]:text-sm")}>
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Playground starting points">
            {presets.map((preset) => <button key={preset.id} type="button" title={preset.description} aria-pressed={key === encodeProfile(preset.profile)} onClick={() => openPreset(preset)} className={cn(action, key === encodeProfile(preset.profile) && "border-mi-ink bg-mi-ink text-mi-surface hover:bg-mi-ink")}>{preset.label}</button>)}
            <button type="button" onClick={() => { edit({ ballot_type: "utility", candidates: ["A", "B", "C"], rows: [{ count: 1, utilities: { A: 100, B: 50, C: 0 } }] }); setVoterType(0); }} className={action}><Plus size={16} aria-hidden />New electorate</button>
          </div>
          {specimenView && activeSearch?.specimen ? <SpecimenBanner specimen={activeSearch.specimen} role={specimenView.role} maxVoters={activeSearch.max_voters} onRole={(role) => { if (activeSearch.specimen) openSpecimen(activeSearch.specimen, role, false); }} onClose={() => setSpecimenView(null)} /> : atlasPoint ? <AtlasPointBanner point={atlasPoint} voters={totalVoters(profile)} types={profile.rows.length} onBack={() => jumpTo("atlas")} onClose={() => setAtlasPoint(null)} /> : null}
          <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)] xl:items-start">
            <div className="min-w-0 space-y-4">
              <Panel title="Your voters"><p className="mb-4 text-sm leading-relaxed text-mi-ink-2">Each row is a group of voters. Move candidates along its preference scale, then change how many voters share it.</p><ProfileEditor profile={profile} selected={selectedType} onSelect={setVoterType} onChange={edit} /></Panel>
              <details className="min-w-0 rounded-[4px] border border-mi-rule bg-mi-surface p-4"><summary className="min-h-11 cursor-pointer text-base font-medium text-mi-ink">Inspect the ballots this creates</summary><div className="min-w-0 pt-3"><BallotsPanel profile={profile} ballots={ready ? resolution.voter_ballots : null} selected={selectedType} onSelect={setVoterType} /></div></details>
            </div>
            <div className="min-w-0 space-y-4" aria-busy={status.kind === "counting"}>
              <Panel title="Compare the methods">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><p role="status" className="text-sm leading-relaxed text-mi-ink-2">{ready ? `${resolution.total_voters} voters · ${new Set(resolution.results.map((result) => result.winner)).size} different winners · seed ${resolution.tiebreak_seed}` : pendingMessage}</p><button type="button" onClick={tracePlayground} disabled={!ready} className={cn(action, "disabled:opacity-40")}><Code2 size={16} aria-hidden />Trace this count <ArrowUpRight size={16} aria-hidden /></button></div>
                {ready ? <Channels resolution={resolution} selected={method} onSelect={setMethod} /> : <div className="min-h-40 rounded-[4px] bg-mi-wash p-5 text-sm leading-relaxed text-mi-ink-2">{status.kind === "empty" ? "The comparison will appear here when the electorate has voters." : status.kind === "offline" ? "Your edits are preserved. Preset examples remain available." : "Updating all seven methods from the current preferences."}</div>}
              </Panel>
            </div>
          </div>
        </div>
      </section>
      <footer className={CONTAINER}><div className="border-t border-mi-rule pt-6 text-sm leading-relaxed text-mi-ink-2">
        <div className="flex flex-wrap items-center justify-between gap-3"><p>Inspect it. Change it. Reproduce it.</p><a href="https://github.com/BenDotWillcox/voting-paradigm" className={action}>View the Python package <ArrowUpRight size={15} aria-hidden /></a></div>
        <details className="mt-4"><summary className="min-h-11 cursor-pointer py-3">Data &amp; provenance</summary><p className="max-w-4xl break-words">Presets, specimens and simulations are saved artifacts in <code>public/data/methods</code>. The sincere-v1 ballot model translates utilities into each ballot format; voting methods run in Python. Edited electorates use <code>POST /api/voting/profile/resolve</code>. Ties use seed {resolution.tiebreak_seed}. Presets SHA-256: <code>{provenance.presetsHash}…</code>. Artifact source: <code>{provenance.sourceHash}…</code>.</p></details>
      </div></footer>
    </main>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="min-w-0 rounded-[4px] border border-mi-rule bg-mi-surface"><h3 className="border-b border-mi-rule px-4 py-3 text-base font-semibold text-mi-ink">{title}</h3><div className="min-w-0 p-4 sm:p-5">{children}</div></section>;
}
