import type { Metadata } from "next";

import { MethodsInstrument } from "@/components/methods/instrument/methods-instrument";
import { instrumentMono, instrumentSans } from "@/lib/methods/fonts";
import { loadInstrumentData } from "@/lib/methods/instrument-data";
import { decodeProfile } from "@/lib/methods/profile";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Voting methods · Nebula Civitas",
  description:
    "Same voters, different winners: edit an electorate and watch plurality, instant runoff, Borda and Ranked Pairs count it at once.",
};

/**
 * Demo 1: the voting-methods instrument (prompts/demo-1-methods-instrument.md).
 * Presets render from static artifacts in public/data/methods/; edits are
 * counted by the Python API through a Server Action. `?p=` holds a profile.
 */
export default async function MethodsPage({
  searchParams,
}: {
  searchParams: Promise<{ p?: string }>;
}) {
  const [{ p }, data] = await Promise.all([searchParams, loadInstrumentData()]);
  const initialProfile = decodeProfile(p) ?? data.presets[0].profile;

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
        initialProfile={initialProfile}
        provenance={{ presetsHash: data.presetsHash, sourceHash: data.sourceHash }}
      />
    </div>
  );
}
