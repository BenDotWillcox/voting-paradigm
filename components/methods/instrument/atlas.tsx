"use client";

import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { resolveAtlasAction, resolveAtlasPointAction } from "@/actions/methods-actions";
import {
  ATLAS_METHOD_VIEWS,
  ATLAS_REFERENCES,
  LAYOUT_COPY,
  cellAt,
  cellCenter,
  isReference,
  layoutKey,
  round,
  shares,
  viewCells,
  viewLabel,
  viewTieCells,
  viewTies,
  type AtlasLayout,
  type AtlasView,
} from "@/lib/methods/atlas";
import { cn } from "@/lib/utils";
import type { AtlasCandidate, AtlasResponse, ProfileResolveResponse } from "@/types/methods";

import { CandidateGlyph, CandidateMark } from "./glyph";
import { MapCanvas, disagreementShade } from "./map-canvas";

// Curated layouts, mapped at build time (scripts/build_methods_artifacts.py)
const ATLAS_DATA = "/data/methods/atlas.json";
// After the last arrow key, wait this long before recounting
const KEY_COMMIT_MS = 450;
// A press that moves less than this many pixels is a click, not a drag
const CLICK_SLOP_PX = 4;

export interface AtlasPoint {
  layout: string;
  cell: number;
  size: number;
  x: number;
  y: number;
}

type Status = { kind: "ready" } | { kind: "counting" } | { kind: "offline"; message: string };

/**
 * Yee's spatial diagrams for the seven methods. Each cell is the same cloud
 * of voters centered there, colored by its winner. Curated layouts load from
 * a static file; dragging a candidate recounts every cell in Python when it
 * is let go, and clicking a cell loads its electorate into the instrument.
 */
