"use client";

import * as React from "react";

import { useReducedMotion } from "@/components/story/chart";
import { mulberry32, type PieceCategory } from "@/lib/apportionment/persona";
import { seriesColor } from "@/lib/story/palette";

/** Color per life dimension (validated categorical slots, fixed order). */
export const PIECE_COLORS: Record<PieceCategory, string> = {
  family: seriesColor(0),
  circumstance: seriesColor(1),
  belief: seriesColor(2),
  concern: seriesColor(3),
  everyday: seriesColor(4),
};
const CATEGORY_ORDER: readonly PieceCategory[] = [
  "family",
  "circumstance",
  "belief",
  "concern",
  "everyday",
];

/** Figure geometry, shared with the crowd so the person stays recognizable. */
export const VIEW = { width: 160, height: 224 };
export const HEAD = { cx: 80, cy: 42, r: 24 };
export const BODY =
  "M50 84 Q50 72 64 70 L96 70 Q110 72 110 84 L114 148 Q114 156 106 156 L101 156 L99 212 " +
  "Q99 218 93 218 L85 218 L82 164 L78 164 L75 218 L67 218 Q61 218 61 212 L59 156 L54 156 " +
  "Q46 156 46 148 Z";

/** Rush arrivals after the three readable pieces. */
export const RUSH_STEPS = 12;

/**
 * Where each named piece lands, as a height in figure units: the chest, the
 * head, then the lower body. The intro sets each piece's words at the same
 * height, so its shard flies straight from its words into place.
 */
export const READABLE_ROWS: readonly [number, number, number] = [100, 44, 140];

/**
 * plain: the outlined figure. wire: its low-poly constellation drawn in,
 * ready for pieces. assembled: pieces in place, the constellation gone.
 */
export type FigureMode = "plain" | "wire" | "assembled";

interface Shard {
  points: string;
  cx: number;
  cy: number;
  category: PieceCategory;
  /** Entry pose for rush shards: offset (figure units), turn, and scale. */
  from: [number, number];
  turn: number;
  depth: number;
  /** Stagger slot within its arrival batch. */
  lane: number;
}

interface PersonFigureProps {
  /** Accessory for the current role (see ROLE ids); null for the plain figure. */
  roleId: string | null;
  mode: FigureMode;
  /**
   * How many pieces have arrived: 0-3 are the named pieces (one shard
   * each), beyond that the rush fills the remaining shards.
   */
  arrived: number;
  /** The named piece to outline as it lands (0-2), or null. */
  highlight?: number | null;
  /** Categories of the three readable pieces, in arrival order. */
  readableCategories?: readonly PieceCategory[];
  /**
   * Where each named piece's shard flies in from, in figure units: the
   * spot on screen where its words appear.
   */
  sources?: ReadonlyArray<readonly [number, number]>;
  /** Seed for the mesh's shape and arrival order (stable per person). */
  seed: number;
  className?: string;
  title?: string;
}

/**
 * A person drawn as a low-poly silhouette. The figure first appears as an
 * outline; then its constellation of vertices and edges draws in, and
 * colored shards fly in and lock into place, each shard one value,
 * concern, or circumstance. Three named shards arrive one at a time from
 * where their words appear; then a rush of unnamed shards from every
 * direction shows how many more there are. Lines use currentColor and the
 * seams between shards are gaps.
 */
