import type { Metadata } from "next";

import {
  MethodsInstrument,
  type SpecimenView,
} from "@/components/methods/instrument/methods-instrument";
import { instrumentMono, instrumentSans } from "@/lib/methods/fonts";
import { loadInstrumentData, loadSpecimenResolution } from "@/lib/methods/instrument-data";
import { loadIRVSource } from "@/lib/methods/irv-source";
import { loadCountSources } from "@/lib/methods/count-sources";
import { decodeProfile, encodeProfile, specimenProfile } from "@/lib/methods/profile";
import { linkedMethod, linkedStep } from "@/lib/methods/sections";
import { anchorForStep, isDemoAnchor } from "@/lib/methods/scroll-sections";
import type { StoryStep } from "@/lib/methods/stories";
import { cn } from "@/lib/utils";
import type { SpecimenRole } from "@/types/methods";

export const metadata: Metadata = {
  title: "Voting methods · Nebula Civitas",
  description:
    "Explore seven voting methods in Python, see why their outcomes differ, examine simulation evidence, and build your own electorate.",
};

/**
 * Demo 1: the voting-methods instrument (prompts/demo-1-methods-instrument.md).
 * Presets and gallery specimens render from static artifacts in
 * public/data/methods/; edits are counted by the Python API through a Server
 * Action. Four sections share one scrolling document. Old step links map to
 * section anchors; method/input/profile query parameters preserve the code
 * explorer's context. The playground is the final section, not a dialog.
 */
export default async function MethodsPage({
  searchParams,
}: {
  searchParams: Promise<{ p?: string; s?: string; v?: string; step?: string; section?: string; play?: string; method?: string; input?: string; example?: string }>;
}) {
  const [{ p, s, v, step, section, play, method, input, example }, data, irvSource, countSources] = await Promise.all([searchParams, loadInstrumentData(), loadIRVSource(), loadCountSources()]);

  const specimen = data.searches.find((search) => search.specimen?.id === s)?.specimen ?? null;
  const role = specimen?.profiles.find((profile) => profile.role === v)?.role ?? specimen?.profiles[0].role;
  const initialSpecimen: SpecimenView | null =
    specimen && role ? { id: specimen.id, role: role as SpecimenRole } : null;

  const initialProfile =
    specimen && role
      ? specimenProfile(specimen, role as SpecimenRole)
      : (decodeProfile(p) ?? data.presets[0].profile);
  const initialResolution = specimen ? await loadSpecimenResolution(encodeProfile(initialProfile)) : null;
  const legacyStep = linkedStep(step, section);
  const initialAnchor = play !== undefined ? "playground"
    : step && isDemoAnchor(step) ? step
    : legacyStep ? anchorForStep(legacyStep)
    : initialSpecimen ? "playground"
    : p !== undefined && input !== "playground" ? "playground" : "implementation";
  const initialStory = data.stories.find((story) => story.step === step)?.step as StoryStep | undefined;

  return (
    <div
      className={cn(
        "methods-instrument min-h-screen font-mi-sans",
        instrumentSans.variable,
        instrumentMono.variable
      )}
    >
      <MethodsInstrument
        presets={data.presets}
        stories={data.stories}
        irvSource={irvSource}
        countSources={countSources}
        samples={data.samples}
        searches={data.searches}
        simulation={data.simulation}
        initialProfile={initialProfile}
        initialResolution={initialResolution}
        initialSpecimen={initialSpecimen}
        initialAnchor={initialAnchor}
        initialStory={initialStory}
        initialReference={legacyStep ?? undefined}
        initialInspectorMethod={linkedMethod(step, method)}
        initialInspectorInput={input === "playground" ? "playground" : "reference"}
        initialRankedPairsCycle={example !== "condorcet"}
        provenance={{ presetsHash: data.presetsHash, sourceHash: data.sourceHash }}
      />
    </div>
  );
}
