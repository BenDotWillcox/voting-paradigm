"use client";

import Link from "next/link";
import { memo, useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowDown, ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { scalarFocusRange, scalarPresentationPreview, scalarTransitionTicks, SCALAR_DOMAIN, type ScalarGraphRange } from "@/lib/expressive-scalar-graph";
import { useScalarViewport } from "@/lib/use-scalar-viewport";
import type { CurveVote, ScalarComparisonResponse, ScalarComparisonVoter, ScalarScenario } from "@/types/expressive-comparison";
import type { ScalarBallotState } from "@/types/expressive-scalar";
import styles from "./electorate-results.module.css";

const rateText = (rate: number) => `${rate.toFixed(2)}%`;
const scoreText = (score: number, digits = 4) => score > 0 && score < 0.0001 ? score.toExponential(digits - 1) : score.toFixed(digits);
// Preserve visible ordering even for tails close to zero or almost-equal peaks.
function pairScoreText(first: number, second: number, tied: boolean): [string, string] {
  for (let digits = 4; digits <= 12; digits += 1) {
    const values: [string, string] = [scoreText(first, digits), scoreText(second, digits)];
    if (tied || values[0] !== values[1] || digits === 12) return values;
  }
  return [String(first), String(second)];
}
const voteText = (vote: CurveVote) => vote === "yes" ? "Yes" : vote === "no" ? "No" : "Equal scores";
const voteClass = (vote: CurveVote) => vote === "yes" ? styles.yes : vote === "no" ? styles.no : styles.equal;
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
const scenarioLabels: Record<ScalarScenario, string> = {
  prepared: "Original electorate",
  "broad-agreement": "Broad agreement",
  polarized: "Polarized electorate",
  "intense-minority": "Intense minority",
};
const scenarioPresets: { id: ScalarScenario; description: string }[] = [
  { id: "broad-agreement", description: "Nearby ideals, varied tolerances, and overlapping approval bands." },
  { id: "polarized", description: "Two separated camps, with different curves within each." },
  { id: "intense-minority", description: "A smaller group’s scores fall sharply; a larger group is more tolerant." },
];
type ScenarioControls = {
  onScenarioChange: (scenario: ScalarScenario) => void;
  scenarioPending: ScalarScenario | null;
  scenarioError: string | null;
  onRetryScenario: () => void;
  scenarioDisabled: boolean;
};

type PreparedVoter = ScalarComparisonVoter & { path: string; miniatureRange: ScalarGraphRange };
type Viewport = ReturnType<typeof useScalarViewport>;
type PlotGeometry = { x: (rate: number) => number; y: (score: number) => number; transform: string; clipId: string; left: number; right: number; top: number; bottom: number };

/** Policy-space paths are sampled once, then transformed as the shared axis zooms. */
function prepareVoter(voter: ScalarComparisonVoter): PreparedVoter {
  const ballot = { ...voter.ballot, probe: voter.ballot.ideal };
  const samples = scalarPresentationPreview(ballot).points.filter((point) => point.value >= ballot.approval_min && point.value <= ballot.approval_max);
  const path = ["M 0 1", `L ${ballot.approval_min} 1`, ...samples.map((point) => `L ${point.value} ${1 - point.unclipped_score}`), `L ${ballot.approval_max} 1`, "L 100 1"].join(" ");
  return { ...voter, path, miniatureRange: scalarFocusRange(ballot.ideal) };
}

const BackgroundCurves = memo(function BackgroundCurves({ voters }: { voters: PreparedVoter[] }) {
  return <g className={styles.backgroundCurves} aria-hidden="true">{voters.map((voter) => <path key={voter.id} d={voter.path} className={voteClass(voter.binary_vote)} vectorEffect="non-scaling-stroke" />)}</g>;
});

function Plot({ viewport, label, children }: { viewport: Viewport; label: string; children: (geometry: PlotGeometry) => ReactNode }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const clipId = useId().replaceAll(":", "");
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(260, entry.contentRect.width)));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const left = width < 500 ? 35 : 46;
  const right = width - 19;
  const top = 26;
  const bottom = width < 500 ? 228 : 268;
  const span = viewport.view.maximum - viewport.view.minimum;
  const x = (rate: number) => left + (rate - viewport.view.minimum) / span * (right - left);
  const y = (score: number) => bottom - score * (bottom - top);
  const transform = `translate(${left} ${top}) scale(${(right - left) / span} ${bottom - top}) translate(${-viewport.view.minimum} 0)`;
  return <div className={styles.plotWrap} ref={container}>
    <svg className={styles.plot} viewBox={`0 0 ${width} ${bottom + 49}`} role="img" aria-label={label}>
      <defs><clipPath id={clipId}><rect x={left} y={top - 5} width={right - left} height={bottom - top + 10} /></clipPath></defs>
      {[0, 0.5, 1].map((score) => <g key={score}><line className={styles.grid} x1={left} x2={right} y1={y(score)} y2={y(score)} /><text x={left - 11} y={y(score) + 4} textAnchor="end">{score}</text></g>)}
      <text x={left} y={12} className={styles.axisTitle}>Declared score</text>
      {scalarTransitionTicks(viewport.from, viewport.target, viewport.progress, width < 500).map(({ value, opacity }) => x(value) >= left - 1 && x(value) <= right + 1 && <g key={value} opacity={opacity}>
        <line className={styles.tick} x1={x(value)} x2={x(value)} y1={bottom} y2={bottom + 5} />
        <text x={x(value)} y={bottom + 21} textAnchor={x(value) < left + 12 ? "start" : x(value) > right - 12 ? "end" : "middle"}>{Number(value.toFixed(2))}%</text>
      </g>)}
      {children({ x, y, transform, clipId, left, right, top, bottom })}
      <text x={(left + right) / 2} y={bottom + 43} textAnchor="middle">Income tax rate</text>
    </svg>
  </div>;
}