export function PersonFigure({
  roleId,
  mode,
  arrived,
  highlight = null,
  readableCategories = DEFAULT_READABLE,
  sources = DEFAULT_SOURCES,
  seed,
  className,
  title,
}: PersonFigureProps) {
  const clipId = React.useId();
  const mesh = React.useMemo(() => buildMesh(seed, readableCategories), [seed, readableCategories]);

  // Shard i is in place once its named piece or its rush batch arrives.
  const readableCount = Math.min(arrived, 3);
  const rushCount = Math.max(0, arrived - 3);
  const namedOf = React.useMemo(
    () => new Map(mesh.named.map((shardIndex, k) => [shardIndex, k])),
    [mesh]
  );
  const rushOrder = React.useMemo(
    () => mesh.shards.map((_, i) => i).filter((i) => !namedOf.has(i)),
    [mesh, namedOf]
  );
  const rushIndex = React.useMemo(() => {
    const map = new Map<number, number>();
    rushOrder.forEach((i, position) => map.set(i, position));
    return map;
  }, [rushOrder]);
  const rushFill = Math.round((rushCount / RUSH_STEPS) * rushOrder.length);

  const reducedMotion = useReducedMotion();
  const wired = mode !== "plain";
  const wireVisible = mode === "wire";

  return (
    <svg
      viewBox={`0 0 ${VIEW.width} ${VIEW.height}`}
      className={className}
      overflow="visible"
      role="img"
      aria-label={title ?? "A person"}
    >
      <defs>
        <clipPath id={clipId}>
          <circle cx={HEAD.cx} cy={HEAD.cy} r={HEAD.r} />
          <path d={BODY} />
        </clipPath>
      </defs>

      {/* The constellation: edges draw head to foot, vertices pop in. */}
      <g
        clipPath={`url(#${clipId})`}
        stroke="currentColor"
        strokeWidth={0.7}
        fill="none"
        style={{ opacity: wireVisible ? 0.55 : 0, transition: "opacity 900ms ease" }}
      >
        {mesh.edges.map((edge, i) => (
          <line
            key={i}
            x1={edge[0]}
            y1={edge[1]}
            x2={edge[2]}
            y2={edge[3]}
            pathLength={1}
            strokeDasharray={1}
            style={{
              strokeDashoffset: wired ? 0 : 1,
              transition: wired
                ? `stroke-dashoffset 650ms cubic-bezier(0.3, 0.6, 0.2, 1) ${Math.round(150 + edge[4] * 950)}ms`
                : "none",
            }}
          />
        ))}
      </g>
      <g fill="currentColor" style={{ opacity: wireVisible ? 0.9 : 0, transition: "opacity 900ms ease" }}>
        {mesh.vertices.map((vertex, i) => (
          <circle
            key={i}
            cx={vertex[0]}
            cy={vertex[1]}
            r={1.5}
            style={{
              transformBox: "fill-box",
              transformOrigin: "center",
              transform: wired ? "scale(1)" : "scale(0)",
              transition: wired
                ? `transform 420ms cubic-bezier(0.3, 1.6, 0.5, 1) ${Math.round(vertex[2] * 800)}ms`
                : "none",
            }}
          />
        ))}
      </g>

      {/* Shards. */}
      <g clipPath={`url(#${clipId})`}>
        {mesh.shards.map((shard, i) => {
          const named = namedOf.get(i);
          const on = named !== undefined ? named < readableCount : (rushIndex.get(i) ?? Infinity) < rushFill;
          let away: string;
          let transition: string;
          if (named !== undefined) {
            // Leaves its words large and turning, settles into place.
            const [sx, sy] = sources[named] ?? DEFAULT_SOURCES[named];
            away = `translate(${(sx - shard.cx).toFixed(1)}px, ${(sy - shard.cy).toFixed(1)}px) rotate(${shard.turn}deg) scale(2.6)`;
            transition = "transform 1100ms cubic-bezier(0.16, 1, 0.3, 1), opacity 220ms ease-out";
          } else {
            away = `translate(${shard.from[0]}px, ${shard.from[1]}px) rotate(${shard.turn}deg) scale(${shard.depth})`;
            transition = `transform 620ms cubic-bezier(0.2, 0.8, 0.2, 1) ${shard.lane * 32}ms, opacity 300ms ease-out ${shard.lane * 32}ms`;
          }
          return (
            <polygon
              key={i}
              points={shard.points}
              fill={PIECE_COLORS[shard.category]}
              style={{
                opacity: on ? 1 : 0,
                transformBox: "fill-box",
                transformOrigin: "center",
                transform: on ? "none" : away,
                transition: mode === "plain" || reducedMotion ? "none" : transition,
              }}
            />
          );
        })}
      </g>

      {/* The named piece now landing, outlined so a single shard reads. */}
      {mesh.named.map((shardIndex, k) => (
        <polygon
          key={shardIndex}
          points={mesh.shards[shardIndex].points}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.6}
          strokeLinejoin="round"
          style={{
            opacity: highlight === k ? 1 : 0,
            transition: highlight === k ? "opacity 300ms ease-out 900ms" : "opacity 400ms ease-out",
          }}
        />
      ))}

      {/* Outline on top so the shards read as filling the person. */}
      <g
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        style={{ opacity: mode === "wire" ? 0.35 : 1, transition: "opacity 700ms ease" }}
      >
        <circle cx={HEAD.cx} cy={HEAD.cy} r={HEAD.r} />
        <path d={BODY} strokeLinejoin="round" />
      </g>
      <g style={{ opacity: mode === "wire" ? 0 : 1, transition: "opacity 500ms ease" }}>
        <Accessory roleId={roleId} />
      </g>
    </svg>
  );
}

