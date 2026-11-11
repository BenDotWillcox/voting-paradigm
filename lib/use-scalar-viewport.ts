"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ScalarGraphRange } from "@/lib/expressive-scalar-graph";

type ViewportFrame = {
  view: ScalarGraphRange;
  from: ScalarGraphRange;
  target: ScalarGraphRange;
  progress: number;
};

const DURATION_MS = 420;
const sameRange = (a: ScalarGraphRange, b: ScalarGraphRange) => a.minimum === b.minimum && a.maximum === b.maximum;
const settled = (view: ScalarGraphRange): ViewportFrame => ({ view, from: view, target: view, progress: 1 });

/** One animated domain drives the curve, controls, and axis on the same frame. */
export function useScalarViewport(initial: ScalarGraphRange) {
  const [frame, setFrame] = useState<ViewportFrame>(() => settled({ ...initial }));
  const current = useRef(frame);
  const pendingFrame = useRef<number | null>(null);
  const generation = useRef(0);
  const reducedMotion = useRef(false);

  const commit = useCallback((next: ViewportFrame) => {
    current.current = next;
    setFrame(next);
  }, []);

  const cancel = useCallback(() => {
    generation.current += 1;
    if (pendingFrame.current !== null) cancelAnimationFrame(pendingFrame.current);
    pendingFrame.current = null;
  }, []);

  const stop = useCallback(() => {
    cancel();
    const view = current.current.view;
    commit(settled(view));
    return view;
  }, [cancel, commit]);

  const setView = useCallback((next: ScalarGraphRange, options?: { immediate?: boolean }) => {
    if (!Number.isFinite(next.minimum) || !Number.isFinite(next.maximum) || next.minimum < 0 || next.maximum > 100 || next.minimum >= next.maximum) {
      throw new RangeError("A scalar viewport must increase within 0–100.");
    }
    // Repeated clicks on the same destination should not slow the transition.
    if (!options?.immediate && !reducedMotion.current && current.current.progress < 1 && sameRange(next, current.current.target)) return;
    cancel();
    const from = current.current.view;
    const target = { ...next };
    if (options?.immediate || reducedMotion.current || sameRange(from, target)) {
      commit(settled(target));
      return;
    }
    const activeGeneration = generation.current;
    const startedAt = performance.now();
    commit({ view: from, from, target, progress: 0 });
    const advance = (now: number) => {
      if (activeGeneration !== generation.current) return;
      const elapsed = Math.min(1, Math.max(0, (now - startedAt) / DURATION_MS));
      const progress = elapsed < 0.5 ? 4 * elapsed ** 3 : 1 - (-2 * elapsed + 2) ** 3 / 2;
      const view = elapsed === 1 ? target : {
        minimum: from.minimum + (target.minimum - from.minimum) * progress,
        maximum: from.maximum + (target.maximum - from.maximum) * progress,
      };
      commit({ view, from, target, progress });
      pendingFrame.current = elapsed < 1 ? requestAnimationFrame(advance) : null;
    };
    pendingFrame.current = requestAnimationFrame(advance);
  }, [cancel, commit]);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const synchronize = () => {
      reducedMotion.current = preference.matches;
      if (preference.matches && current.current.progress < 1) {
        cancel();
        commit(settled(current.current.target));
      }
    };
    synchronize();
    preference.addEventListener("change", synchronize);
    return () => {
      preference.removeEventListener("change", synchronize);
      cancel();
    };
  }, [cancel, commit]);

  return { ...frame, setView, stop };
}
