import type { Vote } from "lucide-react";

export type DemoStatus = "live" | "in-progress" | "planned";

export type Demo = {
  number: number;
  title: string;
  tagline: string;
  description: string;
  showcase: string[];
  href: string | null;
  status: DemoStatus;
  Icon: typeof Vote;
};

/** A demo's plain data, safe to pass to a client component (no icon). */
export type ShowcaseDemo = Omit<Demo, "Icon">;

export function showcaseData(demo: Demo): ShowcaseDemo {
  const { number, title, tagline, description, showcase, href, status } = demo;
  return { number, title, tagline, description, showcase, href, status };
}

export const statusLabel: Record<DemoStatus, string> = {
  live: "Live",
  "in-progress": "In progress",
  planned: "Planned",
};
