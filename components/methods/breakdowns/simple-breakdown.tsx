"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { CandidateData, ElectionResult } from "@/types/methods";
import { VotingMethod } from "@/types/methods";

interface SimpleBreakdownProps {
  result: ElectionResult;
  candidates: CandidateData[];
  method: VotingMethod;
  // For extended result types:
  extraFields?: Record<string, Record<string, number>>;
}

export function SimpleBreakdown({
  result,
  candidates,
  method,
  extraFields,
}: SimpleBreakdownProps) {
  const nameMap = new Map(candidates.map((c) => [c.id, c.name]));

  const sorted = Object.entries(result.vote_counts)
    .sort(([, a], [, b]) => b - a)
    .map(([id, count]) => ({
      name: nameMap.get(id) ?? id,
      count,
      isWinner: result.winners.includes(id),
    }));

  const totalVotes = sorted.reduce((sum, s) => sum + s.count, 0);

  return (
    <Accordion type="single" collapsible>
      <AccordionItem value="step-by-step">
        <AccordionTrigger>Step-by-step breakdown</AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-sm">
            <div>
              <p className="font-medium mb-1">1. Ballots collected</p>
              <p className="text-muted-foreground">
                {result.total_ballots} ballots cast
                {result.abstentions > 0 &&
                  `, ${result.abstentions} abstention${result.abstentions > 1 ? "s" : ""}`}
                .{" "}
                {result.total_ballots - result.abstentions} valid ballots
                counted.
              </p>
            </div>

            <div>
              <p className="font-medium mb-1">2. {getTallyLabel(method)}</p>
              <ul className="space-y-1 text-muted-foreground">
                {sorted.map((s) => (
                  <li key={s.name} className="flex justify-between">
                    <span className={s.isWinner ? "font-semibold text-foreground" : ""}>
                      {s.name}
                    </span>
                    <span className="font-mono">
                      {s.count.toLocaleString()}
                      {totalVotes > 0 &&
                        method !== "borda" &&
                        method !== "score" &&
                        ` (${((s.count / totalVotes) * 100).toFixed(1)}%)`}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            {extraFields &&
              Object.entries(extraFields).map(([label, values]) => (
                <div key={label}>
                  <p className="font-medium mb-1">{label}</p>
                  <ul className="space-y-1 text-muted-foreground">
                    {Object.entries(values)
                      .sort(([, a], [, b]) => b - a)
                      .map(([id, val]) => (
                        <li key={id} className="flex justify-between">
                          <span>{nameMap.get(id) ?? id}</span>
                          <span className="font-mono">
                            {typeof val === "number" && !Number.isInteger(val)
                              ? val.toFixed(2)
                              : val}
                          </span>
                        </li>
                      ))}
                  </ul>
                </div>
              ))}

            <div>
              <p className="font-medium mb-1">3. Winner</p>
              <p className="text-muted-foreground">
                <span className="font-semibold text-foreground">
                  {result.winners.map((id) => nameMap.get(id) ?? id).join(", ")}
                </span>{" "}
                wins with the highest {getMetricLabel(method)}.
                {result.tiebreak_applied && " (Tiebreak was applied.)"}
              </p>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

function getTallyLabel(method: VotingMethod): string {
  switch (method) {
    case "plurality":
      return "Count votes";
    case "approval":
      return "Count approvals";
    case "borda":
      return "Calculate point totals";
    case "score":
      return "Sum scores";
    default:
      return "Tally";
  }
}

function getMetricLabel(method: VotingMethod): string {
  switch (method) {
    case "plurality":
      return "vote count";
    case "approval":
      return "approval count";
    case "borda":
      return "point total";
    case "score":
      return "total score";
    default:
      return "total";
  }
}
