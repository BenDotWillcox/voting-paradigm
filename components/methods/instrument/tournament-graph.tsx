import { GlyphShapeSvg } from "./glyph";

const SIZE = 260;
const CENTER = SIZE / 2;
const RING = 92;
const NODE = 15;

/**
 * Head-to-head results as a tournament: candidates on a ring, an arrow from
 * each pairwise winner to the loser, labeled with the winning margin. A tie
 * is a dashed line. A majority cycle shows up as arrows chasing each other.
 */
export function TournamentGraph({
  candidates,
  pairwise,
  condorcetWinner,
  caption = true,
}: {
  candidates: string[];
  pairwise: Record<string, Record<string, number>>;
  condorcetWinner: string | null;
  /** Off where the page around the graph already explains how to read it. */
  caption?: boolean;
}) {
  const position = new Map(
    candidates.map((id, index) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * index) / candidates.length;
      return [id, [CENTER + RING * Math.cos(angle), CENTER + RING * Math.sin(angle)]] as const;
    })
  );

  const edges = candidates.flatMap((a, i) =>
    candidates.slice(i + 1).map((b) => {
      const margin = (pairwise[a]?.[b] ?? 0) - (pairwise[b]?.[a] ?? 0);
      return margin >= 0
        ? { from: a, to: b, margin, tie: margin === 0 }
        : { from: b, to: a, margin: -margin, tie: false };
    })
  );

  const description = edges
    .map((e) =>
      e.tie
        ? `${e.from} and ${e.to} tie`
        : `${e.from} beats ${e.to} by ${e.margin}`
    )
    .join("; ");

  return (
    <figure className="space-y-2">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="mi-grid-paper mx-auto block w-full max-w-[18rem] rounded-[3px]"
        role="img"
        aria-label={`Head-to-head results: ${description}.`}
      >
        <defs>
          <marker
            id="mi-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0,1 L9,5 L0,9 z" fill="var(--mi-ink)" />
          </marker>
        </defs>

        {edges.map((edge) => {
          const [x1, y1] = position.get(edge.from)!;
          const [x2, y2] = position.get(edge.to)!;
          const dx = x2 - x1;
          const dy = y2 - y1;
          const length = Math.hypot(dx, dy);
          const ux = dx / length;
          const uy = dy / length;
          const gap = NODE + 5;
          const start = [x1 + ux * gap, y1 + uy * gap];
          const end = [x2 - ux * (gap + 2), y2 - uy * (gap + 2)];
          // Label just off the line's midpoint, on its left
          const mx = (x1 + x2) / 2 - uy * 11;
          const my = (y1 + y2) / 2 + ux * 11;
          return (
            <g key={`${edge.from}-${edge.to}`}>
              <line
                x1={start[0]}
                y1={start[1]}
                x2={end[0]}
                y2={end[1]}
                stroke="var(--mi-ink)"
                strokeWidth={1.4}
                strokeDasharray={edge.tie ? "4 4" : undefined}
                markerEnd={edge.tie ? undefined : "url(#mi-arrow)"}
              />
              <text
                x={mx}
                y={my}
                textAnchor="middle"
                dominantBaseline="central"
                className="font-mi-mono"
                fontSize={12}
                fill="var(--mi-ink-2)"
                stroke="var(--mi-surface)"
                strokeWidth={4}
                paintOrder="stroke"
              >
                {edge.tie ? "tie" : edge.margin}
              </text>
            </g>
          );
        })}

        {candidates.map((id) => {
          const [x, y] = position.get(id)!;
          const labelX = CENTER + (x - CENTER) * 1.3;
          const labelY = CENTER + (y - CENTER) * 1.3;
          return (
            <g key={id}>
              {id === condorcetWinner ? (
                <circle
                  cx={x}
                  cy={y}
                  r={NODE + 5}
                  fill="none"
                  stroke="var(--mi-ink)"
                  strokeWidth={1.2}
                />
              ) : null}
              <GlyphShapeSvg id={id} cx={x} cy={y} r={NODE * 0.8} strokeWidth={1.4} />
              <text
                x={labelX}
                y={labelY}
                textAnchor="middle"
                dominantBaseline="central"
                className="font-mi-mono"
                fontSize={13}
                fontWeight={600}
                fill="var(--mi-ink)"
              >
                {id}
              </text>
            </g>
          );
        })}
      </svg>
      {caption ? (
        <figcaption className="text-xs leading-relaxed text-mi-muted">
          Arrows point from the head-to-head winner; numbers are winning margins.
          {condorcetWinner
            ? ` The ringed candidate beats every other: the Condorcet winner.`
            : " No candidate beats every other, so there is no Condorcet winner."}
        </figcaption>
      ) : null}
    </figure>
  );
}
