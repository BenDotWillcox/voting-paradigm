"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { NumberTicker } from "@/components/story/number-ticker";
import {
  STAGE_CAPTION,
  useScrollyProgress,
  useScrollyStep,
  useScrollyStepProgress,
} from "@/components/story/scrolly";
import { SlideSwap } from "@/components/story/slide-swap";
import { DataTable } from "@/components/story/story-figure";
import type { EssayApportionment } from "@/lib/apportionment/essay-data";
import { ROLES, hash, mulberry32, type PieceCategory } from "@/lib/apportionment/persona";
import { observeThemeChanges, resolveCssColor } from "@/lib/canvas-color";
import { assignSeats, hemicycleLayout } from "@/lib/story/hemicycle";
import { cn } from "@/lib/utils";

import { formatCount, useConstituency } from "./constituency";
import {
  ClaimLadder,
  DEFAULT_LADDER_FIPS,
  HOUSE_SIZE,
  RaceBars,
  buildRace,
  dealLayout,
  ordinal,
  racePace,
  seatsAfter,
} from "./deal-figure";
import { COST_PER_MEMBER, EnvelopeChart, NAMED_SIZES, PeersChart, SizeStrip, sizeStripHeight } from "./bigger-figure";
import { FREEZE_YEAR, PER_SEAT_NOTE, PerSeatChart, perSeatLayout, perSeatSeries } from "./freeze-chart";
import { StateSwarm, averageAt, seatsFor, spreadAt } from "./state-swarm";
import { Hemicycle } from "./hemicycle";
import { PIECE_COLORS, VIEW, drawPerson } from "./person-figure";
import { usePersona } from "./persona";
import { useStateFocus } from "./state-focus";
import { TearText } from "./tear-text";

/**
 * Scrolly steps: 0 zooms from one person to 1,000, then to 10,000, and
 * gathers them into dots of 1,000; 1 zooms out to the whole constituency
 * and pours it into one seat of the House; from 2 on, that same chamber
 * carries the House through its history (see `HouseStep`).
 */
export const STAGE_STEPS = { crowd: 0, seat: 1, house: 2 } as const;

/** A primary-source excerpt shown in front of the chamber, like a cutaway. */
export interface StageClip {
  id: string;
  /** Where the words come from, e.g. "U.S. Constitution, Article I, Section 2". */
  label: string;
  /** Verbatim, from the fact register. */
  quote: string;
  /** Phrases (verbatim substrings) highlighted from `at` (0..1 through the step) on. */
  highlights?: ReadonlyArray<{ text: string; at: number }>;
  /** A stamp across the document from `at` on, e.g. "Never ratified". */
  stamp?: { text: string; at: number };
  /**
   * The operative passage shown first (verbatim segments of `quote` joined
   * by ellipses); the full quote is a click away.
   */
  excerpt?: string;
  sources: ReadonlyArray<{ title: string; url: string }>;
}

/** What the chamber shows at one step from STAGE_STEPS.house on. */
export interface HouseStep {
  /** One apportionment, by census year (1787 = the Constitution's). */
  year?: number;
  /** Census years scrubbed through as the reader scrolls the step. */
  years?: readonly number[];
  /** Display label, e.g. "1913" for the 1910 apportionment. */
  label?: string;
  caption?: string;
  /** Reprise the title's tear across the step. */
  tear?: boolean;
  /** A document brought in front of the chamber from `at` through the step. */
  clip?: { at: number; clip: StageClip };
  /** Keep the chamber locked (as at the end of its growth) without the tear. */
  lock?: boolean;
  /**
   * The people-per-seat chart takes over: the locked chamber shrinks into
   * the chart's legend for the frozen years (`morph`, the first chart step)
   * and the line is drawn from where the step before left it (`from`) to
   * `through`, or census by census through `years`.
   */
  chart?: { from?: number; through: number; morph?: boolean };
  /**
   * The seats dealt out again (Act III). guarantee: the chamber grows back
   * out of the chart's legend, empty, and every state gets its first seat;
   * ladder: one state's claims to more; race: seats 51 to 435; spread: people
   * per seat in every state (`spotlight` rings one).
   */
  deal?: { scene: "guarantee" | "ladder" | "race" | "spread"; spotlight?: string };
  /**
   * A bigger House (Act IV). swarm: the states' people per seat against the
   * average at `size`, gliding from size to size; envelope: every size from
   * 435 to 11,036; chamber: the House at `size` seats, with its cost; peers:
   * other democracies.
   */
  bigger?: { scene: "swarm" | "chamber"; size: number } | { scene: "envelope" | "peers" };
}

/** People per dot once individuals are too small to see. */
const UNIT = 1_000;
/** The crowd that gathers into dots: 10 dots of 1,000. */
const GATHERED = 10 * UNIT;
const PRESENT = 2020;

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const COLORS = Object.values(PIECE_COLORS);
const CATEGORIES = Object.keys(PIECE_COLORS) as PieceCategory[];
/** Mesh seeds shared by the neighbors; each is recolored per person. */
const NEIGHBOR_SEEDS = Array.from({ length: 12 }, (_, i) => 0x5100 + i * 7919);
const NEIGHBOR_PIECES: readonly PieceCategory[] = ["family", "belief", "concern"];
/** Unit dot radius as a share of the spacing between unit dots. */
const UNIT_DOT = 0.36;
/** Up close, a person's figure is this share of their spacing tall. */
const FIGURE_SHARE = 0.7;
/** Spacing (px) below which people are drawn as dots instead of figures. */
const FIGURE_MIN_SPACING = 20;

interface HouseStageProps {
  /** 2020 seats per state. */
  seats: Readonly<Record<string, number>>;
  order: readonly string[];
  nationalAverage: number;
  history: readonly EssayApportionment[];
  /** One entry per scrolly step from STAGE_STEPS.house on. */
  houseSteps: readonly HouseStep[];
  /**
   * Inside a stage-layout Scrolly: on wide screens the figure fills the
   * viewport and draws to the right of the caption column.
   */
  stage?: boolean;
}

/**
 * One figure from a single person to the House across two centuries.
 *
 * The crowd: people sit on a sunflower spiral in index order (which is also
 * radius order), so the first N people always form a disc, and the camera
 * scale is chosen so N people fill the frame. Up close each person is a
 * figure with their own colored pieces; by 10,000 they are specks, so each
 * 1,000 flow together into one dot and the zoom continues in dots. Then every
 * dot pours into one seat as the chamber rises around it.
 *
 * The House: that chamber, drawn by a <Hemicycle> placed exactly where the
 * canvas drew it, so the handover is invisible; it then changes with each
 * apportionment, and primary sources come forward in front of it as clips.
 */
