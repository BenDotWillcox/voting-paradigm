/**
 * Hand-drawn line helpers for the home page's pencil sketches. Every mark
 * is a slightly bowed, slightly overshooting stroke, the way a quick pencil
 * line runs a little past its corner; circles never quite close; shading is
 * hatching. A seeded generator makes each sketch the same on every visit.
 * Output is SVG path data plus a rough length, which sets how long the
 * stroke takes to draw. Strokes can be gathered into groups that keep
 * moving once drawn: a turbine's blades spin, a flag waves, a leaf blows
 * away.
 */

export type Tone = "graphite" | "blue" | "aqua" | "rose" | "sun" | "violet" | "green";

export interface Stroke {
  d: string;
  tone: Tone;
  width: number;
  /** Rough length in viewBox units, for timing the draw. */
  length: number;
  /** A lighter mark: hatching, ghost lines, texture. */
  soft?: boolean;
  /** The moving group this stroke belongs to, if any. */
  group?: number;
}

type Point = [number, number];

/**
 * How a group moves once its sketch is drawn. Pivots are in viewBox units;
 * periods and delays in seconds. "fly" happens once: the group drifts off
 * by `to`, turning `turn` degrees, and fades. "drop" repeats: the group
 * falls `distance` into place and slips out of sight, like a pebble into an
 * urn.
 */
export type Motion =
  | { kind: "spin"; pivot: Point; period: number }
  | { kind: "sway"; pivot: Point; degrees: number; period: number }
  | { kind: "wave"; pivot: Point; period: number }
  | { kind: "bob"; distance: number; period: number }
  | { kind: "pulse"; pivot: Point; period: number }
  | { kind: "drop"; distance: number; period: number; delay: number }
  | { kind: "fly"; pivot: Point; to: Point; turn: number; delay: number; duration: number };

export interface Group {
  motion: Motion;
  /** The enclosing group, if this one moves inside another. */
  parent?: number;
}

interface Pen {
  tone?: Tone;
  width?: number;
  soft?: boolean;
  /** How far the stroke may bow from straight, in viewBox units. */
  wobble?: number;
  /** Retrace the stroke once, slightly off, as a quick sketch does. */
  ghost?: boolean;
}

export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const f = (n: number) => n.toFixed(1);

function pathLength(points: Point[]): number {
  let length = 0;
  for (let i = 1; i < points.length; i++) length += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
  return length;
}

export class Sketch {
  readonly strokes: Stroke[] = [];
  readonly groups: Group[] = [];
  private open: number[] = [];

  constructor(private readonly rand: () => number) {}

  /** Draws `body` as a group that keeps moving once the sketch is done. */
  moving(motion: Motion, body: () => void) {
    this.groups.push({ motion, parent: this.open.at(-1) });
    this.open.push(this.groups.length - 1);
    body();
    this.open.pop();
  }

  private jitter(amount: number) {
    return (this.rand() * 2 - 1) * amount;
  }

  private push(stroke: Stroke) {
    this.strokes.push({ ...stroke, group: this.open.at(-1) });
  }

  /** A straight stroke that bows a little and overshoots its ends. */
  line(x1: number, y1: number, x2: number, y2: number, pen: Pen = {}) {
    const length = Math.hypot(x2 - x1, y2 - y1) || 1;
    const ux = (x2 - x1) / length;
    const uy = (y2 - y1) / length;
    const over = Math.min(4, length * 0.05);
    const a: Point = [x1 - ux * over * this.rand(), y1 - uy * over * this.rand()];
    const b: Point = [x2 + ux * over * this.rand(), y2 + uy * over * this.rand()];
    const bow = this.jitter(pen.wobble ?? Math.min(3, length * 0.025));
    const c: Point = [(a[0] + b[0]) / 2 - uy * bow, (a[1] + b[1]) / 2 + ux * bow];
    this.push({ d: `M${f(a[0])} ${f(a[1])}Q${f(c[0])} ${f(c[1])} ${f(b[0])} ${f(b[1])}`, tone: pen.tone ?? "graphite", width: pen.width ?? 1.4, length, soft: pen.soft });
    if (pen.ghost) this.line(x1 + this.jitter(1.2), y1 + this.jitter(1.2), x2 + this.jitter(1.2), y2 + this.jitter(1.2), { ...pen, ghost: false, soft: true, width: (pen.width ?? 1.4) * 0.7 });
  }

