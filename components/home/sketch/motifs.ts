import { Sketch, ellipse, rng, type Group, type Stroke } from "./pencil";

/**
 * Abstract pencil sketches that loosely trace democracy, oldest first: an
 * Athenian urn taking voters' pebbles, a colonnade, a quill and
 * charter, a domed parliament, a sunrise of rights, marching banners, a
 * marked ballot, a network, and finally a growing tree beside sun, wind and
 * solar panels. They are moods, not illustrations: no labels, no dates.
 * Once drawn, parts of each keep moving: pebbles drop, flags wave, signals
 * pulse, turbines spin and the tree's leaves blow away. Smaller doodles
 * (a waving hand, a ballot box, speech bubbles, a sprout) come and go
 * between them.
 */

export interface Motif {
  id: string;
  width: number;
  height: number;
  strokes: Stroke[];
  groups: Group[];
}

type Draw = (s: Sketch, rand: () => number) => void;

const TAU = Math.PI * 2;

/** Athens: an urn taking the pebbles citizens voted with, more waiting on the ground. */
const athens: Draw = (s) => {
  s.line(34, 214, 206, 212, { wobble: 2, ghost: true });
  // The urn's right-hand profile, lip to foot; the left mirrors it.
  const right: [number, number][] = [
    [134, 72],
    [127, 82],
    [127, 98],
    [146, 110],
    [160, 132],
    [158, 160],
    [146, 184],
    [133, 198],
    [140, 208],
  ];
  s.curve(
    right.map(([x, y]) => [240 - x, y]),
    { width: 1.5, ghost: true, wobble: 0.6 }
  );
  s.curve(right, { width: 1.5, ghost: true, wobble: 0.6 });
  s.line(100, 208, 140, 208, { width: 1.4 });
  s.arc(120, 72, 15, 4.5, 0, TAU, { width: 1.2 });
  s.curve([[127, 86], [146, 80], [152, 96], [147, 110]], { width: 1.3, wobble: 0.4 });
  s.curve([[113, 86], [94, 80], [88, 96], [93, 110]], { width: 1.3, wobble: 0.4 });
  // A painted band with a key pattern around the belly.
  s.line(84, 126, 156, 126, { width: 1 });
  s.line(83, 154, 157, 154, { width: 1 });
  s.hatch(
    [
      [84, 127],
      [156, 127],
      [160, 140],
      [157, 153],
      [83, 153],
      [80, 140],
    ],
    0.5,
    3.6,
    { tone: "rose" }
  );
  const key: [number, number][] = [];
  for (let x = 86; x <= 150; x += 8) key.push([x, 147], [x, 133], [x + 4, 133], [x + 4, 147]);
  s.curve(key, { width: 0.9, wobble: 0.2 });
  // Pebbles on the ground: white for one choice, dark for the other.
  const ground: [number, number, number, boolean, "graphite" | "rose"][] = [
    [80, 205, 6, true, "graphite"],
    [93, 209, 5, false, "graphite"],
    [152, 206, 6, false, "rose"],
    [166, 209, 5, true, "graphite"],
  ];
  for (const [x, y, r, dark, tone] of ground) {
    s.circle(x, y, r, { tone, width: 1.2 });
    if (dark) s.hatch(ellipse(x, y, r * 0.85, r * 0.8), 0.7, 2.2);
  }
  // Pebbles falling into the urn, one after another.
  for (const [x, delay, dark] of [
    [116, 0, false],
    [123, 1.1, true],
    [119, 2.2, false],
  ] as [number, number, boolean][]) {
    s.moving({ kind: "drop", distance: 48, period: 3.3, delay }, () => {
      s.circle(x, 60, 4.5, { width: 1.1 });
      if (dark) s.hatch(ellipse(x, 60, 3.6, 3.4), 0.7, 2);
    });
  }
};

/** A republic's colonnade under its pediment. */
const columns: Draw = (s) => {
  s.line(36, 204, 204, 204, { ghost: true });
  s.line(42, 196, 198, 196);
  for (const x of [64, 102, 140, 178]) {
    s.line(x - 7, 194, x - 7, 98);
    s.line(x + 7, 194, x + 7, 98);
    s.line(x, 190, x, 102, { soft: true, width: 0.9 });
    s.line(x - 12, 96, x + 12, 96);
  }
  s.line(40, 88, 200, 88);
  s.line(44, 80, 196, 80);
  const pediment: [number, number][] = [
    [40, 80],
    [120, 40],
    [200, 80],
  ];
  s.curve([...pediment, [40, 80]], { wobble: 0.8, ghost: true });
  s.hatch(pediment, -0.5, 6, { tone: "sun" });
};

