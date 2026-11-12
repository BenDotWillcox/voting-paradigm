"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Minus, Plus, Scan } from "lucide-react";
import { cn } from "@/lib/utils";
import { AppLink as Link } from "./app-link";
import { personHandle, personName, profileHref, type Directory } from "./people";
import { PersonAvatar } from "./person-bits";

export type IncomingEdge = { person: string; category: string };
export type OutgoingEdge = { category: string; delegate: string; flagged?: boolean };
export type HubSelection = { side: "in" | "out"; index: number } | null;

type Props = {
  directory: Directory;
  /** The person at the centre. */
  owner: string;
  /** Categories other people have handed to the owner. */
  incoming: IncomingEdge[];
  /** Categories the owner has handed to other people. */
  outgoing: OutgoingEdge[];
  /** With these, nodes are buttons that select; without, they link to profiles. */
  selected?: HubSelection;
  onSelect?: (selection: HubSelection) => void;
  /** With this, the outgoing side ends in a node for adding a delegation. */
  onAdd?: () => void;
};

// The graph's own coordinates, in pixels at 100% zoom, with the hub at (0, 0).
const NODE_W = 250;
const NODE_H = 56;
const PITCH = 68; // one node and the gap under it
const ROWS = 10; // nodes in a column before the next column starts further out
const COLUMN_GAP = 70;
const HUB_W = 200;
const HUB_H = 168;
const HUB_GAP = 130;
const MARGIN = 48;
const CONTROLS = 52; // height of the frame's bottom strip, in screen pixels

const MIN_ZOOM = 0.05;
const MAX_ZOOM = 1.6;
// How much a node shows depends on how large it is on screen.
const CARD_FROM = 0.6; // category and name
const CHIP_FROM = 0.33; // avatar and name; below this, the avatar alone

type Slot = { x: number; y: number; inner: number };
type View = { x: number; y: number; k: number };

/** Where each node of one side sits: columns of ROWS, stepping away from the hub. */
function slots(count: number, side: "in" | "out"): Slot[] {
  return Array.from({ length: count }, (_, index) => {
    const column = Math.floor(index / ROWS);
    const inColumn = Math.min(ROWS, count - column * ROWS);
    const y = ((index % ROWS) - (inColumn - 1) / 2) * PITCH;
    const near = HUB_W / 2 + HUB_GAP + column * (NODE_W + COLUMN_GAP);
    return side === "out"
      ? { x: near, y, inner: near }
      : { x: -near - NODE_W, y, inner: -near };
  });
}

/** Where each of `count` lines meets the hub's side, spread around its middle. */
function ports(count: number): number[] {
  const spread = Math.min(12, (HUB_H - 48) / Math.max(count, 1));
  return Array.from({ length: count }, (_, index) => (index - (count - 1) / 2) * spread);
}

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

/**
 * A person as the hub of their delegations, on a canvas that can be moved
 * and zoomed. Read left to right: who hands them a category, the person,
 * who they hand categories to. It opens fitted to the whole graph; zoomed
 * in, a node shows its category and delegate, and further out it shrinks to
 * a name and then to a dot, so a graph of any size stays readable. On a
 * narrow screen the same edges are two lists.
 */
