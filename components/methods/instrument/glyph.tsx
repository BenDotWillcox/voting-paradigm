import { candidateColor, glyphShape, type GlyphShape } from "@/lib/methods/candidates";
import { cn } from "@/lib/utils";

/**
 * A candidate's glyph drawn inside an existing SVG, centered on (cx, cy)
 * with radius r. Fill is the candidate color; an ink outline keeps light
 * fills (C's yellow) visible against the surface.
 */
export function GlyphShapeSvg({
  id,
  cx,
  cy,
  r,
  strokeWidth = 1.5,
}: {
  id: string;
  cx: number;
  cy: number;
  r: number;
  strokeWidth?: number;
}) {
  const common = {
    fill: candidateColor(id),
    stroke: "var(--mi-ink)",
    strokeWidth,
    strokeLinejoin: "round" as const,
  };
  const shape: GlyphShape = glyphShape(id);
  if (shape === "circle") return <circle cx={cx} cy={cy} r={r * 0.92} {...common} />;
  if (shape === "square") {
    const s = r * 0.82;
    return <rect x={cx - s} y={cy - s} width={2 * s} height={2 * s} {...common} />;
  }
  return <polygon points={polygonPoints(shape, cx, cy, r)} {...common} />;
}

function polygonPoints(shape: GlyphShape, cx: number, cy: number, r: number): string {
  let points: [number, number][];
  if (shape === "triangle") {
    points = [-90, 30, 150].map((deg) => polar(cx, cy + r * 0.18, r * 1.08, deg));
  } else if (shape === "diamond") {
    points = [-90, 0, 90, 180].map((deg) => polar(cx, cy, r * 1.05, deg));
  } else {
    points = Array.from({ length: 10 }, (_, i) =>
      polar(cx, cy + r * 0.06, i % 2 === 0 ? r * 1.08 : r * 0.47, -90 + i * 36)
    );
  }
  return points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

function polar(cx: number, cy: number, r: number, deg: number): [number, number] {
  const rad = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

/** A standalone glyph, sized in pixels. Decorative unless given a title. */
export function CandidateGlyph({
  id,
  size = 14,
  title,
  className,
}: {
  id: string;
  size?: number;
  title?: string;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={cn("inline-block shrink-0 overflow-visible align-[-0.125em]", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
    >
      {title ? <title>{title}</title> : null}
      <GlyphShapeSvg id={id} cx={12} cy={12} r={9} strokeWidth={1.6} />
    </svg>
  );
}

/** Glyph plus letter: how a candidate is named everywhere in the instrument. */
export function CandidateMark({
  id,
  size = 14,
  className,
}: {
  id: string;
  size?: number;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1 font-mi-mono", className)}>
      <CandidateGlyph id={id} size={size} />
      <span>{id}</span>
    </span>
  );
}
