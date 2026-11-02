import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** The page's one content width, shared by the hero, the nav and every band. */
export const CONTAINER = "mx-auto w-full max-w-[90rem] px-4 sm:px-6 lg:px-10";

/** A section's tone: its band, body, rule and nav tick. Surfaces only, never a mark. */
export type Tone = 1 | 2 | 3 | 4;

export const TONES: Record<Tone, { band: string; body: string; rule: string; fill: string; text: string }> = {
  1: { band: "bg-mi-band-1", body: "bg-mi-body-1", rule: "border-mi-tone-1", fill: "bg-mi-tone-1", text: "text-mi-tone-1" },
  2: { band: "bg-mi-band-2", body: "bg-mi-body-2", rule: "border-mi-tone-2", fill: "bg-mi-tone-2", text: "text-mi-tone-2" },
  3: { band: "bg-mi-band-3", body: "bg-mi-body-3", rule: "border-mi-tone-3", fill: "bg-mi-tone-3", text: "text-mi-tone-3" },
  4: { band: "bg-mi-band-4", body: "bg-mi-body-4", rule: "border-mi-tone-4", fill: "bg-mi-tone-4", text: "text-mi-tone-4" },
};

/** A section's opening: a tinted band with its number, claim, and one small figure from its data. */
export function SectionBand({ tone, number, id, title, description, figure }: {
  tone: Tone;
  number: string;
  id: string;
  title: string;
  description: string;
  figure?: ReactNode;
}) {
  return (
    <header className={cn("border-t-[3px]", TONES[tone].band, TONES[tone].rule)}>
      <div className={cn(CONTAINER, "flex flex-wrap items-end gap-x-12 gap-y-8 py-8 sm:py-14")}>
        <div className="min-w-0 flex-[999_1_30rem] space-y-4">
          <div className="flex items-baseline gap-x-4 sm:gap-x-5">
            <span aria-hidden className="shrink-0 font-mi-mono text-5xl font-light leading-none text-mi-ink-2 sm:text-6xl lg:text-7xl">{number}</span>
            <h2 id={id} className="min-w-0 text-3xl font-semibold leading-tight tracking-[-0.03em] text-mi-ink sm:text-4xl lg:text-5xl">{title}</h2>
          </div>
          <p className="max-w-2xl text-base leading-relaxed text-mi-ink-2 sm:text-lg">{description}</p>
        </div>
        {/* Figures preview the section; on a phone the section itself follows at once. */}
        {figure && <div className="hidden min-w-0 flex-[0_1_36rem] sm:block">{figure}</div>}
      </div>
    </header>
  );
}

/** A numbered label over a part of a section: "02.1", a tone dash, and the part's question. */
export function Subhead({ tone, number, children }: { tone: Tone; number: string; children: ReactNode }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm font-medium text-mi-ink-2">
      <span aria-hidden className={cn("h-[3px] w-5", TONES[tone].fill)} />
      <span className="font-mi-mono font-normal">{number}</span>
      {children}
    </p>
  );
}
