"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { PairwiseQuestion } from "./pairwise-question";
import { ProgressIndicator } from "./progress-indicator";
import { submitPreferenceResponseAction } from "@/actions/preferences-actions";
import type { SessionData } from "@/actions/preferences-actions";
import type { QuestionDto, PreferenceStateDto } from "@/lib/preferences-api";
import { Button } from "@/components/ui/button";

interface ElicitationFlowProps {
  initial: SessionData;
}

export function ElicitationFlow({ initial }: ElicitationFlowProps) {
  const router = useRouter();
  const [question, setQuestion] = useState<QuestionDto | null>(initial.question);
  const [state, setState] = useState<PreferenceStateDto>(initial.state);
  const [progress, setProgress] = useState(initial.progress);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleSubmit = (input: {
    chosenOptionId: string;
    strength: number;
    responseTimeMs: number;
  }) => {
    if (!question) return;
    setError(null);
    startTransition(async () => {
      const result = await submitPreferenceResponseAction({
        sessionId: initial.sessionId,
        questionId: question.id,
        chosenOptionId: input.chosenOptionId,
        strength: input.strength,
        responseTimeMs: input.responseTimeMs,
      });
      if (!result.isSuccess || !result.data) {
        setError(result.message);
        return;
      }
      setState(result.data.state);
      setProgress(result.data.progress);
      if (result.data.isComplete || !result.data.question) {
        router.push(`/preferences/${initial.sessionId}/summary`);
        router.refresh();
        return;
      }
      setQuestion(result.data.question);
    });
  };

  // Touch state so linting doesn't complain; state is kept for completeness/debug.
  void state;

  if (!question) {
    return (
      <div className="space-y-4 text-center">
        <p>Session complete.</p>
        <Button onClick={() => router.push(`/preferences/${initial.sessionId}/summary`)}>
          View Results
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <ProgressIndicator
        nAnswered={progress.nAnswered}
        targetQuestions={progress.targetQuestions}
        convergencePct={progress.convergencePct}
      />
      <PairwiseQuestion
        question={question}
        onSubmit={handleSubmit}
        disabled={isPending}
      />
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
    </div>
  );
}
