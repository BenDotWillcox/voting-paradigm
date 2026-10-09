"use client";

import * as React from "react";

import { useReducedMotion } from "./chart";

interface NumberTickerProps {
  value: number;
  /** Decimal places shown. */
  decimals?: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  className?: string;
}

/**
 * A number that counts to each new value instead of jumping. The final value
 * is always exact; reduced motion shows it immediately. Screen readers get
 * only the settled value.
 */
export function NumberTicker({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  duration = 700,
  className,
}: NumberTickerProps) {
  const reducedMotion = useReducedMotion();
  const [shown, setShown] = React.useState(value);
  const shownRef = React.useRef(value);

  React.useEffect(() => {
    const from = shownRef.current;
    if (reducedMotion || from === value || document.visibilityState === "hidden") {
      shownRef.current = value;
      setShown(value);
      return;
    }
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      const next = t === 1 ? value : from + (value - from) * eased;
      shownRef.current = next;
      setShown(next);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, reducedMotion]);

  const format = (n: number) =>
    n.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });

  return (
    <span className={className}>
      <span aria-hidden="true" className="tabular-nums">
        {prefix}
        {format(shown)}
        {suffix}
      </span>
      <span className="sr-only">
        {prefix}
        {format(value)}
        {suffix}
      </span>
    </span>
  );
}
