"use client";

import * as React from "react";

/** While a jump scrolls past lazy sections they hold off mounting; see jumpToSection. */
let holding = false;
const releases = new Set<() => void>();
const OPEN_EVENT = "dd:open-section";

function hold(value: boolean) {
  holding = value;
  if (!value) for (const release of releases) release();
}

/**
 * True once the element comes within rootMargin of the viewport; it stays
 * true. During a jump it waits until the jump settles, and then turns true
 * only if the element is still near, so a long jump draws just where it lands.
 */
export function useNear(ref: React.RefObject<Element | null>, rootMargin = "900px 0px") {
  const [near, setNear] = React.useState(false);
  React.useEffect(() => {
    const node = ref.current;
    if (near || !node) return;
    let inside = false;
    const release = () => { if (inside) setNear(true); };
    const observer = new IntersectionObserver((entries) => {
      inside = entries[entries.length - 1].isIntersecting;
      if (inside && !holding) setNear(true);
    }, { rootMargin });
    observer.observe(node);
    releases.add(release);
    return () => {
      observer.disconnect();
      releases.delete(release);
    };
  }, [near, ref, rootMargin]);
  return near;
}

/**
 * Holds back heavy content, like the 50-state explorer and its map payloads,
 * until it is within two screens of the viewport: it does not compete with
 * what is above it, but is drawn by the time the reader arrives. Mounts at
 * once when the address points at it (`#explorer`), names a state, or a jump
 * targets it.
 */
export function DeferUntilNear({ fallback, anchor, children }: { fallback: React.ReactNode; anchor: string; children: React.ReactNode }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const near = useNear(ref, "200% 0px");
  const [linked, setLinked] = React.useState(false);
  React.useEffect(() => {
    const check = () => {
      if (window.location.hash === `#${anchor}` || new URLSearchParams(window.location.search).has("state")) setLinked(true);
    };
    const open = (event: Event) => { if ((event as CustomEvent<string>).detail === anchor) setLinked(true); };
    check();
    window.addEventListener("hashchange", check);
    window.addEventListener(OPEN_EVENT, open);
    return () => {
      window.removeEventListener("hashchange", check);
      window.removeEventListener(OPEN_EVENT, open);
    };
  }, [anchor]);
  return near || linked ? <>{children}</> : <div ref={ref}>{fallback}</div>;
}

const STOP_EVENTS = ["wheel", "touchstart", "keydown", "pointerdown"] as const;

/** How long after landing a jump keeps its target in place while sections near it draw. */
const KEEP_MS = 2000;

/**
 * Opens the section with this id now (a DeferUntilNear anchored there starts
 * loading at once) and scrolls to it. Lazy sections passed on the way hold
 * off mounting until the jump lands, and the scroll repeats if anything above
 * still moves the target. After landing, the sections near it mount, and for
 * a moment any change in the page's height snaps the target back, before the
 * frame is painted. Everything stops as soon as the reader scrolls themselves.
 */
export function jumpToSection(id: string) {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: id }));
  const target = document.getElementById(id);
  if (!target) return;
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const margin = parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
  const placed = () => Math.abs(target.getBoundingClientRect().top - margin) <= 2
    || window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
  let tries = 0;
  let timer = 0;
  let keeper: ResizeObserver | null = null;
  const go = () => target.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
  const stop = () => {
    window.clearTimeout(timer);
    window.clearTimeout(limit);
    window.removeEventListener("scroll", onScroll);
    for (const type of STOP_EVENTS) window.removeEventListener(type, stop);
    keeper?.disconnect();
    hold(false);
  };
  const land = () => {
    if (keeper) return;
    window.clearTimeout(timer);
    window.removeEventListener("scroll", onScroll);
    // Resize observations arrive after layout and before paint, so the snap is never seen.
    keeper = new ResizeObserver(() => { if (!placed()) target.scrollIntoView({ behavior: "auto", block: "start" }); });
    keeper.observe(document.documentElement);
    hold(false);
    window.clearTimeout(limit);
    limit = window.setTimeout(stop, KEEP_MS);
  };
  const settle = () => {
    if (placed() || ++tries > 3) land();
    else go();
  };
  // A scroll has ended once no scroll event arrives for a moment; scrollend is not universal.
  const onScroll = () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(settle, 150);
  };
  let limit = window.setTimeout(land, 5000);
  hold(true);
  window.addEventListener("scroll", onScroll, { passive: true });
  for (const type of STOP_EVENTS) window.addEventListener(type, stop, { passive: true });
  timer = window.setTimeout(settle, 400);
  go();
}
