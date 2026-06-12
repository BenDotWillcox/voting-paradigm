"use client";

import { useMemo, useState, useTransition } from "react";
import {
  AlertCircle,
  BarChart3,
  Braces,
  CheckCircle2,
  Gauge,
  Info,
  SlidersHorizontal,
  Trophy,
  Users,
} from "lucide-react";
import { resolveDemoScenarioAction } from "@/actions/methods-actions";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import {
  ApprovalResult,
  AnyElectionResult,
  BordaResult,
  CandidateData,
  DemoScenario,
  DemoScenarioResolution,
  IRVResult,
  QuadraticResult,
  RankedPairsResult,
  ScoreResult,
  VotingMethod,
} from "@/types/methods";
import {
  methodDescriptions,
  methodOrder,
} from "@/lib/methods/method-descriptions";
import { BarChartResult } from "./charts/bar-chart-result";
import { IRVRoundsChart } from "./charts/irv-rounds-chart";
import { PairwiseMatrix } from "./charts/pairwise-matrix";
import { QuadraticChart } from "./charts/quadratic-chart";
import { VictoryGraph } from "./charts/victory-graph";
import { ResultSummary } from "./result-summary";
import { SimpleBreakdown } from "./breakdowns/simple-breakdown";
import { IRVBreakdown } from "./breakdowns/irv-breakdown";
import { RankedPairsBreakdown } from "./breakdowns/ranked-pairs-breakdown";
import { QuadraticBreakdown } from "./breakdowns/quadratic-breakdown";

interface MethodsLabProps {
  scenarios: DemoScenario[];
  initialResolution: DemoScenarioResolution;
}

export function MethodsLab({
  scenarios,
  initialResolution,
}: MethodsLabProps) {
  const [resolution, setResolution] = useState(initialResolution);
  const [selectedScenarioId, setSelectedScenarioId] = useState(
    initialResolution.scenario.id
  );
  const [selectedMethod, setSelectedMethod] =
    useState<VotingMethod>("plurality");
  const [controls, setControls] = useState(initialResolution.controls);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedScenarioId),
    [scenarios, selectedScenarioId]
  );

  function resolveScenario(scenarioId: string, nextControls: Record<string, number>) {
    setError(null);
    startTransition(async () => {
      const result = await resolveDemoScenarioAction(scenarioId, nextControls);
      if (result.isSuccess && result.data) {
        setResolution(result.data);
        setControls(result.data.controls);
      } else {
        setError(result.message);
      }
    });
  }

  function handleScenarioChange(scenario: DemoScenario) {
    setSelectedScenarioId(scenario.id);
    setSelectedMethod("plurality");
    setControls(scenario.default_controls);
    resolveScenario(scenario.id, scenario.default_controls);
  }

  function handleControlChange(controlId: string, value: number) {
    const nextControls = { ...controls, [controlId]: value };
    setControls(nextControls);
    resolveScenario(selectedScenarioId, nextControls);
  }

  const candidates = resolution.scenario.candidates;

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Could not update demo</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <section className="space-y-4">
        <ScenarioPicker
          scenarios={scenarios}
          selectedScenarioId={selectedScenarioId}
          onSelect={handleScenarioChange}
        />
        <ScenarioExplainer scenario={resolution.scenario} />
      </section>

      <section>
        <ElectorateView
          scenario={resolution.scenario}
          candidates={candidates}
        />
      </section>

      <ControlPanel
        scenario={selectedScenario ?? resolution.scenario}
        controls={controls}
        isPending={isPending}
        onControlChange={handleControlChange}
      />

      <WinnerComparison
        resolution={resolution}
        selectedMethod={selectedMethod}
        onSelect={setSelectedMethod}
      />

      <Tabs
        value={selectedMethod}
        onValueChange={(value) => setSelectedMethod(value as VotingMethod)}
        className="space-y-4"
      >
        <TabsList className="flex h-auto flex-wrap gap-1">
          {methodOrder.map((method) => (
            <TabsTrigger
              key={method}
              value={method}
              className="text-xs sm:text-sm"
            >
              {methodDescriptions[method].name}
            </TabsTrigger>
          ))}
        </TabsList>

        {methodOrder.map((method) => (
          <TabsContent key={method} value={method}>
            <MethodDetail
              method={method}
              resolution={resolution}
              candidates={candidates}
            />
          </TabsContent>
        ))}
      </Tabs>

      <TechnicalPanel resolution={resolution} />
    </div>
  );
}

