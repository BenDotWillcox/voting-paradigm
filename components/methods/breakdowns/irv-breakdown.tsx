"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { CandidateData, IRVRound } from "@/types/methods";

interface IRVBreakdownProps {
  rounds: IRVRound[];
  candidates: CandidateData[];
  winners: string[];
  totalExhausted: number;
  totalBallots: number;
}

export function IRVBreakdown({
  rounds,
  candidates,
  winners,
  totalExhausted,
  totalBallots,
}: IRVBreakdownProps) {
  const nameMap = new Map(candidates.map((c) => [c.id, c.name]));
  const getName = (id: string) => nameMap.get(id) ?? id;
  const winnerSet = new Set(winners);

  return (
    <Accordion type="single" collapsible>
      <AccordionItem value="irv-breakdown">
        <AccordionTrigger>
          Round-by-round breakdown ({rounds.length} round
          {rounds.length !== 1 ? "s" : ""})
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-4 text-sm">
            {rounds.map((round, i) => {
              const sorted = Object.entries(round.vote_counts).sort(
                ([, a], [, b]) => b - a
              );
              const isLast = i === rounds.length - 1;
              const majorityNeeded = Math.floor(round.active_ballots / 2) + 1;

              return (
                <div key={i} className="border-l-2 border-muted pl-4">
                  <p className="font-medium">
                    Round {round.round_number}
                    <span className="text-muted-foreground font-normal ml-2">
                      ({round.active_ballots} active ballot
                      {round.active_ballots !== 1 ? "s" : ""}
                      {round.exhausted_ballots > 0 &&
                        `, ${round.exhausted_ballots} exhausted`}
                      )
                    </span>
                  </p>

                  <ul className="mt-1 space-y-0.5 text-muted-foreground">
                    {sorted.map(([id, count]) => (
                      <li key={id} className="flex items-center gap-2">
                        <span
                          className={
                            winnerSet.has(id) && isLast
                              ? "font-semibold text-foreground"
                              : ""
                          }
                        >
                          {getName(id)}
                        </span>
                        <span className="font-mono">{count}</span>
                        {winnerSet.has(id) && isLast && (
                          <Badge variant="default" className="text-xs">
                            Winner
                          </Badge>
                        )}
                        {round.eliminated.includes(id) && (
                          <Badge variant="destructive" className="text-xs">
                            Eliminated
                          </Badge>
                        )}
                      </li>
                    ))}
                  </ul>

                  {isLast && sorted.length > 0 && (
                    <p className="mt-1 text-muted-foreground">
                      Majority threshold: {majorityNeeded} votes.
                    </p>
                  )}

                  {round.eliminated.length > 0 && (
                    <p className="mt-1 text-muted-foreground">
                      {round.eliminated.map(getName).join(", ")} eliminated
                      {round.elimination_was_tiebreak &&
                        " (tiebreak applied)"}
                      . Votes redistribute to next preferences.
                    </p>
                  )}
                </div>
              );
            })}

            {totalExhausted > 0 && (
              <p className="text-muted-foreground">
                {totalExhausted} of {totalBallots} ballots exhausted (all
                ranked candidates were eliminated).
              </p>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