export function HouseStageFigure({
  seats,
  order,
  nationalAverage,
  history,
  houseSteps,
  stage = false,
}: HouseStageProps) {
  const constituency = useConstituency(nationalAverage);
  const { focus, states } = useStateFocus();
  const { persona, personAt } = usePersona();
  const reducedMotion = useReducedMotion();
  const { step } = useScrollyStep();
  const stepProgress = useScrollyProgress();
  const p0 = useScrollyStepProgress(STAGE_STEPS.crowd);
  const p1 = useScrollyStepProgress(STAGE_STEPS.seat);

  const wrapperRef = React.useRef<HTMLElement | null>(null);
  const boxRef = React.useRef<HTMLDivElement | null>(null);
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);
  /** reserve: px kept clear on the left for a stage caption (0 otherwise). */
  const [size, setSize] = React.useState({ width: 0, height: 0, reserve: 0, fill: false });
  // Phones: the pinned figure can open full screen; a placeholder keeps its
  // place in the page so the steps don't move underneath.
  const [expanded, setExpanded] = React.useState<{ placeholder: number } | null>(null);
  React.useEffect(() => {
    if (!expanded) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setExpanded(null);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [expanded]);
  const [themeTick, setThemeTick] = React.useState(0);

  React.useEffect(() => {
    const node = wrapperRef.current;
    const box = boxRef.current;
    if (!node || !box) return;
    const wideQuery = window.matchMedia("(min-width: 1024px)");
    const measure = () => {
      const fill = stage && wideQuery.matches;
      if (fill) {
        const rect = box.getBoundingClientRect();
        const width = Math.round(rect.width);
        const reserve = Math.round(Math.min(STAGE_CAPTION.maxPx, width * STAGE_CAPTION.share) + 32);
        setSize({ width, height: Math.round(rect.height), reserve, fill });
        return;
      }
      // The box's own width: the expanded figure is padded.
      const width = Math.round(box.getBoundingClientRect().width);
      const height = expanded
        ? Math.round(Math.max(260, window.innerHeight - 250))
        : Math.round(Math.max(230, Math.min(width * 0.75, window.innerHeight * 0.4, 560)));
      setSize({ width, height, reserve: 0, fill });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    observer.observe(box);
    wideQuery.addEventListener("change", measure);
    return () => {
      observer.disconnect();
      wideQuery.removeEventListener("change", measure);
    };
  }, [stage, expanded]);
  React.useEffect(() => observeThemeChanges(() => setThemeTick((t) => t + 1)), []);

  const total = Math.max(GATHERED * 10, Math.round(constituency.population));
  const units = Math.round(total / UNIT);
  const scales = [1, 100, 1_000, 10_000, 100_000, total];
  const snap = reducedMotion;
  const ease = (t: number) => (snap ? (t < 0.5 ? 0 : 1) : t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

  // Where the scroll is: people in view, how far the gather has gone, and
  // how far the dots have poured into the seat.
  let people = 1;
  let gather = 0;
  let converge = 0;
  if (step <= STAGE_STEPS.crowd) {
    // A beat on the single person first (where the intro's person lands),
    // then out to 1,000, then on to 10,000 and the gather.
    const toThousand = segment(p0, 0.1, 0.42);
    const toTenThousand = segment(p0, 0.48, 0.66);
    people = toTenThousand > 0 ? 1_000 * 10 ** ease(toTenThousand) : 1_000 ** ease(toThousand);
    gather = snap ? (p0 < 0.8 ? 0 : 1) : segment(p0, 0.66, 0.88);
  } else {
    people = GATHERED * (total / GATHERED) ** ease(segment(p1, 0, 0.45));
    gather = 1;
    converge = snap ? (p1 < 0.7 ? 0 : 1) : segment(p1, 0.52, 0.96);
  }

  // The House across time, from STAGE_STEPS.house on.
  const houseIndex = step - STAGE_STEPS.house;
  const house = houseIndex >= 0 && houseSteps.length > 0;
  const view = house ? houseView(houseSteps[Math.min(houseIndex, houseSteps.length - 1)], stepProgress) : null;
  const current = (view && history.find((a) => a.year === view.year)) ?? history[history.length - 1];
  const previous = history[history.indexOf(current) - 1] ?? null;
  const shrank = previous !== null && previous.reapportioned && current.houseSize < previous.houseSize;
  const activeClip = view?.clip && stepProgress >= view.clip.at ? view.clip.clip : null;
  const chartEntry = house ? houseSteps[Math.min(houseIndex, houseSteps.length - 1)] : null;
  const chartView = chartEntry?.chart && !activeClip ? chartEntry.chart : null;
  const dealView = chartEntry?.deal ?? null;
  const biggerView = chartEntry?.bigger ?? null;
  const biggerSize = biggerView && "size" in biggerView ? biggerView.size : null;
  const biggerChamber = biggerView?.scene === "chamber" && biggerSize !== null;
  const swarmShown = dealView?.scene === "spread" || biggerView?.scene === "swarm";
  const ladderState = focus ?? states.find((s) => s.fips === DEFAULT_LADDER_FIPS) ?? null;
  const ladder = dealView?.scene === "ladder" && ladderState !== null;
  const houseLabel = ladder
    ? ladderState.name
    : view?.label ??
      (current.year === PRESENT && !chartView ? "Today" : current.year === 1787 ? "1789" : `${current.year} census`);
  const houseCaption = ladder
    ? "Its claims to each seat after the first"
    : shrank && previous
    ? `Smaller than the House before it: ${previous.houseSize} → ${current.houseSize} seats`
    : view?.caption ??
      (current.year === PRESENT && !chartView
        ? "The House after the 2020 census"
        : current.year === 1787
          ? "The First Congress, seated by the Constitution’s allocation"
          : current.reapportioned
            ? current.method
            : "No reapportionment after this census");
  const morphProgress = chartView ? (chartView.morph ? stepProgress : 1) : 0;
  const morph = chartView ? (snap ? (morphProgress < 0.2 ? 0 : 1) : easeInOutCubic(segment(morphProgress, 0, 0.4))) : 0;
  const chartReveal = chartView ? (snap ? morph : smoothstep(0.12, 0.4, morphProgress)) : 0;
  const drawTo = chartEntry && chartView ? chartReach(chartEntry, stepProgress, snap) : 0;
  const perSeat = React.useMemo(() => perSeatSeries(history), [history]);

  // Act III: how many seats are out, and whose. The first 50 sweep across
  // the chamber west to east; the race then deals the rest.
  const race = React.useMemo(() => buildRace(states), [states]);
  const firstSeats = order.length;
  const dealt = !dealView
    ? 0
    : dealView.scene === "guarantee"
      ? Math.round((snap ? (stepProgress < 0.6 ? 0 : 1) : segment(stepProgress, 0.35, 0.85)) * firstSeats)
      : dealView.scene === "ladder"
        ? firstSeats
        : dealView.scene === "race"
          ? firstSeats + racePace(stepProgress)
          : HOUSE_SIZE;
  const regrow = !dealView
    ? 0
    : dealView.scene === "guarantee" && !snap
      ? easeInOutCubic(segment(stepProgress, 0, 0.35))
      : 1;
  const dealing = dealView !== null && dealView.scene !== "spread";
  const biggerSeats = React.useMemo(
    () => (biggerChamber && biggerSize !== null ? seatsFor(biggerSize) : null),
    [biggerChamber, biggerSize]
  );
  const spread = biggerSize !== null ? spreadAt(biggerSize) : null;
  const filled = React.useMemo(
    () => (dealing ? seatsAfter(race, order, dealt) : undefined),
    [dealing, race, order, dealt]
  );
  const stateName = (fips: string) => states.find((s) => s.fips === fips)?.name ?? fips;
  const latestAward = dealt > firstSeats ? race[dealt - firstSeats - 1] : null;
  const latest =
    dealt === 0
      ? { label: "First", value: "One seat per state" }
      : latestAward
        ? { label: `Seat ${latestAward.seat}`, value: `${stateName(latestAward.fips)}, ${ordinal(latestAward.claim)}` }
        : { label: `Seat ${dealt}`, value: `${stateName(order[dealt - 1])}, 1st` };
  // The canvas hands the chamber to the <Hemicycle> in one frame (same
  // pixels), so that switch must not fade; later dimming does.
  const wasHouse = React.useRef(house);
  const handingOver = wasHouse.current !== house;
  React.useEffect(() => {
    wasHouse.current = house;
  }, [house]);

  // Growth since 1789: the historical chambers order seats by age (the
  // original 65, then everything added since, the newest in strong blue), a
  // running count sits in the chamber's center, and a lock closes once the
  // House stops growing.
  const founding = history.find((a) => a.year === 1787)?.houseSize ?? current.houseSize;
  const growing =
    house &&
    !activeClip &&
    !chartView &&
    !dealView &&
    !biggerView &&
    previous !== null &&
    current.year !== 1787 &&
    current.year !== PRESENT;
  const added = current.houseSize - founding;
  const change = previous ? current.houseSize - previous.houseSize : 0;
  const since = previous ? (previous.year === 1787 ? "1789" : `the ${previous.year} census`) : "";
  const lockShown = chartView !== null || (growing && (view?.tear !== undefined || view?.lock === true));
  const locked = chartView !== null || (lockShown && change === 0);
  // Once the chart has the stage, the chamber stays the frozen House.
  const frozenHouse = history.find((a) => a.year > FREEZE_YEAR) ?? current;
  const chamberEntry = chartView ? frozenHouse : current;
  const chamberPrevious = history[history.indexOf(chamberEntry) - 1] ?? null;
  const clips = React.useMemo(() => {
    const unique = new Map<string, StageClip>();
    for (const entry of houseSteps) if (entry.clip) unique.set(entry.clip.clip.id, entry.clip.clip);
    return [...unique.values()];
  }, [houseSteps]);

  const gathering = React.useMemo(() => buildGathering(), []);
  const pour = React.useMemo(() => buildPour(units), [units]);

  // Every chamber the House has had shares one frame, padded for the
  // largest seats (the 65-seat First Congress), as <Hemicycle> pads it.
  const reserveRadius = React.useMemo(
    () => Math.max(...history.map((a) => hemicycleLayout(a.houseSize).dotRadius)),
    [history]
  );
  const chamber = React.useMemo(() => {
    const layout = hemicycleLayout(Object.values(seats).reduce((a, b) => a + b, 0));
    const dots = assignSeats(layout, order, seats);
    const fips = focus?.fips ?? null;
    const seatIndex = persona?.district ? persona.district - 1 : 0;
    const found = fips ? dots.find((dot) => dot.key === `${fips}-${seatIndex}`) : undefined;
    const seat = found ?? dots[Math.floor(dots.length / 2)];
    return { layout, dots, seat, fips };
  }, [seats, order, focus, persona]);
  const frame = React.useMemo(
    () => chamberFrame(size, Math.max(reserveRadius, chamber.layout.dotRadius, 0.01)),
    [size, reserveRadius, chamber]
  );

  const draw = React.useCallback(() => {
    const canvas = canvasRef.current;
    const { width, height } = size;
    if (!canvas || width === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    // Once the House takes over, the chamber is the <Hemicycle>'s to draw.
    if (house) return;
    const color = (name: string) => resolveCssColor(canvas, name);
    const colors = COLORS.map(color);
    const ink = color("--story-ink");
    const focusColor = color("--story-seat-focus");
    const seatColor = color("--story-seat");
    const paper = color("--story-page");
    // The reader's person, drawn as the intro drew them; hidden while the
    // handoff still has them on the stage or in flight.
    const focal = persona
      ? {
          seed: persona.seed,
          readableCategories: persona.readable.map((piece) => piece.category),
          roleId: persona.role.id,
          colorFor: (category: keyof typeof PIECE_COLORS) => color(PIECE_COLORS[category]),
        }
      : null;
    const focalHidden = personAt === "stage" || personAt === "flight";
    // Where the focal person is drawn, for the handoff (none after the zoom).
    canvas.dataset.focalH = "0";

    // The crowd is drawn in the area right of any stage caption.
    const { viewRadius, cx, cy } = crowdGeometry(size);

    // The chamber, exactly where the <Hemicycle> will draw it.
    const hemiOuter = frame.outer;
    const seatR = Math.max(0.6, chamber.layout.dotRadius * hemiOuter);
    const seatX = frame.cx + chamber.seat.x * hemiOuter;
    const seatY = frame.baseline - chamber.seat.y * hemiOuter;

    if (gather === 0) {
      // Individuals: figures, then two-dot people, then single dots.
      const s = viewRadius / Math.sqrt(people);
      const spot = spiral(0);
      const settle = Math.min(1, Math.log10(people) / 2);
      const originX = cx - spot.x * s * (1 - settle);
      const originY = cy + spot.y * s * (1 - settle);
      const focalX = originX + spot.x * s;
      const focalY = originY - spot.y * s;
      ctx.save();
      // Dots are trimmed to a clean disc; whole figures fade in instead, so
      // none is ever sliced at the edge.
      if (s < FIGURE_MIN_SPACING) {
        ctx.beginPath();
        ctx.arc(cx, cy, viewRadius * 1.02 + s * 0.5, 0, Math.PI * 2);
        ctx.clip();
      }
      drawPeople(ctx, { people, s, originX, originY, width, height, colors, ink, paper, focal, focalHidden });
      ctx.restore();
      canvas.dataset.focalX = String(focalX);
      canvas.dataset.focalY = String(focalY);
      canvas.dataset.focalH = String(s * FIGURE_SHARE);
      // The reader's person stays ringed until they are too small to see;
      // during the handoff the ring is the spot they land in.
      const ringAlpha = smoothstep(2.6, 4.6, s);
      if (ringAlpha > 0) {
        ctx.globalAlpha = ringAlpha;
        ctx.strokeStyle = focusColor;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(focalX, focalY, Math.max(7, s * 0.55), 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      return;
    }

    if (gather < 1) {
      // 10,000 specks flow together, 1,000 to a dot.
      const s = viewRadius / Math.sqrt(GATHERED);
      const g = gathering;
      const paths = colors.map(() => new Path2D());
      const speck = Math.max(1, s * 0.62);
      for (let i = 0; i < GATHERED; i++) {
        const t = clamp01((gather - g.delay[i]) / 0.58);
        const e = easeInOutCubic(t);
        const dx = g.tx[i] - g.sx[i];
        const dy = g.ty[i] - g.sy[i];
        const bulge = g.swirl[i] * Math.sin(Math.PI * e);
        const x = g.sx[i] + dx * e - dy * bulge;
        const y = g.sy[i] + dy * e + dx * bulge;
        paths[g.color[i]].rect(cx + x * s - speck / 2, cy - y * s - speck / 2, speck, speck);
      }
      ctx.globalAlpha = 1 - smoothstep(0.86, 1, gather);
      paths.forEach((path, k) => {
        ctx.fillStyle = colors[k];
        ctx.fill(path);
      });
      const unitAlpha = smoothstep(0.78, 1, gather);
      if (unitAlpha > 0) {
        ctx.globalAlpha = unitAlpha;
        drawUnits(ctx, { count: GATHERED / UNIT, spacing: viewRadius / Math.sqrt(GATHERED / UNIT), cx, cy, fill: ink });
      }
      ctx.globalAlpha = 1;
      return;
    }

    // Dots of 1,000: zoom out to the whole constituency...
    const inView = people / UNIT;
    const spacing = viewRadius / Math.sqrt(inView);
    if (converge === 0) {
      drawUnits(ctx, { count: Math.min(units, Math.ceil(inView)), spacing, cx, cy, fill: ink });
      return;
    }

    // ...then pour every dot into one seat, as the chamber rises around it.
    const chamberAlpha = smoothstep(0.45, 0.9, converge);
    if (chamberAlpha > 0) {
      const neutral = new Path2D();
      const delegation = new Path2D();
      for (const dot of chamber.dots) {
        if (dot === chamber.seat) continue;
        const x = frame.cx + dot.x * hemiOuter;
        const y = frame.baseline - dot.y * hemiOuter;
        const target = dot.fips === chamber.fips ? delegation : neutral;
        target.moveTo(x + seatR, y);
        target.arc(x, y, seatR, 0, Math.PI * 2);
      }
      ctx.globalAlpha = chamberAlpha;
      ctx.fillStyle = seatColor;
      ctx.fill(neutral);
      ctx.fillStyle = focusColor;
      ctx.fill(delegation);
      ctx.globalAlpha = 1;
    }

    const radius = Math.max(0.8, spacing * UNIT_DOT);
    const moving = new Path2D();
    let landed = 0;
    for (let k = 0; k < units; k++) {
      const p = spiral(k);
      const fromX = cx + p.x * spacing;
      const fromY = cy - p.y * spacing;
      const t = clamp01((converge - pour.delay[k]) / 0.42);
      if (t >= 1) {
        landed++;
        continue;
      }
      const e = easeInOutCubic(t);
      const dx = seatX - fromX;
      const dy = seatY - fromY;
      const bulge = pour.swirl[k] * Math.sin(Math.PI * e);
      const x = fromX + dx * e - dy * bulge;
      const y = fromY + dy * e + dx * bulge;
      const r = radius + (seatR * 0.7 - radius) * e;
      moving.moveTo(x + r, y);
      moving.arc(x, y, r, 0, Math.PI * 2);
    }
    ctx.fillStyle = ink;
    ctx.fill(moving);

    // The seat fills as the dots arrive.
    const filled = landed / units;
    if (filled > 0) {
      ctx.globalAlpha = Math.min(1, 0.25 + filled);
      ctx.fillStyle = focusColor;
      ctx.beginPath();
      ctx.arc(seatX, seatY, seatR * (1 + 0.6 * (1 - filled)), 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = smoothstep(0.85, 1, converge);
      ctx.strokeStyle = ink;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(seatX, seatY, seatR + 4, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }, [size, people, gather, converge, chamber, frame, house, units, persona, personAt, gathering, pour]);

  React.useEffect(() => {
    draw();
  }, [draw, themeTick]);

  const note = (
    <>
      Each figure is one person; colors stand for the many dimensions of a life (illustrative).
      From 10,000 people on, each dot is 1,000 people. Population: {constituency.source}.
    </>
  );
  const seated = converge > 0.55;
  const count = displayCount(people, scales);
  const crowdLabel = seated ? "One seat in the House" : `${formatCount(count)} ${count === 1 ? "person" : "people"}`;
  const visualArea = { left: size.reserve, width: size.width - size.reserve };
  const stripCompact = visualArea.width < 560;
  const stripHeight = biggerView?.scene === "swarm" ? sizeStripHeight(stripCompact) : 0;
  // What one mark stands for, on every scene: the dots change meaning from
  // a person to 1,000 people to a seat to a state, so the label says so.
  const unit = activeClip
    ? null
    : !house
      ? gather === 0
        ? "One figure or dot = one person"
        : seated
          ? "One dot = one House seat"
          : null
      : chartView
        ? "One point = one census"
        : dealView
          ? dealView.scene === "spread"
            ? "One dot = one state"
            : dealView.scene === "ladder"
              ? "Chamber dots: seats · chart dots: claims"
              : dealView.scene === "race"
                ? "Dots: seats · bars: each state’s next claim"
                : "One dot = one seat · ring = not yet dealt"
          : biggerView
            ? biggerView.scene === "swarm"
              ? "One dot = one state"
              : biggerView.scene === "chamber"
                ? "One dot = one House seat"
                : biggerView.scene === "peers"
                  ? "One bar = one country"
                  : "Lines: highest and lowest state average"
            : "One dot = one House seat";
  const chartLayout = perSeatLayout({ ...visualArea, height: size.height });
  const deal = dealLayout({ ...visualArea, height: size.height });
  const iconBox = { left: chartLayout.icon.left, top: chartLayout.icon.top, width: chartLayout.icon.width };
  const chamberBox = chartView ? mixBox(frame, iconBox, morph) : dealView ? mixBox(iconBox, deal.chamber, regrow) : null;
  const chamberMorph =
    chamberBox && frame.width > 0
      ? { x: chamberBox.left - frame.left, y: chamberBox.top - frame.top, scale: chamberBox.width / frame.width }
      : { x: 0, y: 0, scale: 1 };
  // The lock lands on the icon at a size that still reads.
  const lockWidth = Math.max(44, frame.outer * 0.3);
  const lockCenter = { x: frame.cx, y: frame.baseline - frame.outer * 0.66 };
  const iconLock = {
    x: chartLayout.icon.left + chartLayout.icon.width / 2,
    y: chartLayout.icon.top + chartLayout.icon.width * 0.3,
    width: chartLayout.compact ? 18 : 26,
  };
  // In the chart the lock sits on the icon; after it, it rides the chamber out, fading.
  const lockMorph = chartView
    ? {
        x: (iconLock.x - lockCenter.x) * morph,
        y: (iconLock.y - lockCenter.y) * morph,
        scale: 1 + (iconLock.width / lockWidth - 1) * morph,
      }
    : {
        x: frame.left + chamberMorph.x + (lockCenter.x - frame.left) * chamberMorph.scale - lockCenter.x,
        y: frame.top + chamberMorph.y + (lockCenter.y - frame.top) * chamberMorph.scale - lockCenter.y,
        scale: iconLock.width / lockWidth,
      };

  // The key "● = 1,000 people" is born on one of the ten dots: "1,000" shows
  // on the top-right dot once the specks have gathered, then lifts off and
  // flies to the figure's top-right corner, where it becomes the key.
  const unitKey = React.useMemo(() => {
    let best = 0;
    for (let k = 1; k < GATHERED / UNIT; k++) {
      const p = spiral(k);
      const q = spiral(best);
      if (p.x + p.y > q.x + q.y) best = k;
    }
    return spiral(best);
  }, []);
  const keyNumberRef = React.useRef<HTMLSpanElement | null>(null);
  const keySuffixRef = React.useRef<HTMLSpanElement | null>(null);
  const [keyWidths, setKeyWidths] = React.useState({ number: 36, suffix: 48 });
  React.useEffect(() => {
    const measure = () =>
      setKeyWidths({
        number: keyNumberRef.current?.offsetWidth ?? 36,
        suffix: keySuffixRef.current?.offsetWidth ?? 48,
      });
    measure();
    void document.fonts?.ready.then(measure);
  }, [size.width]);
  const geometry = crowdGeometry(size);
  const unitSpacing = geometry.viewRadius / Math.sqrt(GATHERED / UNIT);
  const unitRadius = unitSpacing * UNIT_DOT;
  const keyOnDot = unitRadius >= 22; // else it sits just above the dot
  const keyDotX = geometry.cx + unitKey.x * unitSpacing;
  const keyDotY = HEADER_HEIGHT + geometry.cy - unitKey.y * unitSpacing - (keyOnDot ? 0 : unitRadius + 10);
  const keyShown = house ? 0 : step > STAGE_STEPS.crowd ? 1 : smoothstep(0.86, 0.9, p0);
  const keyFlight =
    step > STAGE_STEPS.crowd ? 1 : snap ? (p0 < 0.95 ? 0 : 1) : easeInOutCubic(segment(p0, 0.91, 0.985));
  const keySettled = step > STAGE_STEPS.crowd ? 1 : smoothstep(0.96, 0.99, p0);
  const keyGone = house ? 1 : smoothstep(0.5, 0.6, converge);
  const keyX =
    keyDotX + (size.width - keyWidths.suffix - keyWidths.number / 2 - keyDotX) * keyFlight;
  const keyY = keyDotY + (16 - keyDotY) * keyFlight - Math.sin(Math.PI * keyFlight) * 40;


  // The figure's caption: what it shows and where the numbers come from, and
  // its data as a table.
  let captionText: React.ReactNode = note;
  let captionTable: React.ReactNode = null;
  if (house && biggerView) {
    captionText =
      biggerView.scene === "chamber"
        ? "Cost at today’s rates, not a forecast: salary ($174,000) plus the average Members’ Representational Allowance ($1,928,107; Congressional Research Service, 2026) for each seat; excludes benefits, office space and buildings."
        : biggerView.scene === "peers"
          ? "Pew Research Center, 2018: each country’s population divided by the seats in its lower (or only) chamber."
          : "Average people per seat by state: 2020 apportionment population divided by seats, by the method of equal proportions at each House size (U.S. Census Bureau data). State averages, not actual districts.";
    captionTable = (
      <DataTable
        caption="Both gaps at each proposed House size, 2020 census"
        columns={[
          { key: "size", label: "Seats", numeric: true },
          { key: "rule", label: "Rule" },
          { key: "average", label: "Average per seat", numeric: true },
          { key: "ratio", label: "Highest ÷ lowest", numeric: true },
          { key: "typical", label: "Typical gap", numeric: true },
        ]}
        rows={NAMED_SIZES.map(({ size: seats, label }) => {
          const row = spreadAt(seats);
          return {
            size: seats,
            rule: label,
            average: Math.round(averageAt(seats)),
            ratio: `${row.ratio.toFixed(2)}×`,
            typical: `${(row.typical * 100).toFixed(1)}%`,
          };
        })}
      />
    );
  } else if (house && dealView) {
    captionText = dealing
      ? "Seats dealt by the method of equal proportions from the 2020 apportionment populations (U.S. Census Bureau); the result matches the published apportionment."
      : "Average people per seat by state: the Census Bureau’s 2020 average apportionment population per representative. State averages, not actual districts.";
    captionTable = (
      <DataTable
        caption="Seats and average people per seat by state, 2020 census"
        columns={[
          { key: "state", label: "State" },
          { key: "seats", label: "Seats", numeric: true },
          { key: "perSeat", label: "Average per seat", numeric: true },
        ]}
        rows={[...states]
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((s) => ({ state: s.name, seats: s.seats, perSeat: s.averagePerSeat }))}
      />
    );
  } else if (house) {
    captionText = chartView ? PER_SEAT_NOTE : "Source: House Historian apportionment table; U.S. Census Bureau population counts";
    captionTable = (
      <DataTable
        caption="House seats, U.S. population and people per seat by census"
        columns={[
          { key: "year", label: "Apportionment" },
          { key: "seats", label: "Seats", numeric: true },
          { key: "population", label: "U.S. population", numeric: true },
          { key: "perSeat", label: "People per seat", numeric: true },
        ]}
        rows={history.map((a) => ({
          year: a.year === 1787 ? "1787 (Constitution)" : `${a.year} census`,
          seats: a.houseSize,
          population: a.residentPopulation ?? "—",
          perSeat: perSeat.find((p) => p.year === a.year)?.perSeat ?? "—",
        }))}
      />
    );
  }

  return (
    <div
      className={cn("relative w-full", size.fill && "h-full")}
      style={expanded ? { height: expanded.placeholder } : undefined}
    >
    <figure
      ref={wrapperRef}
      className={cn(
        "relative w-full",
        size.fill && "flex h-full flex-col",
        expanded && "fixed inset-0 z-50 overflow-y-auto bg-story-page px-4 pt-4 pb-6"
      )}
    >
      {/* One header slot, fixed in height so the chamber never moves. Its
          text changes the way captions do: old up and out, new up into
          place; the House's numbers stay put and count. */}
      <div className="relative mb-2 h-24 overflow-hidden font-sans">
        <p className="sr-only" aria-live="polite">
          {house ? `${houseLabel}. ${houseCaption}.` : crowdLabel}
        </p>
        <SlideSwap
          swapKey={house ? `house:${houseLabel}:${houseCaption}` : "crowd"}
          className="absolute inset-y-0 left-0 right-40 sm:right-56"
        >
          {house ? (
            <div aria-hidden="true">
              <p className="text-3xl font-semibold tabular-nums tracking-tight text-story-ink">{houseLabel}</p>
              <p className={cn("mt-1 text-sm", shrank ? "text-[var(--gap-more-3)]" : "text-story-ink-2")}>{houseCaption}</p>
            </div>
          ) : (
            <p aria-hidden="true" className="text-2xl font-semibold tabular-nums tracking-tight text-story-ink">
              {crowdLabel}
            </p>
          )}
        </SlideSwap>
        <SlideSwap
          swapKey={
            house
              ? dealing
                ? "deal"
                : biggerView
                  ? `bigger-${biggerView.scene === "swarm" || biggerView.scene === "chamber" ? biggerView.scene : "none"}`
                  : "house"
              : seated
                ? "seated"
                : "none"
          }
          className="absolute top-0 right-0 text-right"
        >
          {house && dealing ? (
            <dl>
              <dt className="text-xs text-story-muted">Seats assigned</dt>
              <dd className="text-2xl leading-tight font-semibold text-story-ink">
                <NumberTicker value={dealt} duration={250} />
                <span className="text-sm font-normal text-story-muted"> of {HOUSE_SIZE}</span>
              </dd>
              <dt className="mt-1 text-xs text-story-muted">{latest.label}</dt>
              <dd className="text-base leading-tight font-semibold text-story-ink">{latest.value}</dd>
            </dl>
          ) : house && biggerView ? (
            biggerView.scene === "swarm" && spread && biggerSize !== null ? (
              <dl>
                <dt className="text-xs text-story-muted">Average people per seat</dt>
                <dd className="text-2xl leading-tight font-semibold text-story-ink">
                  <NumberTicker value={Math.round(averageAt(biggerSize))} />
                </dd>
                <dt className="mt-1 text-xs text-story-muted">Highest ÷ lowest state average</dt>
                <dd className="text-base leading-tight font-semibold text-story-ink">
                  <NumberTicker value={spread.ratio} decimals={2} suffix="×" />
                </dd>
              </dl>
            ) : biggerView.scene === "chamber" && biggerSize !== null ? (
              <dl>
                <dt className="text-xs text-story-muted">Seats in the House</dt>
                <dd className="text-2xl leading-tight font-semibold text-story-ink">
                  <NumberTicker value={biggerSize} />
                </dd>
                <dt className="mt-1 text-xs text-story-muted">Pay and allowances a year, at today’s rates</dt>
                <dd className="text-base leading-tight font-semibold text-story-ink">
                  {dollars(biggerSize * COST_PER_MEMBER)}
                  {biggerSize > HOUSE_SIZE ? (
                    <span className="font-normal text-story-muted"> (+{dollars((biggerSize - HOUSE_SIZE) * COST_PER_MEMBER)})</span>
                  ) : null}
                </dd>
              </dl>
            ) : null
          ) : house ? (
            <dl>
              <dt className="text-xs text-story-muted">Seats in the House</dt>
              <dd className="text-2xl leading-tight font-semibold text-story-ink">
                <NumberTicker value={current.houseSize} />
              </dd>
              <dt className="mt-1 text-xs text-story-muted">
                {current.residentPopulation ? `U.S. population, ${current.year} census` : "U.S. population"}
              </dt>
              <dd className="text-base leading-tight font-semibold text-story-ink">
                {current.residentPopulation ? <NumberTicker value={current.residentPopulation} /> : "No census yet"}
              </dd>
            </dl>
          ) : seated ? (
            <p className="pt-1.5 text-sm text-story-muted">
              {formatCount(constituency.population)}{" "}
              {constituency.kind === "district" ? "people" : "people per seat, on average"}
            </p>
          ) : null}
        </SlideSwap>
      </div>

      {/* The key, anchored on its number: "1,000" on a dot, then in flight,
          then "● = 1,000 people" in the corner. */}
      {size.width > 0 ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-0 left-0 z-10 font-sans text-sm leading-5 font-semibold whitespace-nowrap tabular-nums"
          style={{
            transform: `translate(${keyX.toFixed(1)}px, ${(keyY - 8 * keyGone).toFixed(1)}px) translate(-50%, -50%)`,
            opacity: keyShown * (1 - keyGone),
            color: keyOnDot
              ? // Paper on the dark dot, ink as soon as it lifts off.
                `color-mix(in srgb, var(--story-page) ${Math.round((1 - Math.min(1, keyFlight * 5)) * 100)}%, var(--story-ink-2))`
              : "var(--story-ink-2)",
          }}
        >
          <span
            className="absolute top-0 right-full flex items-center gap-1.5 pr-1.5 font-normal"
            style={{ opacity: keySettled }}
          >
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-story-ink" />=
          </span>
          <span ref={keyNumberRef}>{formatCount(UNIT)}</span>
          <span ref={keySuffixRef} className="absolute top-0 left-full pl-1 font-normal" style={{ opacity: keySettled }}>
            people
          </span>
        </div>
      ) : null}

      <div
        ref={boxRef}
        className={cn("relative", size.fill && "min-h-0 flex-1")}
        style={size.fill ? undefined : { height: size.height || 300 }}
      >
        <canvas
          ref={canvasRef}
          data-person-target=""
          role="img"
          aria-hidden={house}
          aria-label={`A crowd growing from one person to ${formatCount(total)} people, drawn from 10,000 on as dots of 1,000, then pouring into one seat of the 435-seat House.`}
          className="absolute inset-0 block h-full w-full"
        />

        {/* The chamber, where the canvas drew it; it recedes behind a clip. */}
        {frame.width > 0 ? (
          <div
            className="absolute"
            style={{
              left: frame.left,
              top: frame.top,
              width: frame.width,
              opacity: !house
                ? 0
                : biggerView
                  ? biggerChamber
                    ? activeClip
                      ? 0.14
                      : 1
                    : 0
                : dealView
                  ? dealing
                    ? 0.85 + 0.15 * regrow
                    : 0
                  : activeClip
                    ? 0.14
                    : chartView
                      ? 0.55 + 0.3 * morph
                      : locked
                        ? 0.55
                        : 1,
              transform: chamberBox
                ? `translate(${chamberMorph.x.toFixed(1)}px, ${chamberMorph.y.toFixed(1)}px) scale(${chamberMorph.scale.toFixed(4)})`
                : activeClip
                  ? "scale(0.96)"
                  : "none",
              transformOrigin: chamberBox ? "0 0" : undefined,
              filter: activeClip && !dealView ? "blur(1px)" : "none",
              pointerEvents: house && !activeClip && !chamberBox ? "auto" : "none",
              // Scroll drives the shrinking and regrowing, so they must not lag.
              transition:
                reducedMotion || handingOver
                  ? "none"
                  : chamberBox
                    ? "opacity 500ms ease, filter 600ms ease"
                    : "opacity 500ms ease, transform 600ms ease, filter 600ms ease",
            }}
          >
            <Hemicycle
              seats={biggerSeats ?? chamberEntry.stateSeats}
              order={order}
              highlightFocus={biggerSeats !== null || chamberEntry.year === PRESENT}
              byAge={
                biggerSeats !== null || chamberEntry.year === PRESENT
                  ? undefined
                  : {
                      original: founding,
                      previous: chamberEntry.year === 1787 ? null : chamberPrevious?.houseSize ?? null,
                    }
              }
              filled={filled}
              ariaLabel={
                dealing
                  ? `The House being dealt: ${dealt} of ${HOUSE_SIZE} seats assigned.`
                  : biggerSeats && biggerSize !== null
                    ? `The House with ${biggerSize.toLocaleString("en-US")} seats.`
                    : `The House, ${houseLabel}: ${chamberEntry.houseSize} seats.`
              }
              reserveRadius={reserveRadius}
            />
          </div>
        ) : null}

        {/* The running count: in the chamber's empty center, or just under
            the chamber when it is too small to hold it (phones). */}
        {frame.width > 0 ? (
          frame.outer >= 240 ? (
            <div
              aria-live="polite"
              className="pointer-events-none absolute text-center font-sans transition-opacity duration-500"
              style={{
                left: frame.cx,
                top: frame.baseline,
                width: frame.outer * 0.64,
                transform: "translate(-50%, -100%)",
                opacity: growing ? 1 : 0,
              }}
            >
              <p className="flex items-center justify-center gap-1.5 text-xs tracking-wide text-story-muted uppercase">
                <Swatch tone="added" />
                Seats added since 1789
              </p>
              <p
                className="leading-none font-semibold tabular-nums text-story-ink"
                style={{ fontSize: Math.min(44, frame.outer * 0.12) }}
              >
                <NumberTicker value={added} prefix="+" />
              </p>
              <p
                className="mt-1 flex items-center justify-center gap-1.5 text-sm tabular-nums"
                style={{ color: changeColor(change) }}
              >
                {change > 0 ? <Swatch tone="focus" /> : null}
                {changeText(change, since)}
              </p>
              {/* Seats alone suggest representation kept pace; it didn't. */}
              {current.residentPerSeat ? (
                <p className="mt-1 text-xs text-story-muted tabular-nums">
                  One seat per <NumberTicker value={Math.round(current.residentPerSeat)} /> people
                </p>
              ) : null}
            </div>
          ) : (
            <div
              aria-live="polite"
              className="pointer-events-none absolute text-center font-sans text-sm leading-snug whitespace-nowrap transition-opacity duration-500"
              style={{
                left: frame.cx,
                top: frame.baseline + 8,
                transform: "translateX(-50%)",
                opacity: growing ? 1 : 0,
              }}
            >
              <p className="flex items-center justify-center gap-1.5 text-story-ink-2">
                <Swatch tone="added" />
                <span className="font-semibold text-story-ink tabular-nums">
                  <NumberTicker value={added} prefix="+" />
                </span>{" "}
                seats since 1789
              </p>
              <p
                className="flex items-center justify-center gap-1.5 tabular-nums"
                style={{ color: changeColor(change) }}
              >
                {change > 0 ? <Swatch tone="focus" /> : null}
                {changeText(change, since)}
                {current.residentPerSeat ? (
                  <span className="text-story-muted">
                    {" "}
                    · one per <NumberTicker value={Math.round(current.residentPerSeat)} />
                  </span>
                ) : null}
              </p>
            </div>
          )
        ) : null}

        {/* Once the House stops growing, it locks. */}
        {frame.width > 0 ? (
          <div
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute transition-opacity duration-500",
              locked && "motion-safe:animate-[story-lock-click_420ms_ease-out_380ms_both]"
            )}
            style={{
              left: lockCenter.x,
              top: lockCenter.y,
              width: lockWidth,
              translate: "-50% -50%",
              transform:
                chartView || dealView
                  ? `translate(${lockMorph.x.toFixed(1)}px, ${lockMorph.y.toFixed(1)}px) scale(${lockMorph.scale.toFixed(4)})`
                  : undefined,
              opacity: lockShown ? 1 : 0,
            }}
          >
            <svg viewBox="0 0 100 124" className="block w-full overflow-visible">
              <path
                d="M28 60 V40 a22 22 0 0 1 44 0 V60"
                fill="none"
                stroke="var(--story-ink)"
                strokeWidth={9}
                strokeLinecap="round"
                style={{
                  transformBox: "fill-box",
                  transformOrigin: "right bottom",
                  transform: locked ? "none" : "translateY(-14px) rotate(-30deg)",
                  transition: reducedMotion ? "none" : "transform 420ms cubic-bezier(0.34, 1.56, 0.64, 1)",
                }}
              />
              <rect x={12} y={56} width={76} height={62} rx={10} fill="var(--story-surface)" stroke="var(--story-ink)" strokeWidth={5} />
              <circle cx={50} cy={82} r={7} fill="var(--story-ink)" />
              <path d="M50 86 V100" stroke="var(--story-ink)" strokeWidth={6} strokeLinecap="round" />
            </svg>
          </div>
        ) : null}

        {view?.tear !== undefined ? (
          <p
            className="pointer-events-none absolute top-[3%] text-center font-story-serif text-2xl font-medium text-story-ink sm:text-3xl"
            style={visualArea}
          >
            <TearText left="The Representation" right="Gap" strain={view.tear} />
          </p>
        ) : null}

        {(chartView || dealView?.scene === "guarantee") && size.width > 0 ? (
          <div
            className="pointer-events-none absolute inset-0"
            style={{ opacity: chartView ? 1 : 1 - smoothstep(0, 0.25, stepProgress) }}
          >
            <PerSeatChart
              layout={chartLayout}
              points={perSeat}
              drawTo={chartView ? drawTo : PRESENT}
              reveal={chartView ? chartReveal : 1}
              pinned={[FREEZE_YEAR + 10]}
              width={size.width}
              height={size.height}
            />
          </div>
        ) : null}

        {dealing && size.width > 0 ? (
          <>
            <ClaimLadder race={race} box={deal.panel} visible={dealView?.scene === "ladder"} />
            <RaceBars
              race={race}
              awarded={Math.max(0, dealt - firstSeats)}
              box={deal.panel}
              visible={dealView?.scene === "race"}
            />
          </>
        ) : null}
        {/* One swarm from Act III's dot plot through Act IV's House sizes,
            so the dots glide from one to the next. */}
        {swarmShown && size.width > 0 ? (
          <StateSwarm
            area={visualArea}
            height={size.height - stripHeight}
            size={biggerSize ?? HOUSE_SIZE}
            relative={biggerView !== null}
            nationalAverage={nationalAverage}
            dim={activeClip !== null}
            spotlight={dealView?.spotlight}
          />
        ) : null}
        {biggerView?.scene === "swarm" && biggerSize !== null && size.width > 0 ? (
          <SizeStrip area={visualArea} current={biggerSize} compact={stripCompact} />
        ) : null}
        {biggerView?.scene === "envelope" && size.width > 0 ? (
          <div className="pointer-events-none absolute inset-0 motion-safe:animate-[story-fade-in_500ms_ease-out_both]">
            <EnvelopeChart
              area={visualArea}
              height={size.height}
              reveal={snap ? 1 : segment(stepProgress, 0.04, 0.6)}
            />
          </div>
        ) : null}
        {biggerView?.scene === "peers" && size.width > 0 ? (
          <div className="pointer-events-none absolute inset-0 motion-safe:animate-[story-fade-in_500ms_ease-out_both]">
            <PeersChart area={visualArea} height={size.height} />
          </div>
        ) : null}

        {unit ? (
          <div className="pointer-events-none absolute top-0 right-0 z-10 font-sans">
            <span
              key={unit}
              className="inline-flex items-center gap-1.5 rounded-full bg-story-surface px-2.5 py-1 text-xs text-story-ink-2 ring-1 ring-story-rule motion-safe:animate-[story-flash_1.6s_ease-out]"
            >
              <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-story-ink" />
              {unit}
            </span>
            <span className="sr-only" aria-live="polite">
              {unit}
            </span>
          </div>
        ) : null}

        {clips.map((clip) => (
          <ClipCard
            key={clip.id}
            clip={clip}
            visible={activeClip?.id === clip.id}
            progress={activeClip?.id === clip.id ? stepProgress : 0}
            area={visualArea}
          />
        ))}
      </div>

      {/* Fixed in height on wide screens, so the chamber's box never resizes
          when the note changes; the data table opens above it. Phones fold
          the note and data away, beside the Expand control. */}
      <figcaption
        className={cn("relative mt-2 font-sans text-xs leading-relaxed text-story-muted", size.fill && "h-16 shrink-0")}
        style={size.fill ? { marginLeft: size.reserve } : undefined}
      >
        {size.fill ? (
          <>
            <p>{captionText}</p>
            {captionTable ? (
              <details className="mt-1">
                <summary className="cursor-pointer select-none text-story-ink-2">View data</summary>
                <div className="absolute bottom-full left-0 z-10 mb-2 max-h-[60vh] w-[min(36rem,100%)] overflow-auto rounded-md bg-story-surface p-2 shadow-xl ring-1 ring-story-rule">
                  {captionTable}
                </div>
              </details>
            ) : null}
          </>
        ) : (
          <div className="flex items-start justify-between gap-3">
            <details className="min-w-0 flex-1">
              <summary className="cursor-pointer select-none text-story-ink-2">About this chart</summary>
              <p className="mt-1">{captionText}</p>
              {captionTable ? <div className="mt-2 max-h-56 overflow-auto">{captionTable}</div> : null}
            </details>
            <button
              type="button"
              onClick={() =>
                setExpanded((value) => (value ? null : { placeholder: wrapperRef.current?.offsetHeight ?? 0 }))
              }
              className="shrink-0 text-story-ink-2 underline underline-offset-2 hover:text-story-ink"
            >
              {expanded ? "Close" : "Expand chart"}
            </button>
          </div>
        )}
      </figcaption>
    </figure>
    </div>
  );
}

/** The figure's header slot: h-24 plus its mb-2. */
const HEADER_HEIGHT = 104;

/** Where the crowd sits in its box: right of any stage caption, centered. */
function crowdGeometry(size: { width: number; height: number; reserve: number; fill: boolean }) {
  const stageWidth = size.width - size.reserve;
  return {
    viewRadius: Math.min(stageWidth, size.height) * (size.fill ? 0.45 : 0.42),
    cx: size.reserve + stageWidth / 2,
    cy: size.height / 2,
  };
}

/** A seat-colored dot that keys a number to its seats in the chamber. */
function Swatch({ tone }: { tone: "added" | "focus" }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ background: tone === "added" ? "var(--story-seat-added)" : "var(--story-seat-focus)" }}
    />
  );
}

/** The change from the census before, in words. */
function changeText(change: number, since: string): string {
  if (change === 0) return `No change since ${since}`;
  return `${change > 0 ? "+" : "−"}${Math.abs(change)} since ${since}`;
}

function changeColor(change: number): string {
  return change > 0 ? "var(--story-seat-focus)" : change < 0 ? "var(--gap-more-3)" : "var(--story-ink-2)";
}

interface HouseView {
  year: number;
  label?: string;
  caption?: string;
  /** Tear strain 0..1 when the step reprises the tear. */
  tear?: number;
  lock?: boolean;
  clip?: HouseStep["clip"];
}

/** The apportionment a house step shows at a given progress through it. */
function houseView(entry: HouseStep, progress: number): HouseView {
  if (entry.years && entry.years.length > 0) {
    const years = entry.years;
    return {
      year: years[Math.min(years.length - 1, Math.floor(progress * years.length))],
      caption: entry.caption,
      tear: entry.tear ? 0.3 + 0.7 * progress : undefined,
      lock: entry.lock,
      clip: entry.clip,
    };
  }
  return {
    year: entry.year ?? PRESENT,
    label: entry.label,
    caption: entry.caption,
    tear: entry.tear ? 0.3 : undefined,
    lock: entry.lock,
    clip: entry.clip,
  };
}

/** "$914 million", "$2.10 billion", "$23.2 billion". */
function dollars(amount: number): string {
  if (amount < 1e9) return `$${Math.round(amount / 1e6).toLocaleString("en-US")} million`;
  return `$${(amount / 1e9).toFixed(amount < 1e10 ? 2 : 1)} billion`;
}

/** A box partway from `a` to `b` (left, top and width; the chamber keeps its shape). */
function mixBox(
  a: { left: number; top: number; width: number },
  b: { left: number; top: number; width: number },
  t: number
): { left: number; top: number; width: number } {
  return {
    left: a.left + (b.left - a.left) * t,
    top: a.top + (b.top - a.top) * t,
    width: a.width + (b.width - a.width) * t,
  };
}

/**
 * How far the people-per-seat line is drawn (a fractional census year) at a
 * point in a chart step. Scrubbed census by census, each new segment grows
 * just after the header turns to its year; otherwise the line draws across
 * the step (after the chamber has shrunk away, on the first chart step).
 */
function chartReach(entry: HouseStep, progress: number, snap: boolean): number {
  const chart = entry.chart;
  if (!chart) return 0;
  const start = chart.from ?? 1780;
  if (entry.years && entry.years.length > 0) {
    const years = entry.years;
    const i = Math.min(years.length - 1, Math.floor(progress * years.length));
    if (snap) return years[i];
    const prior = i === 0 ? start : years[i - 1];
    const grow = clamp01((progress - i / years.length) / (0.6 / years.length));
    return prior + (years[i] - prior) * (1 - (1 - grow) ** 3);
  }
  if (snap) return progress < 0.5 ? Math.max(start, 1790) : chart.through;
  return start + (chart.through - start) * easeInOutCubic(segment(progress, chart.morph ? 0.4 : 0, 0.95));
}

/**
 * Where the chamber sits in the figure: the box a <Hemicycle> of width
 * `width` fills, centered in the visual area and as large as fits, with the
 * outer radius and baseline that <DotField> derives from that width.
 */
function chamberFrame(
  size: { width: number; height: number; reserve: number },
  pad: number
): { left: number; top: number; width: number; outer: number; baseline: number; cx: number } {
  const stageWidth = size.width - size.reserve;
  if (stageWidth <= 0 || size.height <= 0) return { left: 0, top: 0, width: 0, outer: 0, baseline: 0, cx: 0 };
  const fitOuter = Math.min((stageWidth / 2 - 2) / (1 + pad), (size.height * 0.88 - 4) / (1 + 2 * pad));
  const width = Math.max(40, Math.floor(2 * (fitOuter * (1 + pad) + 2)));
  // DotField's own geometry for that width.
  const outer = (width / 2 - 2) / (1 + pad);
  const height = Math.ceil(outer * (1 + 2 * pad) + 4);
  const left = Math.round(size.reserve + (stageWidth - width) / 2);
  const top = Math.round((size.height - height) / 2);
  return { left, top, width, outer, baseline: top + height - outer * pad - 2, cx: left + width / 2 };
}

/**
 * A primary source brought in front of the chamber: the excerpt, phrases
 * highlighted as the reader scrolls, and an optional stamp.
 */
function ClipCard({
  clip,
  visible,
  progress,
  area,
}: {
  clip: StageClip;
  visible: boolean;
  progress: number;
  area: { left: number; width: number };
}) {
  const stamped = clip.stamp !== undefined && visible && progress >= clip.stamp.at;
  const [full, setFull] = React.useState(false);
  React.useEffect(() => {
    if (!visible) setFull(false);
  }, [visible]);
  const text = full || !clip.excerpt ? clip.quote : clip.excerpt;
  // Where the document is taller than its frame (phones), keep the latest
  // highlighted phrase in view as it lights up.
  const scrollerRef = React.useRef<HTMLElement | null>(null);
  const lit = visible ? (clip.highlights ?? []).filter((h) => progress >= h.at).length : 0;
  React.useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller || scroller.scrollHeight <= scroller.clientHeight) return;
    const marks = scroller.querySelectorAll("mark");
    const target = lit > 0 ? (marks[lit - 1] as HTMLElement | undefined) : undefined;
    const top = target ? target.offsetTop - scroller.clientHeight / 3 : 0;
    scroller.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }, [lit]);
  return (
    <div
      aria-hidden={!visible}
      className={cn(
        "absolute inset-y-0 flex items-center justify-center p-2 transition-[opacity,translate] duration-500 ease-out",
        visible ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-6 opacity-0"
      )}
      style={area}
    >
      <figure
        ref={scrollerRef}
        className="relative max-h-full w-full max-w-xl overflow-auto rounded-md bg-story-surface px-5 py-4 shadow-xl ring-1 ring-story-rule sm:px-7 sm:py-6"
      >
        <figcaption className="font-sans text-[0.7rem] font-semibold tracking-wide text-story-muted uppercase sm:text-xs">
          {clip.label}
        </figcaption>
        <blockquote className="mt-2 font-story-serif text-[0.8rem] leading-relaxed text-story-ink italic sm:mt-3 sm:text-lg">
          <Highlighted text={text} highlights={clip.highlights ?? []} progress={visible ? progress : 0} />
        </blockquote>
        {clip.excerpt ? (
          <button
            type="button"
            onClick={() => setFull((value) => !value)}
            className="mt-2 font-sans text-xs text-story-ink-2 underline decoration-story-axis underline-offset-2 hover:text-story-ink"
          >
            {full ? "Show the key passage" : "Read the full passage"}
          </button>
        ) : null}
        <p className="mt-2 font-sans text-[0.7rem] text-story-muted sm:mt-3 sm:text-xs">
          {clip.sources.map((source, index) => (
            <React.Fragment key={source.url}>
              {index > 0 ? "; " : "Source: "}
              <a href={source.url} className="underline decoration-story-axis underline-offset-2 hover:text-story-ink">
                {source.title}
              </a>
            </React.Fragment>
          ))}
        </p>
        {clip.stamp ? (
          // Stamped across the text, as on the real thing.
          <span
            className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-sm border-[3px] border-[var(--gap-more-3)] bg-story-surface/40 px-4 py-1.5 font-sans text-lg font-black tracking-[0.18em] whitespace-nowrap text-[var(--gap-more-3)] uppercase transition-[opacity,scale] duration-300 ease-out sm:text-2xl"
            style={{ opacity: stamped ? 0.88 : 0, scale: stamped ? "1" : "1.7", rotate: "-10deg" }}
          >
            {clip.stamp.text}
          </span>
        ) : null}
      </figure>
    </div>
  );
}

