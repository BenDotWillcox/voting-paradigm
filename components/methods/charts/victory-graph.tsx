"use client";

import { CandidateData } from "@/types/methods";

interface VictoryGraphProps {
  candidates: CandidateData[];
  lockedVictories: [string, string, number][];
  skippedVictories: [string, string, number][];
  winners: string[];
}

export function VictoryGraph({
  candidates,
  lockedVictories,
  skippedVictories,
  winners,
}: VictoryGraphProps) {
  const winnerSet = new Set(winners);
  const n = candidates.length;
  const cx = 200;
  const cy = 180;
  const r = 120;

  // Position candidates in a ring
  const positions = candidates.map((c, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    return {
      id: c.id,
      name: c.name,
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    };
  });

  const posMap = new Map(positions.map((p) => [p.id, p]));

  // Compute arrowhead offset (move endpoint slightly back from center)
  const nodeRadius = 28;

  function getEdgePoints(fromId: string, toId: string) {
    const from = posMap.get(fromId)!;
    const to = posMap.get(toId)!;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    const ux = dx / dist;
    const uy = dy / dist;
    return {
      x1: from.x + ux * nodeRadius,
      y1: from.y + uy * nodeRadius,
      x2: to.x - ux * nodeRadius,
      y2: to.y - uy * nodeRadius,
    };
  }

  return (
    <div className="flex justify-center">
      <svg
        viewBox="0 0 400 360"
        className="w-full max-w-[400px] h-auto"
      >
        <defs>
          <marker
            id="arrowhead-locked"
            markerWidth="8"
            markerHeight="6"
            refX="8"
            refY="3"
            orient="auto"
          >
            <polygon
              points="0 0, 8 3, 0 6"
              className="fill-green-600 dark:fill-green-400"
            />
          </marker>
          <marker
            id="arrowhead-skipped"
            markerWidth="8"
            markerHeight="6"
            refX="8"
            refY="3"
            orient="auto"
          >
            <polygon
              points="0 0, 8 3, 0 6"
              className="fill-red-400 dark:fill-red-500"
            />
          </marker>
        </defs>

        {/* Skipped edges (drawn first, behind locked) */}
        {skippedVictories.map(([from, to, margin], i) => {
          const pts = getEdgePoints(from, to);
          return (
            <g key={`skip-${i}`}>
              <line
                {...pts}
                className="stroke-red-400 dark:stroke-red-500"
                strokeWidth={1.5}
                strokeDasharray="6 4"
                markerEnd="url(#arrowhead-skipped)"
              />
              <text
                x={(pts.x1 + pts.x2) / 2 + 8}
                y={(pts.y1 + pts.y2) / 2 - 4}
                className="fill-red-500 dark:fill-red-400 text-[10px]"
                textAnchor="middle"
              >
                +{margin}
              </text>
            </g>
          );
        })}

        {/* Locked edges */}
        {lockedVictories.map(([from, to, margin], i) => {
          const pts = getEdgePoints(from, to);
          return (
            <g key={`lock-${i}`}>
              <line
                {...pts}
                className="stroke-green-600 dark:stroke-green-400"
                strokeWidth={2}
                markerEnd="url(#arrowhead-locked)"
              />
              <text
                x={(pts.x1 + pts.x2) / 2 + 8}
                y={(pts.y1 + pts.y2) / 2 - 4}
                className="fill-green-700 dark:fill-green-300 text-[10px]"
                textAnchor="middle"
              >
                +{margin}
              </text>
            </g>
          );
        })}

        {/* Candidate nodes */}
        {positions.map((p) => (
          <g key={p.id}>
            <circle
              cx={p.x}
              cy={p.y}
              r={nodeRadius}
              className={
                winnerSet.has(p.id)
                  ? "fill-primary stroke-primary"
                  : "fill-muted stroke-border"
              }
              strokeWidth={2}
            />
            <text
              x={p.x}
              y={p.y}
              textAnchor="middle"
              dominantBaseline="central"
              className={
                winnerSet.has(p.id)
                  ? "fill-primary-foreground text-[11px] font-bold"
                  : "fill-foreground text-[11px]"
              }
            >
              {p.name.length > 8 ? p.id : p.name}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
