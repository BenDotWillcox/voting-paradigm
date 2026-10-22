import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { ProfileResolveResponse, SpecimenSearch, UtilityProfile } from "@/types/methods";

/**
 * Static data for the methods instrument, from the artifacts that
 * scripts/build_methods_artifacts.py writes. Presets carry their full
 * resolution, so the page renders them with no Python process; specimens
 * resolve from specimen-resolutions.json the same way.
 */

export interface InstrumentPreset {
  id: string;
  label: string;
  description: string;
  profile: UtilityProfile;
  resolution: ProfileResolveResponse;
}

export interface InstrumentData {
  presets: InstrumentPreset[];
  /** Every gallery search: the method, criterion, bound and specimen, if any. */
  searches: SpecimenSearch[];
  /** First 12 hex digits of presets.json's SHA-256, from the manifest. */
  presetsHash: string;
  /** First 12 hex digits of the source the artifacts were built from. */
  sourceHash: string;
}

const ARTIFACTS = join(process.cwd(), "public", "data", "methods");

const PRESET_COPY: Record<string, { label: string; description: string }> = {
  "majority-cycle": {
    label: "Majority cycle",
    description:
      "Every candidate loses one head-to-head race, and the seven counts pick three different winners.",
  },
  "center-squeeze": {
    label: "Center squeeze",
    description:
      "C is everyone's acceptable middle: it beats both rivals head to head but has the fewest first choices.",
  },
};

interface PresetRecord {
  id: string;
  resolution: ProfileResolveResponse;
}

export async function loadInstrumentData(): Promise<InstrumentData> {
  const [presetsText, specimensText, manifestText] = await Promise.all([
    readFile(join(ARTIFACTS, "presets.json"), "utf-8"),
    readFile(join(ARTIFACTS, "specimens.json"), "utf-8"),
    readFile(join(ARTIFACTS, "manifest.json"), "utf-8"),
  ]);
  const { presets } = JSON.parse(presetsText) as { presets: PresetRecord[] };
  const { searches } = JSON.parse(specimensText) as { searches: SpecimenSearch[] };
  const manifest = JSON.parse(manifestText) as {
    source_sha256: string;
    outputs: Record<string, string>;
  };

  return {
    presets: presets.map((record) => {
      const copy = PRESET_COPY[record.id];
      const profile = record.resolution?.profile;
      if (!copy || profile?.ballot_type !== "utility") {
        throw new Error(`Preset ${record.id} is missing copy or a utility profile`);
      }
      return { id: record.id, ...copy, profile, resolution: record.resolution };
    }),
    searches,
    presetsHash: manifest.outputs["presets.json"].slice(0, 12),
    sourceHash: manifest.source_sha256.slice(0, 12),
  };
}

/** The build-time resolution of a specimen profile, by the instrument's key. */
export async function loadSpecimenResolution(key: string): Promise<ProfileResolveResponse | null> {
  const text = await readFile(join(ARTIFACTS, "specimen-resolutions.json"), "utf-8");
  const { resolutions } = JSON.parse(text) as {
    resolutions: Record<string, ProfileResolveResponse>;
  };
  return resolutions[key] ?? null;
}
