"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";
import { ArrowLeftRight, Info, MoveVertical, TriangleAlert, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SpectrumFineAdjustment } from "./spectrum-fine-adjustment";
import styles from "./spectrum-answer.module.css";
import {
  DEFAULT_UNCERTAINTY_SD, formatSpectrumUncertainty, formatSpectrumValue,
  initialSpectrumPosition, sampleSpectrumCurve, SPECTRUM_DENSITY_MAX,
  spectrumAxisTicks, spectrumValueAtFraction, uncertaintyFromVerticalDrag, updateSpectrumHandle,
  type SpectrumDraft,
} from "@/lib/preferences/spectrum";
import {
  SPECTRUM_SD_MIN, SPECTRUM_SD_MAX,
  type AcceptableRange, type SpectrumQuestion,
} from "@/lib/validations/elicitation-schemas";

type SpectrumAnswerProps = {
  question: SpectrumQuestion;
  draft: SpectrumDraft;
  onChange: (draft: SpectrumDraft) => void;
  disabled?: boolean;
};
type Handle = "position" | "uncertainty" | "lower" | "upper";
type Drag = {
  pointerId: number;
  handle: Handle;
  x: number;
  y: number;
  value: number;
  position: number;
};

// Keep bounds' tabs above the plot and the position thumb on the baseline.
// Separate hit-target lanes keep coincident handles reachable, including L = R.
const PLOT_TOP = 112;
const PLOT_HEIGHT = 224;
const BASELINE = PLOT_TOP + PLOT_HEIGHT;
const TARGET = "absolute z-20 flex size-11 -translate-x-1/2 -translate-y-1/2 touch-none select-none items-center justify-center rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

function GraphHandle({ label, value, min, max, valueText, vertical = false, active = false, handleRef,
  left, top, disabled, children, onKeyDown, onPointerDown, onPointerMove,
  onPointerUp, onPointerCancel,
}: {
  label: string; value: number; min: number; max: number; valueText: string;
  vertical?: boolean; active?: boolean; left: number; top: number; disabled: boolean; children: ReactNode;
  handleRef: (element: HTMLDivElement | null) => void;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
  onPointerDown: (event: PointerEvent<HTMLDivElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLDivElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLDivElement>) => void;
  onPointerCancel: () => void;
}) {
  return <div ref={handleRef} role="slider" tabIndex={disabled ? -1 : 0} aria-label={label}
    aria-valuemin={min} aria-valuemax={max} aria-valuenow={value}
    aria-valuetext={valueText} aria-orientation={vertical ? "vertical" : "horizontal"}
    aria-disabled={disabled} title={label + ": " + valueText} data-active={active}
    className={TARGET + " " + styles.handle + (disabled ? " cursor-not-allowed opacity-40" : vertical ? " cursor-ns-resize" : " cursor-ew-resize")}
    style={{ left: left + "%", top }}
    onKeyDown={onKeyDown} onPointerDown={onPointerDown} onPointerMove={onPointerMove}
    onPointerUp={onPointerUp} onPointerCancel={onPointerCancel} onLostPointerCapture={onPointerCancel}>
    {children}
  </div>;
}

function SignalHelp({ label, children }: { label: string; children: ReactNode }) {
  return <Popover>
    <PopoverTrigger asChild>
      <Button type="button" variant="ghost" className="size-11 shrink-0 p-0"
        aria-label={label} title={label}>
        <Info className="size-4" aria-hidden="true" />
      </Button>
    </PopoverTrigger>
    <PopoverContent side="top" className="max-w-[calc(100vw-2rem)] text-sm leading-relaxed" aria-label={label}>
      {children}
    </PopoverContent>
  </Popover>;
}

