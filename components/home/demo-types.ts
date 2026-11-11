import type { Vote } from "lucide-react";

export type DemoStatus = "live" | "in-progress" | "planned";

/**
 * How soon an idea could be a real-world option: already used in real
 * elections, one law away, needing real-world pilots, or still research.
 */
export type Readiness = 1 | 2 | 3 | 4;

export const readinessLabel: Record<Readiness, string> = {
  1: "In use today",
  2: "One law away",
  3: "Needs real-world pilots",
  4: "Still research",
};

export type Demo = {
  number: number;
  title: string;
  tagline: string;
  description: string;
  showcase: string[];
  href: string | null;
  status: DemoStatus;
  readiness: Readiness;
  /** Rank by how impressive the demo is, 1 first; breaks every tie when sorting. */
  impressiveness: number;
  Icon: typeof Vote;
};

/** A demo's plain data, safe to pass to a client component (no icon). */
export type ShowcaseDemo = Omit<Demo, "Icon">;

export function showcaseData(demo: Demo): ShowcaseDemo {
  const { number, title, tagline, description, showcase, href, status, readiness, impressiveness } = demo;
  return { number, title, tagline, description, showcase, href, status, readiness, impressiveness };
}

export const statusLabel: Record<DemoStatus, string> = {
  live: "Live",
  "in-progress": "In progress",
  planned: "Planned",
};
