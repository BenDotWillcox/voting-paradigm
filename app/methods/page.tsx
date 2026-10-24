import type { Metadata } from "next";

import {
  MethodsInstrument,
  type SpecimenView,
} from "@/components/methods/instrument/methods-instrument";
import { instrumentMono, instrumentSans } from "@/lib/methods/fonts";
import { loadInstrumentData, loadSpecimenResolution } from "@/lib/methods/instrument-data";
import { decodeProfile, encodeProfile, specimenProfile } from "@/lib/methods/profile";
import { linkedStep } from "@/lib/methods/sections";
import { cn } from "@/lib/utils";
import type { SpecimenRole } from "@/types/methods";

export const metadata: Metadata = {
  title: "Voting methods · Nebula Civitas",
  description:
    "Same voters, different winners: edit an electorate and watch seven voting methods count it at once, with a gallery of the smallest examples of each method failing a fairness criterion.",
};

/**
 * Demo 1: the voting-methods instrument (prompts/demo-1-methods-instrument.md).
 * Presets and gallery specimens render from static artifacts in
 * public/data/methods/; edits are counted by the Python API through a Server
 * Action. `?step=` names a step (an old `?section=` slide still resolves);
 * `?play` opens the playground; `?p=` holds a profile and opens it in the
 * playground; `?s=` and `?v=` a specimen and its profile, on the gallery step.
 */
export default async function MethodsPage({
  searchParams,
}: {
  searchParams: Promise<{ p?: string; s?: string; v?: string; step?: string; section?: string; play?: string }>;
}) {
  const [{ p, s, v, step, section, play }, data] = await Promise.all([searchParams, loadInstrumentData()]);

  const specimen = data.searches.find((search) => search.specimen?.id === s)?.specimen ?? null;
  const role = specimen?.profiles.find((profile) => profile.role === v)?.role ?? specimen?.profiles[0].role;
  const initialSpecimen: SpecimenView | null =
    specimen && role ? { id: specimen.id, role: role as SpecimenRole } : null;

  const initialProfile =
    specimen && role
      ? specimenProfile(specimen, role as SpecimenRole)
      : (decodeProfile(p) ?? data.presets[0].profile);
  const initialResolution = specimen ? await loadSpecimenResolution(encodeProfile(initialProfile)) : null;

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
        examples={data.examples}
        stories={data.stories}
        samples={data.samples}
        searches={data.searches}
        simulation={data.simulation}
        initialProfile={initialProfile}
        initialResolution={initialResolution}
        initialSpecimen={initialSpecimen}
        initialStep={initialSpecimen ? "gallery" : (linkedStep(step, section) ?? "voters")}
        initialPlay={play !== undefined || (p !== undefined && !initialSpecimen)}
        provenance={{ presetsHash: data.presetsHash, sourceHash: data.sourceHash }}
      />
    </div>
  );
}
