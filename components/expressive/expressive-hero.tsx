"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import styles from "./expressive-hero.module.css";

// Decorative preference curves in the same family as the richer ballot:
// value = 2^-((x - ideal) / halfWidth)^2, asymmetric half-widths, optional
// approval clipping (value drops to zero outside the approved range).
type CurveSpec = {
  tone: "teal" | "gold" | "taper" | "rose" | "deep";
  ideal: (t: number) => number;
  lower: (t: number) => number;
  upper: (t: number) => number;
  approval?: [number, number];
  delay: number;
};

const CURVES: CurveSpec[] = [
  { tone: "taper", ideal: (t) => 2.9+0.7*Math.sin(t*0.31+2), lower: () => 0.8, upper: (t) => 3.2+0.5*Math.sin(t*0.5), delay: 0.25 },
  { tone: "gold", ideal: (t) => 6.6+0.8*Math.sin(t*0.27+1), lower: (t) => 2+0.4*Math.sin(t*0.45+1), upper: () => 1, delay: 0.5 },
  { tone: "rose", ideal: (t) => 7.9+0.45*Math.sin(t*0.22+3), lower: () => 2.6, upper: () => 1.4, approval: [5.2, 10], delay: 0.75 },
  { tone: "deep", ideal: (t) => 5.2+1.1*Math.sin(t*0.18+4), lower: (t) => 1.6+0.6*Math.sin(t*0.4), upper: (t) => 1.6+0.6*Math.sin(t*0.4+1.4), delay: 1 },
  { tone: "teal", ideal: (t) => 4.4+0.6*Math.sin(t*0.35), lower: () => 1.2, upper: () => 2.4, approval: [2.4, 7.4], delay: 0 },
];

const W = 640, H = 360, LEFT = 18, RIGHT = W-18, TOP = 34, BOTTOM = H-40, DOMAIN = 10;
const px = (value: number) => LEFT+(RIGHT-LEFT)*value/DOMAIN;
const py = (score: number) => BOTTOM-(BOTTOM-TOP)*score;
const round = (value: number) => Math.round(value*10)/10;
const DRAW_SECONDS = 1.4;

function curvePath(spec: CurveSpec, t: number, reveal: number) {
  const ideal = spec.ideal(t), lower = spec.lower(t), upper = spec.upper(t);
  const [minimum, maximum] = spec.approval ?? [0, DOMAIN];
  const end = DOMAIN*reveal;
  const parts: string[] = [];
  for (let x = 0; x <= end+1e-9; x += 0.05) {
    const inside = x >= minimum && x <= maximum;
    const width = x < ideal ? lower : upper;
    const score = inside ? 2**-(((x-ideal)/width)**2) : 0;
    parts.push(`${parts.length ? "L" : "M"}${round(px(x))},${round(py(score))}`);
  }
  return { line: parts.join(" "), fill: parts.length > 1 ? `${parts.join(" ")} L${round(px(Math.min(end, DOMAIN)))},${BOTTOM} L${LEFT},${BOTTOM} Z` : "", peak: ideal <= end ? { x: round(px(ideal)), y: py(1) } : null };
}

function curveFrame(spec: CurveSpec, clock: number) {
  const reveal = Math.max(0, Math.min(1, (clock-spec.delay)/DRAW_SECONDS));
  const eased = 1-(1-reveal)**3;
  return curvePath(spec, Math.max(0, clock-spec.delay-DRAW_SECONDS)+spec.delay*7, eased);
}
// Server and first client render agree on the undrawn state.
const FIRST_FRAME = CURVES.map((spec) => curveFrame(spec, 0));

type CurveNodes = { fill: SVGPathElement | null; line: SVGPathElement | null; peak: SVGCircleElement | null };

