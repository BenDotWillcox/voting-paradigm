"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { CandidateGlyph } from "@/components/methods/instrument/glyph";
import { MapCanvas } from "@/components/methods/instrument/map-canvas";
import { useReducedMotion } from "@/components/story/chart";
import { instrumentMono, instrumentSans } from "@/lib/methods/fonts";
import { METHOD_META } from "@/lib/methods/instrument";
import type { HomeCardAtlas } from "@/lib/methods/instrument-data";
import { cn } from "@/lib/utils";

import { useCanHover, useInView } from "./card-hooks";
import { statusLabel, type ShowcaseDemo } from "./demo-types";

const STEP_MS = 1700;
/** First step after the pointer arrives: start promptly, not after a hold. */
const START_MS = 350;

/**
 * Demo 1's home card, in the instrument's "drafting table" identity. The
 * atlas's hub layout, where D sits inside A, B and C, steps through the seven
 * methods' maps while the list beside it marks how much of the map D wins
 * under each. The voters never change; only the method does.
 *
 * The map rests on plurality and plays while hovered or focused; leaving
 * returns it to plurality. Touch screens play it while the card is on
 * screen. Reduced motion holds on plurality; every share stays in the list.
 */
export function MethodsCard({ demo, atlas }: { demo: ShowcaseDemo; atlas: HomeCardAtlas }) {
  const reducedMotion = useReducedMotion();
  const canHover = useCanHover();
  const visible = useInView<HTMLAnchorElement>();
  const [hovered, setHovered] = React.useState(false);
  const [step, setStep] = React.useState(0);
  const started = React.useRef(false);
  const playing = !reducedMotion && (canHover ? hovered : visible.inView);

  React.useEffect(() => {
    if (!playing) {
      started.current = false;
      setStep(0);
      return;
    }
    const hold = started.current ? STEP_MS : START_MS;
    const timer = window.setTimeout(() => {
      started.current = true;
      setStep((current) => (current + 1) % atlas.maps.length);
    }, hold);
    return () => window.clearTimeout(timer);
  }, [step, playing, atlas.maps.length]);

  const current = atlas.maps[step];
  const label = METHOD_META[current.method].label;

  const card = (
    <div
      className={cn(
        "methods-instrument h-full rounded-xl font-mi-sans",
        instrumentSans.variable,
        instrumentMono.variable
      )}
    >
      <div className="@container flex h-full flex-col rounded-xl border border-mi-rule bg-mi-surface p-6 text-mi-ink transition-shadow hover:shadow-md">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-mi-mono text-xs text-mi-muted">Demo {demo.number}</p>
            <h2 className="text-2xl leading-tight font-semibold tracking-[-0.02em]">{demo.title}</h2>
          </div>
          <span className="rounded-[3px] border border-mi-ink px-2 py-0.5 font-mi-mono text-xs">
            {statusLabel[demo.status]}
          </span>
        </div>
        <p className="mt-2 text-lg leading-snug text-mi-ink-2">{demo.tagline}</p>

        <figure className="mt-4 grid gap-4 @sm:grid-cols-[11rem_minmax(0,1fr)]">
          <div>
            <div className="relative aspect-square w-full max-w-[11rem] overflow-hidden rounded-[3px] border border-mi-ink">
              <MapCanvas
                cells={current.winners}
                size={atlas.size}
                ties={current.ties}
                label={`${label}: ${atlas.focus} wins ${share(current.focusShare)} of the map outright`}
                className="absolute inset-0"
              />
              {atlas.candidates.map((candidate) => (
                <span
                  key={candidate.id}
                  aria-hidden
                  className="absolute grid size-4 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-mi-surface shadow-[0_0_0_1px_var(--mi-ink)]"
                  style={{ left: `${candidate.x * 100}%`, top: `${candidate.y * 100}%` }}
                >
                  <CandidateGlyph id={candidate.id} size={10} />
                </span>
              ))}
            </div>
            <p className="mt-1.5 text-[0.7rem] leading-snug text-mi-muted">
              Each point is an electorate centered there. Lighter: tied for the lead.
            </p>
          </div>

          <figcaption>
            <p className="flex items-center gap-1.5 text-xs text-mi-muted">
              <CandidateGlyph id={atlas.focus} size={11} />
              {atlas.focus}&apos;s share of the map, outright
            </p>
            <ol className="mt-1.5 space-y-0.5">
              {atlas.maps.map((map, i) => (
                <li
                  key={map.method}
                  className={cn(
                    "flex items-baseline justify-between gap-3 border-l-2 pl-2 text-sm transition-colors",
                    i === step ? "border-mi-ink text-mi-ink" : "border-transparent text-mi-muted"
                  )}
                >
                  <span className="truncate">{METHOD_META[map.method].label}</span>
                  <span className="font-mi-mono text-xs tabular-nums">{share(map.focusShare)}</span>
                </li>
              ))}
            </ol>
          </figcaption>
        </figure>

        <p className="mt-4 text-sm leading-6 text-mi-ink-2">{demo.description}</p>
        <ul className="mt-4 flex flex-wrap gap-1.5">
          {demo.showcase.map((tag) => (
            <li key={tag} className="rounded-[3px] border border-mi-rule px-2 py-0.5 text-xs text-mi-ink-2">
              {tag}
            </li>
          ))}
        </ul>
        <div className="mt-auto flex items-center gap-1 pt-4 text-sm font-medium text-mi-ink">
          Open the instrument
          <ArrowRight className="h-4 w-4" />
        </div>
      </div>
    </div>
  );

  return demo.href ? (
    <Link
      ref={visible.ref}
      href={demo.href}
      className="block h-full"
      onPointerEnter={(event) => event.pointerType === "mouse" && setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
    >
      {card}
    </Link>
  ) : (
    card
  );
}

function share(value: number): string {
  const p = value * 100;
  return `${p >= 10 ? p.toFixed(0) : p.toFixed(1)}%`;
}