/** Text with phrases that get a marker swipe once `progress` passes their `at`. */
function Highlighted({
  text,
  highlights,
  progress,
}: {
  text: string;
  highlights: ReadonlyArray<{ text: string; at: number }>;
  progress: number;
}) {
  const parts: React.ReactNode[] = [];
  let rest = text;
  const ordered = highlights
    .map((h) => ({ ...h, index: text.indexOf(h.text) }))
    .filter((h) => h.index >= 0)
    .sort((a, b) => a.index - b.index);
  let offset = 0;
  for (const h of ordered) {
    const start = h.index - offset;
    if (start < 0) continue;
    parts.push(rest.slice(0, start));
    const on = progress >= h.at;
    parts.push(
      <mark
        key={h.index}
        className="bg-transparent text-inherit"
        style={{
          backgroundImage:
            "linear-gradient(color-mix(in srgb, var(--story-series-4) 38%, transparent), color-mix(in srgb, var(--story-series-4) 38%, transparent))",
          backgroundRepeat: "no-repeat",
          backgroundSize: on ? "100% 100%" : "0% 100%",
          transition: "background-size 800ms ease-out",
        }}
      >
        {h.text}
      </mark>
    );
    rest = rest.slice(start + h.text.length);
    offset = h.index + h.text.length;
  }
  parts.push(rest);
  return <>{parts}</>;
}