/** A quill and a charter, the age of written rights. */
const quill: Draw = (s, rand) => {
  s.line(70, 72, 182, 66);
  s.line(182, 66, 188, 186, { wobble: 2 });
  s.line(188, 186, 76, 192);
  s.line(76, 192, 70, 72, { wobble: 2 });
  s.arc(70, 64, 9, 9, Math.PI * 0.5, Math.PI * 2.2, { width: 1.2 });
  s.arc(188, 194, 9, 9, -Math.PI * 0.5, Math.PI * 1.2, { width: 1.2 });
  for (let i = 0; i < 6; i++) {
    const y = 92 + i * 16;
    const end = 168 - rand() * 34;
    const points: [number, number][] = [];
    for (let x = 88; x <= end; x += 6) points.push([x, y + Math.sin(x * 0.7 + i) * 1.6]);
    s.curve(points, { tone: "blue", width: 1, wobble: 0.3 });
  }
  // The feather: a curved spine with barbs swept back along it.
  const spine = (t: number): [number, number] => [42 + t * 150 + Math.sin(t * Math.PI) * 18, 222 - t * 190 - Math.sin(t * Math.PI) * 10];
  // The feather rocks on its nib, as if still writing.
  s.moving({ kind: "sway", pivot: spine(0), degrees: 5, period: 2.6 }, () => {
    s.curve(Array.from({ length: 9 }, (_, i) => spine(i / 8)), { ghost: true });
    for (let i = 0; i < 15; i++) {
      const t = 0.32 + i * 0.045;
      const [x, y] = spine(t);
      const reach = 16 * Math.sin(((t - 0.3) / 0.7) * Math.PI) + 4;
      s.line(x, y, x - reach * 0.9, y - reach * 0.2, { width: 0.9, soft: true });
      s.line(x, y, x + reach * 0.2, y + reach * 0.9, { width: 0.9, soft: true });
    }
  });
};

/** A parliament's dome over its drum and steps. */
const dome: Draw = (s) => {
  s.line(32, 206, 208, 206, { ghost: true });
  s.line(40, 196, 200, 196);
  s.line(50, 186, 190, 186);
  s.line(70, 186, 70, 142);
  s.line(170, 186, 170, 142);
  s.line(64, 142, 176, 142);
  for (let i = 0; i < 5; i++) s.arc(84 + i * 18, 172, 5, 7, Math.PI, TAU, { width: 1 });
  s.arc(120, 142, 50, 56, Math.PI, TAU, { ghost: true });
  for (const k of [-0.5, 0, 0.5]) s.curve([[120 + k * 70, 142], [120 + k * 46, 112], [120, 88]], { soft: true, width: 1 });
  s.hatch(ellipse(120, 142, 48, 54, Math.PI, TAU, 16), 0.9, 5, { tone: "aqua" });
  s.line(110, 86, 130, 86);
  s.arc(120, 86, 10, 12, Math.PI, TAU, { width: 1.2 });
  s.line(120, 74, 120, 46);
  s.moving({ kind: "wave", pivot: [120, 52], period: 1.4 }, () => s.curve([[120, 46], [142, 52], [120, 58]], { tone: "rose", width: 1.4 }));
};

/** A sunrise of rights over lines of print. */
const sunrise: Draw = (s, rand) => {
  s.line(26, 168, 214, 168, { ghost: true });
  s.moving({ kind: "bob", distance: 3, period: 4.2 }, () => {
    s.arc(120, 168, 38, 38, Math.PI, TAU, { tone: "sun", width: 1.8, ghost: true });
    s.hatch(ellipse(120, 168, 36, 36, Math.PI, TAU, 16), 0.35, 4.5, { tone: "sun" });
  });
  // The rays fan slowly back and forth.
  s.moving({ kind: "sway", pivot: [120, 168], degrees: 4, period: 5 }, () => {
    for (let i = 0; i <= 10; i++) {
      const a = Math.PI * 1.06 + (i / 10) * Math.PI * 0.88;
      const length = 22 + rand() * 30;
      s.line(120 + Math.cos(a) * 48, 168 + Math.sin(a) * 48, 120 + Math.cos(a) * (48 + length), 168 + Math.sin(a) * (48 + length), { width: 1.1 });
    }
  });
  for (let row = 0; row < 3; row++) {
    let x = 48;
    while (x < 186) {
      const w = 8 + rand() * 22;
      s.line(x, 184 + row * 10, Math.min(x + w, 192), 184 + row * 10, { width: 1, soft: true, wobble: 0.4 });
      x += w + 5;
    }
  }
};

