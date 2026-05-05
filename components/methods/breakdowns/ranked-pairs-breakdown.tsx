"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { CandidateData } from "@/types/methods";

interface RankedPairsBreakdownProps {
  candidates: CandidateData[];
  hadCondorcetWinner: boolean;
  lockedVictories: [string, string, number][];
  skippedVictories: [string, string, number][];
  winners: string[];
}

export function RankedPairsBreakdown({
  candidates,
  hadCondorcetWinner,
  lockedVictories,
  skippedVictories,
  winners,
}: RankedPairsBreakdownProps) {
  const nameMap = new Map(candidates.map((c) => [c.id, c.name]));
  const getName = (id: string) => nameMap.get(id) ?? id;

  return (
    <Accordion type="single" collapsible>
      <AccordionItem value="rp-breakdown">
        <AccordionTrigger>Step-by-step breakdown</AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-sm">
            <div>
              <p className="font-medium mb-1">1. Pairwise comparisons</p>
              <p className="text-muted-foreground">
                Every candidate is compared head-to-head with every other
                candidate using the ranked ballots. See the matrix above.
              </p>
            </div>

            <div>
              <p className="font-medium mb-1">2. Condorcet winner check</p>
              {hadCondorcetWinner ? (
                <p className="text-muted-foreground">
                  <span className="font-semibold text-foreground">
                    {winners.map(getName).join(", ")}
                  </span>{" "}
                  beats every other candidate head-to-head — a Condorcet winner
                  exists. No further resolution needed.
                </p>
              ) : (
                <p className="text-muted-foreground">
                  No candidate beats all others head-to-head. Preferences form a
                  cycle. Proceeding to Ranked Pairs resolution.
                </p>
              )}
            </div>

            {!hadCondorcetWinner && (
              <>
                <div>
                  <p className="font-medium mb-1">
                    3. Lock victories by margin (strongest first)
                  </p>
                  <div className="space-y-1.5 text-muted-foreground">
                    {lockedVictories.map(([w, l, margin], i) => (
                      <div key={i} className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className="bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800"
                        >
                          Locked
                        </Badge>
                        <span>
                          {getName(w)} beats {getName(l)} by margin of{" "}
                          {margin}
                        </span>
                      </div>
                    ))}
                    {skippedVictories.map(([w, l, margin], i) => (
                      <div key={i} className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className="bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800"
                        >
                          Skipped
                        </Badge>
                        <span>
                          {getName(w)} beats {getName(l)} by margin of{" "}
                          {margin} — would create cycle
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="font-medium mb-1">4. Winner</p>
                  <p className="text-muted-foreground">
                    <span className="font-semibold text-foreground">
                      {winners.map(getName).join(", ")}
                    </span>{" "}
                    has no incoming locked edges — they are the Ranked Pairs
                    winner.
                  </p>
                </div>
              </>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
