"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { ComponentProps, KeyboardEvent, PointerEvent } from "react";
import { CircleHelp, RotateCcw, SlidersHorizontal, ZoomIn, ZoomOut } from "lucide-react";
import { SCALAR_DOMAIN, scalarFocusRange, scalarTransitionTicks, scalarPresentationPreview, scalarPresentationScore, taperRailPoint, taperRailWidth } from "@/lib/expressive-scalar-graph";
import type { TaperRailBounds } from "@/lib/expressive-scalar-graph";
import { useScalarViewport } from "@/lib/use-scalar-viewport";
import { TAX_MEASURE } from "@/lib/expressive-tax-measure";
import type { ScalarBallotState } from "@/types/expressive-scalar";
import styles from "./scalar-ballot.module.css";

const INITIAL: ScalarBallotState = { ideal: TAX_MEASURE.statusQuo, lower_half_width: 2, upper_half_width: 2, approval_min: 0, approval_max: 100, probe: TAX_MEASURE.statusQuo };
const rateText = (value: number) => value.toFixed(2);
const fieldText = (value: number) => Number(value.toFixed(3)).toString();
// Keep SVG serialization stable across JS runtimes; model values stay continuous.
const pixel = (value: number) => Math.round(value*1000)/1000;
const bounded = (value: number, minimum: number, maximum: number) => Math.max(minimum, Math.min(maximum, value));
type Handle = keyof ScalarBallotState;
type Point = { x: number; y: number };
type DragState = { id: number; handle: Handle; start: Point; startValue: number; ratePerPixel: number; moved: boolean; rail?: { ideal: number; direction: "lower" | "upper"; bounds: TaperRailBounds; point: Point } };
type Annotation = { key: Handle; title: string; detail?: string; point: Point; labelOffset: number; lane: number; labelWidth: number; tone: "ideal" | "bound" | "taper" | "probe"; offScale?: boolean };
type PlacedAnnotation = Annotation & { box: { x: number; y: number; width: number; height: number } };

interface NumberFieldProps extends Omit<ComponentProps<"input">, "value" | "type" | "onChange"> { value: number; onValueChange: (value: number) => void }
function NumberField({ value, onValueChange, onFocus, onBlur, ...props }: NumberFieldProps) {
  const [draft, setDraft] = useState<string | null>(null);
  return <input {...props} type="number" value={draft ?? fieldText(value)} onFocus={(event) => { setDraft(fieldText(value)); onFocus?.(event); }} onChange={(event) => { setDraft(event.currentTarget.value); if (Number.isFinite(event.currentTarget.valueAsNumber)) onValueChange(event.currentTarget.valueAsNumber); }} onBlur={(event) => { setDraft(null); onBlur?.(event); }} />;
}

// Fixed vertical lanes and widths keep every label reachable when handles
// coincide. Only horizontal positions follow the values, with continuous bounds.
function placeAnnotations(annotations: Annotation[], canvasWidth: number): PlacedAnnotation[] {
  const safeLeft = canvasWidth < 600 ? 48 : 60;
  return annotations.map((annotation) => {
    const labelWidth = Math.min(canvasWidth-safeLeft-12, annotation.labelWidth);
    return {
      ...annotation,
      box: {
        x: bounded(annotation.point.x-annotation.labelOffset, safeLeft, canvasWidth-labelWidth-12),
        y: annotation.lane,
        width: labelWidth,
        height: annotation.detail ? 36 : 22,
      },
    };
  });
}

interface ScalarBallotProps {
  onSubmitBallot?: (ballot: ScalarBallotState) => void;
  submittedBallot?: ScalarBallotState | null;
  canSubmit?: boolean;
  isSubmitting?: boolean;
  submissionHint?: string;
}