/** Banners carried in a march, and a ribbon running through them. */
const banners: Draw = (s) => {
  const flags: [number, number, number, "violet" | "rose" | "sun" | "aqua"][] = [
    [52, 74, -0.12, "violet"],
    [96, 52, 0.04, "rose"],
    [140, 66, -0.05, "sun"],
    [184, 84, 0.1, "aqua"],
  ];
  flags.forEach(([x, top, lean, tone], i) => {
    const tipX = x + lean * 150;
    s.line(x, 214, tipX, top, { width: 1.5 });
    const cloth: [number, number][] = [
      [tipX, top + 2],
      [tipX + 46, top + 18],
      [tipX + 2, top + 38],
    ];
    s.moving({ kind: "wave", pivot: [tipX, top + 20], period: 1.2 + i * 0.17 }, () => {
      s.curve([...cloth, cloth[0]], { tone, width: 1.4, wobble: 0.8 });
      s.hatch(cloth, 0.9, 3.6, { tone });
    });
  });
  s.moving({ kind: "bob", distance: 4, period: 3 }, () =>
    s.curve([[22, 178], [70, 150], [120, 172], [170, 140], [218, 150]], { tone: "rose", width: 1.6, ghost: true })
  );
};

/** A ballot, one oval filled in. */
const ballot: Draw = (s) => s.moving({ kind: "bob", distance: 3, period: 3.4 }, () => ballotLines(s));

function ballotLines(s: Sketch) {
  const corner = (x: number, y: number): [number, number] => {
    const a = -0.08;
    return [120 + (x - 120) * Math.cos(a) - (y - 125) * Math.sin(a), 125 + (x - 120) * Math.sin(a) + (y - 125) * Math.cos(a)];
  };
  const [a, b, c, d, e] = [corner(56, 44), corner(170, 44), corner(186, 60), corner(186, 206), corner(56, 206)];
  s.line(...a, ...b);
  s.line(...b, ...c);
  s.line(...c, ...d, { wobble: 2 });
  s.line(...d, ...e);
  s.line(...e, ...a, { wobble: 2 });
  const fold = corner(170, 60);
  s.curve([b, fold, c], { soft: true, width: 1 });
  s.line(...corner(72, 64), ...corner(150, 64), { width: 2 });
  for (let row = 0; row < 4; row++) {
    const [ox, oy] = corner(80, 92 + row * 30);
    s.circle(ox, oy, 8, { width: 1.1 });
    const [lx, ly] = corner(98, 92 + row * 30);
    const [rx, ry] = corner(166 - row * 9, 92 + row * 30);
    s.line(lx, ly, rx, ry, { width: 1, soft: true });
    if (row === 1) s.scribble(ox, oy, 7, 5);
  }
  const [cx, cy] = corner(196, 116);
  s.moving({ kind: "pulse", pivot: [cx, cy], period: 1.8 }, () =>
    s.curve([[cx - 10, cy], [cx - 4, cy + 8], [cx + 10, cy - 12]], { tone: "blue", width: 2, wobble: 0.4 })
  );
}