export function Atlas({
  onLoadPoint,
}: {
  onLoadPoint: (response: ProfileResolveResponse, point: AtlasPoint, view: AtlasView) => void;
}) {
  const [layouts, setLayouts] = useState<AtlasLayout[] | null>(null);
  const [layoutId, setLayoutId] = useState<string | null>(null);
  const [atlas, setAtlas] = useState<AtlasResponse | null>(null);
  const [positions, setPositions] = useState<AtlasCandidate[]>([]);
  const [status, setStatus] = useState<Status>({ kind: "ready" });
  const [view, setView] = useState<AtlasView>("plurality");
  const [cell, setCell] = useState<number | null>(null);
  const [loadingPoint, setLoadingPoint] = useState(false);
  const cache = useRef(new Map<string, AtlasResponse>());
  const latest = useRef(0);

  useEffect(() => {
    let cancelled = false;
    fetch(ATLAS_DATA)
      .then((response) => (response.ok ? response.json() : null))
      .then((data: { layouts?: { id: string; atlas: AtlasResponse }[] } | null) => {
        if (cancelled || !data?.layouts?.length) return;
        const loaded = data.layouts.map((layout) => ({
          id: layout.id,
          label: LAYOUT_COPY[layout.id]?.label ?? layout.id,
          caption: LAYOUT_COPY[layout.id]?.caption ?? "",
          atlas: layout.atlas,
        }));
        for (const layout of loaded) cache.current.set(layoutKey(layout.atlas.candidates), layout.atlas);
        setLayouts(loaded);
        show(loaded[0].atlas, loaded[0].id);
      })
      .catch(() => setStatus({ kind: "offline", message: "The atlas maps could not be loaded." }));
    return () => {
      cancelled = true;
    };
  }, []);

  function show(next: AtlasResponse, id: string | null) {
    latest.current++;
    setAtlas(next);
    setPositions(next.candidates);
    setLayoutId(id);
    setCell(null);
    setStatus({ kind: "ready" });
  }

  async function recount(candidates: AtlasCandidate[]) {
    if (!atlas) return;
    const request = candidates.map((c) => ({ id: c.id, x: round(c.x), y: round(c.y) }));
    const key = layoutKey(request);
    if (key === layoutKey(atlas.candidates)) return setPositions(atlas.candidates);
    const curated = layouts?.find((layout) => layoutKey(layout.atlas.candidates) === key);
    const cached = cache.current.get(key);
    if (cached) return show(cached, curated?.id ?? null);

    const id = ++latest.current;
    setStatus({ kind: "counting" });
    setCell(null);
    const result = await resolveAtlasAction({ candidates: request });
    if (id !== latest.current) return;
    if (result.isSuccess && result.data) {
      cache.current.set(key, result.data);
      show(result.data, null);
    } else {
      // Put the candidates back where the maps were counted
      setPositions(atlas.candidates);
      setStatus({ kind: "offline", message: result.message });
    }
  }

  async function loadPoint(target: number) {
    if (!atlas) return;
    setCell(target);
    setLoadingPoint(true);
    const result = await resolveAtlasPointAction({ candidates: atlas.candidates, cell: target });
    setLoadingPoint(false);
    if (result.isSuccess && result.data) {
      const [x, y] = cellCenter(target, atlas.size);
      const label = layouts?.find((l) => l.id === layoutId)?.label ?? "Your layout";
      onLoadPoint(result.data, { layout: label, cell: target, size: atlas.size, x, y }, view);
    } else {
      setStatus({
        kind: "offline",
        message: `${result.message} Loading a point needs the live counter.`,
      });
    }
  }

  if (!atlas) {
    return (
      <p className="text-sm text-mi-muted">
        {status.kind === "offline" ? status.message : "Loading the atlas…"}
      </p>
    );
  }

  const current = layouts?.find((layout) => layout.id === layoutId);
  const dragging = layoutKey(positions) !== layoutKey(atlas.candidates);

  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-sm leading-relaxed text-mi-ink-2">
        Each point on a map is an electorate: {atlas.cloud.offsets.length * atlas.cloud.voters_per_type}{" "}
        voters in {atlas.cloud.offsets.length} types, scattered around it. Their utility falls
        with distance, sincere-v1 turns it into ballots, and the cell takes the color of the
        winner. Drag a candidate and every map recounts when you let go; click a point to
        open its electorate in the playground.
      </p>

      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Atlas layouts">
        {layouts?.map((layout) => (
          <button
            key={layout.id}
            type="button"
            aria-pressed={layout.id === layoutId}
            aria-label={`${layout.label}, ${layout.atlas.candidates.length} candidates`}
            onClick={() => show(layout.atlas, layout.id)}
            className={cn(
              "rounded-[3px] border px-2.5 py-1 text-sm",
              layout.id === layoutId
                ? "border-mi-ink bg-mi-ink text-mi-surface"
                : "border-mi-rule text-mi-ink hover:border-mi-ink"
            )}
          >
            {layout.label}
            <span className="ml-1.5 font-mi-mono text-xs opacity-75">
              {layout.atlas.candidates.length}
            </span>
          </button>
        ))}
        {layoutId === null ? (
          <span className="rounded-[3px] border border-dashed border-mi-ink px-2.5 py-1 text-sm text-mi-ink">
            Your layout
          </span>
        ) : null}
      </div>
      {current?.caption ? (
        <p className="max-w-3xl text-sm leading-relaxed text-mi-ink">{current.caption}</p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div className="space-y-3">
          <MainMap
            atlas={atlas}
            view={view}
            positions={positions}
            cell={cell}
            stale={dragging || status.kind === "counting"}
            onMove={setPositions}
            onCommit={recount}
            onPick={loadPoint}
          />
          <Legend atlas={atlas} view={view} />
          <p className="font-mi-mono text-xs text-mi-muted" aria-live="polite">
            {status.kind === "counting"
              ? "Counting 4,096 electorates…"
              : status.kind === "offline"
                ? status.message
                : loadingPoint
                  ? "Loading that electorate…"
                  : "Drag a candidate, or click a point."}
          </p>
        </div>

        <div className="space-y-4">
          <ThumbGroup
            title="Methods"
            views={ATLAS_METHOD_VIEWS}
            atlas={atlas}
            selected={view}
            onSelect={setView}
          />
          <ThumbGroup
            title="References"
            views={ATLAS_REFERENCES.map((r) => r.id)}
            atlas={atlas}
            selected={view}
            onSelect={setView}
          />
        </div>
      </div>

      <p className="font-mi-mono text-xs leading-relaxed text-mi-muted">
        {atlas.size} × {atlas.size} cells · {atlas.cloud.offsets.length} voter types ×{" "}
        {atlas.cloud.voters_per_type} voters on a sunflower spiral, spread {atlas.cloud.spread} ·
        utility linear in distance · ballots {atlas.ballot_model} · every cell counted by the
        reference methods · lighter cells: a tiebreak (seed {atlas.tiebreak_seed}) decided.
        {layoutId ? " Curated layouts: public/data/methods/atlas.json." : " Counted live: POST /api/voting/atlas."}
      </p>
    </div>
  );
}

function MainMap({
  atlas,
  view,
  positions,
  cell,
  stale,
  onMove,
  onCommit,
  onPick,
}: {
  atlas: AtlasResponse;
  view: AtlasView;
  positions: AtlasCandidate[];
  cell: number | null;
  stale: boolean;
  onMove: (positions: AtlasCandidate[]) => void;
  onCommit: (positions: AtlasCandidate[]) => void;
  onPick: (cell: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: string } | null>(null);
  const press = useRef<{ x: number; y: number } | null>(null);
  const moved = useRef(positions);
  const keyTimer = useRef<number | null>(null);
  moved.current = positions;

  function pointAt(event: React.PointerEvent): [number, number] {
    const rect = box.current?.getBoundingClientRect();
    if (!rect) return [0, 0];
    return [
      Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
      Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
    ];
  }

  function moveTo(id: string, x: number, y: number) {
    onMove(moved.current.map((c) => (c.id === id ? { ...c, x: round(x), y: round(y) } : c)));
  }

  const center = cell === null ? null : cellCenter(cell, atlas.size);
  const label = viewLabel(view);

  return (
    <div
      ref={box}
      className="relative aspect-square w-full touch-none select-none overflow-hidden rounded-[3px] border border-mi-ink"
      onPointerDown={(event) => {
        press.current = { x: event.clientX, y: event.clientY };
      }}
      onPointerMove={(event) => {
        if (!drag.current) return;
        const [x, y] = pointAt(event);
        moveTo(drag.current.id, x, y);
      }}
      onPointerUp={(event) => {
        if (drag.current) {
          drag.current = null;
          onCommit(moved.current);
          return;
        }
        const start = press.current;
        press.current = null;
        if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) < CLICK_SLOP_PX) {
          const [x, y] = pointAt(event);
          onPick(cellAt(x, y, atlas.size));
        }
      }}
      onPointerCancel={() => {
        drag.current = null;
        press.current = null;
        onMove(moved.current);
      }}
    >
      <MapCanvas
        cells={viewCells(atlas, view)}
        size={atlas.size}
        ties={viewTieCells(atlas, view)}
        kind={view === "disagreement" ? "disagreement" : "winners"}
        label={`${label} map`}
        className={cn("absolute inset-0 transition-opacity", stale && "opacity-45")}
      />
      {center ? (
        <svg
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden
        >
          {atlas.cloud.offsets.map(([dx, dy], i) => (
            <circle
              key={i}
              cx={center[0] + dx}
              cy={center[1] + dy}
              r={0.006}
              fill="var(--mi-surface)"
              stroke="var(--mi-ink)"
              strokeWidth={0.003}
            />
          ))}
          <rect
            x={center[0] - 0.5 / atlas.size}
            y={center[1] - 0.5 / atlas.size}
            width={1 / atlas.size}
            height={1 / atlas.size}
            fill="none"
            stroke="var(--mi-ink)"
            strokeWidth={0.004}
          />
        </svg>
      ) : null}
      {positions.map((candidate) => (
        <button
          key={candidate.id}
          type="button"
          aria-label={`Candidate ${candidate.id} at ${candidate.x.toFixed(2)}, ${candidate.y.toFixed(2)}. Drag, or use the arrow keys, to move it.`}
          className="absolute grid size-8 -translate-x-1/2 -translate-y-1/2 cursor-grab place-items-center rounded-full focus-visible:outline-2 focus-visible:outline-mi-ink active:cursor-grabbing"
          style={{ left: `${candidate.x * 100}%`, top: `${candidate.y * 100}%` }}
          onPointerDown={(event) => {
            event.stopPropagation();
            press.current = null;
            drag.current = { id: candidate.id };
            box.current?.setPointerCapture(event.pointerId);
          }}
          onKeyDown={(event) => {
            const step = (event.shiftKey ? 4 : 1) / atlas.size;
            const delta: Record<string, [number, number]> = {
              ArrowLeft: [-step, 0],
              ArrowRight: [step, 0],
              ArrowUp: [0, -step],
              ArrowDown: [0, step],
            };
            const d = delta[event.key];
            if (!d) return;
            event.preventDefault();
            moveTo(candidate.id, candidate.x + d[0], candidate.y + d[1]);
            if (keyTimer.current) window.clearTimeout(keyTimer.current);
            keyTimer.current = window.setTimeout(() => onCommit(moved.current), KEY_COMMIT_MS);
          }}
        >
          {/* A surface disc keeps the glyph visible on its own color */}
          <span className="relative grid size-7 place-items-center rounded-full bg-mi-surface shadow-[0_0_0_1px_var(--mi-ink)]">
            <CandidateGlyph id={candidate.id} size={18} />
            <span className="absolute -right-2.5 -top-2.5 font-mi-mono text-[0.7rem] font-semibold text-mi-ink [text-shadow:0_0_3px_var(--mi-surface)]">
              {candidate.id}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}

function ThumbGroup({
  title,
  views,
  atlas,
  selected,
  onSelect,
}: {
  title: string;
  views: AtlasView[];
  atlas: AtlasResponse;
  selected: AtlasView;
  onSelect: (view: AtlasView) => void;
}) {
  return (
    <div>
      <p className="mb-1.5 font-mi-mono text-xs text-mi-muted">{title}</p>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {views.map((view) => (
          <button
            key={view}
            type="button"
            aria-pressed={view === selected}
            aria-label={`Show the ${viewLabel(view).toLowerCase()} map`}
            onClick={() => onSelect(view)}
            className={cn(
              "rounded-[3px] border p-1 text-left",
              view === selected ? "border-mi-ink" : "border-mi-rule hover:border-mi-ink"
            )}
          >
            <span className="relative block aspect-square w-full">
              <MapCanvas
                cells={viewCells(atlas, view)}
                size={atlas.size}
                ties={viewTieCells(atlas, view)}
                kind={view === "disagreement" ? "disagreement" : "winners"}
                className="absolute inset-0"
              />
            </span>
            <span className="mt-1 block truncate text-xs text-mi-ink">{viewLabel(view)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function Legend({ atlas, view }: { atlas: AtlasResponse; view: AtlasView }) {
  const cells = viewCells(atlas, view);
  const tied = viewTies(atlas, view);
  // Tied cells are counted apart: the seeded draw would credit them unevenly
  const share = shares([...cells].map((c, i) => (tied.has(i) ? "~" : c)).join(""));
  const ties = share.get("~") ?? 0;
  const reference = ATLAS_REFERENCES.find((r) => r.id === view);

  return (
    <div className="space-y-1.5 text-xs">
      <p className="font-medium text-mi-ink">
        {viewLabel(view)}
        {isReference(view) ? "" : " · share of the map each candidate wins outright"}
      </p>
      {view === "disagreement" ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {[...share.keys()].sort().map((n) => (
            <span key={n} className="inline-flex items-center gap-1.5 font-mi-mono text-mi-ink-2">
              <span
                aria-hidden
                className="size-3 rounded-[2px] border border-mi-rule"
                style={{ background: disagreementCss(Number(n)) }}
              />
              {n} {n === "1" ? "winner" : "winners"} {percent(share.get(n) ?? 0)}
            </span>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {atlas.candidates.map((c) => (
            <span key={c.id} className="font-mi-mono text-mi-ink-2">
              <CandidateMark id={c.id} size={11} /> {percent(share.get(c.id) ?? 0)}
            </span>
          ))}
          {share.has("-") ? (
            <span className="font-mi-mono text-mi-ink-2">none {percent(share.get("-") ?? 0)}</span>
          ) : null}
        </div>
      )}
      {reference ? (
        <p className="text-mi-muted">{reference.description}</p>
      ) : (
        <p className="text-mi-muted">
          {ties > 0
            ? `Tied for the lead in ${percent(ties)} of the cells, drawn lighter in the color the seeded tiebreak picked.`
            : "No cell needed a tiebreak."}
        </p>
      )}
    </div>
  );
}

/** Where an atlas point loaded into the instrument came from. */
export function AtlasPointBanner({
  point,
  voters,
  types,
  onBack,
  onClose,
}: {
  point: AtlasPoint;
  voters: number;
  types: number;
  onBack: () => void;
  onClose: () => void;
}) {
  const row = Math.floor(point.cell / point.size);
  const col = point.cell % point.size;
  return (
    <section aria-label="Atlas point" className="rounded-[4px] border border-mi-ink bg-mi-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mi-mono text-xs text-mi-muted">
            Atlas point · {point.layout} · row {row + 1}, column {col + 1}
          </p>
          <h2 className="mt-1 text-lg font-semibold text-mi-ink">
            The electorate at ({point.x.toFixed(3)}, {point.y.toFixed(3)})
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close the atlas point"
          title="Close the atlas point"
          className="grid size-7 shrink-0 place-items-center rounded-[3px] text-mi-ink-2 hover:bg-mi-wash hover:text-mi-ink"
        >
          <X className="size-4" />
        </button>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-mi-ink">
        The {voters} voters the atlas counted in this cell, as {types} voter types: each type&apos;s
        utilities fall linearly with its distance to the candidates. The seven counts below are the
        colors of this cell on each map.{" "}
        <button type="button" onClick={onBack} className="underline underline-offset-2 hover:text-mi-ink-2">
          Back to the atlas
        </button>
      </p>
    </section>
  );
}

function disagreementCss(count: number): string {
  return `color-mix(in srgb, var(--mi-ink) ${Math.round(disagreementShade(count) * 100)}%, var(--mi-surface))`;
}

function percent(value: number): string {
  const p = value * 100;
  return `${p >= 10 || p === 0 ? p.toFixed(0) : p.toFixed(1)}%`;
}
