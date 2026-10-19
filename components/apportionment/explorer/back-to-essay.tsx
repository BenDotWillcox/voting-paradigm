"use client";

import * as React from "react";
import Link from "next/link";

import { markReturning, readReturnPoint } from "@/components/apportionment/essay/return-point";

/**
 * The way back to the essay: to where the reader left it when they came
 * from there (the essay restores the position), otherwise to its start.
 */
export function BackToEssay() {
  const [returnable, setReturnable] = React.useState(false);
  React.useEffect(() => setReturnable(readReturnPoint() !== null), []);

  return (
    <Link
      href="/apportionment"
      onClick={() => {
        if (returnable) markReturning();
      }}
      className="font-sans text-sm text-story-ink-2 underline decoration-story-axis underline-offset-4 hover:text-story-ink"
    >
      ← {returnable ? "Back to the essay, where you left off" : "The Representation Gap"}
    </Link>
  );
}