export function ExpressiveHero() {
  const [animate, setAnimate] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const nodes = useRef<CurveNodes[]>(CURVES.map(() => ({ fill: null, line: null, peak: null })));

  useEffect(() => {
    // Paint frames straight into the SVG; React state per frame would
    // re-render the whole hero sixty times a second.
    const paint = (clock: number) => CURVES.forEach((spec, index) => {
      const { line, fill, peak } = curveFrame(spec, clock);
      const node = nodes.current[index];
      node.line?.setAttribute("d", line);
      node.fill?.setAttribute("d", fill);
      if (!node.peak) return;
      node.peak.style.display = peak ? "" : "none";
      if (peak) { node.peak.setAttribute("cx", String(peak.x)); node.peak.setAttribute("cy", String(peak.y)); }
    });
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduced.matches) { paint(DRAW_SECONDS+2); return; }
    setAnimate(true);
    let frame = 0, visible = true, last = performance.now(), elapsed = 0;
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; });
    if (host.current) observer.observe(host.current);
    const tick = (now: number) => {
      // Pause (rather than skip ahead) while scrolled out of view.
      if (visible && !document.hidden) { elapsed += Math.min(0.1, (now-last)/1000); paint(elapsed); }
      last = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, []);

  return <section className={styles.hero} aria-labelledby="expressive-title">
    <span className={styles.timingMarks} aria-hidden="true" />
    <div className={styles.inner}>
      <Link href="/" className={styles.back}><ArrowLeft className="h-4 w-4" aria-hidden="true" />All demos</Link>

      <div className={styles.copy}>
        <p className={styles.eyebrow}>Demo 06 · Expressive ballots</p>
        <h1 id="expressive-title">A ballot can say more than a single choice.</h1>
        <p className={styles.lede}>What does a yes or no leave unsaid? Answer Colorado’s 2022 tax question two ways, then see what changes when a ballot can express room for compromise.</p>
      </div>

      {/* The story in one row: a single mark, then the curves it leaves out. */}
      <div className={styles.story} aria-hidden="true">
        <figure className={`${styles.sheet} ${animate ? styles.sheetAnimated : ""}`}>
          <div className={styles.sheetHeading}>Proposition 121 (Statutory)</div>
          <div className={styles.sheetLines}><i /><i /><i style={{ width: "62%" }} /></div>
          <div className={styles.sheetChoices}>
            <span>YES/FOR<b className={styles.bubble}><em className={styles.markYes} /></b></span>
            <span>NO/AGAINST<b className={styles.bubble}><em className={styles.markNo} /></b></span>
          </div>
          <figcaption>One mark. One bit.</figcaption>
        </figure>

        <div className={styles.connector}><ArrowRight className={styles.connectorArrow} /><span>or say how much</span></div>

        <div ref={host} className={styles.visual}>
          <svg viewBox={`0 0 ${W} ${H}`} className={styles.curves} preserveAspectRatio="xMidYMid meet">
            {[0, 0.5, 1].map((score) => <line key={score} x1={LEFT} x2={RIGHT} y1={py(score)} y2={py(score)} className={styles.grid} />)}
            {[0, 2, 4, 6, 8, 10].map((value) => <text key={value} x={px(value)} y={BOTTOM+24} textAnchor={value === 0 ? "start" : value === 10 ? "end" : "middle"} className={styles.tick}>{value}%</text>)}
            {CURVES.map((spec, index) => <g key={spec.tone} className={styles[spec.tone]}>
              <path ref={(element) => { nodes.current[index].fill = element; }} d={FIRST_FRAME[index].fill} className={styles.area} />
              <path ref={(element) => { nodes.current[index].line = element; }} d={FIRST_FRAME[index].line} className={styles.line} />
              <circle ref={(element) => { nodes.current[index].peak = element; }} cx={0} cy={0} r={4.5} className={styles.peak} style={{ display: "none" }} />
            </g>)}
          </svg>
          <p className={styles.visualCaption}>Ideal rate · what you accept · how fast support falls away</p>
        </div>
      </div>
    </div>
  </section>;
}