function ZoomControls({ viewport, focus, focusLabel }: { viewport: Viewport; focus: number; focusLabel: string }) {
  const isFull = viewport.target.minimum === 0 && viewport.target.maximum === 100;
  return <div className={styles.zoomControls}>
    <span>{viewport.target.minimum}–{viewport.target.maximum}% view</span>
    <button type="button" onClick={() => viewport.setView(scalarFocusRange(focus))}>{focusLabel}</button>
    <button type="button" aria-pressed={isFull} onClick={() => viewport.setView(SCALAR_DOMAIN)}>0–100%</button>
  </div>;
}

function VoterGraph({ voters, selected, data }: { voters: PreparedVoter[]; selected: PreparedVoter; data: ScalarComparisonResponse }) {
  const viewport = useScalarViewport(scalarFocusRange(data.status_quo));
  const outside = selected.ballot.ideal < viewport.target.minimum || selected.ballot.ideal > viewport.target.maximum;
  return <div className={styles.voterGraph}>
    <div className={styles.graphToolbar}>
      <span className={styles.graphKey}><i className={`${styles.lineKey} ${voteClass(selected.binary_vote)}`} />Selected voter <i className={styles.contextKey} />Other voters</span>
      <ZoomControls viewport={viewport} focus={selected.ballot.ideal} focusLabel="Focus selected" />
    </div>
    <Plot viewport={viewport} label={`${selected.label}: ideal ${rateText(selected.ballot.ideal)}, ${voteText(selected.binary_vote)} on the binary ballot. Proposal score ${scoreText(selected.proposal_score)}; status quo score ${scoreText(selected.status_quo_score)}.`}>
      {({ x, y, transform, clipId, top, bottom }) => <>
        <g clipPath={`url(#${clipId})`}>
          <g transform={transform}><BackgroundCurves voters={voters} /></g>
          <line className={styles.statusMarker} x1={x(data.status_quo)} x2={x(data.status_quo)} y1={top} y2={bottom} />
          <line className={styles.proposalMarker} x1={x(data.proposal)} x2={x(data.proposal)} y1={top} y2={bottom} />
          <g transform={transform}><path d={selected.path} className={`${styles.selectedCurve} ${voteClass(selected.binary_vote)}`} vectorEffect="non-scaling-stroke" /></g>
          <circle className={`${styles.idealDot} ${voteClass(selected.binary_vote)}`} cx={x(selected.ballot.ideal)} cy={y(1)} r={4.5} />
          <circle className={styles.statusDot} cx={x(data.status_quo)} cy={y(selected.status_quo_score)} r={5} />
          <path className={styles.proposalDot} d={`M ${x(data.proposal)} ${y(selected.proposal_score) - 5} l 5 5 l -5 5 l -5 -5 Z`} />
        </g>
      </>}
    </Plot>
    <div className={styles.plotLegend}><span><i className={styles.proposalKey} />Yes → {rateText(data.proposal)}</span><span><i className={styles.statusKey} />No → {rateText(data.status_quo)}</span></div>
    <p className={styles.offscreenNote} data-visible={outside} aria-hidden={!outside}>This voter’s ideal is outside the view. <button type="button" tabIndex={outside ? 0 : -1} onClick={() => viewport.setView(scalarFocusRange(selected.ballot.ideal))}>Focus {rateText(selected.ballot.ideal)}</button></p>
  </div>;
}