  /** A smooth stroke through points, each nudged a little off its mark. */
  curve(points: Point[], pen: Pen = {}) {
    const wobble = pen.wobble ?? 1.2;
    const p = points.map(([x, y]) => [x + this.jitter(wobble), y + this.jitter(wobble)] as Point);
    let d = `M${f(p[0][0])} ${f(p[0][1])}`;
    for (let i = 1; i < p.length - 1; i++) {
      const mid: Point = [(p[i][0] + p[i + 1][0]) / 2, (p[i][1] + p[i + 1][1]) / 2];
      d += `Q${f(p[i][0])} ${f(p[i][1])} ${f(mid[0])} ${f(mid[1])}`;
    }
    const last = p[p.length - 1];
    d += `L${f(last[0])} ${f(last[1])}`;
    this.push({ d, tone: pen.tone ?? "graphite", width: pen.width ?? 1.4, length: pathLength(p), soft: pen.soft });
    if (pen.ghost) this.curve(points, { ...pen, ghost: false, soft: true, width: (pen.width ?? 1.4) * 0.7, wobble: wobble * 1.6 });
  }

  /** An elliptical arc from angle a0 to a1 (radians, y down). */
  arc(cx: number, cy: number, rx: number, ry: number, a0: number, a1: number, pen: Pen = {}) {
    const steps = Math.max(6, Math.round((Math.abs(a1 - a0) * Math.max(rx, ry)) / 7));
    const points = Array.from({ length: steps + 1 }, (_, i) => {
      const a = a0 + ((a1 - a0) * i) / steps;
      const wave = 1 + Math.sin(a * 3 + rx) * 0.015;
      return [cx + Math.cos(a) * rx * wave, cy + Math.sin(a) * ry * wave] as Point;
    });
    this.curve(points, { wobble: 0.6, ...pen });
  }

  /** A loop that runs a little past where it started, never quite closing. */
  circle(cx: number, cy: number, r: number, pen: Pen = {}) {
    const start = this.rand() * Math.PI * 2;
    this.arc(cx, cy, r, r * (0.94 + this.rand() * 0.1), start, start + Math.PI * 2.12, pen);
  }

  /** Parallel shading strokes inside a polygon, at `angle` radians and `spacing` apart. */
  hatch(polygon: Point[], angle: number, spacing: number, pen: Pen = {}) {
    const cos = Math.cos(-angle);
    const sin = Math.sin(-angle);
    const turned = polygon.map(([x, y]) => [x * cos - y * sin, x * sin + y * cos] as Point);
    const ys = turned.map((p) => p[1]);
    const back = (x: number, y: number): Point => [x * cos + y * sin, -x * sin + y * cos];
    for (let y = Math.min(...ys) + spacing / 2; y < Math.max(...ys); y += spacing) {
      const xs: number[] = [];
      for (let i = 0; i < turned.length; i++) {
        const [x1, y1] = turned[i];
        const [x2, y2] = turned[(i + 1) % turned.length];
        if ((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) xs.push(x1 + ((y - y1) / (y2 - y1)) * (x2 - x1));
      }
      xs.sort((a, b) => a - b);
      for (let i = 0; i + 1 < xs.length; i += 2) {
        const inset = spacing * 0.3;
        const a = back(xs[i] + inset * this.rand(), y);
        const b = back(xs[i + 1] - inset * this.rand(), y);
        this.line(a[0], a[1], b[0], b[1], { width: 0.9, soft: true, wobble: 0.6, ...pen });
      }
    }
  }

  /** A dense back-and-forth scribble filling an ellipse, like a filled-in ballot oval. */
  scribble(cx: number, cy: number, rx: number, ry: number, pen: Pen = {}) {
    const points: Point[] = [];
    for (let i = 0; i <= 9; i++) {
      const t = -1 + (2 * i) / 9;
      const half = Math.sqrt(1 - t * t) * rx * 0.92;
      const y = cy + t * ry * 0.85;
      points.push(i % 2 ? [cx + half, y] : [cx - half, y]);
    }
    this.curve(points, { wobble: 0.4, width: 1.1, ...pen });
  }
}

/** Points around an ellipse, for hatching inside it. */
export function ellipse(cx: number, cy: number, rx: number, ry: number, from = 0, to = Math.PI * 2, steps = 28): Point[] {
  return Array.from({ length: steps + 1 }, (_, i) => {
    const a = from + ((to - from) * i) / steps;
    return [cx + Math.cos(a) * rx, cy + Math.sin(a) * ry] as Point;
  });
}