function ScenarioPicker({
  scenarios,
  selectedScenarioId,
  onSelect,
}: {
  scenarios: DemoScenario[];
  selectedScenarioId: string;
  onSelect: (scenario: DemoScenario) => void;
}) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {scenarios.map((scenario) => {
        const selected = scenario.id === selectedScenarioId;
        return (
          <button
            key={scenario.id}
            type="button"
            onClick={() => onSelect(scenario)}
            className={cn(
              "min-w-[15rem] flex-1 rounded-lg border bg-card p-4 text-left shadow-sm transition hover:border-primary/60 lg:min-w-0",
              selected && "border-primary ring-2 ring-primary/15"
            )}
          >
            <div className="mb-3 flex items-center justify-between gap-2">
              <Badge variant={selected ? "default" : "secondary"}>
                {scenario.domain}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {scenario.voter_count} voters
              </span>
            </div>
            <h2 className="text-base font-semibold">{scenario.title}</h2>
            <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">
              {scenario.thesis}
            </p>
          </button>
        );
      })}
    </div>
  );
}

function ScenarioExplainer({ scenario }: { scenario: DemoScenario }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>{scenario.title}</CardTitle>
            <CardDescription>{scenario.domain}</CardDescription>
          </div>
          <Badge variant="secondary">
            <Users className="h-3 w-3" />
            {scenario.voter_count} voters
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <p className="text-sm text-muted-foreground">{scenario.thesis}</p>
        <div className="rounded-md border bg-muted/40 p-3 text-sm">
          {scenario.lesson}
        </div>
      </CardContent>
    </Card>
  );
}

