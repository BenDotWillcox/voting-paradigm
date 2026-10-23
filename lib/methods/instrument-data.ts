import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type {
  AtlasCandidate,
  AtlasResponse,
  ProfileResolveResponse,
  SimulationSummary,
  SpecimenSearch,
  UtilityProfile,
  VotingMethod,
} from "@/types/methods";

/**
 * Static data for the methods instrument, from the artifacts that
 * scripts/build_methods_artifacts.py writes. Presets carry their full
 * resolution, so the page renders them with no Python process; specimens
 * resolve from specimen-resolutions.json the same way. The simulation summary
 * comes from the eval/ benchmark (python -m eval.run_methods_simulation).
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
  /** The methods simulation's summary, with Wilson intervals. */
  simulation: SimulationSummary;
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
  const [presetsText, specimensText, manifestText, simulationText] = await Promise.all([
    readFile(join(ARTIFACTS, "presets.json"), "utf-8"),
    readFile(join(ARTIFACTS, "specimens.json"), "utf-8"),
    readFile(join(ARTIFACTS, "manifest.json"), "utf-8"),
    readFile(join(ARTIFACTS, "simulation.json"), "utf-8"),
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
    simulation: JSON.parse(simulationText) as SimulationSummary,
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

/** One method's map for the home card, with the focus candidate's share. */
export interface HomeCardMap {
  method: VotingMethod;
  winners: string;
  ties: number[];
  /** Share of the full map the focus candidate wins outright. */
  focusShare: number;
  /** Share of the full map a tiebreak decided. */
  tieShare: number;
}

export interface HomeCardAtlas {
  size: number;
  candidates: AtlasCandidate[];
  focus: string;
  maps: HomeCardMap[];
}

/**
 * The atlas's hub layout for the methods home card: each method's map,
 * every other cell in each direction, with shares from the full map. The
 * home page carries a few kilobytes instead of atlas.json.
 */
export async function loadHomeCardAtlas(
  layoutId = "hub",
  focus = "D",
  step = 2
): Promise<HomeCardAtlas> {
  const text = await readFile(join(ARTIFACTS, "atlas.json"), "utf-8");
  const { layouts } = JSON.parse(text) as { layouts: { id: string; atlas: AtlasResponse }[] };
  const atlas = layouts.find((layout) => layout.id === layoutId)?.atlas;
  if (!atlas) throw new Error(`atlas.json has no ${layoutId} layout`);

  const full = atlas.size * atlas.size;
  const size = Math.floor(atlas.size / step);
  // The cell nearest the center of each step × step block
  const source = (row: number, col: number) =>
    (row * step + step / 2) * atlas.size + (col * step + step / 2);

  return {
    size,
    candidates: atlas.candidates,
    focus,
    maps: atlas.maps.map((map) => {
      const tied = new Set(map.ties);
      let winners = "";
      const ties: number[] = [];
      for (let row = 0; row < size; row++) {
        for (let col = 0; col < size; col++) {
          const cell = source(row, col);
          winners += map.winners[cell];
          if (tied.has(cell)) ties.push(row * size + col);
        }
      }
      let outright = 0;
      for (let cell = 0; cell < full; cell++) {
        if (map.winners[cell] === focus && !tied.has(cell)) outright++;
      }
      return {
        method: map.method,
        winners,
        ties,
        focusShare: outright / full,
        tieShare: map.ties.length / full,
      };
    }),
  };
}