/** Connected people: nodes and links, with a signal spreading from one of them. */
const network: Draw = (s, rand) => {
  const nodes: [number, number][] = [];
  while (nodes.length < 11) {
    const p: [number, number] = [36 + rand() * 168, 40 + rand() * 160];
    if (nodes.every(([x, y]) => Math.hypot(x - p[0], y - p[1]) > 34)) nodes.push(p);
  }
  const drawn = new Set<string>();
  nodes.forEach((p, i) => {
    const near = nodes
      .map((q, j) => [j, Math.hypot(q[0] - p[0], q[1] - p[1])] as const)
      .filter(([j]) => j !== i)
      .sort((u, v) => u[1] - v[1])
      .slice(0, 2);
    for (const [j] of near) {
      const key = [i, j].sort().join("-");
      if (drawn.has(key)) continue;
      drawn.add(key);
      s.line(p[0], p[1], nodes[j][0], nodes[j][1], { width: 1, wobble: 1.5 });
    }
  });
  nodes.forEach(([x, y], i) => {
    const r = 5 + (i % 3) * 1.6;
    s.circle(x, y, r, { tone: i % 4 === 0 ? "blue" : "graphite", width: 1.2 });
    if (i % 4 === 0) s.hatch(ellipse(x, y, r * 0.8, r * 0.8), -0.6, 2.2, { tone: "blue" });
  });
  const [hx, hy] = nodes[0];
  s.moving({ kind: "pulse", pivot: [hx, hy], period: 2.2 }, () => {
    for (const r of [16, 24, 32]) s.arc(hx, hy, r, r, -1.1, 0.2, { tone: "aqua", width: 1.1 });
  });
};

/** The future, part one: a tree growing branch by branch, in leaf and blossom, that sheds leaves into the wind. */
const tree: Draw = (s, rand) => {
  s.curve([[20, 300], [90, 292], [150, 296], [220, 290], [282, 298]], { ghost: true, wobble: 2 });
  for (let i = 0; i < 16; i++) {
    const x = 30 + rand() * 240;
    s.line(x, 298, x + (rand() - 0.5) * 6, 286 - rand() * 8, { tone: "green", width: 0.9, soft: true });
  }
  s.moving({ kind: "sway", pivot: [150, 296], degrees: 1.4, period: 4.6 }, () => {
    // Grow breadth-first, so the tree rises the way it would.
    let tips: { x: number; y: number; angle: number; length: number }[] = [{ x: 150, y: 296, angle: -Math.PI / 2, length: 64 }];
    const leaves: [number, number, number][] = [];
    for (let depth = 0; depth < 5; depth++) {
      const next: typeof tips = [];
      for (const tip of tips) {
        const x2 = tip.x + Math.cos(tip.angle) * tip.length;
        const y2 = tip.y + Math.sin(tip.angle) * tip.length;
        const bend = (rand() - 0.5) * tip.length * 0.25;
        s.curve(
          [
            [tip.x, tip.y],
            [(tip.x + x2) / 2 + bend, (tip.y + y2) / 2],
            [x2, y2],
          ],
          { width: Math.max(0.9, 2.4 - depth * 0.35), wobble: 0.6 }
        );
        if (depth === 4) leaves.push([x2, y2, tip.angle]);
        else
          for (const turn of [-1, 1]) next.push({ x: x2, y: y2, angle: tip.angle + turn * (0.32 + rand() * 0.28), length: tip.length * (0.68 + rand() * 0.1) });
      }
      tips = next;
    }
    let flown = 0;
    leaves.forEach(([x, y, angle], i) => {
      const tone = i % 7 === 0 ? "rose" : i % 9 === 0 ? "sun" : "green";
      const ax = Math.cos(angle);
      const ay = Math.sin(angle);
      const tipX = x + ax * 14;
      const tipY = y + ay * 14;
      const leaf = () => {
        s.curve([[x, y], [x + ax * 7 - ay * 5, y + ay * 7 + ax * 5], [tipX, tipY], [x + ax * 7 + ay * 5, y + ay * 7 - ax * 5], [x, y]], { tone, width: 1.1, wobble: 0.3 });
        if (i % 2 === 0) s.line(x, y, tipX, tipY, { tone, width: 0.8, soft: true, wobble: 0.3 });
      };
      // Every third leaf lets go, one after another, and blows off downwind.
      if (i % 3 === 1) {
        const delay = 0.6 + flown++ * 0.85;
        s.moving({ kind: "fly", pivot: [x, y], to: [90 + rand() * 140, -20 + rand() * 150], turn: 200 + rand() * 400, delay, duration: 4.2 + rand() * 1.6 }, leaf);
      } else leaf();
    });
  });
};

