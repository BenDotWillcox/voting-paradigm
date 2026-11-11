"use client";

import { useId } from "react";
import { BALLOT_INSTRUCTIONS, BALLOT_PREAMBLE, TAX_MEASURE } from "@/lib/expressive-tax-measure";
import type { BinaryVote } from "@/types/expressive-comparison";
import styles from "./income-tax-ballot.module.css";

const BOULDER_SAMPLE_URL = "https://assets.bouldercounty.gov/wp-content/uploads/2022/09/2022-General-Election-Compiled-Sample-Ballot.pdf";

export function IncomeTaxBallot({ vote, onVoteChange }: { vote: BinaryVote | null; onVoteChange: (vote: BinaryVote) => void }) {
  const id = useId();

  return <div className={styles.example}>
    <div className={styles.reference}>
      <p>Interactive ballot excerpt · {TAX_MEASURE.electionDate}</p>
      <span>Question and labels from the {TAX_MEASURE.county} sample ballot. <a href={TAX_MEASURE.ballotUrl} target="_blank" rel="noreferrer">View the official sample ↗</a></span>
    </div>
    <div className={styles.layout}>
      <div>
        <div className={styles.paper}>
          <div className={styles.instructions}>
            <h3>Instructions to Voters</h3>
            <div><p><strong>To vote your ballot:</strong><br />{BALLOT_INSTRUCTIONS[0]}<br />{BALLOT_INSTRUCTIONS[1]}</p><span className={styles.filledExample} aria-hidden="true" /></div>
          </div>
          <div className={styles.stateHeading}>{TAX_MEASURE.jurisdiction}</div>
          <fieldset className={styles.measure} aria-labelledby={`${id}-title`} aria-describedby={`${id}-question`}>
            <legend className={styles.srOnly}>{TAX_MEASURE.title}</legend>
            <h3 id={`${id}-title`} className={styles.measureHeading}>{TAX_MEASURE.title}</h3>
            <p id={`${id}-question`} className={styles.question}>{TAX_MEASURE.question}</p>
            <div className={styles.choices}>
              {(["yes", "no"] as const).map((choice) => <label key={choice} className={styles.choice}>
                <span>{choice === "yes" ? "YES/FOR" : "NO/AGAINST"}</span>
                <input type="radio" name={`${id}-vote`} value={choice} checked={vote === choice} onChange={() => onVoteChange(choice)} />
                <span className={styles.oval} aria-hidden="true" />
              </label>)}
            </div>
          </fieldset>
        </div>
        <p className={styles.adaptation}>Select an oval to answer. This is an adapted excerpt for the demo; the printed measure’s wording is unchanged. <a href={BOULDER_SAMPLE_URL} target="_blank" rel="noreferrer">Paper layout reference: Boulder County ↗</a></p>
      </div>
      <aside className={styles.context} aria-label="Meaning of the two answers">
        <p className={styles.contextLabel}>The choice in 2022</p>
        <dl>
          <div><dt>YES/FOR</dt><dd>Reduce the statutory rate to <strong>{TAX_MEASURE.proposal.toFixed(2)}%</strong>.</dd></div>
          <div><dt>NO/AGAINST</dt><dd>Keep the statutory rate at <strong>{TAX_MEASURE.statusQuo.toFixed(2)}%</strong>.</dd></div>
        </dl>
        <p className={styles.contextNote}>The historical question is real. Your answer here is used only in the demo’s synthetic comparison.</p>
        <details className={styles.guide}>
          <summary>Context from the 2022 voter guide</summary>
          <p>The proposal concerned the permanent income tax rate for individuals and corporations. Temporary TABOR adjustments could change the rate actually paid in a particular year.</p>
          <p>The official Blue Book explains the tax and revenue effects and presents arguments for and against. That information accompanied the election but was not printed inside this measure’s ballot block.</p>
          <a href={TAX_MEASURE.guideUrl} target="_blank" rel="noreferrer">Read the official 2022 Blue Book ↗</a>
        </details>
      </aside>
    </div>
    <details className={styles.originalContext}>
      <summary>Original paper instructions and statewide ballot preamble</summary>
      <div className={styles.originalColumns}>
        <div><h4>Instructions to Voters</h4><p><strong>To vote your ballot:</strong></p>{BALLOT_INSTRUCTIONS.map((instruction) => <p key={instruction}>{instruction}</p>)}<p className={styles.annotation}>The original includes marking illustrations; they are not reproduced here. In this interactive excerpt, choose the other oval to revise your answer.</p><a href={TAX_MEASURE.instructionsUrl} target="_blank" rel="noreferrer">Original instructions, page 1 ↗</a></div>
        <div><h4>Statewide ballot preamble</h4><p>{BALLOT_PREAMBLE}</p><a href={TAX_MEASURE.ballotUrl} target="_blank" rel="noreferrer">Original preamble and measure, page 2 ↗</a></div>
      </div>
    </details>
  </div>;
}
