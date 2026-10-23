import "server-only";

import { readFile } from "node:fs/promises";
import { join } from "node:path";

import type { ExampleSlide, SlideExample } from "@/lib/methods/sections";
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
  /** What to notice about this preset on each slide that shows it. */
  notes: Record<ExampleSlide, string>;
  profile: UtilityProfile;
  resolution: ProfileResolveResponse;
}

export interface InstrumentData {
  presets: InstrumentPreset[];
  /** The examples on each slide that shows the shared electorate. */
  examples: Record<ExampleSlide, SlideExample[]>;
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

// In display order: the first preset opens the page. Notes describe the
// preset as built, so they show only while it is unedited.
const PRESET_COPY: Record<string, Omit<InstrumentPreset, "id" | "profile" | "resolution">> = {
  "center-squeeze": {
    label: "Center squeeze",
    description:
      "C is everyone's acceptable middle: it beats both rivals head to head but has the fewest first choices.",
    notes: {
      counts:
        "C is everyone's acceptable middle but has the fewest first choices, so plurality and instant runoff pass it over.",
      "head-to-head": "C wins both of its two-way races, though fewer voters rank it first than either rival.",
      ballots:
        "C sits above most voters' average, so their approval ballots include it: approval elects C, where plurality elects A.",
    },
  },
  "majority-cycle": {
    label: "Majority cycle",
    description:
      "Every candidate loses one head-to-head race, and the seven counts pick three different winners.",
    notes: {
      counts: "Every candidate loses one two-way race, and the counts split three ways. Head to head shows the cycle.",
      "head-to-head": "A beats B, B beats C, and C beats A: there is no top for the methods to find.",
      ballots:
        "Each voter's middle candidate sits exactly at their average, so approval approves only favorites and matches plurality.",
    },
  },
  consensus: {
    label: "Consensus",
    description: "Voters split on their favorite, but A is everyone's first or second choice.",
    notes: {
      counts:
        "Voters split three ways on their favorite, but A is every voter's first or second choice, so all seven methods agree.",
      "head-to-head": "A beats both rivals one-on-one without a majority of first choices: a clear Condorcet winner.",
      ballots: "Two of the three voter types approve A as well as their favorite, because A sits above their average.",
    },
  },
  "ballot-shapes": {
    label: "Ballot shapes",
    description: "Every voter ranks A, B, C; only how far B sits from A changes.",
    notes: {
      counts: "Every voter ranks A first, so all seven methods elect A. The differences are in the ballots.",
      "head-to-head": "Every voter ranks A over B over C, so each two-way race is unanimous.",
      ballots: "Every voter ranks A, then B, then C; only how far B sits from A changes.",
    },
  },
};
const PRESET_ORDER = Object.keys(PRESET_COPY);

// Each slide's examples, in chip order. Label and note default to the
// preset's own. The ballot shapes' voter types are a clear favorite, an
// indifferent middle and a close second (scripts/build_methods_artifacts.py).
const SLIDE_EXAMPLES: Record<ExampleSlide, (Partial<SlideExample> & { presetId: string })[]> = {
  counts: [{ presetId: "center-squeeze" }, { presetId: "consensus" }, { presetId: "majority-cycle" }],
  "head-to-head": [{ presetId: "center-squeeze" }, { presetId: "majority-cycle" }, { presetId: "consensus" }],
  ballots: [
    {
      presetId: "ballot-shapes",
      voterType: 0,
      label: "Clear favorite",
      note: "B sits well below this voter's average: approval leaves it out, score gives it 2, and quadratic voting spends votes against it.",
    },
    {
      presetId: "ballot-shapes",
      voterType: 1,
      label: "Indifferent middle",
      note: "B sits exactly at this voter's average: approval still leaves it out, score gives it 5, and quadratic voting spends nothing on it.",
    },
    {
      presetId: "ballot-shapes",
      voterType: 2,
      label: "Close second",
      note: "B sits just below A: approval now includes it, score gives it 9, and quadratic voting spends votes for it. The ranked ballot never changed.",
    },
  ],
};

function slideExamples(presets: InstrumentPreset[]): Record<ExampleSlide, SlideExample[]> {
  const resolve = (slide: ExampleSlide) =>
    SLIDE_EXAMPLES[slide].map((example) => {
      const preset = presets.find((p) => p.id === example.presetId);
      if (!preset) throw new Error(`Example on ${slide} names a missing preset ${example.presetId}`);
      return { label: preset.label, note: preset.notes[slide], ...example };
    });
  return { counts: resolve("counts"), "head-to-head": resolve("head-to-head"), ballots: resolve("ballots") };
}

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

  const ordered = presets
    .map((record) => {
      const copy = PRESET_COPY[record.id];
      const profile = record.resolution?.profile;
      if (!copy || profile?.ballot_type !== "utility") {
        throw new Error(`Preset ${record.id} is missing copy or a utility profile`);
      }
      return { id: record.id, ...copy, profile, resolution: record.resolution };
    })
    .sort((a, b) => PRESET_ORDER.indexOf(a.id) - PRESET_ORDER.indexOf(b.id));

  return {
    presets: ordered,
    examples: slideExamples(ordered),
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
