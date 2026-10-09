"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Swaps its content the way scrolling text moves: when `swapKey` changes,
 * the old content slides up and out while the new slides up into place.
 * Content with the same key updates in place (a ticking number stays put).
 * Clip the parent (overflow-hidden) to make it read as a window. Reduced
 * motion swaps instantly.
 */
export function SlideSwap({
  swapKey,
  children,
  className,
}: {
  swapKey: string;
  children: React.ReactNode;
  className?: string;
}) {
  const last = React.useRef<{ key: string; node: React.ReactNode }>({ key: swapKey, node: children });
  const serial = React.useRef(0);
  const [leaving, setLeaving] = React.useState<Array<{ id: number; node: React.ReactNode }>>([]);

  const timers = React.useRef<number[]>([]);
  React.useEffect(() => () => timers.current.forEach((timer) => window.clearTimeout(timer)), []);

  // On a new key, the content last shown under the old key leaves exactly
  // as it looked (the effect below records it after every render).
  React.useEffect(() => {
    if (last.current.key === swapKey) return;
    const id = ++serial.current;
    const node = last.current.node;
    setLeaving((items) => [...items.slice(-1), { id, node }]);
    timers.current.push(
      window.setTimeout(() => setLeaving((items) => items.filter((item) => item.id !== id)), 600)
    );
  }, [swapKey]);
  React.useEffect(() => {
    last.current = { key: swapKey, node: children };
  }, [swapKey, children]);

  return (
    <div className={cn("relative", className)}>
      {leaving.map((item) => (
        <div
          key={item.id}
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 motion-reduce:hidden motion-safe:animate-[story-swap-out_380ms_cubic-bezier(0.5,0,0.75,0)_both]"
        >
          {item.node}
        </div>
      ))}
      <div key={swapKey} className="motion-safe:animate-[story-swap-in_480ms_cubic-bezier(0.2,0.7,0.2,1)_160ms_both]">
        {children}
      </div>
    </div>
  );
}