/** Position of item i on the unit-spacing sunflower spiral. */
function spiral(i: number): { x: number; y: number } {
  const r = Math.sqrt(i + 0.5);
  const theta = i * GOLDEN_ANGLE;
  return { x: r * Math.cos(theta), y: r * Math.sin(theta) };
}

/**
 * Where each of 10,000 people flows to become one of ten dots of exactly
 * 1,000. People are split into ten equal, compact regions (a balanced power
 * diagram: Voronoi cells whose weights are nudged until every cell holds
 * 1,000, then a greedy pass for exact counts). Coordinates are in person
 * spacings, centered on the crowd.
 */
function buildGathering() {
  const n = GATHERED;
  const k = n / UNIT;
  const sx = new Float32Array(n);
  const sy = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const p = spiral(i);
    sx[i] = p.x;
    sy[i] = p.y;
  }
  // Unit dots sit where the zoom in dots will continue from.
  const unitSpacing = Math.sqrt(UNIT);
  const centers = Array.from({ length: k }, (_, j) => {
    const p = spiral(j);
    return { x: p.x * unitSpacing, y: p.y * unitSpacing };
  });

  const distance2 = new Float64Array(n * k);
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < k; j++) {
      distance2[i * k + j] = (sx[i] - centers[j].x) ** 2 + (sy[i] - centers[j].y) ** 2;
    }
  }
  const weights = new Float64Array(k);
  const cost = (i: number, j: number) => distance2[i * k + j] - weights[j];
  for (let iteration = 0; iteration < 80; iteration++) {
    const sizes = new Array<number>(k).fill(0);
    for (let i = 0; i < n; i++) {
      let best = 0;
      for (let j = 1; j < k; j++) if (cost(i, j) < cost(i, best)) best = j;
      sizes[best]++;
    }
    if (sizes.every((count) => count === UNIT)) break;
    for (let j = 0; j < k; j++) weights[j] += 3 * (UNIT - sizes[j]);
  }
  // Exact counts: the most decided people choose first.
  const order = Array.from({ length: n }, (_, i) => {
    let first = Infinity;
    let second = Infinity;
    for (let j = 0; j < k; j++) {
      const c = cost(i, j);
      if (c < first) [first, second] = [c, first];
      else if (c < second) second = c;
    }
    return { i, regret: second - first };
  }).sort((a, b) => b.regret - a.regret);
  const remaining = new Array<number>(k).fill(UNIT);
  const unitOf = new Uint8Array(n);
  for (const { i } of order) {
    let best = -1;
    for (let j = 0; j < k; j++) {
      if (remaining[j] === 0) continue;
      if (best < 0 || cost(i, j) < cost(i, best)) best = j;
    }
    unitOf[i] = best;
    remaining[best]--;
  }

  const random = mulberry32(0x6a7e);
  const tx = new Float32Array(n);
  const ty = new Float32Array(n);
  const delay = new Float32Array(n);
  const swirl = new Float32Array(n);
  const color = new Uint8Array(n);
  const dotRadius = UNIT_DOT * unitSpacing;
  for (let i = 0; i < n; i++) {
    const center = centers[unitOf[i]];
    // Land inside the dot, packed toward its middle.
    const angle = random() * Math.PI * 2;
    const r = dotRadius * 0.85 * Math.sqrt(random());
    tx[i] = center.x + Math.cos(angle) * r;
    ty[i] = center.y + Math.sin(angle) * r;
    const distance = Math.hypot(tx[i] - sx[i], ty[i] - sy[i]);
    delay[i] = 0.3 * random() + 0.12 * Math.min(1, distance / 40);
    swirl[i] = (random() - 0.5) * 0.7;
    color[i] = hash(`p${i}`) % 5;
  }
  return { sx, sy, tx, ty, delay, swirl, color };
}

