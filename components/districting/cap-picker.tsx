"use client";

import * as React from "react";

import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { CAP_ANCHORS } from "@/lib/districting-cap-scale";

interface CapPickerProps {
  /** Currently selected House cap. Must match one of CAP_ANCHORS. */
  cap: number;
  /** Fired when the user picks a different anchor. */
  onCapChange: (cap: number) => void;
}

/**
 * Discrete-anchor picker for the House size.
 *
 * Replaces the earlier logarithmic slider: this demo only ever computes
 * district maps at the five educational anchors (current 435, Wyoming Rule,
 * Cube Root Rule, an "expanded" round number, and the Article I §2
 * constitutional ratio). A toggle group makes that scope honest and
 * prevents users from picking caps we won't have results for.
 */
export function CapPicker({ cap, onCapChange }: CapPickerProps) {
  const active = CAP_ANCHORS.find((a) => a.cap === cap) ?? CAP_ANCHORS[0];

  return (
    <TooltipProvider delayDuration={150}>
      <div className="w-full space-y-3">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <div className="space-y-1">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              House size
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-semibold tabular-nums">
                {active.cap.toLocaleString()}
              </span>
              <span className="text-sm text-muted-foreground">
                {active.label}
              </span>
            </div>
          </div>
          <p className="text-xs text-muted-foreground max-w-md text-right">
            {active.description}
          </p>
        </div>

        <ToggleGroup
          type="single"
          variant="outline"
          value={String(cap)}
          onValueChange={(value) => {
            // Radix fires "" when the user clicks the active item; ignore it
            // so the picker behaves as a radio group (always one selected).
            if (!value) return;
            const next = Number.parseInt(value, 10);
            if (!Number.isFinite(next)) return;
            onCapChange(next);
          }}
          className="w-full"
          aria-label="House size"
        >
          {CAP_ANCHORS.map((anchor) => (
            <Tooltip key={anchor.cap}>
              <TooltipTrigger asChild>
                <ToggleGroupItem
                  value={String(anchor.cap)}
                  className="flex-col gap-0.5 h-auto py-2.5 px-3"
                  aria-label={`${anchor.cap.toLocaleString()} (${anchor.label})`}
                >
                  <span className="text-base font-semibold tabular-nums leading-none">
                    {anchor.cap.toLocaleString()}
                  </span>
                  <span className="text-[11px] font-normal opacity-80 leading-tight">
                    {anchor.label}
                  </span>
                </ToggleGroupItem>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-xs">
                <div className="font-semibold">
                  {anchor.cap.toLocaleString()} — {anchor.label}
                </div>
                <div className="font-normal opacity-90">
                  {anchor.description}
                </div>
              </TooltipContent>
            </Tooltip>
          ))}
        </ToggleGroup>
      </div>
    </TooltipProvider>
  );
}
