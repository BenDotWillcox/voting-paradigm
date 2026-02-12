"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

type BallotType = "single_choice" | "approval" | "ranked_choice" | "score" | "quadratic";

const ballotTypeMeta: Record<BallotType, { label: string; description: string }> = {
  single_choice: {
    label: "Single Choice",
    description: "Each voter may pick exactly one candidate or abstain.",
  },
  approval: {
    label: "Approval",
    description: "Each voter may approve zero or more candidates.",
  },
  ranked_choice: {
    label: "Ranked Choice",
    description: "Each voter submits a strict, full ranking of all candidates.",
  },
  score: {
    label: "Score",
    description: "Each voter assigns integer scores to candidates on a fixed range.",
  },
  quadratic: {
    label: "Quadratic",
    description: "Each voter allocates votes under a quadratic credit budget.",
  },
};

const candidateTextToList = (raw: string): string[] =>
  raw
    .split("\n")
    .map((value) => value.trim())
    .filter(Boolean);

export function BallotCreationForm() {
  const [ballotType, setBallotType] = useState<BallotType>("single_choice");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [candidateText, setCandidateText] = useState("Alice\nBob\nCarol");

  const [allowAbstention, setAllowAbstention] = useState(true);
  const [scoreMin, setScoreMin] = useState(0);
  const [scoreMax, setScoreMax] = useState(10);
  const [quadraticCredits, setQuadraticCredits] = useState(100);
  const [allowNegativeVotes, setAllowNegativeVotes] = useState(true);

  const candidates = useMemo(() => candidateTextToList(candidateText), [candidateText]);

  const errors = useMemo(() => {
    const formErrors: string[] = [];

    if (!title.trim()) {
      formErrors.push("Election title is required.");
    }

    if (candidates.length < 2) {
      formErrors.push("At least two candidates are required.");
    }

    const candidateSet = new Set(candidates);
    if (candidateSet.size !== candidates.length) {
      formErrors.push("Candidate names must be unique.");
    }

    if (ballotType === "ranked_choice" && candidates.length < 3) {
      formErrors.push("Ranked choice works best with at least three candidates.");
    }

    if (ballotType === "score") {
      if (!Number.isInteger(scoreMin) || !Number.isInteger(scoreMax)) {
        formErrors.push("Score bounds must be integers.");
      }
      if (scoreMin >= scoreMax) {
        formErrors.push("Score minimum must be less than score maximum.");
      }
    }

    if (ballotType === "quadratic") {
      if (!Number.isInteger(quadraticCredits) || quadraticCredits <= 0) {
        formErrors.push("Quadratic credit budget must be a positive integer.");
      }
    }

    return formErrors;
  }, [ballotType, candidates, quadraticCredits, scoreMax, scoreMin, title]);

  const electionPayload = useMemo(() => {
    const base = {
      election: {
        title: title.trim(),
        description: description.trim(),
      },
      ballotType,
      candidates,
    };

    if (ballotType === "single_choice") {
      return {
        ...base,
        constraints: {
          maxSelections: 1,
          allowAbstention,
        },
      };
    }

    if (ballotType === "approval") {
      return {
        ...base,
        constraints: {
          minApprovals: 0,
          maxApprovals: candidates.length,
          allowAbstention,
        },
      };
    }

    if (ballotType === "ranked_choice") {
      return {
        ...base,
        constraints: {
          requiresFullRanking: true,
          strictOrdering: true,
          allowAbstention,
        },
      };
    }

    if (ballotType === "score") {
      return {
        ...base,
        constraints: {
          scoreRange: {
            min: scoreMin,
            max: scoreMax,
          },
          integerOnly: true,
          allowPartialScoring: true,
          allowAbstention,
        },
      };
    }

    return {
      ...base,
      constraints: {
        creditBudget: quadraticCredits,
        costFunction: "votes^2",
        allowNegativeVotes,
        allowAbstention,
      },
    };
  }, [allowAbstention, allowNegativeVotes, ballotType, candidates, description, quadraticCredits, scoreMax, scoreMin, title]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Create Election from Ballot Type</CardTitle>
          <CardDescription>
            Select a ballot model and define election inputs that satisfy its constraints.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-2">
            <Label htmlFor="title">Election title</Label>
            <Input
              id="title"
              placeholder="2026 Civic Budget Referendum"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="description">Election description (optional)</Label>
            <Textarea
              id="description"
              rows={3}
              placeholder="What is being decided and why this ballot model was selected."
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="ballot-type">Ballot type</Label>
            <Select value={ballotType} onValueChange={(value) => setBallotType(value as BallotType)}>
              <SelectTrigger id="ballot-type">
                <SelectValue placeholder="Select ballot type" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(ballotTypeMeta).map(([value, meta]) => (
                  <SelectItem key={value} value={value}>
                    {meta.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">{ballotTypeMeta[ballotType].description}</p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="candidate-list">Candidates (one per line)</Label>
            <Textarea
              id="candidate-list"
              rows={6}
              value={candidateText}
              onChange={(event) => setCandidateText(event.target.value)}
            />
            <p className="text-sm text-muted-foreground">Current candidates: {candidates.length}</p>
          </div>

          <div className="space-y-4 rounded-lg border p-4">
            <p className="text-sm font-semibold">Ballot-specific constraints</p>

            <div className="flex items-center justify-between rounded-md border p-3">
              <div>
                <p className="font-medium">Allow abstention</p>
                <p className="text-sm text-muted-foreground">Permit submitting an intentionally blank ballot.</p>
              </div>
              <Switch checked={allowAbstention} onCheckedChange={setAllowAbstention} />
            </div>

            {ballotType === "score" ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label htmlFor="score-min">Minimum score</Label>
                  <Input
                    id="score-min"
                    type="number"
                    value={scoreMin}
                    onChange={(event) => setScoreMin(Number(event.target.value))}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="score-max">Maximum score</Label>
                  <Input
                    id="score-max"
                    type="number"
                    value={scoreMax}
                    onChange={(event) => setScoreMax(Number(event.target.value))}
                  />
                </div>
              </div>
            ) : null}

            {ballotType === "quadratic" ? (
              <div className="space-y-4">
                <div className="grid gap-2">
                  <Label htmlFor="credit-budget">Credit budget per voter</Label>
                  <Input
                    id="credit-budget"
                    type="number"
                    value={quadraticCredits}
                    onChange={(event) => setQuadraticCredits(Number(event.target.value))}
                  />
                </div>

                <div className="flex items-center justify-between rounded-md border p-3">
                  <div>
                    <p className="font-medium">Allow negative votes</p>
                    <p className="text-sm text-muted-foreground">Allow voters to spend credits on opposition votes.</p>
                  </div>
                  <Switch checked={allowNegativeVotes} onCheckedChange={setAllowNegativeVotes} />
                </div>
              </div>
            ) : null}
          </div>

          {errors.length > 0 ? (
            <Alert variant="destructive">
              <AlertTitle>Configuration issues</AlertTitle>
              <AlertDescription>
                <ul className="list-disc space-y-1 pl-4">
                  {errors.map((error) => (
                    <li key={error}>{error}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : (
            <Alert>
              <AlertTitle>Ready to create</AlertTitle>
              <AlertDescription>
                Your election definition satisfies the current ballot-type constraints.
              </AlertDescription>
            </Alert>
          )}

          <Button disabled={errors.length > 0}>Create Election</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Generated configuration preview</CardTitle>
          <CardDescription>
            This payload can be sent to a backend election-creation endpoint.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-md bg-muted p-4 text-sm">
            {JSON.stringify(electionPayload, null, 2)}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