export function HubGraph({
  directory,
  owner,
  incoming,
  outgoing,
  selected = null,
  onSelect,
  onAdd,
}: Props) {
  const inSlots = useMemo(() => slots(incoming.length, "in"), [incoming.length]);
  const outSlots = useMemo(
    () => slots(outgoing.length + (onAdd ? 1 : 0), "out"),
    [outgoing.length, onAdd]
  );
  const inPorts = useMemo(() => ports(inSlots.length), [inSlots.length]);
  const outPorts = useMemo(() => ports(outSlots.length), [outSlots.length]);

  const bounds = useMemo(() => {
    const all = [...inSlots, ...outSlots];
    const left = Math.min(-HUB_W / 2, ...all.map((slot) => slot.x));
    const right = Math.max(HUB_W / 2, ...all.map((slot) => slot.x + NODE_W));
    const reach = Math.max(HUB_H / 2, ...all.map((slot) => Math.abs(slot.y) + NODE_H / 2));
    return { left: left - MARGIN, right: right + MARGIN, top: -reach - MARGIN, bottom: reach + MARGIN };
  }, [inSlots, outSlots]);

  const frame = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  // Until the reader moves or zooms, the graph keeps itself fitted.
  const touched = useRef(false);

  const fit = useCallback(
    (width: number, fullHeight: number): View => {
      // Keep clear of the strip along the bottom that holds the controls.
      const height = Math.max(fullHeight - CONTROLS, 1);
      const k = clamp(
        Math.min(width / (bounds.right - bounds.left), height / (bounds.bottom - bounds.top)),
        MIN_ZOOM,
        1
      );
      return {
        k,
        x: width / 2 - (k * (bounds.left + bounds.right)) / 2,
        y: height / 2 - (k * (bounds.top + bounds.bottom)) / 2,
      };
    },
    [bounds]
  );

  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    // Measure now as well as on change: an observer's first report can be
    // late, or never come while the page is not being painted.
    setSize({ width: element.clientWidth, height: element.clientHeight });
    const observer = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (size.width > 0 && !touched.current) setView(fit(size.width, size.height));
  }, [size, fit]);

  /** Zoom to `k`, keeping the canvas point under (px, py) where it is. */
  const zoomTo = useCallback((k: number, px: number, py: number) => {
    touched.current = true;
    setView((current) => {
      const next = clamp(k, MIN_ZOOM, MAX_ZOOM);
      const ratio = next / current.k;
      return { k: next, x: px - (px - current.x) * ratio, y: py - (py - current.y) * ratio };
    });
  }, []);

  // Ctrl or Cmd with the wheel zooms (a trackpad pinch arrives the same way).
  // A plain wheel is left alone, so the page still scrolls past the graph.
  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const box = element.getBoundingClientRect();
      setView((current) => {
        touched.current = true;
        const next = clamp(current.k * Math.exp(-event.deltaY * 0.01), MIN_ZOOM, MAX_ZOOM);
        const ratio = next / current.k;
        const px = event.clientX - box.left;
        const py = event.clientY - box.top;
        return { k: next, x: px - (px - current.x) * ratio, y: py - (py - current.y) * ratio };
      });
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, []);

  // Dragging moves the canvas. A press that travels is a drag, not a click.
  const drag = useRef<{ x: number; y: number; view: View; moved: boolean } | null>(null);
  const dragged = useRef(false);
  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    drag.current = { x: event.clientX, y: event.clientY, view, moved: false };
    dragged.current = false;
  };
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const start = drag.current;
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!start.moved && Math.hypot(dx, dy) < 4) return;
    if (!start.moved) {
      start.moved = true;
      dragged.current = true;
      touched.current = true;
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    setView({ k: start.view.k, x: start.view.x + dx, y: start.view.y + dy });
  };
  const onPointerUp = () => {
    drag.current = null;
  };
  /** Wrap a node's action so the click that ends a drag does nothing. */
  const unlessDragged = (action: () => void) => (event: React.MouseEvent) => {
    if (dragged.current) {
      event.preventDefault();
      dragged.current = false;
      return;
    }
    action();
  };

  const level = view.k >= CARD_FROM ? "card" : view.k >= CHIP_FROM ? "chip" : "dot";
  const stroke = 1.5 / view.k;
  const dimmed = (side: "in" | "out", index: number) =>
    selected !== null && !(selected.side === side && selected.index === index);

  // ---- nodes -------------------------------------------------------------

  const shell = (accent: "in" | "out", flagged: boolean, faded: boolean, active: boolean) =>
    cn(
      "flex h-14 w-full items-center text-left transition-[opacity,border-color,background-color] focus-visible:outline-2 focus-visible:outline-primary",
      level === "dot"
        ? cn("rounded-full", accent === "in" ? "justify-end" : "justify-start")
        : cn(
            "liquid-panel gap-2.5 px-2.5 hover:border-primary hover:bg-accent",
            accent === "in"
              ? "border-r-2 border-r-[var(--lq-blue)]"
              : "border-l-2 border-l-[var(--lq-violet)]",
            flagged && "border-l-amber-400"
          ),
      faded && "opacity-35",
      active && level !== "dot" && "liquid-glow"
    );

  const contents = (person: string, category: string, flagged: boolean, active: boolean) => {
    if (level === "dot") {
      return (
        <PersonAvatar
          directory={directory}
          id={person}
          size="lg"
          className={cn("h-14 w-14", active && "liquid-glow", flagged && "ring-2 ring-amber-400")}
        />
      );
    }
    if (level === "chip") {
      return (
        <>
          <PersonAvatar directory={directory} id={person} />
          <span className="min-w-0 flex-1 truncate text-[1.35rem] font-medium leading-none">
            {personName(directory, person)}
          </span>
        </>
      );
    }
    return (
      <>
        <PersonAvatar directory={directory} id={person} size="sm" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[0.8rem] font-medium leading-tight">{category}</span>
          <span className="block truncate text-xs text-muted-foreground">
            {personName(directory, person)}
          </span>
        </span>
        {flagged && (
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" aria-label="needs a look" />
        )}
      </>
    );
  };

  const node = (side: "in" | "out", index: number, list: boolean) => {
    const person = side === "in" ? incoming[index].person : outgoing[index].delegate;
    const category = side === "in" ? incoming[index].category : outgoing[index].category;
    const flagged = side === "out" && Boolean(outgoing[index].flagged);
    const active = selected?.side === side && selected.index === index;
    const label =
      side === "in"
        ? `${personName(directory, person)} ${personHandle(directory, person)} hands over ${category}`
        : `${category}, handed to ${personName(directory, person)} ${personHandle(directory, person)}`;
    const title = `${category} · ${personName(directory, person)}`;
    // In the list there is no zoom: always the full card.
    const classes = list
      ? cn(
          "liquid-panel flex h-14 w-full items-center gap-2.5 px-2.5 text-left hover:border-primary hover:bg-accent",
          side === "in"
            ? "border-r-2 border-r-[var(--lq-blue)]"
            : "border-l-2 border-l-[var(--lq-violet)]",
          flagged && "border-l-amber-400"
        )
      : shell(side, flagged, dimmed(side, index), active);
    const body = list ? (
      <>
        <PersonAvatar directory={directory} id={person} size="sm" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[0.8rem] font-medium leading-tight">{category}</span>
          <span className="block truncate text-xs text-muted-foreground">
            {personName(directory, person)}
          </span>
        </span>
      </>
    ) : (
      contents(person, category, flagged, active)
    );
    const pick = () => onSelect?.(active ? null : { side, index });
    return onSelect ? (
      <button
        type="button"
        aria-label={label}
        aria-pressed={active}
        title={title}
        className={classes}
        onClick={list ? pick : unlessDragged(pick)}
      >
        {body}
      </button>
    ) : (
      <Link
        href={profileHref(directory, person)}
        aria-label={label}
        title={title}
        className={classes}
        draggable={false}
        onClick={list ? undefined : unlessDragged(() => undefined)}
      >
        {body}
      </Link>
    );
  };

  const addNode = (list: boolean) =>
    onAdd && (
      <button
        type="button"
        title="Add a delegate"
        onClick={list ? onAdd : unlessDragged(onAdd)}
        className={cn(
          "flex h-14 items-center gap-2.5 text-primary transition-colors",
          !list && level === "dot"
            ? "w-14 justify-center rounded-full border border-dashed border-primary/60 hover:bg-primary/10"
            : "w-full rounded-xl border border-dashed border-primary/60 px-2.5 text-sm font-medium hover:bg-primary/10"
        )}
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-dashed border-current">
          <Plus className="h-4 w-4" aria-hidden="true" />
        </span>
        {(list || level !== "dot") && (
          <span className={cn(!list && level === "chip" && "text-[1.35rem] leading-none")}>
            Add a delegate
          </span>
        )}
      </button>
    );

  const viewerOwns = owner === directory.viewer;
  const control =
    "flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground";

  return (
    <>
      {/* Wide screens: the canvas */}
      <div
        ref={frame}
        className="liquid-panel liquid-dots relative hidden h-[34rem] cursor-grab touch-none select-none overflow-hidden active:cursor-grabbing lg:block"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div
          className="absolute left-0 top-0 origin-top-left will-change-transform"
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})` }}
        >
          <svg className="absolute left-0 top-0 overflow-visible" width="1" height="1" aria-hidden="true">
            {inSlots.map((slot, index) => {
              const d = `M ${slot.inner} ${slot.y} C ${slot.inner + HUB_GAP / 2} ${slot.y}, ${-HUB_W / 2 - HUB_GAP / 2} ${inPorts[index]}, ${-HUB_W / 2} ${inPorts[index]}`;
              return (
                <g key={`in-${index}`} opacity={dimmed("in", index) ? 0.15 : 1} fill="none">
                  <path d={d} stroke="var(--lq-blue)" strokeOpacity={level === "card" ? 0.35 : 0.6} strokeWidth={stroke} />
                  {level === "card" && (
                    <path d={d} className="liquid-flow" stroke="var(--lq-blue)" strokeWidth={stroke} />
                  )}
                </g>
              );
            })}
            {outSlots.map((slot, index) => {
              const d = `M ${HUB_W / 2} ${outPorts[index]} C ${HUB_W / 2 + HUB_GAP / 2} ${outPorts[index]}, ${slot.inner - HUB_GAP / 2} ${slot.y}, ${slot.inner} ${slot.y}`;
              const adding = index >= outgoing.length;
              const faded = adding ? selected !== null : dimmed("out", index);
              return (
                <g key={`out-${index}`} opacity={faded ? 0.15 : adding ? 0.5 : 1} fill="none">
                  <path
                    d={d}
                    stroke="var(--lq-violet)"
                    strokeOpacity={level === "card" ? 0.35 : 0.6}
                    strokeWidth={stroke}
                    strokeDasharray={adding ? `${3 / view.k} ${5 / view.k}` : undefined}
                  />
                  {level === "card" && !adding && (
                    <path d={d} className="liquid-flow" stroke="var(--lq-violet)" strokeWidth={stroke} />
                  )}
                </g>
              );
            })}
          </svg>

          {incoming.map((edge, index) => (
            <div
              key={`${edge.person}-${edge.category}`}
              className="absolute"
              style={{ left: inSlots[index].x, top: inSlots[index].y - NODE_H / 2, width: NODE_W }}
            >
              {node("in", index, false)}
            </div>
          ))}

          <div
            className="absolute"
            style={{ left: -HUB_W / 2, top: -HUB_H / 2, width: HUB_W, height: HUB_H }}
          >
            {level === "card" ? (
              <div className="liquid-panel liquid-glow flex h-full flex-col items-center justify-center gap-1.5 bg-background/80 px-2 text-center">
                <PersonAvatar directory={directory} id={owner} size="lg" />
                <span className="max-w-full truncate text-sm font-semibold">
                  {personName(directory, owner)}
                </span>
                <span className="max-w-full truncate font-mono text-[0.65rem] text-muted-foreground">
                  {personHandle(directory, owner)}
                </span>
                <span className="flex gap-3 font-mono text-[0.65rem]">
                  <span className="text-[var(--lq-blue)]">IN {incoming.length}</span>
                  <span className="text-[var(--lq-violet)]">OUT {outgoing.length}</span>
                </span>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center" title={personName(directory, owner)}>
                <PersonAvatar
                  directory={directory}
                  id={owner}
                  size="lg"
                  className="liquid-glow h-36 w-36 text-5xl"
                />
              </div>
            )}
          </div>

          {outgoing.map((edge, index) => (
            <div
              key={`${edge.category}-${edge.delegate}`}
              className="absolute"
              style={{ left: outSlots[index].x, top: outSlots[index].y - NODE_H / 2, width: NODE_W }}
            >
              {node("out", index, false)}
            </div>
          ))}
          {onAdd && (
            <div
              className="absolute"
              style={{
                left: outSlots[outgoing.length].x,
                top: outSlots[outgoing.length].y - NODE_H / 2,
                width: NODE_W,
              }}
            >
              {addNode(false)}
            </div>
          )}
        </div>

        {/* Fixed to the frame, not the canvas */}
        <p className="liquid-label pointer-events-none absolute left-4 top-3">
          <span className="text-[var(--lq-blue)]">●</span> Handed to {viewerOwns ? "you" : "them"} ·{" "}
          {incoming.length}
        </p>
        <p className="liquid-label pointer-events-none absolute right-4 top-3">
          <span className="text-[var(--lq-violet)]">●</span> {viewerOwns ? "You hand" : "They hand"}{" "}
          over · {outgoing.length}
        </p>
        <p className="liquid-label pointer-events-none absolute bottom-4 left-4 !normal-case !tracking-normal">
          Drag to move · Ctrl + scroll to zoom
        </p>
        <div
          className="absolute bottom-3 right-3 flex items-center gap-0.5 rounded-lg border bg-popover/90 p-1 shadow-lg"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            className={control}
            aria-label="Zoom out"
            onClick={() => zoomTo(view.k / 1.25, size.width / 2, size.height / 2)}
          >
            <Minus className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            className={cn(control, "w-14 font-mono tabular-nums")}
            aria-label={`Zoom ${Math.round(view.k * 100)} percent; set to 100 percent`}
            title="Set to 100%"
            onClick={() => zoomTo(1, size.width / 2, size.height / 2)}
          >
            {Math.round(view.k * 100)}%
          </button>
          <button
            type="button"
            className={control}
            aria-label="Zoom in"
            onClick={() => zoomTo(view.k * 1.25, size.width / 2, size.height / 2)}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
          </button>
          <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />
          <button
            type="button"
            className={cn(control, "gap-1.5")}
            title="Center the graph and fit all of it"
            onClick={() => {
              touched.current = false;
              setView(fit(size.width, size.height));
            }}
          >
            <Scan className="h-4 w-4" aria-hidden="true" />
            Center
          </button>
        </div>
      </div>

      {/* Narrow screens: the same edges as two lists */}
      <div className="space-y-6 lg:hidden">
        <div className="space-y-2">
          <p className="liquid-label">
            <span className="text-[var(--lq-violet)]">●</span> {viewerOwns ? "You hand" : "They hand"}{" "}
            over · {outgoing.length}
          </p>
          <ul className="space-y-2">
            {outgoing.map((edge, index) => (
              <li key={`${edge.category}-${edge.delegate}`}>{node("out", index, true)}</li>
            ))}
            {onAdd && <li>{addNode(true)}</li>}
          </ul>
        </div>
        <div className="space-y-2">
          <p className="liquid-label">
            <span className="text-[var(--lq-blue)]">●</span> Handed to {viewerOwns ? "you" : "them"} ·{" "}
            {incoming.length}
          </p>
          {incoming.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nobody yet.</p>
          ) : (
            <ul className="space-y-2">
              {incoming.map((edge, index) => (
                <li key={`${edge.person}-${edge.category}`}>{node("in", index, true)}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}