/** The future, part two: a turning sun, two spinning turbines and solar panels, wound with a vine. */
const sunAndWind: Draw = (s, rand) => {
  s.moving({ kind: "spin", pivot: [196, 62], period: 40 }, () => {
    const spiral: [number, number][] = [];
    for (let a = 0; a < TAU * 2.6; a += 0.35) spiral.push([196 + Math.cos(a) * (3 + a * 3.6), 62 + Math.sin(a) * (3 + a * 3.6)]);
    s.curve(spiral, { tone: "sun", width: 1.4, wobble: 0.4 });
    for (let i = 0; i < 9; i++) {
      const a = (i / 9) * TAU;
      s.line(196 + Math.cos(a) * 40, 62 + Math.sin(a) * 40, 196 + Math.cos(a) * (50 + rand() * 10), 62 + Math.sin(a) * (50 + rand() * 10), { tone: "sun", width: 1.1 });
    }
  });
  for (const [x, h, period] of [
    [58, 150, 3.4],
    [112, 118, 4.3],
  ]) {
    const top = 236 - h;
    s.line(x - 3, 236, x, top, { width: 1.4 });
    s.line(x + 3, 236, x, top, { width: 1 });
    s.moving({ kind: "spin", pivot: [x, top], period }, () => {
      s.circle(x, top, 3.5, { width: 1.1 });
      for (let k = 0; k < 3; k++) {
        const a = (k / 3) * TAU - Math.PI / 2 + 0.3;
        const tipX = x + Math.cos(a) * 46;
        const tipY = top + Math.sin(a) * 46;
        s.curve([[x, top], [x + Math.cos(a + 0.18) * 26, top + Math.sin(a + 0.18) * 26], [tipX, tipY]], { width: 1.2, wobble: 0.4 });
      }
    });
  }
  // Solar panels, gridded in blue.
  const panel: [number, number][] = [
    [148, 196],
    [222, 182],
    [234, 212],
    [160, 226],
  ];
  s.curve([...panel, panel[0]], { tone: "blue", width: 1.4, wobble: 0.5 });
  for (let k = 1; k < 4; k++) {
    const t = k / 4;
    s.line(148 + 74 * t, 196 - 14 * t, 160 + 74 * t, 226 - 14 * t, { tone: "blue", width: 0.9, soft: true });
  }
  s.line(154, 211, 228, 197, { tone: "blue", width: 0.9, soft: true });
  s.line(190, 220, 192, 240, { width: 1.2 });
  // A vine curling up the nearer turbine, its leaves fluttering.
  const vine: [number, number][] = [];
  for (let y = 236; y > 140; y -= 6) vine.push([112 + Math.sin(y * 0.18) * 7, y]);
  s.curve(vine, { tone: "green", width: 1.2, wobble: 0.3 });
  for (let i = 0; i < 6; i++) {
    const y = 226 - i * 15;
    const x = 112 + Math.sin(y * 0.18) * 7;
    const side = i % 2 ? 1 : -1;
    s.moving({ kind: "wave", pivot: [x, y], period: 1.6 + i * 0.13 }, () =>
      s.curve([[x, y], [x + side * 8, y - 6], [x + side * 13, y - 2], [x, y]], { tone: "green", width: 1, wobble: 0.3 })
    );
  }
  s.line(10, 238, 250, 236, { ghost: true, wobble: 2 });
};

function make(id: string, seed: number, width: number, height: number, draw: Draw): Motif {
  const rand = rng(seed);
  const sketch = new Sketch(rand);
  draw(sketch, rand);
  return { id, width, height, strokes: sketch.strokes, groups: sketch.groups };
}

/** Oldest first. The last two are drawn together as the finale. */
export const MOTIFS: Motif[] = [
  make("athens", 11, 240, 240, athens),
  make("columns", 23, 240, 240, columns),
  make("quill", 37, 240, 240, quill),
  make("dome", 41, 240, 240, dome),
  make("sunrise", 53, 240, 240, sunrise),
  make("banners", 67, 240, 240, banners),
  make("ballot", 71, 240, 240, ballot),
  make("network", 89, 240, 240, network),
  make("tree", 97, 300, 320, tree),
  make("sun-and-wind", 103, 260, 250, sunAndWind),
];

/** A raised hand, waving: the oldest way to vote. */
const hand: Draw = (s) =>
  s.moving({ kind: "sway", pivot: [63, 118], degrees: 9, period: 1.2 }, () => {
    s.curve([[42, 70], [42, 96], [56, 106], [76, 104], [84, 88], [84, 66]], { width: 1.4, wobble: 0.4 });
    [6, 0, 3, 10].forEach((drop, i) => {
      const x = 44 + i * 10;
      const top = 24 + drop;
      s.curve([[x, 70], [x, top + 4], [x + 4, top], [x + 8, top + 4], [x + 8, 70]], { width: 1.2, wobble: 0.3 });
    });
    s.curve([[42, 78], [30, 66], [26, 57], [33, 53], [44, 66]], { width: 1.2, wobble: 0.3 });
    s.line(52, 106, 51, 120, { width: 1.1 });
    s.line(75, 104, 76, 120, { width: 1.1 });
  });

