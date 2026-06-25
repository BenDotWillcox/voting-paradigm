export type PreferenceDimensionId =
  | "transitAccess"
  | "climateAction"
  | "fiscalDiscipline"
  | "roadCapacity"
  | "localControl"
  | "publicSafety"
  | "equityAccess"
  | "deliverySpeed";

export type ChatRole = "assistant" | "user";

export interface PreferenceDimension {
  id: PreferenceDimensionId;
  label: string;
  shortLabel: string;
  description: string;
  lowAnchor: string;
  highAnchor: string;
  color: string;
}

export interface PreferenceSignal {
  dimensionId: PreferenceDimensionId;
  direction: -1 | 1;
  strength: number;
  confidence: number;
  evidence: string;
  source?: "llm" | "replay" | "manual";
}

export interface PreferenceEstimate {
  dimensionId: PreferenceDimensionId;
  value: number;
  confidence: number;
  evidenceCount: number;
  evidence: string[];
}

export interface BallotOption {
  id: string;
  title: string;
  summary: string;
  policyVector: Record<PreferenceDimensionId, number>;
  tradeoffs: string[];
}

export interface AgentVoteScore {
  optionId: string;
  score: number;
  normalizedScore: number;
  matchedDimensions: PreferenceDimensionId[];
}

export interface AgentVote {
  selectedOptionId: string;
  confidence: number;
  scores: AgentVoteScore[];
  rationale: string;
  uncertainDimensions: PreferenceDimensionId[];
}

export interface PreferenceMessage {
  id: string;
  role: ChatRole;
  content: string;
}

export interface PreferenceDemoState {
  messages: PreferenceMessage[];
  signals: PreferenceSignal[];
  estimates: PreferenceEstimate[];
  vote: AgentVote;
  overrideOptionId: string | null;
  replayStep: number;
}