/** Per-dot timing for the pour into the seat: a stream, not a jump cut. */
function buildPour(units: number) {
  const random = mulberry32(0x5ea7 ^ units);
  const delay = new Float32Array(units);
  const swirl = new Float32Array(units);
  for (let k = 0; k < units; k++) {
    // Inner dots leave first, so the disc drains from its center outward.
    delay[k] = 0.42 * Math.sqrt(k / units) + 0.12 * random();
    swirl[k] = (random() - 0.5) * 0.5;
  }
  return { delay, swirl };
}

function drawUnits(
  ctx: CanvasRenderingContext2D,
  o: { count: number; spacing: number; cx: number; cy: number; fill: string }
) {
  const r = Math.max(0.8, o.spacing * UNIT_DOT);
  const path = new Path2D();
  for (let k = 0; k < o.count; k++) {
    const p = spiral(k);
    const x = o.cx + p.x * o.spacing;
    const y = o.cy - p.y * o.spacing;
    path.moveTo(x + r, y);
    path.arc(x, y, r, 0, Math.PI * 2);
  }
  ctx.fillStyle = o.fill;
  ctx.fill(path);
}

function drawPeople(
  ctx: CanvasRenderingContext2D,
  o: {
    people: number;
    s: number;
    originX: number;
    originY: number;
    width: number;
    height: number;
    colors: string[];
    ink: string;
    paper: string;
    /** The reader's own person, drawn exactly as the intro drew them. */
    focal: Omit<Parameters<typeof drawPerson>[1], "ink" | "paper" | "lineWidth"> | null;
    /** Leave the reader's person out (the handoff is drawing them). */
    focalHidden: boolean;
  }
) {
  const count = Math.min(Math.ceil(o.people), GATHERED);
  const margin = o.s;
  const inView = (x: number, y: number) =>
    x > -margin && x < o.width + margin && y > -margin && y < o.height + margin;

  if (o.s >= FIGURE_MIN_SPACING) {
    // Full figures, each a mosaic as detailed as the reader's own: one of a
    // few prebuilt meshes, recolored per person, about half with a role.
    for (let i = 0; i < count; i++) {
      const p = spiral(i);
      const x = o.originX + p.x * o.s;
      const y = o.originY - p.y * o.s;
      if (!inView(x, y)) continue;
      if (i === 0 && o.focalHidden) continue;
      // Each neighbor fades in as the count reaches them, so no partial
      // figure (or stray accessory) shows at the edge of the frame.
      const arrival = Math.max(0, Math.min(1, (o.people - i - 0.25) / 0.75));
      if (arrival <= 0) continue;
      const k = (o.s * FIGURE_SHARE) / VIEW.height;
      const lineWidth = Math.max(2, 1.2 / k);
      ctx.save();
      ctx.globalAlpha = arrival;
      ctx.translate(x - (VIEW.width / 2) * k, y - (VIEW.height / 2) * k);
      ctx.scale(k, k);
      if (i === 0 && o.focal) {
        drawPerson(ctx, { ...o.focal, ink: o.ink, paper: o.paper, lineWidth });
      } else {
        const h = hash(`p${i}`);
        const shift = (h >>> 4) % o.colors.length;
        drawPerson(ctx, {
          seed: NEIGHBOR_SEEDS[h % NEIGHBOR_SEEDS.length],
          readableCategories: NEIGHBOR_PIECES,
          roleId: (h >>> 8) % 2 === 0 ? ROLES[(h >>> 9) % ROLES.length].id : null,
          colorFor: (category) => o.colors[(CATEGORIES.indexOf(category) + shift) % o.colors.length],
          ink: o.ink,
          paper: o.paper,
          lineWidth,
        });
      }
      ctx.restore();
    }
    return;
  }

  // Dots, batched per color.
  const paths = o.colors.map(() => new Path2D());
  const twoDot = o.s >= 7;
  const r = twoDot ? o.s * 0.16 : Math.max(0.5, o.s * 0.34);
  for (let i = 0; i < count; i++) {
    const p = spiral(i);
    const x = o.originX + p.x * o.s;
    const y = o.originY - p.y * o.s;
    if (!inView(x, y)) continue;
    if (i === 0 && o.focalHidden) continue;
    const h = hash(`p${i}`);
    if (twoDot) {
      const head = paths[h % 5];
      head.moveTo(x + r, y - r * 1.4);
      head.arc(x, y - r * 1.4, r, 0, Math.PI * 2);
      const body = paths[(h >>> 3) % 5];
      body.moveTo(x + r * 1.3, y + r * 0.6);
      body.arc(x, y + r * 0.6, r * 1.3, 0, Math.PI * 2);
    } else if (r >= 1) {
      const dot = paths[h % 5];
      dot.moveTo(x + r, y);
      dot.arc(x, y, r, 0, Math.PI * 2);
    } else {
      paths[h % 5].rect(x - 0.5, y - 0.5, 1, 1);
    }
  }
  paths.forEach((path, k) => {
    ctx.fillStyle = o.colors[k];
    ctx.fill(path);
  });
}

/**
 * The running count over the figure: exact at each milestone (and at the
 * constituency itself), otherwise rounded to two significant figures so it
 * reads as a counter rather than a measurement.
 */
function displayCount(people: number, milestones: readonly number[]): number {
  const near = milestones.find((m) => Math.abs(people - m) / m < 0.02);
  if (near !== undefined) return near;
  if (people < 10) return Math.max(1, Math.round(people));
  const magnitude = 10 ** (Math.floor(Math.log10(people)) - 1);
  return Math.round(people / magnitude) * magnitude;
}

/** Progress through [start, end] of a step, clamped to 0..1. */
function segment(progress: number, start: number, end: number): number {
  return clamp01((progress - start) / (end - start));
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  const t = clamp01((value - edge0) / (edge1 - edge0));
  return t * t * (3 - 2 * t);
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}