function ElectorateView({
  scenario,
  candidates,
}: {
  scenario: DemoScenario;
  candidates: CandidateData[];
}) {
  const nameMap = new Map(candidates.map((candidate) => [candidate.id, candidate.name]));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="h-5 w-5" />
          Electorate
        </CardTitle>
        <CardDescription>
          Weighted voter blocs drive every ballot type in this scenario.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))]">
        {scenario.blocs.map((bloc) => {
          const ranked = Object.entries(bloc.utilities).sort(
            ([, a], [, b]) => b - a
          );
          return (
            <div key={bloc.id} className="flex h-full flex-col rounded-md border p-3">
              <div className="min-h-[3.9rem]">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className="h-3 w-3 rounded-full"
                      style={{ backgroundColor: bloc.color }}
                    />
                    <p className="truncate font-medium">{bloc.name}</p>
                  </div>
                  <Badge variant="outline" className="mt-0.5">
                    {bloc.voters ?? Math.round((bloc.share / 100) * scenario.voter_count)} voters
                  </Badge>
                </div>
                <p className="mt-1 min-h-8 text-xs leading-4 text-muted-foreground">
                  {bloc.description}
                </p>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${bloc.share}%`,
                    backgroundColor: bloc.color,
                  }}
                />
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {ranked.slice(0, 4).map(([candidateId, utility], index) => (
                  <Badge
                    key={candidateId}
                    variant={index === 0 ? "secondary" : "outline"}
                    className="max-w-full"
                  >
                    {nameMap.get(candidateId) ?? candidateId}: {utility}
                  </Badge>
                ))}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function WinnerComparison({
  resolution,
  selectedMethod,
  onSelect,
}: {
  resolution: DemoScenarioResolution;
  selectedMethod: VotingMethod;
  onSelect: (method: VotingMethod) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Trophy className="h-5 w-5" />
          Winner Comparison
        </CardTitle>
        <CardDescription>
          The same adjusted electorate is resolved under every rule.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Method</TableHead>
                <TableHead>Winner</TableHead>
                <TableHead>Basis</TableHead>
                <TableHead>Why</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {methodOrder.map((method) => {
                const row = resolution.comparison[method];
                const winnerColor = getCandidateSupportColor(
                  resolution.scenario,
                  row.winner
                );
                return (
                  <TableRow
                    key={method}
                    className={cn(
                      "cursor-pointer",
                      selectedMethod === method && "bg-muted/60"
                    )}
                    onClick={() => onSelect(method)}
                  >
                    <TableCell className="font-medium">
                      {methodDescriptions[method].name}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className="border-transparent shadow-sm"
                        style={
                          winnerColor
                            ? {
                                backgroundColor: winnerColor,
                                color: getReadableTextColor(winnerColor),
                              }
                            : undefined
                        }
                      >
                        {row.winner_name}
                      </Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                      {row.basis}
                    </TableCell>
                    <TableCell className="min-w-[18rem] text-sm text-muted-foreground">
                      {row.reason}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          {resolution.annotations.map((annotation) => (
            <div
              key={`${annotation.type}-${annotation.label}`}
              className={cn(
                "rounded-md border p-3 text-sm",
                annotation.severity === "success" && "border-green-500/30 bg-green-500/10",
                annotation.severity === "warning" && "border-amber-500/30 bg-amber-500/10",
                annotation.severity === "info" && "bg-muted/45"
              )}
            >
              <div className="mb-1 flex items-center gap-2 font-medium">
                {annotation.severity === "success" ? (
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                ) : annotation.severity === "warning" ? (
                  <AlertCircle className="h-4 w-4 text-amber-600" />
                ) : (
                  <Info className="h-4 w-4 text-primary" />
                )}
                {annotation.label}
              </div>
              <p className="text-muted-foreground">{annotation.description}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function getCandidateSupportColor(
  scenario: DemoScenario,
  candidateId: string | null
): string | null {
  if (!candidateId) return null;

  const strongestBloc = scenario.blocs
    .filter((bloc) => {
      const candidateUtility = bloc.utilities[candidateId] ?? -1;
      const topUtility = Math.max(...Object.values(bloc.utilities));
      return candidateUtility === topUtility;
    })
    .sort((a, b) => (b.voters ?? 0) - (a.voters ?? 0))[0];

  return strongestBloc?.color ?? null;
}

function getCandidateSupportColors(
  scenario: DemoScenario
): Record<string, string> {
  return Object.fromEntries(
    scenario.candidates
      .map((candidate) => [
        candidate.id,
        getCandidateSupportColor(scenario, candidate.id),
      ] as const)
      .filter((entry): entry is readonly [string, string] => Boolean(entry[1]))
  );
}

function getReadableTextColor(oklchColor: string): string {
  const lightness = Number(oklchColor.match(/oklch\(([\d.]+)/)?.[1] ?? 0.6);
  return lightness > 0.64
    ? "oklch(0.16 0.03 260)"
    : "oklch(0.98 0.01 260)";
}

function ControlPanel({
  scenario,
  controls,
  isPending,
  onControlChange,
}: {
  scenario: DemoScenario;
  controls: Record<string, number>;
  isPending: boolean;
  onControlChange: (controlId: string, value: number) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2">
              <SlidersHorizontal className="h-5 w-5" />
              Guided Controls
            </CardTitle>
            <CardDescription>
              Adjust the electorate, then recompute all methods together.
            </CardDescription>
          </div>
          <Badge variant={isPending ? "secondary" : "outline"}>
            {isPending ? "Updating" : "Deterministic"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-5 md:grid-cols-2 xl:grid-cols-5">
        {scenario.controls.map((control) => (
          <div key={control.id} className="flex h-full flex-col">
            <div className="grid min-h-[4.7rem] grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">{control.label}</p>
                <p className="mt-1 min-h-8 text-xs leading-4 text-muted-foreground">
                  {control.description}
                </p>
              </div>
              <span className="font-mono text-sm">
                {controls[control.id] ?? control.default}
              </span>
            </div>
            <div className="mt-3">
              <Slider
                min={control.min}
                max={control.max}
                step={control.step}
                value={[controls[control.id] ?? control.default]}
                onValueChange={([value]) => onControlChange(control.id, value)}
              />
            </div>
            <div className="flex justify-between text-[11px] text-muted-foreground">
              <span>{control.low_label}</span>
              <span>{control.high_label}</span>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function MethodDetail({
  method,
  resolution,
  candidates,
}: {
  method: VotingMethod;
  resolution: DemoScenarioResolution;
  candidates: CandidateData[];
}) {
  const result = resolution.results[method];
  const comparison = resolution.comparison[method];
  const description = methodDescriptions[method];

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{description.name}</CardTitle>
            <CardDescription className="mt-1 max-w-3xl">
              {description.howItWorks}
            </CardDescription>
          </div>
          <Badge variant="outline">{description.ballotType}</Badge>
        </div>
        <ResultSummary result={result} candidates={candidates} />
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="rounded-md border bg-muted/35 p-3 text-sm">
          <span className="font-medium">{comparison.winner_name}</span>{" "}
          wins here. {comparison.reason}
        </div>
        <MethodChart
          method={method}
          result={result}
          resolution={resolution}
          candidates={candidates}
        />
        <MethodBreakdown method={method} result={result} candidates={candidates} />
        <div className="grid gap-3 md:grid-cols-2">
          <MethodList title="Strengths" items={description.strengths} />
          <MethodList title="Weaknesses" items={description.weaknesses} />
        </div>
      </CardContent>
    </Card>
  );
}

function MethodChart({
  method,
  result,
  resolution,
  candidates,
}: {
  method: VotingMethod;
  result: AnyElectionResult;
  resolution: DemoScenarioResolution;
  candidates: CandidateData[];
}) {
  const candidateColors = getCandidateSupportColors(resolution.scenario);

  if (method === "irv") {
    const irvResult = result as IRVResult;
    return (
      <IRVRoundsChart
        candidates={candidates}
        rounds={irvResult.rounds}
        winners={result.winners}
        candidateColors={candidateColors}
      />
    );
  }

  if (method === "borda") {
    const bordaResult = result as BordaResult;
    return (
      <BarChartResult
        candidates={candidates}
        values={bordaResult.point_totals}
        winners={result.winners}
        valueLabel="Points"
        candidateColors={candidateColors}
      />
    );
  }

  if (method === "ranked_pairs") {
    const rankedPairsResult = result as RankedPairsResult;
    return (
      <div className="space-y-4">
        <PairwiseMatrix
          candidates={candidates}
          matrix={rankedPairsResult.pairwise_matrix}
          winners={result.winners}
        />
        <VictoryGraph
          candidates={candidates}
          lockedVictories={rankedPairsResult.locked_victories}
          skippedVictories={rankedPairsResult.skipped_victories}
          winners={result.winners}
        />
      </div>
    );
  }

  if (method === "score") {
    const scoreResult = result as ScoreResult;
    return (
      <BarChartResult
        candidates={candidates}
        values={scoreResult.score_totals}
        winners={result.winners}
        valueLabel="Total score"
        candidateColors={candidateColors}
      />
    );
  }

  if (method === "quadratic") {
    const quadraticResult = result as QuadraticResult;
    return (
      <QuadraticChart
        candidates={candidates}
        voteTotals={quadraticResult.vote_totals}
        winners={result.winners}
        overallUtilization={quadraticResult.overall_utilization}
        avgVoterUtilization={quadraticResult.avg_voter_utilization}
        candidateColors={candidateColors}
      />
    );
  }

  return (
    <BarChartResult
      candidates={candidates}
      values={result.vote_counts}
      winners={result.winners}
      valueLabel={method === "approval" ? "Approvals" : "Votes"}
      candidateColors={candidateColors}
    />
  );
}

function MethodBreakdown({
  method,
  result,
  candidates,
}: {
  method: VotingMethod;
  result: AnyElectionResult;
  candidates: CandidateData[];
}) {
  if (method === "irv") {
    const irvResult = result as IRVResult;
    return (
      <IRVBreakdown
        rounds={irvResult.rounds}
        candidates={candidates}
        winners={result.winners}
        totalExhausted={irvResult.total_exhausted}
        totalBallots={result.total_ballots}
      />
    );
  }

  if (method === "ranked_pairs") {
    const rankedPairsResult = result as RankedPairsResult;
    return (
      <RankedPairsBreakdown
        candidates={candidates}
        hadCondorcetWinner={rankedPairsResult.had_condorcet_winner}
        lockedVictories={rankedPairsResult.locked_victories}
        skippedVictories={rankedPairsResult.skipped_victories}
        winners={result.winners}
      />
    );
  }

  if (method === "quadratic") {
    return (
      <QuadraticBreakdown
        result={result as QuadraticResult}
        candidates={candidates}
      />
    );
  }

  if (method === "approval") {
    const approvalResult = result as ApprovalResult;
    return (
      <SimpleBreakdown
        result={result}
        candidates={candidates}
        method={method}
        extraFields={{ "Approval rates": approvalResult.approval_rates }}
      />
    );
  }

  if (method === "borda") {
    const bordaResult = result as BordaResult;
    return (
      <SimpleBreakdown
        result={result}
        candidates={candidates}
        method={method}
        extraFields={{ "Point totals": bordaResult.point_totals }}
      />
    );
  }

  if (method === "score") {
    const scoreResult = result as ScoreResult;
    return (
      <SimpleBreakdown
        result={result}
        candidates={candidates}
        method={method}
        extraFields={{
          "Average scores": scoreResult.avg_scores,
          "Score percentages": scoreResult.score_percentages,
        }}
      />
    );
  }

  return (
    <SimpleBreakdown
      result={result}
      candidates={candidates}
      method={method}
    />
  );
}

function MethodList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-md border p-3">
      <p className="mb-2 text-sm font-medium">{title}</p>
      <ul className="space-y-1 text-sm text-muted-foreground">
        {items.slice(0, 4).map((item) => (
          <li key={item} className="flex gap-2">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TechnicalPanel({
  resolution,
}: {
  resolution: DemoScenarioResolution;
}) {
  const sample = {
    controls: resolution.controls,
    plurality: resolution.derived_ballots.plurality.slice(0, 6),
    approval: resolution.derived_ballots.approval.slice(0, 6),
    ranked: resolution.derived_ballots.ranked.slice(0, 6),
    score: resolution.derived_ballots.score.slice(0, 6),
    quadratic: resolution.derived_ballots.quadratic.slice(0, 6),
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Braces className="h-5 w-5" />
          Technical Payload
        </CardTitle>
        <CardDescription>
          A compact sample of derived ballots and the active control state.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Accordion type="single" collapsible>
          <AccordionItem value="payload">
            <AccordionTrigger>
              <span className="flex items-center gap-2">
                <Gauge className="h-4 w-4" />
                Inspect derived ballots
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <pre className="max-h-[28rem] overflow-auto rounded-md bg-muted p-4 text-xs">
                {JSON.stringify(sample, null, 2)}
              </pre>
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="results">
            <AccordionTrigger>
              <span className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                Inspect result object
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <pre className="max-h-[28rem] overflow-auto rounded-md bg-muted p-4 text-xs">
                {JSON.stringify(resolution.results, null, 2)}
              </pre>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
}
