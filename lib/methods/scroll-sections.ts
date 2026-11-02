import type { StepId } from "./sections";

/** The demo is one document. Old slide links now land within that document. */
export const DEMO_SECTIONS = [
  { id: "implementation", label: "Implementation" },
  { id: "why-it-matters", label: "Why it matters" },
  { id: "simulation", label: "Simulation evidence" },
  { id: "playground", label: "Playground" },
] as const;

export type DemoSection = (typeof DEMO_SECTIONS)[number]["id"];
export type DemoAnchor = DemoSection | "comparison" | "experiment" | "examples" | "fairness" | "ballots" | "gallery" | "efficiency" | "disagreement" | "atlas" | "one-election" | "correctness" | "voters" | "head-to-head";

export function anchorForStep(step: StepId | null): DemoAnchor {
  if (!step) return "implementation";
  if (step === "testing") return "simulation";
  if (step.startsWith("ballot-")) return "ballots";
  if (step.startsWith("paradox-")) return "experiment";
  return step as DemoAnchor;
}

export function isDemoAnchor(value: string): value is DemoAnchor {
  return ["implementation", "why-it-matters", "simulation", "playground", "comparison", "experiment", "examples", "fairness", "ballots", "gallery", "efficiency", "disagreement", "atlas", "one-election", "correctness", "voters", "head-to-head"].includes(value);
}