/** A ballot box taking an envelope. */
const box: Draw = (s) => {
  s.curve([[28, 62], [92, 60], [94, 106], [26, 108], [28, 62]], { width: 1.4, ghost: true, wobble: 0.6 });
  s.line(46, 61, 74, 60, { width: 2.2 });
  s.line(44, 86, 76, 85, { width: 1, soft: true });
  s.moving({ kind: "drop", distance: 26, period: 2.6, delay: 0 }, () => {
    s.curve([[48, 36], [72, 35], [73, 52], [47, 53], [48, 36]], { tone: "blue", width: 1.2, wobble: 0.3 });
    s.curve([[48, 36], [60, 45], [72, 35]], { tone: "blue", width: 1, wobble: 0.2 });
  });
};

/** Two speech bubbles, one still thinking. */
const talk: Draw = (s) => {
  s.curve([...ellipse(44, 56, 30, 22, 2.2, 2.2 + Math.PI * 1.85, 18), [22, 82], [36, 74]], { width: 1.3, wobble: 0.5 });
  // The thinking dots bob one after another.
  [34, 44, 54].forEach((x, i) => s.moving({ kind: "bob", distance: 3, period: 0.9 + i * 0.12 }, () => s.circle(x, 57, 2.6, { width: 1.1 })));
  s.curve([...ellipse(86, 38, 22, 16, -2.4, -2.4 + Math.PI * 1.85, 14), [104, 58], [96, 50]], { tone: "blue", width: 1.2, wobble: 0.4 });
};

/** A sprout, opening its leaves. */
const sprout: Draw = (s) => {
  s.curve([[18, 98], [60, 93], [102, 98]], { width: 1.2, ghost: true, wobble: 1 });
  s.curve([[60, 95], [57, 76], [62, 52]], { tone: "green", width: 1.4, wobble: 0.3 });
  s.moving({ kind: "wave", pivot: [59, 72], period: 1.8 }, () =>
    s.curve([[59, 72], [44, 62], [34, 66], [46, 75], [59, 72]], { tone: "green", width: 1.2, wobble: 0.3 })
  );
  s.moving({ kind: "wave", pivot: [61, 62], period: 2.1 }, () =>
    s.curve([[61, 62], [78, 50], [88, 54], [76, 65], [61, 62]], { tone: "green", width: 1.2, wobble: 0.3 })
  );
  s.moving({ kind: "pulse", pivot: [62, 48], period: 1.6 }, () => s.circle(62, 47, 4.5, { tone: "rose", width: 1.2 }));
};

/** A ticked box. */
const tick: Draw = (s) => {
  s.curve([[26, 30], [92, 27], [95, 94], [28, 97], [26, 30]], { width: 1.4, ghost: true, wobble: 0.6 });
  s.moving({ kind: "pulse", pivot: [62, 60], period: 1.5 }, () =>
    s.curve([[38, 60], [54, 78], [88, 34]], { tone: "blue", width: 2.4, wobble: 0.4 })
  );
};

/** A small sparkle, turning. */
const sparkle: Draw = (s) => {
  s.moving({ kind: "spin", pivot: [60, 60], period: 14 }, () => {
    s.curve([[60, 18], [67, 53], [102, 60], [67, 67], [60, 102], [53, 67], [18, 60], [53, 53], [60, 18]], { tone: "sun", width: 1.4, wobble: 0.4 });
  });
  s.circle(94, 28, 3, { tone: "sun", width: 1 });
  s.circle(26, 96, 2.4, { tone: "sun", width: 1 });
};

/** Small doodles for the open paper along the top, in no particular order. */
export const DOODLES: Motif[] = [
  make("hand", 201, 120, 124, hand),
  make("box", 203, 120, 120, box),
  make("talk", 207, 120, 120, talk),
  make("sprout", 211, 120, 110, sprout),
  make("tick", 213, 120, 120, tick),
  make("sparkle", 217, 120, 120, sparkle),
];
