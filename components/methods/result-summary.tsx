"use client";

import { Badge } from "@/components/ui/badge";
import { CandidateData, ElectionResult } from "@/types/methods";
import { Trophy, Users, UserX } from "lucide-react";

interface ResultSummaryProps {
  result: ElectionResult;
  candidates: CandidateData[];
}

export function ResultSummary({ result, candidates }: ResultSummaryProps) {
  const nameMap = new Map(candidates.map((c) => [c.id, c.name]));
  const winnerNames = result.winners.map((id) => nameMap.get(id) ?? id);

  return (
    <div className="flex flex-wrap items-center gap-4 py-3">
      <div className="flex items-center gap-2">
        <Trophy className="h-5 w-5 text-primary" />
        <span className="font-semibold">Winner:</span>
        {winnerNames.map((name) => (
          <Badge key={name} variant="default" className="text-sm">
            {name}
          </Badge>
        ))}
        {result.tiebreak_applied && (
          <Badge variant="outline" className="text-xs">
            Tiebreak applied
          </Badge>
        )}
      </div>

      <div className="flex items-center gap-4 text-sm text-muted-foreground">
        <span className="flex items-center gap-1">
          <Users className="h-4 w-4" />
          {result.total_ballots} voters
        </span>
        {result.abstentions > 0 && (
          <span className="flex items-center gap-1">
            <UserX className="h-4 w-4" />
            {result.abstentions} abstentions
          </span>
        )}
      </div>
    </div>
  );
}
