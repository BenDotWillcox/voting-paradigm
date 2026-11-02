"use client";

import * as React from "react";

import { CIRCUIT_COLORS } from "@/lib/districts-palette";

const PITCH = 28;
const SEED = 0x2020_0435;
const FRAME_MS = 1000 / 30;
const TAIL = 56;
const GLOW_RADIUS = 11;
const FLASH_SECONDS = 0.7;
const CARDINAL: readonly Point[] = [[1, 0], [0, 1], [-1, 0], [0, -1]];

type Point = readonly [number, number];
interface Trace { points: Point[]; offsets: number[]; total: number; alpha: number }
interface Electron { trace: number; s: number; speed: number; wait: number }
interface Flash { x: number; y: number; age: number }

function mulberry32(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Orthogonal runs joined by 45° chamfers, as on a printed circuit board. No two
 * traces share a grid node, and the same seed and size always give the same board. */
export function generateBoard(width: number, height: number, seed = SEED): Trace[] {
  const random = mulberry32(seed);
  const cols = Math.ceil(width / PITCH) + 1, rows = Math.ceil(height / PITCH) + 1;
  const used = new Set<number>();
  const free = (x: number, y: number) => x >= 0 && y >= 0 && x < cols && y < rows && !used.has(y * cols + x);
  const traces: Trace[] = [];
  for (let attempt = 0, attempts = Math.round(cols * rows / 5); attempt < attempts; attempt++) {
    let x = Math.floor(random() * cols), y = Math.floor(random() * rows);
    if (!free(x, y)) continue;
    used.add(y * cols + x);
    const nodes: Point[] = [[x, y]];
    let direction = Math.floor(random() * 4);
    const segments = 1 + Math.floor(random() * 3);
    for (let segment = 0; segment < segments; segment++) {
      const [dx, dy] = CARDINAL[direction];
      let blocked = false;
      for (let step = 0, run = 3 + Math.floor(random() * 8); step < run; step++) {
        if (!free(x + dx, y + dy)) { blocked = true; break; }
        x += dx; y += dy; used.add(y * cols + x); nodes.push([x, y]);
      }
      if (blocked || segment === segments - 1) break;
      const next = (direction + (random() < 0.5 ? 1 : 3)) % 4;
      const [nx, ny] = CARDINAL[next];
      for (let step = 0, run = 1 + Math.floor(random() * 2); step < run; step++) {
        if (!free(x + dx + nx, y + dy + ny)) { blocked = true; break; }
        x += dx + nx; y += dy + ny; used.add(y * cols + x); nodes.push([x, y]);
      }
      if (blocked) break;
      direction = next;
    }
    if (nodes.length < 5) continue;
    // Keep only corners; the electron path and the stroke are the same polyline.
    const corners = nodes.filter((node, i) => {
      if (i === 0 || i === nodes.length - 1) return true;
      const [px, py] = nodes[i - 1], [qx, qy] = nodes[i + 1];
      return node[0] - px !== qx - node[0] || node[1] - py !== qy - node[1];
    });
    const points = corners.map(([cx, cy]) => [cx * PITCH + PITCH / 2, cy * PITCH + PITCH / 2] as const);
    const offsets = [0];
    for (let i = 1; i < points.length; i++) {
      offsets.push(offsets[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
    }
    traces.push({ points, offsets, total: offsets[offsets.length - 1], alpha: 0.55 + random() * 0.45 });
  }
  return traces;
}

function pointAt(trace: Trace, s: number): Point {
  let i = 1;
  while (i < trace.offsets.length - 1 && trace.offsets[i] < s) i++;
  const [ax, ay] = trace.points[i - 1], [bx, by] = trace.points[i];
  const span = trace.offsets[i] - trace.offsets[i - 1] || 1;
  const t = Math.min(1, Math.max(0, (s - trace.offsets[i - 1]) / span));
  return [ax + (bx - ax) * t, ay + (by - ay) * t];
}

function rgba(hex: string, alpha: number) {
  const value = Number.parseInt(hex.slice(1), 16);
  return `rgba(${value >> 16}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

/**
 * Decorative backdrop for the districting demo: electrons pulse along a seeded
 * circuit board, a reminder that the maps come from an algorithm. Renders one
 * static frame for viewers who prefer reduced motion.
 */
export function CircuitBackdrop() {
  const frameRef = React.useRef<HTMLDivElement>(null);
  const boardRef = React.useRef<HTMLCanvasElement>(null);
  const signalRef = React.useRef<HTMLCanvasElement>(null);

  React.useEffect(() => {
    const frame = frameRef.current, boardCanvas = boardRef.current, signalCanvas = signalRef.current;
    const board = boardCanvas?.getContext("2d"), signal = signalCanvas?.getContext("2d");
    if (!frame || !boardCanvas || !signalCanvas || !board || !signal) return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const random = mulberry32(SEED ^ 0x9e3779b9);
    let traces: Trace[] = [], electrons: Electron[] = [], flashes: Flash[] = [];
    let width = 0, height = 0, raf = 0, last = 0;

    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const glow = document.createElement("canvas");
    glow.width = glow.height = Math.ceil(GLOW_RADIUS * 2 * ratio);
    const glowContext = glow.getContext("2d");
    if (glowContext) {
      const c = glow.width / 2, gradient = glowContext.createRadialGradient(c, c, 0, c, c, c);
      gradient.addColorStop(0, rgba(CIRCUIT_COLORS.glow, 0.95));
      gradient.addColorStop(0.35, rgba(CIRCUIT_COLORS.glow, 0.55));
      gradient.addColorStop(1, rgba(CIRCUIT_COLORS.glow, 0));
      glowContext.fillStyle = gradient;
      glowContext.fillRect(0, 0, glow.width, glow.height);
    }

    const spawn = (staggered: boolean): Electron => {
      const trace = Math.floor(random() * traces.length);
      return { trace, s: staggered ? random() * traces[trace].total : 0, speed: 45 + random() * 55, wait: staggered ? 0 : 0.2 + random() * 1.4 };
    };

    const drawBoard = () => {
      board.setTransform(ratio, 0, 0, ratio, 0, 0);
      board.clearRect(0, 0, width, height);
      board.lineCap = "round"; board.lineJoin = "round"; board.strokeStyle = CIRCUIT_COLORS.trace;
      for (const trace of traces) {
        board.globalAlpha = trace.alpha; board.lineWidth = 1.5; board.beginPath();
        trace.points.forEach(([x, y], i) => i ? board.lineTo(x, y) : board.moveTo(x, y));
        board.stroke();
        for (const [x, y] of [trace.points[0], trace.points[trace.points.length - 1]]) {
          board.beginPath(); board.arc(x, y, 3.5, 0, Math.PI * 2);
          board.fillStyle = CIRCUIT_COLORS.board; board.fill(); board.stroke();
        }
      }
      board.globalAlpha = 1;
    };

    const drawSignals = () => {
      signal.setTransform(ratio, 0, 0, ratio, 0, 0);
      signal.clearRect(0, 0, width, height);
      signal.lineCap = "round"; signal.lineJoin = "round";
      for (const electron of electrons) {
        if (electron.wait > 0) continue;
        const trace = traces[electron.trace];
        const head = Math.min(electron.s, trace.total), tail = Math.max(0, electron.s - TAIL);
        if (head <= tail) continue;
        const start = pointAt(trace, tail), end = pointAt(trace, head);
        const gradient = signal.createLinearGradient(start[0], start[1], end[0], end[1]);
        gradient.addColorStop(0, rgba(CIRCUIT_COLORS.tail, 0));
        gradient.addColorStop(1, rgba(CIRCUIT_COLORS.tail, 0.95));
        signal.strokeStyle = gradient; signal.lineWidth = 2; signal.beginPath(); signal.moveTo(start[0], start[1]);
        for (let i = 1; i < trace.points.length - 1; i++) {
          if (trace.offsets[i] > tail && trace.offsets[i] < head) signal.lineTo(trace.points[i][0], trace.points[i][1]);
        }
        signal.lineTo(end[0], end[1]); signal.stroke();
        if (electron.s <= trace.total) {
          signal.drawImage(glow, end[0] - GLOW_RADIUS, end[1] - GLOW_RADIUS, GLOW_RADIUS * 2, GLOW_RADIUS * 2);
          signal.fillStyle = CIRCUIT_COLORS.core; signal.beginPath(); signal.arc(end[0], end[1], 1.6, 0, Math.PI * 2); signal.fill();
        }
      }
      for (const flash of flashes) {
        const progress = flash.age / FLASH_SECONDS;
        signal.globalAlpha = 1 - progress;
        signal.drawImage(glow, flash.x - GLOW_RADIUS * 1.4, flash.y - GLOW_RADIUS * 1.4, GLOW_RADIUS * 2.8, GLOW_RADIUS * 2.8);
        signal.strokeStyle = CIRCUIT_COLORS.tail; signal.lineWidth = 1.5;
        signal.beginPath(); signal.arc(flash.x, flash.y, 3.5 + progress * 10, 0, Math.PI * 2); signal.stroke();
      }
      signal.globalAlpha = 1;
    };

    const step = (seconds: number) => {
      for (const electron of electrons) {
        if (electron.wait > 0) { electron.wait -= seconds; continue; }
        electron.s += electron.speed * seconds;
        const trace = traces[electron.trace];
        if (electron.s - seconds * electron.speed <= trace.total && electron.s > trace.total) {
          const [x, y] = trace.points[trace.points.length - 1];
          flashes.push({ x, y, age: 0 });
        }
        if (electron.s - TAIL > trace.total) Object.assign(electron, spawn(false));
      }
      flashes = flashes.filter((flash) => (flash.age += seconds) < FLASH_SECONDS);
    };

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (now - last < FRAME_MS) return;
      const seconds = Math.min(now - last, 100) / 1000;
      last = now;
      step(seconds);
      drawSignals();
    };

    const start = () => {
      cancelAnimationFrame(raf);
      drawSignals();
      if (!motion.matches) { last = performance.now(); raf = requestAnimationFrame(tick); }
    };

    const layout = () => {
      const rect = frame.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      width = rect.width; height = rect.height;
      for (const canvas of [boardCanvas, signalCanvas]) {
        canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      }
      traces = generateBoard(width, height);
      flashes = [];
      electrons = traces.length ? Array.from({ length: Math.min(28, Math.round(traces.length / 3)) }, () => spawn(true)) : [];
      drawBoard();
      start();
    };

    const observer = new ResizeObserver(layout);
    observer.observe(frame);
    motion.addEventListener("change", start);
    return () => { cancelAnimationFrame(raf); observer.disconnect(); motion.removeEventListener("change", start); };
  }, []);

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
      <div ref={frameRef} className="sticky top-0 h-dvh w-full opacity-90">
        <canvas ref={boardRef} className="absolute inset-0 h-full w-full" />
        <canvas ref={signalRef} className="absolute inset-0 h-full w-full" />
      </div>
    </div>
  );
}
