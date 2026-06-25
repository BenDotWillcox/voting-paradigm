"use client";

import * as React from "react";
import { Pause, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
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
import { CAP_ANCHORS, CAP_MIN } from "@/lib/districting-cap-scale";

interface CapPickerProps {
  /** Currently selected House size. */
  cap: number;
  /** Fired when the user picks or scrubs to a different House size. */
  onCapChange: (cap: number) => void;
  /** Upper bound for the scrubber. */
  maxCap: number;
}

/**
 * Anchor-marked scrubber for the apportionment sequence.
 * District maps stay scoped to precomputed anchors, but apportionment itself
 * can be replayed seat-by-seat because the priority sequence is deterministic.
 */
export function CapPicker({ cap, maxCap, onCapChange }: CapPickerProps) {
  const [isPlaying, setIsPlaying] = React.useState(false);
  const activeAnchor = getActiveAnchor(cap);
  const boundedAnchors = CAP_ANCHORS.filter((anchor) => anchor.cap <= maxCap);
  const exactAnchor = boundedAnchors.find((anchor) => anchor.cap === cap);

  React.useEffect(() => {
    if (!isPlaying) return;
    if (cap >= maxCap) {
      setIsPlaying(false);
      return;
    }

    const timer = window.setInterval(() => {
      onCapChange(Math.min(maxCap, cap + 1));
    }, 1450);

    return () => window.clearInterval(timer);
  }, [cap, isPlaying, maxCap, onCapChange]);

  return (
    <TooltipProvider delayDuration={150}>
      <div className="w-full space-y-1.5">
        <div className="flex flex-wrap items-center justify-between gap-1.5">
          <div className="space-y-0.5">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
              House size
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-lg font-semibold tabular-nums">
                {cap.toLocaleString()}
              </span>
              <span className="text-xs text-muted-foreground">
                {activeAnchor.label}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsPlaying((playing) => !playing)}
              aria-label={
                isPlaying
                  ? "Pause seat allocation playback"
                  : "Play seat allocation playback"
              }
            >
              {isPlaying ? <Pause /> : <Play />}
              {isPlaying ? "Pause" : "Play"}
            </Button>
          </div>
        </div>

        <div className="space-y-1">
          <Slider
            min={CAP_MIN}
            max={maxCap}
            step={1}
            value={[cap]}
            onValueChange={([next]) => {
              if (typeof next === "number") onCapChange(next);
            }}
            aria-label="House size"
          />
          <div className="relative h-2.5 text-xs text-muted-foreground">
            {boundedAnchors.map((anchor) => {
              const left = ((anchor.cap - CAP_MIN) / (maxCap - CAP_MIN)) * 100;
              return (
                <button
                  key={anchor.cap}
                  type="button"
                  className="absolute top-0 h-2.5 w-5 -translate-x-1/2 hover:text-foreground"
                  style={{ left: `${left}%` }}
                  onClick={() => onCapChange(anchor.cap)}
                  aria-label={`Jump to ${anchor.cap.toLocaleString()} seats`}
                >
                  <span className="mx-auto block h-2.5 w-px bg-border" />
                </button>
              );
            })}
          </div>
        </div>

        <ToggleGroup
          type="single"
          variant="outline"
          value={exactAnchor ? String(exactAnchor.cap) : ""}
          onValueChange={(value) => {
            if (!value) return;
            const next = Number.parseInt(value, 10);
            if (!Number.isFinite(next)) return;
            onCapChange(next);
          }}
          className="w-full"
          aria-label="House size milestones"
        >
          {boundedAnchors.map((anchor) => (
            <Tooltip key={anchor.cap}>
              <TooltipTrigger asChild>
                <ToggleGroupItem
                  value={String(anchor.cap)}
                  className="h-auto flex-col gap-0.5 px-2 py-1"
                  aria-label={`${anchor.cap.toLocaleString()} (${anchor.label})`}
                >
                  <span className="text-xs font-semibold leading-none tabular-nums">
                    {anchor.cap.toLocaleString()}
                  </span>
                  <span className="text-[10px] font-normal leading-tight opacity-80">
                    {anchor.label}
                  </span>
                </ToggleGroupItem>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-xs">
                <div className="font-semibold">
                  {anchor.cap.toLocaleString()} - {anchor.label}
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

function getActiveAnchor(cap: number) {
  let active = CAP_ANCHORS[0];
  for (const anchor of CAP_ANCHORS) {
    if (anchor.cap <= cap) active = anchor;
  }
  return active;
}
