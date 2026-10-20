"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { saveReturnPoint } from "./return-point";

/**
 * A step's way out to the explorer: the same figures at `size`, or at any
 * size when none is given. The explorer picks up the reader's state itself,
 * and its back link returns here.
 */
export function ExploreLink({ size, children }: { size?: number; children?: ReactNode }) {
  return (
    <p className="mt-2 font-sans text-sm">
      <Link
        href={size === undefined ? "/apportionment/explore" : `/apportionment/explore?size=${size}`}
        onClick={saveReturnPoint}
        className="text-story-ink-2 underline decoration-story-axis underline-offset-4 hover:text-story-ink"
      >
        {children ?? `See every state at ${size?.toLocaleString("en-US")} seats`} →
      </Link>
    </p>
  );
}
