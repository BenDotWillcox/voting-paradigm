"use client";

import * as React from "react";

/**
 * Motion helpers shared by the showcase cards: a card plays while hovered
 * or focused, and on touch screens, which have no hover, while it is on
 * screen.
 */

/** Whether the primary pointer can hover (false on touch screens). */
export function useCanHover(): boolean {
  return React.useSyncExternalStore(
    (onChange) => {
      const query = window.matchMedia("(hover: hover)");
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => window.matchMedia("(hover: hover)").matches,
    () => true
  );
}

/** Whether the element is on screen, so a loop only runs while seen. */
export function useInView<T extends Element>(): { ref: React.RefCallback<T>; inView: boolean } {
  const [node, setNode] = React.useState<T | null>(null);
  const [inView, setInView] = React.useState(false);
  React.useEffect(() => {
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      threshold: 0.35,
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [node]);
  return { ref: setNode, inView };
}