export function ScalarBallot({ onSubmitBallot, submittedBallot, canSubmit = true, isSubmitting = false, submissionHint }: ScalarBallotProps = {}) {
  const [ballot, setBallot] = useState<ScalarBallotState>({ ...INITIAL });
  const { view, from, target, progress, setView } = useScalarViewport(scalarFocusRange(INITIAL.ideal));
  const hostRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<DragState | null>(null);
  const pendingPointer = useRef<{ handle: Handle; value: number } | null>(null);
  const pointerFrame = useRef<number | null>(null);
  const [width, setWidth] = useState(1000);
  const id = useId().replace(/:/g, "");
  const curve = useMemo(() => scalarPresentationPreview({
    ideal: ballot.ideal,
    lower_half_width: ballot.lower_half_width,
    upper_half_width: ballot.upper_half_width,
    approval_min: ballot.approval_min,
    approval_max: ballot.approval_max,
    probe: ballot.ideal,
  }, view), [ballot.ideal, ballot.lower_half_width, ballot.upper_half_width, ballot.approval_min, ballot.approval_max, view]);
  const probe = scalarPresentationScore(ballot, ballot.probe);
  const probeScore = probe.score;
  const approved = probe.approved;
  const curveChanged = submittedBallot && (["ideal", "lower_half_width", "upper_half_width", "approval_min", "approval_max"] as const).some((key) => ballot[key] !== submittedBallot[key]);
  const narrow = width < 600;
  const height = narrow ? 560 : 500;
  const left = narrow ? 52 : 64;
  const right = width - (narrow ? 22 : 34);
  const top = narrow ? 82 : 76;
  const bottom = height - 126;
  const span = view.maximum - view.minimum;
  const inView = (value: number) => value >= view.minimum && value <= view.maximum;
  const x = (value: number) => pixel(left+(right-left)*(bounded(value, view.minimum, view.maximum)-view.minimum)/span);
  const edgeLabel = (value: number) => value < view.minimum ? "← " : value > view.maximum ? " →" : "";
  const y = (score: number) => pixel(bottom-(bottom-top)*score);
  const railBounds = { left, right, top, bottom, ...view };
  const lowerTaper = taperRailPoint(ballot.ideal, ballot.lower_half_width, "lower", railBounds);
  const upperTaper = taperRailPoint(ballot.ideal, ballot.upper_half_width, "upper", railBounds);
  const lowerRailEnd = taperRailPoint(ballot.ideal, 100, "lower", railBounds);
  const upperRailEnd = taperRailPoint(ballot.ideal, 100, "upper", railBounds);
  const paths = useMemo(() => {
    const plotX = (value: number) => pixel(left+(right-left)*(value-view.minimum)/span);
    const plotY = (score: number) => pixel(bottom-(bottom-top)*score);
    const clippedPoints = curve.points.filter((point) => point.value >= ballot.approval_min && point.value <= ballot.approval_max);
    const visibleMinimum = Math.max(view.minimum, ballot.approval_min);
    const visibleMaximum = Math.min(view.maximum, ballot.approval_max);
    const clippedSegments = clippedPoints.map((point) => `L${plotX(point.value)},${plotY(point.unclipped_score)}`).join(" ");
    return {
      unclipped: curve.points.map((point, index) => `${index === 0 ? "M" : "L"}${plotX(point.value)},${plotY(point.unclipped_score)}`).join(" "),
      clipped: clippedPoints.length ? `${ballot.approval_min >= view.minimum ? `M${left},${bottom} L${plotX(visibleMinimum)},${bottom} ` : `M${plotX(clippedPoints[0].value)},${plotY(clippedPoints[0].unclipped_score)} `}${clippedSegments}${ballot.approval_max <= view.maximum ? ` L${plotX(visibleMaximum)},${bottom} L${right},${bottom}` : ""}` : "",
      fill: clippedPoints.length ? `M${plotX(visibleMinimum)},${bottom} ${clippedSegments} L${plotX(visibleMaximum)},${bottom} Z` : "",
    };
  }, [curve, ballot.approval_min, ballot.approval_max, left, right, top, bottom, view, span]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)));
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  useEffect(() => () => {
    if (pointerFrame.current !== null) cancelAnimationFrame(pointerFrame.current);
    pendingPointer.current = null;
  }, []);

  const update = (key: Handle, value: number, continuous = false) => {
    if (!Number.isFinite(value)) return;
    const minimum = key === "ideal" ? ballot.approval_min : key === "approval_max" ? ballot.ideal : key === "lower_half_width" || key === "upper_half_width" ? 0.1 : 0;
    const maximum = key === "ideal" ? ballot.approval_max : key === "approval_min" ? ballot.ideal : 100;
    const subdivisions = key === "lower_half_width" || key === "upper_half_width" ? 10 : 20;
    const next = bounded(continuous ? value : Math.round(value*subdivisions)/subdivisions, minimum, maximum);
    if (key === "ideal" && !inView(next)) setView(scalarFocusRange(next), { immediate: true });
    else if (progress < 1) setView(view, { immediate: true });
    setBallot((previous) => next === previous[key] ? previous : { ...previous, [key]: next });
  };
  const localPoint = (event: PointerEvent<SVGElement>) => {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return null;
    const point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY;
    return point.matrixTransform(matrix.inverse());
  };
  const beginDrag = (event: PointerEvent<SVGGElement>, handle: Handle) => {
    if (event.button !== 0 || drag.current) return;
    const pointer = localPoint(event);
    if (pointer === null) return;
    event.preventDefault();
    // Direct editing takes over the visible scale without a moving target.
    setView(view, { immediate: true });
    // Large hit targets overlap at peaks and viewport edges. Bare markers select
    // the nearest control; labels always select their named control. The ideal
    // wins exact overlaps with the probe so the initial peak remains draggable.
    if (!(event.target as Element).classList.contains(styles.labelBackground)) {
      const candidates: { handle: Handle; point: Point }[] = [
        { handle: "ideal", point: { x: x(ballot.ideal), y: top } },
        { handle: "approval_min", point: { x: x(ballot.approval_min), y: bottom + 8 } },
        { handle: "approval_max", point: { x: x(ballot.approval_max), y: bottom - 8 } },
        { handle: "probe", point: { x: x(ballot.probe), y: y(probeScore) } },
        { handle: "lower_half_width", point: lowerTaper },
        { handle: "upper_half_width", point: upperTaper },
      ];
      handle = candidates.reduce((nearest, candidate) => Math.hypot(pointer.x-candidate.point.x, pointer.y-candidate.point.y) < Math.hypot(pointer.x-nearest.point.x, pointer.y-nearest.point.y) ? candidate : nearest).handle;
    }
    const direction = handle === "lower_half_width" ? "lower" : handle === "upper_half_width" ? "upper" : null;
    drag.current = {
      id: event.pointerId, handle, start: { x: pointer.x, y: pointer.y }, startValue: direction ? ballot[handle] : bounded(ballot[handle], view.minimum, view.maximum), ratePerPixel: span/(right-left), moved: false,
      rail: direction ? { ideal: ballot.ideal, direction, bounds: railBounds, point: taperRailPoint(ballot.ideal, ballot[handle], direction, railBounds) } : undefined,
    };
    svgRef.current?.setPointerCapture(event.pointerId);
  };
  const flushPointer = () => {
    if (pointerFrame.current !== null) cancelAnimationFrame(pointerFrame.current);
    pointerFrame.current = null;
    const pending = pendingPointer.current;
    pendingPointer.current = null;
    if (pending) update(pending.handle, pending.value, true);
  };
  const queuePointer = (event: PointerEvent<SVGSVGElement>) => {
    const active = drag.current;
    if (!active || active.id !== event.pointerId) return;
    const pointer = localPoint(event);
    if (pointer === null) return;
    const deltaX = pointer.x-active.start.x;
    const deltaY = pointer.y-active.start.y;
    if (!active.moved && Math.hypot(deltaX, deltaY) < 2) return;
    active.moved = true;
    const value = active.rail
      ? taperRailWidth(active.rail.ideal, active.rail.direction, { x: active.rail.point.x+deltaX, y: active.rail.point.y+deltaY }, active.rail.bounds)
      : bounded(active.startValue+deltaX*active.ratePerPixel, view.minimum, view.maximum);
    pendingPointer.current = { handle: active.handle, value };
  };
  const moveDrag = (event: PointerEvent<SVGSVGElement>) => {
    queuePointer(event);
    if (pendingPointer.current && pointerFrame.current === null) pointerFrame.current = requestAnimationFrame(flushPointer);
  };
  const endDrag = (event: PointerEvent<SVGSVGElement>) => {
    if (drag.current?.id !== event.pointerId) return;
    queuePointer(event);
    flushPointer();
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const cancelDrag = (event: PointerEvent<SVGSVGElement>) => {
    if (drag.current?.id !== event.pointerId) return;
    flushPointer();
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const onHandleKey = (event: KeyboardEvent<SVGGElement>, handle: Handle) => {
    const subdivisions = handle === "lower_half_width" || handle === "upper_half_width" ? 10 : 20;
    const step = event.shiftKey ? 1 : 1/subdivisions;
    const minimum = handle === "ideal" ? ballot.approval_min : handle === "approval_max" ? ballot.ideal : handle === "lower_half_width" || handle === "upper_half_width" ? 0.1 : 0;
    const maximum = handle === "ideal" ? ballot.approval_max : handle === "approval_min" ? ballot.ideal : 100;
    let next = Math.round(ballot[handle]*subdivisions)/subdivisions;
    if (["ArrowLeft", "ArrowDown"].includes(event.key)) next -= step;
    else if (["ArrowRight", "ArrowUp"].includes(event.key)) next += step;
    else if (event.key === "Home") next = minimum;
    else if (event.key === "End") next = maximum;
    else return;
    event.preventDefault(); update(handle, next, event.key === "Home" || event.key === "End");
  };

  const annotations = placeAnnotations([
    { key: "ideal", title: `Ideal ${rateText(ballot.ideal)}%`, point: { x: x(ballot.ideal), y: top }, labelOffset: 45, lane: 14, labelWidth: 120, tone: "ideal" },
    { key: "approval_min", title: `${edgeLabel(ballot.approval_min)}${rateText(ballot.approval_min)}%`, point: { x: x(ballot.approval_min), y: bottom+8 }, labelOffset: 24, lane: bottom+46, labelWidth: 85, tone: "bound" },
    { key: "approval_max", title: `${rateText(ballot.approval_max)}%${edgeLabel(ballot.approval_max)}`, point: { x: x(ballot.approval_max), y: bottom-8 }, labelOffset: 24, lane: bottom+76, labelWidth: 85, tone: "bound" },
    { key: "lower_half_width", title: "", point: { x: pixel(lowerTaper.x), y: pixel(lowerTaper.y) }, labelOffset: 115, lane: narrow ? 134 : 112, labelWidth: 190, tone: "taper", offScale: lowerTaper.offScale },
    { key: "upper_half_width", title: "", point: { x: pixel(upperTaper.x), y: pixel(upperTaper.y) }, labelOffset: -15, lane: narrow ? 282 : 252, labelWidth: 190, tone: "taper", offScale: upperTaper.offScale },
    { key: "probe", title: `Probe · Tax rate ${rateText(ballot.probe)}%${edgeLabel(ballot.probe)}`, detail: `Score ${probeScore.toFixed(3)}`, point: { x: x(ballot.probe), y: y(probeScore) }, labelOffset: -20, lane: narrow ? 370 : 316, labelWidth: 214, tone: "probe" },
  ], width);
  const handleNames: Record<Handle, string> = { ideal: "Preferred income tax rate", approval_min: "Lower approval bound", approval_max: "Upper approval bound", lower_half_width: "Lower-rate taper half-value distance", upper_half_width: "Higher-rate taper half-value distance", probe: "Proposed rate to inspect on curve" };
  const renderAnnotation = ({ key, title, detail, point, box, tone, offScale }: PlacedAnnotation) => {
    const minimum = key === "ideal" ? ballot.approval_min : key === "approval_max" ? ballot.ideal : key === "lower_half_width" || key === "upper_half_width" ? 0.1 : 0;
    const maximum = key === "ideal" ? ballot.approval_max : key === "approval_min" ? ballot.ideal : 100;
    const isBound = key === "approval_min" || key === "approval_max";
    return <g key={key} role="slider" tabIndex={0} className={`${styles.handle} ${styles[tone]} ${tone === "probe" && !approved ? styles.probeMuted : ""} ${tone === "taper" && offScale ? styles.onRail : ""}`} aria-label={handleNames[key]} aria-valuemin={minimum} aria-valuemax={maximum} aria-valuenow={ballot[key]} aria-valuetext={`${rateText(ballot[key])} ${tone === "taper" ? "percentage points" : "percent"}${key === "probe" ? `, score ${probeScore.toFixed(3)}, ${approved ? "approved" : "outside approval"}` : ""}`} aria-orientation={tone === "taper" && offScale ? "vertical" : "horizontal"} aria-describedby={tone === "taper" ? `${id}-taper-guidance` : undefined} onPointerDown={(event) => beginDrag(event, key)} onKeyDown={(event) => onHandleKey(event, key)}>
      <title>{tone === "taper" ? `${handleNames[key]}: ${fieldText(ballot[key])} percentage points${offScale ? ". Continue up the edge rail to broaden." : ". Drag away from the ideal to broaden."}` : `${handleNames[key]}${!inView(ballot[key]) ? ": outside the visible range. Zoom out to see its position, or drag inward to move it into view." : ""}`}</title>
      {isBound ? <rect className={styles.hitTarget} x={point.x-19} y={key === "approval_min" ? bottom : bottom-28} width={38} height={28} fill="transparent" /> : <circle className={styles.hitTarget} cx={point.x} cy={point.y} r={19} fill="transparent" />}
      {tone === "ideal" && <circle className={styles.handleDot} cx={point.x} cy={point.y} r={7} />}
      {tone === "probe" && <circle className={styles.handleDot} cx={point.x} cy={point.y} r={6} />}
      {tone === "bound" && <path className={styles.boundMarker} d={key === "approval_min" ? `M${point.x-6},${bottom+14} L${point.x},${bottom+3} L${point.x+6},${bottom+14} Z` : `M${point.x-6},${bottom-14} L${point.x},${bottom-3} L${point.x+6},${bottom-14} Z`} />}
      {tone === "taper" && <path className={styles.taperMarker} d={`M${point.x},${point.y-6} L${point.x+6},${point.y} L${point.x},${point.y+6} L${point.x-6},${point.y} Z`} />}
      {title && <><rect className={styles.labelBackground} x={box.x} y={box.y} width={box.width} height={box.height} rx={3} />
      <text x={box.x+7} y={box.y+14} className={styles.annotationTitle}>{title}</text>
      {detail && <text x={box.x+7} y={box.y+28} className={styles.annotationDetail}>{detail}</text>}</>}
    </g>;
  };
  const reset = () => {
    const active = drag.current;
    if (pointerFrame.current !== null) cancelAnimationFrame(pointerFrame.current);
    pointerFrame.current = null;
    pendingPointer.current = null;
    drag.current = null;
    if (active && svgRef.current?.hasPointerCapture(active.id)) svgRef.current.releasePointerCapture(active.id);
    setBallot({ ...INITIAL });
    setView(scalarFocusRange(INITIAL.ideal), { immediate: true });
  };

  return <section className={styles.ballot} aria-label="Scalar income-tax ballot">
    <div className={styles.visualColumn}>
      <div className={styles.questionHeader}><div><span className={styles.eyebrow}>Beyond the 2022 question · an experimental ballot</span><h2>What should the state income tax rate be?</h2></div><button type="button" className={styles.resetButton} onClick={reset} aria-label="Reset rate ballot"><RotateCcw size={14} /> Reset</button></div>
      <div className={styles.zoomBar}>
        <p>Starting from the 2022 statutory rate: <strong>{rateText(TAX_MEASURE.statusQuo)}%</strong></p>
        <div className={styles.zoomControls} role="group" aria-label="Ballot graph zoom">
          <span>{fieldText(target.minimum)}–{fieldText(target.maximum)}%</span>
          <button type="button" onClick={() => { if (!drag.current) setView(SCALAR_DOMAIN); }} aria-pressed={target.minimum === 0 && target.maximum === 100}><ZoomOut size={14} /> 0–100%</button>
          <button type="button" onClick={() => { if (!drag.current) setView(scalarFocusRange(ballot.ideal)); }} aria-label="Zoom to ideal plus or minus 5 percentage points"><ZoomIn size={14} /> Ideal ±5 pp</button>
        </div>
      </div>
      <div ref={hostRef} className={styles.chartHost}>
        <svg ref={svgRef} className={styles.chart} width="100%" height={height} viewBox={`0 0 ${width} ${height}`} aria-labelledby={`${id}-title`} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={cancelDrag} onLostPointerCapture={cancelDrag}>
          <title id={`${id}-title`}>Editable income-tax utility curve with ideal, two taper distances, approval bounds, and a rate probe</title>
          <desc>Drag the markers to edit your ballot or use arrow keys. The gold marker inspects a rate. Fine controls provide numerical alternatives.</desc>
          <desc id={`${id}-taper-guidance`}>Taper diamonds move horizontally at half-value until the plot edge, then upward along the edge rail. Rail height controls taper width; it does not represent the score.</desc>
          <rect x={left} y={top} width={right-left} height={bottom-top} className={styles.plotFrame} />
          <rect x={x(ballot.approval_min)} y={top} width={x(ballot.approval_max)-x(ballot.approval_min)} height={bottom-top} className={styles.approvalBand} />
          {[0,0.5,1].map((score) => <g key={score}><line x1={left} x2={right} y1={y(score)} y2={y(score)} className={styles.gridLine} /><text x={left-11} y={y(score)+4} textAnchor="end" className={styles.tickLabel}>{score}</text></g>)}
          {scalarTransitionTicks(from, target, progress, narrow).filter(({ value }) => inView(value)).map(({ value, opacity }) => <g key={value} opacity={opacity}><line x1={x(value)} x2={x(value)} y1={bottom} y2={bottom+4} className={styles.gridLine} /><text x={x(value)} y={bottom+27} textAnchor={value === 0 ? "start" : value === 100 ? "end" : "middle"} className={styles.tickLabel}>{fieldText(value)}%</text></g>)}
          <text x={(left+right)/2} y={height-10} textAnchor="middle" className={styles.axisLabel}>State income tax rate (%)</text>
          <text transform={`translate(13 ${(top+bottom)/2}) rotate(-90)`} textAnchor="middle" className={styles.axisLabel}>Declared value</text>
          <g><path d={paths.unclipped} className={styles.unclippedCurve} /><path d={paths.fill} className={styles.curveFill} /><path d={paths.clipped} className={styles.clippedCurve} /></g>
          {[ballot.approval_min,ballot.approval_max].filter(inView).map((value,index) => <line key={index} x1={x(value)} x2={x(value)} y1={top} y2={bottom} className={styles.boundLine} />)}
          <path d={`M${left},${y(0.5)} L${left},${pixel(lowerRailEnd.y)} M${pixel(right)},${y(0.5)} L${pixel(right)},${pixel(upperRailEnd.y)}`} className={styles.taperRail} />
          <line x1={x(ballot.ideal)} x2={x(ballot.ideal)} y1={top} y2={bottom} className={styles.idealGuide} />
          {inView(ballot.probe) && <line x1={x(ballot.probe)} x2={x(ballot.probe)} y1={bottom} y2={y(probeScore)} className={`${styles.probeLine} ${!approved ? styles.probeMuted : ""}`} />}
          {annotations.filter((annotation) => annotation.title).map(({ key, point, box, tone }) => <path key={key} d={`M${point.x},${point.y} L${bounded(point.x, box.x+8, box.x+box.width-8)},${bounded(point.y, box.y+7, box.y+box.height-7)}`} className={`${styles.annotationLeader} ${styles[tone]} ${tone === "probe" && !approved ? styles.probeMuted : ""}`} />)}
          {annotations.filter((annotation) => annotation.tone !== "taper" && annotation.tone !== "ideal").map(renderAnnotation)}
          {annotations.filter((annotation) => annotation.tone === "ideal").map(renderAnnotation)}
          {annotations.filter((annotation) => annotation.tone === "taper").map(renderAnnotation)}
        </svg>
      </div>

    </div>

    <details className={styles.fineControls}>
      <summary><SlidersHorizontal size={16} /><span>Fine controls</span><small>Numeric values and sliders</small></summary>
      <div className={styles.fineGrid}>
        <div className={styles.controlSection}><h3>Preferred rate</h3><div className={styles.controlTop}><label htmlFor={`${id}-ideal`}>Preferred rate</label><div className={styles.numberInput}><NumberField id={`${id}-ideal`} min={ballot.approval_min} max={ballot.approval_max} step={0.05} value={ballot.ideal} onValueChange={(value) => update("ideal",value)} aria-label="Preferred rate percentage" /><span>%</span></div></div><input className={styles.range} type="range" min={ballot.approval_min} max={ballot.approval_max} step={0.05} value={ballot.ideal} onChange={(event) => update("ideal",Number(event.currentTarget.value))} aria-label="Adjust preferred rate" /><p>The ideal stays within your approval bounds.</p></div>
        <div className={styles.controlSection}><h3>Approval bounds</h3>{([{key:"approval_min",label:"Lowest approved rate",minimum:0,maximum:ballot.ideal},{key:"approval_max",label:"Highest approved rate",minimum:ballot.ideal,maximum:100}] as const).map(({key,label,minimum,maximum}) => <div className={styles.controlRow} key={key}><div className={styles.controlTop}><label htmlFor={`${id}-${key}`}>{label}</label><div className={styles.numberInput}><NumberField id={`${id}-${key}`} min={minimum} max={maximum} step={0.05} value={ballot[key]} onValueChange={(value) => update(key,value)} /><span>%</span></div></div><input className={styles.range} type="range" min={minimum} max={maximum} step={0.05} value={ballot[key]} onChange={(event) => update(key,Number(event.currentTarget.value))} aria-label={`Adjust ${label.toLowerCase()}`} /></div>)}</div>
        <div className={styles.controlSection}><h3>Preference taper</h3>{([{key:"lower_half_width",label:"Toward lower rates"},{key:"upper_half_width",label:"Toward higher rates"}] as const).map(({key,label}) => <div className={styles.controlRow} key={key}><div className={styles.controlTop}><label htmlFor={`${id}-${key}`}>{label}</label><div className={styles.numberInput}><NumberField id={`${id}-${key}`} min={0.1} max={100} step={0.1} value={ballot[key]} onValueChange={(value) => update(key,value)} /><span>pp</span></div></div><input className={styles.range} type="range" min={0.1} max={100} step={0.1} value={ballot[key]} onChange={(event) => update(key,Number(event.currentTarget.value))} aria-label={`Adjust flexibility ${label.toLowerCase()}`} /></div>)}</div>
        <div className={styles.controlSection}><h3>Rate probe</h3><div className={styles.controlTop}><label htmlFor={`${id}-probe`}>Inspect a proposed rate</label><div className={styles.numberInput}><NumberField id={`${id}-probe`} min={0} max={100} step={0.05} value={ballot.probe} onValueChange={(value) => update("probe",value)} aria-label="Proposed rate to inspect" /><span>%</span></div></div><input className={styles.range} type="range" min={0} max={100} step={0.05} value={ballot.probe} onChange={(event) => update("probe",Number(event.currentTarget.value))} aria-label="Adjust proposed rate" /><p>Probe edits inspect the current curve without changing your ballot.</p></div>
      </div>
    </details>
    <details className={styles.methodDetails}><summary><CircleHelp size={16} /> Guide to this ballot</summary><div>
      <p>Drag the peak to set your ideal rate, the triangles to set inclusive approval bounds, and the gold probe to inspect a rate. Their labels are draggable too. Arrow keys adjust focused controls; Fine controls provide numerical inputs.</p>
      <p>The full range is 0–100%. Zoom in to five percentage points either side of your ideal, rounded outward to whole percentages and clipped at 0% and 100%. The view stays fixed while dragging; press Ideal ±5 pp to recenter. Zoom never changes your ballot. An arrow beside a label means that value is outside the visible range: zoom out to see it, or drag its edge handle inward to bring it into view.</p>
      <p>Move a taper diamond away from the ideal to broaden that side of the curve. It follows the half-value line to the plot edge, then moves up the edge rail as the half-value point extends beyond the displayed rate range. Rail height controls taper width; it is not a score.</p>
      <div className={styles.legend}><span><i className={styles.solidKey} /> Ballot value</span><span><i className={styles.dashedKey} /> Unclipped taper</span><span><i className={styles.goldKey} /> Rate probe</span></div>
      <p>The curve expresses declared value, not probability. Its peak is 1. Within the approval bounds, value is <code>2^−(distance from ideal / half-value distance)²</code>; outside them, value is zero and the probe dims. Clipping never rescales the surviving curve.</p>
      <p>This experimental extension of the 2022 question has no tax-revenue or household-impact model. Assigning zero does not give an individual a veto. The comparison below uses a separately stated collective rule.</p>
    </div></details>
    {onSubmitBallot && <div className={styles.submissionFooter}>
      <p>{submissionHint || (curveChanged ? "Curve edited. The comparison still uses your submitted curve." : submittedBallot ? "The comparison uses your submitted curve. Submit again after making changes." : "Your curve joins 99 prepared ballots. The graph remains editable.")}</p>
      <button type="button" disabled={!canSubmit || isSubmitting} onClick={() => onSubmitBallot({ ...ballot })}>{isSubmitting ? "Comparing ballots…" : submittedBallot ? "Compare again" : "Compare ballots"}<span aria-hidden="true">→</span></button>
    </div>}
  </section>;
}