function VoterStrip({ voters, selectedIndex, onSelect }: { voters: PreparedVoter[]; selectedIndex: number; onSelect: (index: number) => void }) {
  const strip = useRef<HTMLDivElement>(null);
  const cards = useRef<(HTMLButtonElement | null)[]>([]);
  const scrollFrame = useRef<number | null>(null);
  const drag = useRef<{ pointer: number; x: number; left: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const lastSelected = useRef(selectedIndex);
  const initialized = useRef(false);

  const center = useCallback((index: number) => {
    const element = cards.current[index];
    if (element && strip.current) strip.current.scrollLeft = element.offsetLeft + element.offsetWidth / 2 - strip.current.clientWidth / 2;
  }, []);

  useEffect(() => {
    // External arrows, shortcuts, and the range select a card; native scrolling
    // updates lastSelected first so it never fights the user's momentum.
    if (!initialized.current || lastSelected.current !== selectedIndex) center(selectedIndex);
    initialized.current = true;
    lastSelected.current = selectedIndex;
  }, [center, selectedIndex]);

  useEffect(() => {
    if (!strip.current) return;
    const observer = new ResizeObserver(() => center(lastSelected.current));
    observer.observe(strip.current);
    return () => { observer.disconnect(); if (scrollFrame.current !== null) cancelAnimationFrame(scrollFrame.current); };
  }, [center]);

  const selectFromScroll = () => {
    if (scrollFrame.current !== null) return;
    scrollFrame.current = requestAnimationFrame(() => {
      scrollFrame.current = null;
      const element = strip.current;
      if (!element) return;
      const middle = element.scrollLeft + element.clientWidth / 2;
      let nearest = 0;
      let distance = Infinity;
      cards.current.forEach((card, index) => {
        if (!card) return;
        const next = Math.abs(card.offsetLeft + card.offsetWidth / 2 - middle);
        if (next < distance) { distance = next; nearest = index; }
      });
      lastSelected.current = nearest;
      selectRef.current(nearest);
    });
  };

  return <div className={styles.stripShell}>
    <div className={styles.stripCenter} aria-hidden="true" />
    <div ref={strip} className={styles.voterStrip} role="group" aria-label="Voter curves, ordered by ideal tax rate. Scroll horizontally to select a voter."
      onScroll={selectFromScroll}
      onKeyDown={(event) => {
        const index = event.key === "ArrowRight" ? selectedIndex + 1 : event.key === "ArrowLeft" ? selectedIndex - 1 : event.key === "Home" ? 0 : event.key === "End" ? voters.length - 1 : null;
        if (index === null) return;
        event.preventDefault();
        const next = clamp(index, 0, voters.length - 1);
        onSelect(next);
        center(next);
        cards.current[next]?.focus({ preventScroll: true });
      }}
      onPointerDown={(event) => {
        if (event.pointerType !== "mouse" || event.button !== 0) return;
        drag.current = { pointer: event.pointerId, x: event.clientX, left: event.currentTarget.scrollLeft, moved: false };
      }}
      onPointerMove={(event) => {
        const active = drag.current;
        if (!active || active.pointer !== event.pointerId) return;
        if (event.buttons === 0) { drag.current = null; event.currentTarget.style.scrollSnapType = ""; return; }
        const delta = event.clientX - active.x;
        if (Math.abs(delta) < 5 && !active.moved) return;
        active.moved = true;
        event.currentTarget.setPointerCapture(event.pointerId);
        event.currentTarget.style.scrollSnapType = "none";
        event.currentTarget.scrollLeft = active.left - delta;
      }}
      onPointerUp={(event) => {
        if (!drag.current) return;
        suppressClick.current = drag.current.moved;
        drag.current = null;
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        event.currentTarget.style.scrollSnapType = "";
        window.setTimeout(() => { suppressClick.current = false; }, 0);
      }}
      onPointerCancel={(event) => { drag.current = null; event.currentTarget.style.scrollSnapType = ""; }}
      onClickCapture={(event) => { if (suppressClick.current) { event.preventDefault(); event.stopPropagation(); } }}>
      {voters.map((voter, index) => <button type="button" key={voter.id} ref={(element) => { cards.current[index] = element; }}
        className={`${styles.voterCard} ${voteClass(voter.binary_vote)}`} aria-pressed={index === selectedIndex} tabIndex={index === selectedIndex ? 0 : -1}
        aria-label={`${voter.label}, ideal ${rateText(voter.ballot.ideal)}, ${voteText(voter.binary_vote)}`}
        onClick={() => { onSelect(index); center(index); }}>
        <span>{voter.id === "you" ? "You" : voter.label}</span>
        <svg viewBox={`${voter.miniatureRange.minimum} -0.08 ${voter.miniatureRange.maximum - voter.miniatureRange.minimum} 1.16`} preserveAspectRatio="none" aria-hidden="true"><path d={voter.path} vectorEffect="non-scaling-stroke" /></svg>
        <strong>{rateText(voter.ballot.ideal)}</strong><small>{voteText(voter.binary_vote)}</small>
      </button>)}
    </div>
  </div>;
}

function BinaryTally({ data }: { data: ScalarComparisonResponse }) {
  return <div className={styles.binaryTally}>
    <div className={styles.tallyCopy}><strong>100 voters. One yes/no question.</strong><span>Different curves collapse into the same answer.</span></div>
    <div className={styles.tallyChart}>
      <div className={styles.tallyBar} aria-hidden="true"><i className={styles.yesFill} style={{ width: `${data.binary.yes}%` }} /><i className={styles.noFill} style={{ width: `${data.binary.no}%` }} /><i className={styles.equalFill} style={{ width: `${data.binary.abstain}%` }} /></div>
      <div className={styles.tallyLabels}><span className={styles.yes}>{data.binary.yes} Yes</span><span className={styles.no}>{data.binary.no} No</span><span>{data.binary.abstain} equal / unmarked</span></div>
    </div>
  </div>;
}

function RateWinners({ rates }: { rates: number[] }) {
  if (rates.length === 1) return <>{rateText(rates[0])}</>;
  if (rates.length <= 3) return <>{rates.map(rateText).join(" / ")}</>;
  return <>{rates.length} tied rates</>;
}

function ScenarioSelector({ scenario, onScenarioChange, scenarioPending, scenarioError, onRetryScenario, scenarioDisabled }: ScenarioControls & { scenario: ScalarScenario }) {
  const descriptionId = useId();
  return <div className={styles.scenarios}>
    <fieldset disabled={scenarioDisabled} aria-describedby={descriptionId}>
      <legend>Try a different electorate</legend>
      <p id={descriptionId}>Change the other 99 voters. Your submitted curve and explicit yes/no answer stay the same, and every result updates together.</p>
      <div className={styles.scenarioGrid}>
        {scenarioPresets.map(({ id, description }) => <button key={id} type="button" className={styles.scenarioCard} aria-pressed={scenario === id} onClick={() => onScenarioChange(id)}>
          <span className={styles.scenarioCardHeading}><strong>{scenarioLabels[id]}</strong><span>{scenarioPending === id ? "Loading…" : scenario === id ? "Shown" : "Try this"}</span></span>
          <span className={styles.scenarioDescription}>{description}</span>
        </button>)}
      </div>
      <button type="button" className={styles.originalScenario} aria-pressed={scenario === "prepared"} onClick={() => onScenarioChange("prepared")}>Original electorate{scenarioPending === "prepared" ? " · Loading…" : scenario === "prepared" ? " · Shown" : " · Restore"}</button>
    </fieldset>
    <p className={styles.scenarioStatus} role="status">{scenarioDisabled
      ? "Comparing your new ballot. These results still show your previous submission."
      : scenarioPending
        ? `Loading ${scenarioLabels[scenarioPending]}. All results still show ${scenarioLabels[scenario]}.`
        : `Showing ${scenarioLabels[scenario]} throughout this comparison.`}</p>
    {scenarioError && <div className={styles.scenarioError} role="alert"><p>{scenarioError} All results still show {scenarioLabels[scenario]}.</p><button type="button" disabled={scenarioDisabled} onClick={onRetryScenario}>Retry scenario</button></div>}
  </div>;
}

function WhatToNotice({ data }: { data: ScalarComparisonResponse }) {
  const winnerRate = data.winner_rates[0];
  const winner = data.points[Math.round(winnerRate / data.candidate_step)];
  const multipleWinners = data.winner_rates.length > 1;
  const binaryIsWinner = data.winner_rates.includes(data.binary.outcome_rate);
  const sameOutcome = !multipleWinners && binaryIsWinner;
  const exampleIsBinary = winnerRate === data.binary.outcome_rate;
  const samePair = data.pair.winner_rates.length === 1 && data.pair.winner_rates[0] === data.binary.outcome_rate;
  return <section className={styles.notice} aria-label="What to notice about these results">
    <h4>What to notice</h4>
    <p>{data.pair.winner_rates.length > 1
      ? `The two original rates tie on average score; richer scores do not select a single winner between them.`
      : samePair
        ? `Using scores leaves the original two-option result unchanged at ${rateText(data.binary.outcome_rate)}.`
        : `Using scores changes the original two-option result from ${rateText(data.binary.outcome_rate)} to ${rateText(data.pair.winner_rates[0])}.`} {multipleWinners
          ? `${data.winner_rates.length} rates tie for the highest average across the full range.${binaryIsWinner ? " The yes/no outcome is among them." : " The yes/no outcome is not among them."}`
          : sameOutcome
            ? "Opening the full range also selects that same yes/no outcome."
            : `Opening the full range selects ${rateText(winnerRate)}.`}</p>
    <p>{multipleWinners ? `At the lowest tied rate, ${rateText(winnerRate)}, ` : `At ${rateText(winnerRate)}, `}<strong>{winner.approval_count} of 100</strong> voters include the rate in their approval band. {exampleIsBinary
      ? `This is also the yes/no outcome, so all ${winner.indifferent} voters score the comparison equally.`
      : <><strong>{winner.prefer_this} prefer this rate</strong> to the yes/no outcome, {winner.prefer_binary} prefer the yes/no outcome, and {winner.indifferent} score them equally.</>}</p>
    <p className={styles.noticeLimit}>{data.scenario === "intense-minority"
      ? "Here, intensity means steeper differences in declared scores, not a measure of whose welfare matters more. "
      : ""}{!exampleIsBinary && winner.prefer_binary > winner.prefer_this
        ? "More voters prefer the yes/no outcome to this rate. "
        : ""}An approval band is not a first choice, and a higher average does not guarantee a compromise everyone prefers.</p>
  </section>;
}

function AggregateResults({ data, ballot, voters }: { data: ScalarComparisonResponse; ballot: ScalarBallotState; voters: PreparedVoter[] }) {
  const initialRate = data.winner_rates[0];
  const [inspectedRate, setInspectedRate] = useState(initialRate);
  const viewport = useScalarViewport(scalarFocusRange(initialRate));
  const inspected = data.points[clamp(Math.round(inspectedRate / data.candidate_step), 0, data.points.length - 1)];
  const rangeId = useId();
  const aggregatePath = useMemo(() => data.points.map((point, index) => `${index ? "L" : "M"} ${point.rate} ${1 - point.mean_score}`).join(" "), [data.points]);
  const selectRate = (rate: number) => {
    setInspectedRate(rate);
    if (rate < viewport.target.minimum || rate > viewport.target.maximum) viewport.setView(scalarFocusRange(rate));
  };
  const fullRange = viewport.target.minimum === 0 && viewport.target.maximum === 100;
  const pairScores = pairScoreText(data.pair.proposal_mean, data.pair.status_quo_mean, data.pair.winner_rates.length > 1);
  return <>
    <div className={styles.outcomeSteps}>
      <div><span className={styles.stepNumber}>1</span><h4>Yes/no ballot</h4><strong>{rateText(data.binary.outcome_rate)}</strong><p>{data.binary.passed ? "The reduction passes." : data.binary.yes === data.binary.no ? "The count is tied; the status quo remains." : "The status quo remains."} {data.binary.yes} Yes · {data.binary.no} No{data.binary.abstain > 0 ? ` · ${data.binary.abstain} unmarked` : ""}.</p></div>
      <div><span className={styles.stepNumber}>2</span><h4>Richer scores, same two options</h4><strong><RateWinners rates={data.pair.winner_rates} /></strong><div className={styles.pairScores}><span>{rateText(data.proposal)} <b title={data.pair.proposal_mean.toPrecision(12)}>{pairScores[0]}</b></span><span>{rateText(data.status_quo)} <b title={data.pair.status_quo_mean.toPrecision(12)}>{pairScores[1]}</b></span></div><p>Average scores can distinguish strength of preference within the original choice.</p></div>
      <div className={styles.expandedOutcome}><span className={styles.stepNumber}>3</span><h4>Richer scores, more options</h4><strong><RateWinners rates={data.winner_rates} /></strong><p>Now allow rates from 0–100%, in 0.05 percentage-point steps. This also changes the available policy choices.</p></div>
    </div>
    <WhatToNotice data={data} />

    <div className={styles.aggregateChart}>
      <div className={styles.graphToolbar}><span className={styles.graphKey}><i className={styles.meanKey} />Average of all 100 curves</span><ZoomControls viewport={viewport} focus={inspected.rate} focusLabel="Focus inspected" /></div>
      <Plot viewport={viewport} label={`Average declared score by tax rate. Maximum ${scoreText(data.max_mean_score)}. Inspected rate ${rateText(inspected.rate)}, average score ${scoreText(inspected.mean_score)}.`}>
        {({ x, y, transform, clipId, top, bottom }) => <g clipPath={`url(#${clipId})`}>
          <g transform={transform}><BackgroundCurves voters={voters} /><path className={styles.meanArea} d={`${aggregatePath} L 100 1 L 0 1 Z`} /><path className={styles.meanCurve} d={aggregatePath} vectorEffect="non-scaling-stroke" /></g>
          <line className={styles.binaryMarker} x1={x(data.binary.outcome_rate)} x2={x(data.binary.outcome_rate)} y1={top} y2={bottom} />
          {data.winner_rates.map((rate) => <circle key={rate} className={styles.winnerDot} cx={x(rate)} cy={y(data.max_mean_score)} r={4} />)}
          <line className={styles.inspectorMarker} x1={x(inspected.rate)} x2={x(inspected.rate)} y1={y(inspected.mean_score)} y2={bottom} />
          <circle className={styles.inspectorDot} cx={x(inspected.rate)} cy={y(inspected.mean_score)} r={6} />
        </g>}
      </Plot>
      <div className={styles.plotLegend}><span><i className={styles.meanKey} />Highest average</span><span><i className={styles.binaryKey} />Yes/no outcome · {rateText(data.binary.outcome_rate)}</span><span><i className={styles.probeKey} />Inspected rate</span></div>
      <div className={styles.inspection}>
        <div className={styles.inspectionControl}>
          <div className={styles.inspectionLabel}><label htmlFor={rangeId}>Inspect a rate</label><output htmlFor={rangeId}>{rateText(inspected.rate)}</output></div>
          <input id={rangeId} type="range" min={viewport.target.minimum} max={viewport.target.maximum} step={data.candidate_step} value={inspected.rate} onChange={(event) => setInspectedRate(Number(event.target.value))} aria-valuetext={`${rateText(inspected.rate)}, average score ${scoreText(inspected.mean_score)}`} />
          <div className={styles.inspectorEndpoints}><span>{viewport.target.minimum}%</span><span>{viewport.target.maximum}%</span></div>
          <div className={styles.quickRates}>
            <button type="button" aria-pressed={inspected.rate === data.binary.outcome_rate} onClick={() => selectRate(data.binary.outcome_rate)}>Yes/no outcome</button>
            {data.winner_rates.slice(0, 4).map((rate) => <button type="button" key={rate} aria-pressed={inspected.rate === rate} onClick={() => selectRate(rate)}>{data.winner_rates.length === 1 ? "Highest average" : rateText(rate)}</button>)}
            <button type="button" onClick={() => selectRate(Math.round(ballot.ideal / data.candidate_step) * data.candidate_step)}>Your ideal{Math.abs(ballot.ideal / data.candidate_step - Math.round(ballot.ideal / data.candidate_step)) > 1e-8 ? " (nearest step)" : ""}</button>
          </div>
          {!fullRange && <p className={styles.finePrint}>Zoom out to inspect the full 0–100% range.</p>}
        </div>
        <div className={styles.inspectionStats}>
          <div><span>Average score</span><strong className={scoreText(inspected.mean_score).length > 8 ? styles.compactScore : undefined}>{scoreText(inspected.mean_score)}</strong></div>
          <div className={!inspected.user_approved ? styles.dimmedScore : undefined}><span>Your score</span><strong className={scoreText(inspected.user_score).length > 8 ? styles.compactScore : undefined}>{scoreText(inspected.user_score)}</strong></div>
          <div><span>Inside approval bands</span><strong>{inspected.approval_count}<small> / 100</small></strong></div>
        </div>
      </div>
      <div className={styles.preferenceComparison}><span>Compared with the yes/no outcome ({rateText(data.binary.outcome_rate)}):</span><strong>{inspected.prefer_this} prefer {rateText(inspected.rate)}</strong><span>{inspected.prefer_binary} prefer {rateText(data.binary.outcome_rate)}</span><span>{inspected.indifferent} score them equally</span></div>
    </div>
    {data.winner_rates.length > 4 && <details className={styles.details}><summary>All {data.winner_rates.length} equally scoring rates</summary><p>{data.winner_rates.map(rateText).join(", ")}</p></details>}
    <details className={styles.details}><summary>What this illustration assumes</summary>
      <p>These are 99 synthetic voters plus your submitted ballot, held fixed within the selected scenario. Switching scenarios changes the other 99 voters and keeps your submitted curve and explicit yes/no answer. The presets vary ideal rates, tolerance on either side, and approval bands within themed groups. A fixed seed keeps each sample repeatable. Their curves describe declared scores, not probabilities or measured wellbeing. The population is illustrative, not a forecast or a reconstruction of Colorado’s electorate. Seed: {data.electorate.seed}.</p>
      <p>The mean treats each voter’s normalized 0–1 scale as comparable and gives each ballot equal weight. That is an explicit modeling choice. It neither guarantees a majority-preferred result nor removes incentives to vote strategically. A rate outside a voter’s approval band receives a score of zero; it is not vetoed.</p>
      <p>For synthetic voters, the higher score at {rateText(data.proposal)} or {rateText(data.status_quo)} determines Yes or No. Equal scores leave the binary ballot unmarked; your explicitly submitted choice is retained. Yes must exceed No for the proposal to pass; a tie retains the status quo. Scores within {data.score_tie_tolerance} are treated as tied. All tied score maxima are reported.</p>
      <p>Offering every rate from 0–100% is a thought experiment, not a claim that every rate is economically or legally feasible. Comparing the two original rates first separates richer information from expanding the set of policy options.</p>
    </details>
    <section className={styles.closing} aria-label="The opportunity for richer ballots">
      <p className={styles.eyebrow}>The opportunity</p>
      <h3>A vote can express room for compromise.</h3>
      <p className={styles.takeaway}>A richer ballot makes more of each voter’s preference available to the decision rule. Choosing that rule—and the options it can choose—remains a separate democratic decision.</p>
      <nav className={styles.closingLinks} aria-label="Continue exploring">
        <a href="#rate-ballot">Edit your ballot <ArrowRight size={14} aria-hidden="true" /></a>
        <Link href="/">Explore other demos <ArrowRight size={14} aria-hidden="true" /></Link>
      </nav>
    </section>
  </>;
}

function VoterBrowser({ data, voters }: { data: ScalarComparisonResponse; voters: PreparedVoter[] }) {
  const yourIndex = voters.findIndex((voter) => voter.id === "you");
  const [selectedIndex, setSelectedIndex] = useState(Math.max(0, yourIndex));
  const selected = voters[selectedIndex];
  const rangeId = useId();
  const isYou = selected.id === "you";
  const mismatch = isYou && selected.binary_vote !== selected.curve_vote;
  const selectedScores = pairScoreText(selected.proposal_score, selected.status_quo_score, selected.curve_vote === "abstain");
  const isDifferentCurve = (voter: PreparedVoter) => (["ideal", "lower_half_width", "upper_half_width", "approval_min", "approval_max"] as const).some((key) => voter.ballot[key] !== selected.ballot[key]);
  const jumpToDifferentCurve = (vote: CurveVote) => {
    // Navigation only: choose a visually different ideal among the same marks.
    const candidates = voters.map((voter, index) => ({ voter, index })).filter(({ voter }) => voter.binary_vote === vote && isDifferentCurve(voter));
    candidates.sort((a, b) => Math.abs(b.voter.ballot.ideal - selected.ballot.ideal) - Math.abs(a.voter.ballot.ideal - selected.ballot.ideal));
    if (candidates[0]) setSelectedIndex(candidates[0].index);
  };

  return <div className={styles.browser}>
      <div className={styles.selectedHeader}>
        <div aria-live="polite" aria-atomic="true"><span className={styles.voterPosition}>Voter {selectedIndex + 1} of 100</span><h4>{isYou ? "Your submitted ballot" : selected.label}<span>Ideal {rateText(selected.ballot.ideal)}</span></h4></div>
        <span className={`${styles.voteBadge} ${voteClass(selected.binary_vote)}`}>{selected.binary_vote === "abstain" ? "Unmarked" : `${voteText(selected.binary_vote)} on the proposal`}</span>
      </div>
      <div className={styles.selectedBody}>
        <VoterGraph voters={voters} selected={selected} data={data} />
        <div className={styles.ballotProjection}>
          <p className={styles.eyebrow}>The two available options</p>
          <div className={styles.optionScore}><span><i className={styles.proposalKey} />Yes · {rateText(data.proposal)}</span><strong title={selected.proposal_score.toPrecision(12)}>{selectedScores[0]}</strong><div><i style={{ width: `${selected.proposal_score * 100}%` }} /></div></div>
          <div className={styles.optionScore}><span><i className={styles.statusKey} />No · {rateText(data.status_quo)}</span><strong title={selected.status_quo_score.toPrecision(12)}>{selectedScores[1]}</strong><div><i style={{ width: `${selected.status_quo_score * 100}%` }} /></div></div>
          <div className={`${styles.compressedAnswer} ${voteClass(selected.binary_vote)}`}><ArrowDown size={17} aria-hidden="true" /><span>What fits on the ballot</span><strong>{selected.binary_vote === "abstain" ? "Unmarked" : voteText(selected.binary_vote)}</strong></div>
          <p className={styles.answerNote}>{mismatch ? `You explicitly chose ${voteText(selected.binary_vote)}. Your curve ${selected.curve_vote === "abstain" ? "treats the two options as tied" : `would imply ${voteText(selected.curve_vote)}`}; your original answer is retained.` : selected.curve_vote === "abstain" ? `The two scores ${selected.proposal_score === selected.status_quo_score ? "are equal" : "differ by less than the numerical tie tolerance"}, so this simulated voter leaves the choice unmarked.` : isYou ? "Your explicit answer and your curve favor the same option." : "The option with the higher score determines this voter’s mark."}</p>
        </div>
      </div>
      <div className={styles.browseControls}>
        <div className={styles.previousNext}><button type="button" aria-label="Previous voter" disabled={selectedIndex === 0} onClick={() => setSelectedIndex((index) => index - 1)}><ChevronLeft size={18} /></button><span>Drag or scroll through voters</span><button type="button" aria-label="Next voter" disabled={selectedIndex === voters.length - 1} onClick={() => setSelectedIndex((index) => index + 1)}><ChevronRight size={18} /></button></div>
        <span className={styles.orderHint}>Lower ideal <ArrowRight size={13} aria-hidden="true" /> Higher ideal</span>
      </div>
      <VoterStrip voters={voters} selectedIndex={selectedIndex} onSelect={setSelectedIndex} />
      <div className={styles.browseRange}><label htmlFor={rangeId}>Browse all 100</label><input id={rangeId} type="range" min={0} max={voters.length - 1} step={1} value={selectedIndex} onChange={(event) => setSelectedIndex(Number(event.target.value))} aria-valuetext={`Voter ${selectedIndex + 1} of 100. ${selected.label}. Ideal ${rateText(selected.ballot.ideal)}. ${voteText(selected.binary_vote)}.`} /><output htmlFor={rangeId}>{selectedIndex + 1} / 100</output></div>
      <div className={styles.jumpExamples}><span>Same answer, different preferences:</span>{(["yes", "no"] as const).map((vote) => <button key={vote} type="button" onClick={() => jumpToDifferentCurve(vote)} className={voteClass(vote)} disabled={!voters.some((voter) => voter.binary_vote === vote && isDifferentCurve(voter))}>Another {voteText(vote)} curve <ArrowRight size={12} aria-hidden="true" /></button>)}<button type="button" onClick={() => setSelectedIndex(Math.max(0, yourIndex))}>Your ballot <ArrowRight size={12} aria-hidden="true" /></button></div>
      <BinaryTally data={data} />
  </div>;
}

export function ElectorateResults({ data, ballot, ...scenarioControls }: { data: ScalarComparisonResponse; ballot: ScalarBallotState } & ScenarioControls) {
  const voters = useMemo(() => [...data.electorate.voters].sort((a, b) => a.ballot.ideal - b.ballot.ideal || a.id.localeCompare(b.id)).map(prepareVoter), [data.electorate.voters]);
  const [combined, setCombined] = useState(false);
  const [dataset, setDataset] = useState({ data, revision: 0 });
  // Adjust before rendering children, so an accepted response never displays
  // the previous dataset's selected voter or inspected rate, even on a retry.
  if (dataset.data !== data) setDataset({ data, revision: dataset.revision + 1 });
  const aggregateId = useId();
  const aggregateRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (combined) aggregateRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  }, [combined]);

  return <div className={styles.results}>
    <div className={styles.browserHeading}><div><p className={styles.eyebrow}>First, see what a yes/no answer leaves out</p><h3>100 curves. One narrow choice.</h3><p>Scroll through the electorate, ordered by ideal rate. Different preferences can produce the same mark.</p><p className={styles.activeScenario}><strong>{scenarioLabels[data.scenario]}</strong>{scenarioControls.scenarioDisabled ? " · Previous submission shown while your new ballot is compared" : scenarioControls.scenarioPending ? ` · Still shown while ${scenarioLabels[scenarioControls.scenarioPending]} loads` : scenarioControls.scenarioError ? " · Previous results retained" : " · 99 synthetic voters + your submitted ballot"}</p></div></div>
    {/* Reset only dataset-specific exploration; keep the combine step and
        scenario controls mounted so scenario changes preserve focus and place. */}
    <VoterBrowser key={dataset.revision} data={data} voters={voters} />
    <ScenarioSelector scenario={data.scenario} {...scenarioControls} />
    <div className={styles.combinePrompt}><div><h3>What if we keep the curves?</h3><p>Use these same 100 voters to score both the original choices and the wider range of tax rates.</p></div><button type="button" aria-expanded={combined} aria-controls={aggregateId} onClick={() => { if (combined) aggregateRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" }); else setCombined(true); }}>{combined ? "View the combined result" : "Combine these 100 ballots"}<ArrowDown size={16} aria-hidden="true" /></button></div>
    <div ref={aggregateRef} id={aggregateId} className={styles.aggregateAnchor}>{combined && <div className={styles.aggregate}>
      <div className={styles.aggregateHeading}><div><p className={styles.eyebrow}>The same 100 ballots, combined</p><h3>A collective score for every available rate.</h3><p>Give each ballot equal weight. At each rate, average its 100 declared scores; choose the highest average.</p></div><div className={styles.winner}><span>{data.winner_rates.length === 1 ? "Highest average at" : "Equal highest averages"}</span><strong><RateWinners rates={data.winner_rates} /></strong><small>Average score {scoreText(data.max_mean_score)}</small></div></div>
      <AggregateResults key={dataset.revision} data={data} ballot={ballot} voters={voters} />
    </div>}</div>
  </div>;
}