const DEFAULT_READABLE: readonly PieceCategory[] = ["family", "belief", "concern"];
/** Named pieces fly in from the right, where their words appear. */
const DEFAULT_SOURCES: ReadonlyArray<readonly [number, number]> = READABLE_ROWS.map(
  (y) => [250, y] as const
);

/**
 * A jittered grid over the figure, each cell split along a random diagonal
 * into two triangles. Triangles touching the silhouette are kept (the clip
 * trims their edges), so the fill has no gaps.
 */
function buildMesh(seed: number, readable: readonly PieceCategory[]) {
  const random = mulberry32(seed ^ 0x5eed);
  const cols = 8;
  const rows = 14;
  const x0 = 40;
  const x1 = 120;
  const y0 = 16;
  const y1 = 220;
  const vx: number[][] = [];
  const vy: number[][] = [];
  for (let r = 0; r <= rows; r++) {
    vx.push([]);
    vy.push([]);
    for (let c = 0; c <= cols; c++) {
      const edge = r === 0 || r === rows || c === 0 || c === cols;
      const jitter = edge ? 0 : 0.55;
      vx[r].push(x0 + ((c + (random() - 0.5) * jitter) / cols) * (x1 - x0));
      vy[r].push(y0 + ((r + (random() - 0.5) * jitter) / rows) * (y1 - y0));
    }
  }

  const shards: Shard[] = [];
  const edgeSet = new Map<string, [number, number, number, number, number]>();
  const vertexSet = new Map<string, [number, number, number]>();
  const height = y1 - y0;
  const addEdge = (a: [number, number], b: [number, number]) => {
    const key = [a, b]
      .map((p) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`)
      .sort()
      .join("|");
    if (edgeSet.has(key)) return;
    const mx = (a[0] + b[0]) / 2;
    const my = (a[1] + b[1]) / 2;
    if (!insideSilhouette(mx, my, 3)) return;
    edgeSet.set(key, [a[0], a[1], b[0], b[1], (Math.min(a[1], b[1]) - y0) / height]);
  };
  const addVertex = (p: [number, number]) => {
    const key = `${p[0].toFixed(2)},${p[1].toFixed(2)}`;
    if (vertexSet.has(key) || !insideSilhouette(p[0], p[1], 1.5)) return;
    vertexSet.set(key, [p[0], p[1], (p[1] - y0) / height]);
  };

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const a: [number, number] = [vx[r][c], vy[r][c]];
      const b: [number, number] = [vx[r][c + 1], vy[r][c + 1]];
      const d: [number, number] = [vx[r + 1][c], vy[r + 1][c]];
      const e: [number, number] = [vx[r + 1][c + 1], vy[r + 1][c + 1]];
      const triangles: Array<[number, number][]> =
        random() < 0.5 ? [[a, b, e], [a, e, d]] : [[a, b, d], [b, e, d]];
      for (const tri of triangles) {
        const cx = (tri[0][0] + tri[1][0] + tri[2][0]) / 3;
        const cy = (tri[0][1] + tri[1][1] + tri[2][1]) / 3;
        const probes = [[cx, cy], ...tri, ...tri.map((p, i) => midpoint(p, tri[(i + 1) % 3]))];
        if (!probes.some(([x, y]) => insideSilhouette(x, y, 0))) continue;
        const angle = random() * Math.PI * 2;
        const distance = 90 + random() * 90;
        shards.push({
          // Inset toward the centroid so the stage shows through as seams.
          points: tri
            .map((p) => {
              const dx = cx - p[0];
              const dy = cy - p[1];
              const k = Math.min(0.2, 0.45 / Math.max(0.01, Math.hypot(dx, dy)));
              return `${(p[0] + dx * k).toFixed(2)},${(p[1] + dy * k).toFixed(2)}`;
            })
            .join(" "),
          cx,
          cy,
          category: CATEGORY_ORDER[Math.floor(random() * CATEGORY_ORDER.length)],
          // Rounded so server and client render identical style strings.
          from: [Math.round(Math.cos(angle) * distance), Math.round(Math.sin(angle) * distance)],
          turn: Math.round((random() - 0.5) * 300),
          depth: Math.round((1.8 + random() * 1.4) * 100) / 100,
          lane: Math.floor(random() * 9),
        });
        tri.forEach((p, i) => {
          addEdge(p, tri[(i + 1) % 3]);
          addVertex(p);
        });
      }
    }
  }

  // Three named pieces: one whole shard each, the one nearest the center
  // line at its landing height, so the shard reads clearly on its own.
  const named = READABLE_ROWS.map((y, k) => {
    let best = -1;
    let bestDistance = Infinity;
    shards.forEach((shard, i) => {
      const corners = shard.points.split(" ").map((p) => p.split(",").map(Number));
      if (!corners.every(([x, cy]) => insideSilhouette(x, cy, -2))) return;
      const distance = Math.hypot(shard.cx - VIEW.width / 2, shard.cy - y);
      if (distance < bestDistance) {
        best = i;
        bestDistance = distance;
      }
    });
    shards[best].category = readable[k] ?? shards[best].category;
    return best;
  });

  return {
    shards,
    named,
    edges: [...edgeSet.values()],
    vertices: [...vertexSet.values()],
  };
}

function midpoint(a: [number, number], b: [number, number]): [number, number] {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

/** Inside the head or body, grown by `margin` figure units. */
function insideSilhouette(x: number, y: number, margin: number): boolean {
  if ((x - HEAD.cx) ** 2 + (y - HEAD.cy) ** 2 <= (HEAD.r + margin) ** 2) return true;
  if (y >= 70 - margin && y <= 156 + margin && x >= 47 - margin && x <= 113 + margin) return true;
  if (
    y > 156 &&
    y <= 218 + margin &&
    ((x >= 61 - margin && x <= 79 + margin) || (x >= 81 - margin && x <= 99 + margin))
  )
    return true;
  return false;
}

/** One stroke of a role accessory; `fill` is paper (opaque), ink, or none. */
interface AccessoryPart {
  d: string;
  fill?: "paper" | "ink";
}

function circle(cx: number, cy: number, r: number): string {
  return `M${cx - r} ${cy} A${r} ${r} 0 1 0 ${cx + r} ${cy} A${r} ${r} 0 1 0 ${cx - r} ${cy} Z`;
}

function rect(x: number, y: number, w: number, h: number, r = 0): string {
  if (r === 0) return `M${x} ${y} H${x + w} V${y + h} H${x} Z`;
  return (
    `M${x + r} ${y} H${x + w - r} A${r} ${r} 0 0 1 ${x + w} ${y + r} V${y + h - r} ` +
    `A${r} ${r} 0 0 1 ${x + w - r} ${y + h} H${x + r} A${r} ${r} 0 0 1 ${x} ${y + h - r} ` +
    `V${y + r} A${r} ${r} 0 0 1 ${x + r} ${y} Z`
  );
}

const HARD_HAT: readonly AccessoryPart[] = [
  { d: "M54 34 Q56 10 80 10 Q104 10 106 34 Z", fill: "paper" },
  { d: "M50 34 H110" },
];

/**
 * Role accessories as path data, drawn over the figure in its line color so
 * the person stays the same. Data rather than JSX so the crowd's canvas can
 * draw the reader's person exactly as the intro's SVG does.
 */
const ACCESSORIES: Readonly<Record<string, readonly AccessoryPart[]>> = {
  nurse: [{ d: "M64 24 L96 24 L92 12 L68 12 Z", fill: "paper" }, { d: "M80 14 V22 M76 18 H84" }],
  doctor: [{ d: "M66 72 Q66 104 80 106 Q94 104 94 72" }, { d: circle(80, 110, 4), fill: "paper" }],
  teacher: [{ d: "M112 118 L136 112 L136 138 L112 144 Z", fill: "paper" }, { d: "M112 118 L112 144" }],
  lawyer: [{ d: rect(114, 130, 30, 22, 3), fill: "paper" }, { d: "M124 130 V125 H134 V130" }],
  electrician: [...HARD_HAT, { d: "M82 14 L76 24 H84 L78 32" }],
  construction: HARD_HAT,
  retail: [{ d: rect(88, 86, 16, 10, 2), fill: "paper" }],
  cook: [{ d: "M62 26 Q56 6 70 6 Q76 -2 86 6 Q102 4 98 26 Z", fill: "paper" }],
  trucker: [{ d: "M58 30 Q58 14 80 14 Q102 14 102 30 Z", fill: "paper" }, { d: "M98 30 H116" }],
  warehouse: [{ d: rect(60, 104, 40, 30), fill: "paper" }, { d: "M60 114 H100" }],
  factory: [{ d: rect(60, 34, 40, 12, 5), fill: "paper" }],
  farmer: [{ d: "M44 30 H116 M62 30 Q62 12 80 12 Q98 12 98 30", fill: "paper" }],
  maintenance: [{ d: "M118 150 L136 122 M132 118 Q140 116 138 124 Q134 126 132 118" }],
  military: [
    { d: "M58 26 Q60 14 80 12 Q104 12 104 24 L100 30 H58 Z", fill: "paper" },
    { d: circle(92, 22, 2.5), fill: "ink" },
  ],
  athlete: [
    { d: circle(128, 146, 11), fill: "paper" },
    { d: "M117 146 H139 M128 135 Q121 146 128 157 M128 135 Q135 146 128 157" },
  ],
  caregiver: [{ d: "M80 104 Q70 94 74 88 Q78 84 80 90 Q82 84 86 88 Q90 94 80 104 Z", fill: "paper" }],
  parent: [
    { d: circle(132, 152, 9), fill: "paper" },
    { d: "M122 170 Q122 162 132 162 Q142 162 142 170 L142 212 H122 Z", fill: "paper" },
  ],
  student: [{ d: "M56 22 L80 12 L104 22 L80 32 Z", fill: "paper" }, { d: "M104 22 V32" }],
  retired: [{ d: circle(71, 42, 6) }, { d: circle(89, 42, 6) }, { d: "M77 42 H83" }],
  firefighter: [
    { d: "M54 34 Q54 12 80 12 Q106 12 106 34 Z", fill: "paper" },
    { d: "M48 34 H112 Q116 34 116 38" },
    { d: rect(74, 16, 12, 12, 2), fill: "paper" },
  ],
  mail: [
    { d: "M66 72 L106 136" },
    { d: rect(98, 128, 26, 20, 3), fill: "paper" },
    { d: "M98 134 H124" },
  ],
  software: [{ d: rect(114, 118, 30, 20, 2), fill: "paper" }, { d: "M110 140 H148" }],
  bus: [
    { d: "M58 30 Q58 14 80 14 Q102 14 102 30 Z", fill: "paper" },
    { d: "M62 30 H44" },
    { d: circle(80, 22, 2.5), fill: "ink" },
  ],
  hairstylist: [
    { d: circle(122, 152, 4) },
    { d: circle(132, 152, 4) },
    { d: "M124 148 L136 126 M130 148 L118 126" },
  ],
  accountant: [
    { d: rect(114, 118, 22, 30, 2), fill: "paper" },
    { d: rect(118, 122, 14, 6) },
    { d: "M119 134 H121 M124 134 H126 M129 134 H131 M119 140 H121 M124 140 H126 M129 140 H131" },
  ],
  barista: [
    { d: "M116 124 H134 L131 148 H119 Z", fill: "paper" },
    { d: "M134 129 Q142 132 133 140" },
    { d: "M122 118 Q120 114 123 110 M128 118 Q126 114 129 110" },
  ],
  social: [
    { d: rect(114, 116, 24, 32, 2), fill: "paper" },
    { d: "M121 116 V112 H131 V116" },
    { d: "M119 126 H133 M119 132 H133 M119 138 H129" },
  ],
  plumber: [{ d: "M128 112 V146" }, { d: "M118 152 Q118 144 128 144 Q138 144 138 152 Z", fill: "paper" }],
  pharmacist: [
    { d: rect(116, 126, 16, 22, 2), fill: "paper" },
    { d: rect(114, 120, 20, 6, 1), fill: "paper" },
    { d: "M119 134 H129 M119 139 H129" },
  ],
  childcare: [
    { d: rect(114, 136, 14, 14), fill: "paper" },
    { d: rect(128, 136, 14, 14), fill: "paper" },
    { d: rect(121, 122, 14, 14), fill: "paper" },
  ],
};

function Accessory({ roleId }: { roleId: string | null }) {
  const parts = roleId ? ACCESSORIES[roleId] : undefined;
  if (!parts) return null;
  return (
    <g stroke="currentColor" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round">
      {parts.map((part, i) => (
        <path
          key={i}
          d={part.d}
          fill={part.fill === "paper" ? "var(--story-page)" : part.fill === "ink" ? "currentColor" : "none"}
        />
      ))}
    </g>
  );
}

interface CanvasPerson {
  shards: Array<[PieceCategory, Path2D]>;
  silhouette: Path2D;
  head: Path2D;
  body: Path2D;
}
const canvasPeople = new Map<string, CanvasPerson>();

/**
 * Draw the finished person on a canvas, in figure units (the caller maps
 * the 160 x 224 figure box into place): the same mesh, colors, outline,
 * and accessory as the assembled <PersonFigure>, so the crowd can take the
 * reader's person over from the intro without a visible change.
 */
export function drawPerson(
  ctx: CanvasRenderingContext2D,
  o: {
    seed: number;
    readableCategories: readonly PieceCategory[];
    roleId: string | null;
    colorFor: (category: PieceCategory) => string;
    ink: string;
    paper: string;
    /** Line width in figure units (2 matches the SVG). */
    lineWidth: number;
  }
) {
  const key = `${o.seed}:${o.readableCategories.join(",")}`;
  let person = canvasPeople.get(key);
  if (!person) {
    const mesh = buildMesh(o.seed, o.readableCategories);
    const byCategory = new Map<PieceCategory, string>();
    for (const shard of mesh.shards) {
      const [a, b, c] = shard.points.split(" ");
      byCategory.set(shard.category, `${byCategory.get(shard.category) ?? ""}M${a} L${b} L${c} Z `);
    }
    const head = new Path2D(circle(HEAD.cx, HEAD.cy, HEAD.r));
    const body = new Path2D(BODY);
    const silhouette = new Path2D(head);
    silhouette.addPath(body);
    person = {
      shards: [...byCategory].map(([category, d]) => [category, new Path2D(d)]),
      silhouette,
      head,
      body,
    };
    // The reader, a dozen neighbor meshes, and room for state changes.
    if (canvasPeople.size > 32) canvasPeople.clear();
    canvasPeople.set(key, person);
  }

  ctx.save();
  ctx.clip(person.silhouette);
  for (const [category, path] of person.shards) {
    ctx.fillStyle = o.colorFor(category);
    ctx.fill(path);
  }
  ctx.restore();

  ctx.save();
  ctx.lineWidth = o.lineWidth;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.strokeStyle = o.ink;
  ctx.stroke(person.head);
  ctx.stroke(person.body);
  for (const part of (o.roleId ? ACCESSORIES[o.roleId] : undefined) ?? []) {
    const path = new Path2D(part.d);
    if (part.fill) {
      ctx.fillStyle = part.fill === "paper" ? o.paper : o.ink;
      ctx.fill(path);
    }
    ctx.stroke(path);
  }
  ctx.restore();
}
