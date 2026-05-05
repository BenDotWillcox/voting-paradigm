"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { CandidateData, QuadraticResult } from "@/types/methods";

interface QuadraticBreakdownProps {
  result: QuadraticResult;
  candidates: CandidateData[];
}

export function QuadraticBreakdown({
  result,
  candidates,
}: QuadraticBreakdownProps) {
  const nameMap = new Map(candidates.map((c) => [c.id, c.name]));
  const getName = (id: string) => nameMap.get(id) ?? id;

  const sorted = Object.entries(result.vote_totals).sort(
    ([, a], [, b]) => b - a
  );

  return (
    <Accordion type="single" collapsible>
      <AccordionItem value="qv-breakdown">
        <AccordionTrigger>Step-by-step breakdown</AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-sm">
            <div>
              <p className="font-medium mb-1">1. Credit allocation</p>
              <p className="text-muted-foreground">
                {result.total_ballots} voters each received a budget of credits.
                {result.abstentions > 0 &&
                  ` ${result.abstentions} abstained.`}{" "}
                The cost to cast v votes for a candidate is v², encouraging
                voters to spread support across multiple candidates.
              </p>
            </div>

            <div>
              <p className="font-medium mb-1">2. Credit utilization</p>
              <p className="text-muted-foreground">
                {result.total_credits_spent.toLocaleString()} of{" "}
                {result.total_credits_available.toLocaleString()} total credits
                spent ({(result.overall_utilization * 100).toFixed(1)}%
                utilization). Average voter used{" "}
                {(result.avg_voter_utilization * 100).toFixed(1)}% of their
                budget.
              </p>
            </div>

            <div>
              <p className="font-medium mb-1">3. Net vote totals</p>
              <p className="text-muted-foreground mb-1">
                Each candidate&apos;s total is the sum of all votes received
                (positive votes add, negative votes subtract):
              </p>
              <ul className="space-y-0.5 text-muted-foreground">
                {sorted.map(([id, total]) => (
                  <li key={id} className="flex justify-between">
                    <span
                      className={
                        result.winners.includes(id)
                          ? "font-semibold text-foreground"
                          : ""
                      }
                    >
                      {getName(id)}
                    </span>
                    <span
                      className={`font-mono ${total < 0 ? "text-destructive" : ""}`}
                    >
                      {total > 0 ? "+" : ""}
                      {total}
                    </span>
                  </li>
                ))}
              </ul>
              {result.candidates_with_negative_totals > 0 && (
                <p className="text-muted-foreground mt-1">
                  {result.candidates_with_negative_totals} candidate
                  {result.candidates_with_negative_totals > 1 ? "s" : ""} received
                  more opposition than support.
                </p>
              )}
            </div>

            <div>
              <p className="font-medium mb-1">4. Winner</p>
              <p className="text-muted-foreground">
                <span className="font-semibold text-foreground">
                  {result.winners.map(getName).join(", ")}
                </span>{" "}
                wins with the highest net vote total.
                {result.tiebreak_applied && " (Tiebreak was applied.)"}
              </p>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
