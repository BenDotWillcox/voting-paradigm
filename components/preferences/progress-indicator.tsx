"use client";

import { Progress } from "@/components/ui/progress";

interface ProgressIndicatorProps {
  nAnswered: number;
  targetQuestions: number;
  convergencePct: number;
}

export function ProgressIndicator({
  nAnswered,
  targetQuestions,
  convergencePct,
}: ProgressIndicatorProps) {
  const pct =
    targetQuestions > 0
      ? Math.min(100, (nAnswered / targetQuestions) * 100)
      : 0;

  return (
    <div className="w-full space-y-2">
      <div className="flex justify-between text-sm text-muted-foreground">
        <span>
          Question {Math.min(nAnswered + 1, targetQuestions)} of{" "}
          {targetQuestions}
        </span>
        <span>{convergencePct.toFixed(0)}% complete</span>
      </div>
      <Progress value={pct} />
    </div>
  );
}