export interface ReplayTurn {
  id: string;
  messages: PreferenceMessage[];
  signals: PreferenceSignal[];
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

export const preferenceDimensions: PreferenceDimension[] = [
  {
    id: "transitAccess",
    label: "Transit access",
    shortLabel: "Transit",
    description: "Preference for frequent, reliable service beyond private cars.",
    lowAnchor: "Car-first network",
    highAnchor: "Frequent transit",
    color: "oklch(0.54 0.16 250)",
  },
  {
    id: "climateAction",
    label: "Climate action",
    shortLabel: "Climate",
    description: "Willingness to cut emissions and adapt infrastructure.",
    lowAnchor: "Emissions tolerated",
    highAnchor: "Climate-first",
    color: "oklch(0.55 0.16 150)",
  },
  {
    id: "fiscalDiscipline",
    label: "Fiscal discipline",
    shortLabel: "Cost",
    description: "Preference for lower cost, lower debt, and maintenance value.",
    lowAnchor: "Spend for impact",
    highAnchor: "Cost restraint",
    color: "oklch(0.58 0.15 75)",
  },
  {
    id: "roadCapacity",
    label: "Road capacity",
    shortLabel: "Roads",
    description: "Preference for expanding vehicle throughput.",
    lowAnchor: "Do not induce trips",
    highAnchor: "Add capacity",
    color: "oklch(0.56 0.14 35)",
  },
  {
    id: "localControl",
    label: "Local control",
    shortLabel: "Local",
    description: "Preference for neighborhood choice and local implementation.",
    lowAnchor: "Regional standard",
    highAnchor: "Local choice",
    color: "oklch(0.55 0.14 305)",
  },
  {
    id: "publicSafety",
    label: "Public safety",
    shortLabel: "Safety",
    description: "Preference for crash reduction, safer crossings, and reliability.",
    lowAnchor: "Speed over safety",
    highAnchor: "Safety first",
    color: "oklch(0.55 0.17 20)",
  },
  {
    id: "equityAccess",
    label: "Equity and access",
    shortLabel: "Access",
    description: "Preference for serving riders and neighborhoods with fewer options.",
    lowAnchor: "Average benefit",
    highAnchor: "Underserved first",
    color: "oklch(0.53 0.16 185)",
  },
  {
    id: "deliverySpeed",
    label: "Delivery speed",
    shortLabel: "Speed",
    description: "Preference for projects that can show visible results soon.",
    lowAnchor: "Long build",
    highAnchor: "Near-term delivery",
    color: "oklch(0.56 0.16 105)",
  },
];

export const ballotOptions: BallotOption[] = [
  {
    id: "electric-brt",
    title: "Electric Bus Rapid Transit",
    summary:
      "Build dedicated bus lanes, signal priority, and charging depots on the busiest cross-town corridors.",
    policyVector: {
      transitAccess: 0.96,
      climateAction: 0.88,
      fiscalDiscipline: -0.34,
      roadCapacity: -0.36,
      localControl: -0.2,
      publicSafety: 0.46,
      equityAccess: 0.78,
      deliverySpeed: 0.28,
    },
    tradeoffs: [
      "High transit and climate gains",
      "Requires capital spending and lane reallocation",
      "Benefits depend on regional corridor discipline",
    ],
  },
  {
    id: "fix-it-first",
    title: "Fix-It-First Streets Package",
    summary:
      "Prioritize pavement repair, dangerous intersection redesigns, bus stop upgrades, and bridge maintenance.",
    policyVector: {
      transitAccess: 0.24,
      climateAction: 0.28,
      fiscalDiscipline: 0.86,
      roadCapacity: -0.08,
      localControl: 0.38,
      publicSafety: 0.78,
      equityAccess: 0.46,
      deliverySpeed: 0.82,
    },
    tradeoffs: [
      "Fast, lower-risk delivery",
      "Strong safety and maintenance value",
      "Less transformative for emissions or mode shift",
    ],
  },
  {
    id: "managed-lanes",
    title: "Managed Highway Lanes",
    summary:
      "Add priced express lanes and ramp improvements to reduce peak-hour congestion on the beltway.",
    policyVector: {
      transitAccess: -0.42,
      climateAction: -0.62,
      fiscalDiscipline: -0.18,
      roadCapacity: 0.92,
      localControl: -0.32,
      publicSafety: 0.22,
      equityAccess: -0.28,
      deliverySpeed: 0.38,
    },
    tradeoffs: [
      "Directly targets congestion",
      "Adds vehicle capacity and toll complexity",
      "Weak fit for climate and access goals",
    ],
  },
  {
    id: "neighborhood-mobility",
    title: "Neighborhood Climate Mobility Grants",
    summary:
      "Fund local protected lanes, traffic calming, shade, school streets, and first-mile transit links.",
    policyVector: {
      transitAccess: 0.58,
      climateAction: 0.72,
      fiscalDiscipline: 0.12,
      roadCapacity: -0.54,
      localControl: 0.88,
      publicSafety: 0.84,
      equityAccess: 0.68,
      deliverySpeed: 0.56,
    },
    tradeoffs: [
      "Strong local and safety alignment",
      "Smaller network effect than major corridors",
      "Requires careful grant oversight",
    ],
  },
  {
    id: "autonomous-shuttles",
    title: "Autonomous Shuttle Pilot",
    summary:
      "Launch low-speed shared shuttles connecting park-and-ride lots, campuses, and transit stations.",
    policyVector: {
      transitAccess: 0.5,
      climateAction: 0.32,
      fiscalDiscipline: 0.24,
      roadCapacity: 0.08,
      localControl: 0.18,
      publicSafety: -0.22,
      equityAccess: 0.18,
      deliverySpeed: 0.62,
    },
    tradeoffs: [
      "Good technology showcase",
      "Uncertain safety and ridership payoff",
      "Limited impact without strong fixed-route transit",
    ],
  },
];

export const openingMessage: PreferenceMessage = {
  id: "opening-assistant",
  role: "assistant",
  content:
    "I will interview you like a civic preference model. Tell me what matters most on a transportation and climate ballot, and I will translate the evidence into an auditable vote.",
};

export const replayTurns: ReplayTurn[] = [
  {
    id: "replay-1",
    messages: [
      {
        id: "replay-1-user",
        role: "user",
        content:
          "I care most about cutting emissions and making it easier for people without cars to get across town. I am willing to spend if the project actually changes how people travel.",
      },
      {
        id: "replay-1-assistant",
        role: "assistant",
        content:
          "That points strongly toward climate action, transit access, and equity. I also hear that cost matters, but you are not treating low spending as the highest priority when the impact is real.",
      },
    ],
    signals: [
      {
        dimensionId: "climateAction",
        direction: 1,
        strength: 0.92,
        confidence: 0.9,
        evidence: "Cutting emissions is named as a top priority.",
        source: "replay",
      },
      {
        dimensionId: "transitAccess",
        direction: 1,
        strength: 0.88,
        confidence: 0.88,
        evidence: "The user wants better cross-town travel without a car.",
        source: "replay",
      },
      {
        dimensionId: "equityAccess",
        direction: 1,
        strength: 0.72,
        confidence: 0.78,
        evidence: "People without cars are explicitly prioritized.",
        source: "replay",
      },
      {
        dimensionId: "fiscalDiscipline",
        direction: -1,
        strength: 0.36,
        confidence: 0.68,
        evidence: "The user is willing to spend for meaningful mode shift.",
        source: "replay",
      },
    ],
  },
  {
    id: "replay-2",
    messages: [
      {
        id: "replay-2-user",
        role: "user",
        content:
          "I also want something visible within a few years. Big promises are less persuasive if the city cannot deliver. Safety around schools and crossings matters a lot too.",
      },
      {
        id: "replay-2-assistant",
        role: "assistant",
        content:
          "I am adding a practical delivery preference and a strong safety signal. That narrows the model away from plans that are ambitious but slow or operationally fragile.",
      },
    ],
    signals: [
      {
        dimensionId: "deliverySpeed",
        direction: 1,
        strength: 0.76,
        confidence: 0.82,
        evidence: "Visible results within a few years are preferred.",
        source: "replay",
      },
      {
        dimensionId: "publicSafety",
        direction: 1,
        strength: 0.86,
        confidence: 0.88,
        evidence: "School and crossing safety is named as important.",
        source: "replay",
      },
      {
        dimensionId: "fiscalDiscipline",
        direction: 1,
        strength: 0.34,
        confidence: 0.58,
        evidence: "The user is skeptical of promises the city cannot deliver.",
        source: "replay",
      },
    ],
  },
  {
    id: "replay-3",
    messages: [
      {
        id: "replay-3-user",
        role: "user",
        content:
          "I am not excited about adding highway capacity. It feels like it locks in more driving. Neighborhoods should have some say, but I still want the regional network to work.",
      },
      {
        id: "replay-3-assistant",
        role: "assistant",
        content:
          "That gives the model a clear negative road-capacity signal and a moderate local-control signal. The best vote should now balance climate, transit, safety, and deliverability.",
      },
    ],
    signals: [
      {
        dimensionId: "roadCapacity",
        direction: -1,
        strength: 0.86,
        confidence: 0.9,
        evidence: "The user rejects adding highway capacity.",
        source: "replay",
      },
      {
        dimensionId: "localControl",
        direction: 1,
        strength: 0.56,
        confidence: 0.7,
        evidence: "Neighborhood say matters, but not at the expense of network function.",
        source: "replay",
      },
      {
        dimensionId: "climateAction",
        direction: 1,
        strength: 0.5,
        confidence: 0.68,
        evidence: "More driving is treated as a climate and land-use concern.",
        source: "replay",
      },
    ],
  },
];

export function createInitialPreferenceState(): PreferenceDemoState {
  const estimates = computePreferenceEstimates([]);
  return {
    messages: [openingMessage],
    signals: [],
    estimates,
    vote: computeAgentVote(estimates),
    overrideOptionId: null,
    replayStep: 0,
  };
}

export function computePreferenceEstimates(
  signals: PreferenceSignal[]
): PreferenceEstimate[] {
  return preferenceDimensions.map((dimension) => {
    const relevant = signals.filter(
      (signal) => signal.dimensionId === dimension.id
    );
    const support = relevant.reduce(
      (sum, signal) =>
        sum + clamp(signal.strength, 0, 1) * clamp(signal.confidence, 0, 1),
      0
    );
    const signedSupport = relevant.reduce(
      (sum, signal) =>
        sum +
        signal.direction *
          clamp(signal.strength, 0, 1) *
          clamp(signal.confidence, 0, 1),
      0
    );
    const preference = support > 0 ? signedSupport / support : 0;
    const confidence = clamp(support / 1.8, 0, 0.96);

    return {
      dimensionId: dimension.id,
      value: clamp(preference * confidence, -1, 1),
      confidence,
      evidenceCount: relevant.length,
      evidence: relevant.map((signal) => signal.evidence).slice(-3),
    };
  });
}

export function computeAgentVote(
  estimates: PreferenceEstimate[],
  overrideOptionId?: string | null
): AgentVote {
  const estimateByDimension = new Map(
    estimates.map((estimate) => [estimate.dimensionId, estimate])
  );

  const rawScores = ballotOptions.map((option) => {
    const score = preferenceDimensions.reduce((sum, dimension) => {
      const estimate = estimateByDimension.get(dimension.id);
      return sum + (estimate?.value ?? 0) * option.policyVector[dimension.id];
    }, 0);
    const matchedDimensions = preferenceDimensions
      .filter((dimension) => {
        const estimate = estimateByDimension.get(dimension.id);
        const vector = option.policyVector[dimension.id];
        return estimate ? estimate.value * vector > 0.08 : false;
      })
      .map((dimension) => dimension.id);
    return { optionId: option.id, score, matchedDimensions };
  });

  const minScore = Math.min(...rawScores.map((score) => score.score), 0);
  const maxScore = Math.max(...rawScores.map((score) => score.score), 0.001);
  const scoreRange = Math.max(maxScore - minScore, 0.001);
  const scores = rawScores
    .map((score) => ({
      ...score,
      normalizedScore: clamp(
        ((score.score - minScore) / scoreRange) * 100,
        0,
        100
      ),
    }))
    .sort((a, b) => b.score - a.score);

  const selectedOptionId = overrideOptionId || scores[0]?.optionId || ballotOptions[0].id;
  const selectedScore =
    scores.find((score) => score.optionId === selectedOptionId) ?? scores[0];
  const runnerUp = scores.find((score) => score.optionId !== selectedOptionId);
  const topMargin = selectedScore && runnerUp ? selectedScore.score - runnerUp.score : 0;
  const meanModelConfidence =
    estimates.reduce((sum, estimate) => sum + estimate.confidence, 0) /
    Math.max(estimates.length, 1);
  const confidence = overrideOptionId
    ? 1
    : clamp(0.12 + meanModelConfidence * 0.42 + Math.max(topMargin, 0) * 0.26, 0.12, 0.94);

  const uncertainDimensions = preferenceDimensions
    .filter((dimension) => {
      const estimate = estimateByDimension.get(dimension.id);
      const selectedOption = ballotOptions.find(
        (option) => option.id === selectedOptionId
      );
      const runnerOption = runnerUp
        ? ballotOptions.find((option) => option.id === runnerUp.optionId)
        : null;
      const selectedVector = selectedOption?.policyVector[dimension.id] ?? 0;
      const runnerVector = runnerOption?.policyVector[dimension.id] ?? 0;
      return (
        Math.abs(selectedVector - runnerVector) > 0.35 &&
        (!estimate || estimate.confidence < 0.45)
      );
    })
    .slice(0, 3)
    .map((dimension) => dimension.id);

  return {
    selectedOptionId,
    confidence,
    scores,
    rationale: buildVoteRationale(selectedOptionId, scores, estimates, overrideOptionId),
    uncertainDimensions,
  };
}

function buildVoteRationale(
  selectedOptionId: string,
  scores: AgentVoteScore[],
  estimates: PreferenceEstimate[],
  overrideOptionId?: string | null
): string {
  const option = ballotOptions.find((candidate) => candidate.id === selectedOptionId);
  if (!option) {
    return "No matching option was found for the current model state.";
  }
  if (overrideOptionId) {
    return `${option.title} is selected by user override. The model scores remain visible so the override can be audited against the inferred preferences.`;
  }

  const estimateByDimension = new Map(
    estimates.map((estimate) => [estimate.dimensionId, estimate])
  );
  const strongestMatches = preferenceDimensions
    .map((dimension) => {
      const estimate = estimateByDimension.get(dimension.id);
      const alignment = (estimate?.value ?? 0) * option.policyVector[dimension.id];
      return { dimension, alignment };
    })
    .filter((item) => item.alignment > 0.08)
    .sort((a, b) => b.alignment - a.alignment)
    .slice(0, 3)
    .map((item) => item.dimension.shortLabel.toLowerCase());

  const leader = scores[0];
  const runner = scores[1];
  const margin =
    leader && runner ? Math.round((leader.normalizedScore - runner.normalizedScore) * 10) / 10 : 0;
  const basis =
    strongestMatches.length > 0
      ? `It best matches ${strongestMatches.join(", ")}.`
      : "The model has too little evidence, so the current selection is provisional.";

  return `${option.title} leads the ballot model. ${basis} Normalized margin over the runner-up is ${margin} points.`;
}

export function normalizeSignals(signals: PreferenceSignal[]): PreferenceSignal[] {
  return signals
    .filter((signal) =>
      preferenceDimensions.some((dimension) => dimension.id === signal.dimensionId)
    )
    .map((signal) => ({
      ...signal,
      direction: signal.direction === -1 ? -1 : 1,
      strength: clamp(Number(signal.strength) || 0, 0, 1),
      confidence: clamp(Number(signal.confidence) || 0, 0, 1),
      evidence: String(signal.evidence || "Preference evidence extracted."),
      source: signal.source,
    }));
}

export function recomputePreferenceState(
  state: PreferenceDemoState
): PreferenceDemoState {
  const estimates = computePreferenceEstimates(state.signals);
  return {
    ...state,
    estimates,
    vote: computeAgentVote(estimates, state.overrideOptionId),
  };
}

export function getPreferenceDimension(id: PreferenceDimensionId) {
  return preferenceDimensions.find((dimension) => dimension.id === id);
}
