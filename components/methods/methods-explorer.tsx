"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Info } from "lucide-react";
import {
  VotingMethod,
  MethodDemo,
  ApprovalResult,
  IRVResult,
  BordaResult,
  RankedPairsResult,
  ScoreResult,
  QuadraticResult,
} from "@/types/methods";
import {
  methodDescriptions,
  methodOrder,
} from "@/lib/methods/method-descriptions";
import { MethodExplanation } from "./method-explanation";
import { ResultSummary } from "./result-summary";
import { BarChartResult } from "./charts/bar-chart-result";
import { IRVRoundsChart } from "./charts/irv-rounds-chart";
import { PairwiseMatrix } from "./charts/pairwise-matrix";
import { VictoryGraph } from "./charts/victory-graph";
import { QuadraticChart } from "./charts/quadratic-chart";
import { SimpleBreakdown } from "./breakdowns/simple-breakdown";
import { IRVBreakdown } from "./breakdowns/irv-breakdown";
import { RankedPairsBreakdown } from "./breakdowns/ranked-pairs-breakdown";
import { QuadraticBreakdown } from "./breakdowns/quadratic-breakdown";

interface MethodsExplorerProps {
  demos: Record<VotingMethod, MethodDemo>;
}

export function MethodsExplorer({ demos }: MethodsExplorerProps) {
  return (
    <Tabs defaultValue="plurality" className="w-full">
      <TabsList className="flex flex-wrap h-auto gap-1">
        {methodOrder.map((method) => (
          <TabsTrigger key={method} value={method} className="text-xs sm:text-sm">
            {methodDescriptions[method].name}
          </TabsTrigger>
        ))}
      </TabsList>

      {methodOrder.map((method) => {
        const demo = demos[method];
        if (!demo) return null;

        return (
          <TabsContent key={method} value={method} className="space-y-4 mt-4">
            <MethodExplanation description={methodDescriptions[method]} />
            <MethodPanel method={method} demo={demo} />
          </TabsContent>
        );
      })}
    </Tabs>
  );
}

function MethodPanel({
  method,
  demo,
}: {
  method: VotingMethod;
  demo: MethodDemo;
}) {
  const { scenario, result } = demo;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>{scenario.title}</CardTitle>
            <CardDescription className="mt-1">
              {scenario.description}
            </CardDescription>
          </div>
          <Badge variant="outline">{scenario.voter_count} voters</Badge>
        </div>
        <ResultSummary result={result} candidates={scenario.candidates} />
      </CardHeader>
      <CardContent className="space-y-4">
        <MethodChart method={method} demo={demo} />

        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Key Insight</AlertTitle>
          <AlertDescription>{scenario.key_insight}</AlertDescription>
        </Alert>

        <MethodBreakdown method={method} demo={demo} />
      </CardContent>
    </Card>
  );
}

function MethodChart({
  method,
  demo,
}: {
  method: VotingMethod;
  demo: MethodDemo;
}) {
  const { scenario, result } = demo;

  switch (method) {
    case "plurality":
      return (
        <BarChartResult
          candidates={scenario.candidates}
          values={result.vote_counts}
          winners={result.winners}
          valueLabel="Votes"
        />
      );

    case "approval": {
      return (
        <BarChartResult
          candidates={scenario.candidates}
          values={result.vote_counts}
          winners={result.winners}
          valueLabel="Approvals"
        />
      );
    }

    case "irv": {
      const irvResult = result as IRVResult;
      return (
        <IRVRoundsChart
          candidates={scenario.candidates}
          rounds={irvResult.rounds}
          winners={result.winners}
        />
      );
    }

    case "borda": {
      const bordaResult = result as BordaResult;
      return (
        <BarChartResult
          candidates={scenario.candidates}
          values={bordaResult.point_totals}
          winners={result.winners}
          valueLabel="Points"
        />
      );
    }

    case "ranked_pairs": {
      const rpResult = result as RankedPairsResult;
      return (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium mb-2">Pairwise Comparison Matrix</p>
            <PairwiseMatrix
              candidates={scenario.candidates}
              matrix={rpResult.pairwise_matrix}
              winners={result.winners}
            />
          </div>
          {rpResult.locked_victories.length > 0 && (
            <div>
              <p className="text-sm font-medium mb-2">Victory Graph</p>
              <VictoryGraph
                candidates={scenario.candidates}
                lockedVictories={rpResult.locked_victories}
                skippedVictories={rpResult.skipped_victories}
                winners={result.winners}
              />
              <div className="flex gap-4 justify-center text-xs text-muted-foreground mt-2">
                <span className="flex items-center gap-1">
                  <span className="w-4 h-0.5 bg-green-600 inline-block" /> Locked
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-4 h-0.5 bg-red-400 inline-block border-dashed border-t" /> Skipped (cycle)
                </span>
              </div>
            </div>
          )}
        </div>
      );
    }

    case "score": {
      const scoreResult = result as ScoreResult;
      return (
        <BarChartResult
          candidates={scenario.candidates}
          values={scoreResult.score_totals}
          winners={result.winners}
          valueLabel="Total Score"
        />
      );
    }

    case "quadratic": {
      const qResult = result as QuadraticResult;
      return (
        <QuadraticChart
          candidates={scenario.candidates}
          voteTotals={qResult.vote_totals}
          winners={result.winners}
          overallUtilization={qResult.overall_utilization}
          avgVoterUtilization={qResult.avg_voter_utilization}
        />
      );
    }

    default:
      return null;
  }
}

function MethodBreakdown({
  method,
  demo,
}: {
  method: VotingMethod;
  demo: MethodDemo;
}) {
  const { scenario, result } = demo;

  switch (method) {
    case "plurality":
      return (
        <SimpleBreakdown
          result={result}
          candidates={scenario.candidates}
          method={method}
        />
      );

    case "approval": {
      const approvalResult = result as ApprovalResult;
      return (
        <SimpleBreakdown
          result={result}
          candidates={scenario.candidates}
          method={method}
          extraFields={{
            "Approval rates": approvalResult.approval_rates,
          }}
        />
      );
    }

    case "irv": {
      const irvResult = result as IRVResult;
      return (
        <IRVBreakdown
          rounds={irvResult.rounds}
          candidates={scenario.candidates}
          winners={result.winners}
          totalExhausted={irvResult.total_exhausted}
          totalBallots={result.total_ballots}
        />
      );
    }

    case "borda": {
      const bordaResult = result as BordaResult;
      return (
        <SimpleBreakdown
          result={result}
          candidates={scenario.candidates}
          method={method}
          extraFields={{
            "Point totals": bordaResult.point_totals,
          }}
        />
      );
    }

    case "ranked_pairs": {
      const rpResult = result as RankedPairsResult;
      return (
        <RankedPairsBreakdown
          candidates={scenario.candidates}
          hadCondorcetWinner={rpResult.had_condorcet_winner}
          lockedVictories={rpResult.locked_victories}
          skippedVictories={rpResult.skipped_victories}
          winners={result.winners}
        />
      );
    }

    case "score": {
      const scoreResult = result as ScoreResult;
      return (
        <SimpleBreakdown
          result={result}
          candidates={scenario.candidates}
          method={method}
          extraFields={{
            "Average scores": scoreResult.avg_scores,
            "Score percentages (%)": scoreResult.score_percentages,
          }}
        />
      );
    }

    case "quadratic": {
      const qResult = result as QuadraticResult;
      return (
        <QuadraticBreakdown
          result={qResult}
          candidates={scenario.candidates}
        />
      );
    }

    default:
      return null;
  }
}