export function SpectrumAnswer({ question, draft, onChange, disabled = false }: SpectrumAnswerProps) {
  const id = useId();
  const graphRef = useRef<HTMLDivElement>(null);
  const handles = useRef<Partial<Record<Handle, HTMLDivElement | null>>>({});
  const drag = useRef<Drag | null>(null);
  const [activeHandle, setActiveHandle] = useState<Handle | null>(null);
  const [plotWidth, setPlotWidth] = useState(0);
  // Visible defaults are previews only. Omission retains the last setting
  // locally so toggling back does not discard the participant's work.
  const lastRange = useRef<AcceptableRange>(draft.acceptable_range ?? { lower: question.scale.min, upper: question.scale.max });
  const lastUncertainty = useRef(draft.reported_uncertainty ?? { sd_fraction: DEFAULT_UNCERTAINTY_SD });
  const [proposedRange, setProposedRange] = useState<AcceptableRange | null>(
    draft.acceptable_range === null ? lastRange.current : null,
  );
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const observer = new ResizeObserver(([entry]) => setPlotWidth(entry.contentRect.width));
    observer.observe(graph);
    return () => observer.disconnect();
  }, []);
  const latest = useRef({ draft, onChange, proposedRange });
  latest.current = { draft, onChange, proposedRange };
  const { scale } = question;
  const span = scale.max - scale.min;
  const position = draft.position ?? initialSpectrumPosition(scale);
  const fraction = (position - scale.min) / span;
  const sd = (draft.reported_uncertainty ?? lastUncertainty.current).sd_fraction;
  const range = proposedRange ?? draft.acceptable_range;
  const preview = draft.position === null || draft.reported_uncertainty === null;
  const points = sampleSpectrumCurve(fraction, { sd_fraction: sd });
  const peak = Math.max(...points.map((point) => point.density));
  const peakY = BASELINE - peak / SPECTRUM_DENSITY_MAX * PLOT_HEIGHT;
  const outline = "M" + points.map((point) =>
    (point.position * 1000).toFixed(3) + "," + (PLOT_HEIGHT * (1 - point.density / SPECTRUM_DENSITY_MAX)).toFixed(3),
  ).join(" L");
  const certainty = Math.round((SPECTRUM_SD_MAX - sd) / (SPECTRUM_SD_MAX - SPECTRUM_SD_MIN) * 1000) / 10;
  const outside = draft.acceptable_range !== null && draft.position !== null &&
    (draft.position < draft.acceptable_range.lower || draft.position > draft.acceptable_range.upper);
  const percent = (value: number) => (value - scale.min) / span * 100;
  const ticks = spectrumAxisTicks(scale, plotWidth);
  // Labels live in separate lanes from the axis and bound tabs. Side labels
  // face into the plot; centered labels clamp at the ends without moving a handle.
  const labelSide = fraction > 0.5 ? styles.labelLeft : styles.labelRight;
  const peakLabelAbove = Math.max(fraction, 1 - fraction) * plotWidth < 160;

  function currentValue(handle: Handle): number {
    const current = latest.current;
    if (handle === "position") return current.draft.position ?? initialSpectrumPosition(scale);
    if (handle === "uncertainty") return (current.draft.reported_uncertainty ?? lastUncertainty.current).sd_fraction;
    return (current.proposedRange ?? current.draft.acceptable_range)?.[handle] ?? scale[handle === "lower" ? "min" : "max"];
  }

  function change(handle: Handle, value: number) {
    if (disabled) return;
    const current = latest.current;
    if ((handle === "lower" || handle === "upper") && current.proposedRange) {
      const next = updateSpectrumHandle({ ...current.draft, acceptable_range: current.proposedRange }, handle, value);
      // Direct manipulation is an explicit answer, just like moving the peak.
      // Only untouched (or deliberately omitted) defaults stay previews.
      latest.current = { ...current, draft: next, proposedRange: null };
      setProposedRange(null);
      current.onChange(next);
    } else {
      const next = updateSpectrumHandle(current.draft, handle, value);
      if (next.reported_uncertainty) lastUncertainty.current = next.reported_uncertainty;
      latest.current = { ...current, draft: next };
      current.onChange(next);
    }
  }

  function begin(handle: Handle, event: PointerEvent<HTMLDivElement>, axisClick = false) {
    if (disabled || drag.current || !event.isPrimary || event.button !== 0 ||
      (handle === "uncertainty" && draft.position === null)) return;
    const rect = graphRef.current?.getBoundingClientRect();
    if (!rect?.width) return;
    event.preventDefault();
    event.stopPropagation();
    handles.current[handle]?.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    const value = axisClick ? spectrumValueAtFraction((event.clientX - rect.left) / rect.width, scale) : currentValue(handle);
    drag.current = { pointerId: event.pointerId, handle, x: event.clientX, y: event.clientY, value, position: fraction };
    setActiveHandle(handle);
    change(handle, value);
  }

  function move(event: PointerEvent<HTMLDivElement>) {
    const start = drag.current;
    const rect = graphRef.current?.getBoundingClientRect();
    if (disabled || !start || event.pointerId !== start.pointerId || !rect?.width) return;
    const value = start.handle === "uncertainty"
      ? uncertaintyFromVerticalDrag(start.value, event.clientY - start.y, PLOT_HEIGHT, start.position)
      : spectrumValueAtFraction((start.value - scale.min) / span + (event.clientX - start.x) / rect.width, scale);
    change(start.handle, value);
  }

  function end(event: PointerEvent<HTMLDivElement>) {
    if (event.pointerId !== drag.current?.pointerId) return;
    move(event);
    drag.current = null;
    setActiveHandle(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function cancelDrag() { drag.current = null; setActiveHandle(null); }

  function key(handle: Handle, event: KeyboardEvent<HTMLDivElement>) {
    if (disabled || (handle === "uncertainty" && draft.position === null)) return;
    const value = currentValue(handle);
    const width = handle === "uncertainty";
    let next: number;
    const direction = ["ArrowRight", "ArrowUp", "PageUp"].includes(event.key) ? 1
      : ["ArrowLeft", "ArrowDown", "PageDown"].includes(event.key) ? -1 : 0;
    if (direction) next = value + direction * (width ? -0.001 : scale.step) * (event.key.startsWith("Page") ? 10 : 1);
    else if (event.key === "Home") next = width ? SPECTRUM_SD_MAX : scale.min;
    else if (event.key === "End") next = width ? SPECTRUM_SD_MIN : scale.max;
    else if (event.key === "Enter" || event.key === " ") next = value;
    else return;
    event.preventDefault();
    change(handle, width ? next : spectrumValueAtFraction((next - scale.min) / span, scale));
  }

  function handleEvents(handle: Handle) {
    return {
      onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => key(handle, event),
      onPointerDown: (event: PointerEvent<HTMLDivElement>) => begin(handle, event),
      onPointerMove: move, onPointerUp: end, onPointerCancel: cancelDrag,
    };
  }

  function toggleUncertainty() {
    if (disabled || draft.position === null) return;
    if (draft.reported_uncertainty) lastUncertainty.current = draft.reported_uncertainty;
    onChange({ ...draft, reported_uncertainty: draft.reported_uncertainty === null ? lastUncertainty.current : null });
  }

  function toggleRangeAnswer() {
    if (disabled || range === null) return;
    lastRange.current = range;
    const included = draft.acceptable_range !== null;
    onChange({ ...draft, acceptable_range: included ? null : range });
    setProposedRange(included ? range : null);
  }

  function toggleRangeVisibility() {
    if (disabled) return;
    if (range) {
      lastRange.current = range;
      onChange({ ...draft, acceptable_range: null });
      setProposedRange(null);
    } else {
      // Showing a remembered setting never re-includes it without confirmation.
      setProposedRange(lastRange.current);
    }
  }

  return (
    <div className={styles.instrument + " min-w-0 space-y-4"}>
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="font-medium">Shape your answer</p>
        <p className="text-xs text-muted-foreground">Move the dot ↔ · Pull the peak ↕ · Set the bars ↔</p>
      </div>
      <div className={styles.surface + " rounded-lg border px-6 pb-4 pt-3 sm:px-8"}>
        <div ref={graphRef} role="group" aria-label="Position, uncertainty, and acceptable range graph"
          aria-describedby={id + "-help"} className="relative" style={{ height: BASELINE + 118 }}>
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0" style={{ top: PLOT_TOP, height: PLOT_HEIGHT }}>
            {[0, 0.5, 1].map((level) => <div key={level} className={styles.gridLine + " absolute inset-x-0 border-t"}
              style={{ top: level * 100 + "%" }} />)}
            {range && <div className={styles.acceptableBand + " absolute inset-y-0 " + (proposedRange ? "border-x border-dashed" : "")}
              data-preview={proposedRange !== null}
              style={{ left: percent(range.lower) + "%", width: percent(range.upper) - percent(range.lower) + "%" }} />}
            <svg className="h-full w-full overflow-visible" viewBox="0 0 1000 224" preserveAspectRatio="none">
              <path d={outline + " L1000,224 L0,224 Z"} className={styles.curveFill} data-preview={preview} />
              <path d={outline} fill="none" className={styles.curveLine} data-preview={preview}
                strokeWidth="2.5" strokeDasharray={preview ? "5 5" : undefined} vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
          <div aria-hidden="true" className={styles.positionGuide + " pointer-events-none absolute border-l border-dashed"}
            style={{ left: percent(position) + "%", top: peakY, height: BASELINE - peakY }} />
          <div className="absolute inset-x-0 z-10 h-11 -translate-y-1/2 cursor-pointer touch-none"
            aria-hidden="true" style={{ top: BASELINE }}
            onPointerDown={(event) => begin("position", event, true)}
            onPointerMove={move} onPointerUp={end} onPointerCancel={cancelDrag} onLostPointerCapture={cancelDrag}>
            <div className={styles.axisLine + " absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 rounded-full"} />
          </div>
          <GraphHandle label="Your position" value={position} min={scale.min} max={scale.max}
            handleRef={(element) => { handles.current.position = element; }}
            valueText={formatSpectrumValue(position, scale) + (draft.position === null ? "; preview, press Enter to select" : "")}
            left={percent(position)} top={BASELINE} disabled={disabled} active={activeHandle === "position"} {...handleEvents("position")}>
            <span className={styles.positionKnob + " " + styles.knob + " flex size-7 items-center justify-center rounded-full border-2"}
              data-preview={draft.position === null}>
              <ArrowLeftRight className="size-4" aria-hidden="true" />
            </span>
          </GraphHandle>
          <GraphHandle label="Uncertainty width, pull up to narrow" value={certainty} min={0} max={100} vertical
            handleRef={(element) => { handles.current.uncertainty = element; }}
            valueText={formatSpectrumUncertainty({ sd_fraction: sd }) + (draft.reported_uncertainty === null ? "; preview, press Enter to include" : "; up narrows, down broadens")}
            left={percent(position)} top={peakY} disabled={disabled || draft.position === null}
            active={activeHandle === "uncertainty"} {...handleEvents("uncertainty")}>
            <span className={styles.peakKnob + " " + styles.knob + " flex size-8 items-center justify-center rounded-full border " +
              (draft.reported_uncertainty === null ? "border-dashed" : "")}>
              <MoveVertical className="size-4" aria-hidden="true" />
            </span>
          </GraphHandle>
          <div aria-hidden="true" className={styles.peakValue + " " + (peakLabelAbove ? styles.labelAbove : labelSide)}
            style={{ left: percent(position) + "%", top: peakY - (peakLabelAbove ? 24 : 0) }}>
            <span className={styles.labelCaption}>{draft.reported_uncertainty === null ? "Width preview" : "Uncertainty width"}</span>
            <span className="font-semibold tabular-nums">{formatSpectrumUncertainty({ sd_fraction: sd })}</span>
          </div>
          {range && (["lower", "upper"] as const).map((bound) => (
            <div key={bound}>
              <div aria-hidden="true" className={styles.boundLine + " pointer-events-none absolute border-l-2 " + (proposedRange ? "border-dashed" : "")}
                data-preview={proposedRange !== null}
                style={{ left: percent(range[bound]) + "%", top: bound === "lower" ? 24 : 68, height: BASELINE - (bound === "lower" ? 24 : 68) }} />
              <div aria-hidden="true" className="absolute z-10 w-11 -translate-x-1/2 cursor-ew-resize touch-none"
                style={{ left: percent(range[bound]) + "%", top: PLOT_TOP, height: PLOT_HEIGHT - 24 }}
                onPointerDown={(event) => begin(bound, event)} onPointerMove={move}
                onPointerUp={end} onPointerCancel={cancelDrag} onLostPointerCapture={cancelDrag} />
              <GraphHandle label={bound === "lower" ? "Lowest acceptable value" : "Highest acceptable value"}
                handleRef={(element) => { handles.current[bound] = element; }}
                value={range[bound]} min={bound === "lower" ? scale.min : range.lower}
                max={bound === "upper" ? scale.max : range.upper}
                valueText={formatSpectrumValue(range[bound], scale) + (proposedRange ? "; preview, move or press Enter to include" : "; included in this answer")}
                left={percent(range[bound])} top={bound === "lower" ? 24 : 68} disabled={disabled}
                active={activeHandle === bound} {...handleEvents(bound)}>
                <span className={styles.boundKnob + " " + styles.knob + " rounded border px-2 py-1 text-xs font-semibold"}
                  data-preview={proposedRange !== null}>
                  {bound === "lower" ? "Min" : "Max"}
                </span>
              </GraphHandle>
              <div aria-hidden="true" className={styles.boundValue + " " +
                (percent(range[bound]) > 50 ? styles.labelLeft : styles.labelRight)}
                data-preview={proposedRange !== null}
                style={{ left: percent(range[bound]) + "%", top: bound === "lower" ? 24 : 68 }}>
                {formatSpectrumValue(range[bound], scale)}
              </div>
            </div>
          ))}
          <div aria-hidden="true" className={styles.positionStem} style={{ left: percent(position) + "%", top: BASELINE + 14 }} />
          <div aria-hidden="true" className={styles.positionValue}
            style={{ left: `clamp(3.5rem, ${percent(position)}%, calc(100% - 3.5rem))`, top: BASELINE + 24 }}>
            {draft.position === null ? <span className={styles.previewText}>Choose a position</span> : formatSpectrumValue(position, scale)}
          </div>
          <div aria-hidden="true" className={styles.axisTicks + " pointer-events-none absolute inset-x-0"} style={{ top: BASELINE }}>
            {ticks.map((tick) => <div key={tick.value} className="absolute" data-axis-tick={tick.value}
              style={{ left: tick.fraction * 100 + "%" }}>
              <span className={styles.tickMark} data-major={tick.label !== null} />
              {tick.label !== null && <span className={styles.tickLabel}
                style={{ transform: `translateX(-${tick.fraction === 0 ? 0 : tick.fraction === 1 ? 100 : 50}%)` }}>{tick.label}</span>}
            </div>)}
            <span className={styles.axisUnit}>{scale.format === "clock_hour" ? "Time of day" : scale.unit === "%" ? "Percent (%)" : scale.unit}</span>
          </div>
        </div>
        <p id={id + "-help"} className={styles.help + " text-xs leading-relaxed"}>
          {draft.position === null ? "Drag the dot or tap the axis to choose a position. The dashed curve is only a preview."
            : draft.reported_uncertainty === null ? "Pull the peak up to be more sure, down to be less sure. Dashed width is a preview until you choose it."
              : "Higher and narrower means more sure; lower and wider means less sure. Acceptable bounds are independent of the curve."}
          {proposedRange && <span className="mt-1 block">The amber, dashed Min/Max bars are not included yet. Move either bar or choose “Use this range” to include them.</span>}
          <span className="sr-only"> Tab to each handle. Arrow keys adjust it; Home and End reach its limits. Enter includes the handle’s current preview value. Editing either bound includes both bounds.</span>
        </p>
      </div>

      <dl className="sr-only">
        <div><dt className="text-xs text-muted-foreground">Position</dt><dd className="mt-1 font-medium tabular-nums">
          {draft.position === null ? "Not selected" : formatSpectrumValue(draft.position, scale)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Uncertainty width · σ</dt><dd className="mt-1 font-medium tabular-nums">
          {draft.reported_uncertainty === null ? "Not provided" : formatSpectrumUncertainty(draft.reported_uncertainty)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Acceptable outcomes</dt><dd className="mt-1 font-medium tabular-nums">
          {draft.acceptable_range === null ? "Not provided" : formatSpectrumValue(draft.acceptable_range.lower, scale) + " – " + formatSpectrumValue(draft.acceptable_range.upper, scale)}</dd></div>
      </dl>
      <div className="mx-auto grid w-full max-w-2xl gap-4 text-center sm:grid-cols-2" aria-label="Optional answer details">
        <div className={styles.optionalDetail + " min-w-0 space-y-1"}>
          <div className="flex items-center justify-center text-sm font-medium">
            Uncertainty
            <SignalHelp label="About reported uncertainty">
              Pull the peak to describe how unsure you feel about your position.
              This is your report, not model confidence. Leave it unanswered to omit
              it; answering again restores your last width. A dashed curve is only a preview.
            </SignalHelp>
          </div>
          <p id={id + "-uncertainty-value"} className="text-base font-semibold tabular-nums">
            {draft.reported_uncertainty === null ? "Not answered" : formatSpectrumUncertainty(draft.reported_uncertainty)}
          </p>
          <p id={id + "-uncertainty-status"} className="min-h-5 text-xs text-muted-foreground">
            {draft.position === null ? "Choose a position first" : draft.reported_uncertainty === null ? "Preview only · not included" : "Included when you record this position"}
          </p>
          <Button type="button" variant="outline" disabled={disabled || draft.position === null}
            className={"min-h-11 " + (draft.reported_uncertainty !== null ? styles.clearAnswer : "")}
            aria-describedby={id + "-uncertainty-value " + id + "-uncertainty-status"} onClick={toggleUncertainty}>
            {draft.reported_uncertainty !== null && <X className="size-4" aria-hidden="true" />}
            {draft.reported_uncertainty === null ? "Answer uncertainty" : "Leave uncertainty unanswered"}
          </Button>
        </div>
        <div className={styles.optionalDetail + " min-w-0 space-y-1"} data-unanswered={proposedRange !== null}>
          <div className="flex items-center justify-center text-sm font-medium">
            Acceptable range
            <SignalHelp label="About acceptable outcomes">
              Moving either Min or Max bar includes the range in this answer, as does
              editing a bound in Fine adjustment. Use this range includes the displayed
              bounds without moving them. The initial full-width bars are not an answer.
              Hiding the range leaves it unanswered; showing it restores a preview
              for you to edit or include. Acceptance never changes the uncertainty curve.
            </SignalHelp>
          </div>
          <p id={id + "-range-value"} className="text-base font-semibold tabular-nums">
            {draft.acceptable_range === null ? "Not answered" :
              formatSpectrumValue(draft.acceptable_range.lower, scale) + " – " + formatSpectrumValue(draft.acceptable_range.upper, scale)}
          </p>
          <p id={id + "-range-status"} className={"min-h-5 text-xs " + (proposedRange ? styles.unansweredNotice : "text-muted-foreground")}>
            {proposedRange && <TriangleAlert className="mr-1 inline size-4 align-text-bottom" aria-hidden="true" />}
            {range === null ? "Hidden · not included" : proposedRange ? "Optional · not included yet" : "Included when you record this position"}
          </p>
          {proposedRange && <p className={styles.unansweredNotice + " text-xs"}>Move a bar or use this range to include it.</p>}
          <div className="flex flex-wrap justify-center gap-1">
            <Button type="button" variant="outline" disabled={disabled || range === null}
              className={"min-h-11 " + (draft.acceptable_range !== null ? styles.clearAnswer : "")}
              aria-describedby={id + "-range-value " + id + "-range-status"} onClick={toggleRangeAnswer}>
              {draft.acceptable_range !== null && <X className="size-4" aria-hidden="true" />}
              {draft.acceptable_range === null ? "Use this range" : "Leave range unanswered"}
            </Button>
            <Button type="button" variant="ghost" className="min-h-11" disabled={disabled}
              aria-describedby={id + "-range-status"} onClick={toggleRangeVisibility}>
              {range === null ? "Show range" : "Hide range"}
            </Button>
          </div>
        </div>
      </div>
      {outside && <p className="text-xs text-muted-foreground">Your position is outside your acceptable range. Neither answer will be adjusted automatically.</p>}
      <details className="border-t pt-3">
        <summary className="min-h-11 cursor-pointer text-sm">Fine adjustment and keyboard help</summary>
        <div className="grid gap-4 py-3 text-sm sm:grid-cols-2">
          <SpectrumFineAdjustment label="Position" scale={scale} disabled={disabled} min={scale.min} max={scale.max}
            step={scale.step} value={draft.position} onChange={(value) => change("position", value)} />
          <SpectrumFineAdjustment label="Uncertainty width (% of scale)" disabled={disabled || draft.position === null}
            min={SPECTRUM_SD_MIN * 100} max={SPECTRUM_SD_MAX * 100} step={0.1}
            value={draft.reported_uncertainty === null ? null : Number((sd * 100).toFixed(1))}
            onChange={(value) => change("uncertainty", value / 100)} />
          {range && (["lower", "upper"] as const).map((bound) => <SpectrumFineAdjustment key={bound} scale={scale}
            label={(bound === "lower" ? "Lowest" : "Highest") + " acceptable value" + (proposedRange ? " (proposed)" : "")}
            disabled={disabled} min={bound === "lower" ? scale.min : range.lower}
            max={bound === "upper" ? scale.max : range.upper} step={scale.step} value={range[bound]}
            onChange={(value) => change(bound, value)} />)}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">Tab between graph handles; use arrows for small changes and Page Up/Down for larger changes.
          On the peak, Up narrows and Down broadens. Min and Max remain reachable even when they coincide.
          Width is the illustrative Gaussian kernel’s standard deviation as a fraction of the scale.
          The displayed curve is bounded and area-normalized; this is not a measured probability or model confidence.</p>
      </details>
    </div>
  );
}
