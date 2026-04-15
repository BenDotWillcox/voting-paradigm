"use client";

import { useMemo, useState } from "react";
import { PreferenceSlider } from "@/components/ui/preference-slider";
import { Button } from "@/components/ui/button";
import type { QuestionDto } from "@/lib/preferences-api";

interface PairwiseQuestionProps {
  question: QuestionDto;
  disabled?: boolean;
  onSubmit: (input: {
    chosenOptionId: string;
    strength: number;
    responseTimeMs: number;
  }) => void;
}

/**
 * Wraps the existing PreferenceSlider for pairwise comparison.
 *
 * Slider convention: left option = -10, right option = +10.
 * We map slider value → (chosenOptionId, strength):
 *   value < 0 → left option chosen, strength = |value|
 *   value > 0 → right option chosen, strength = |value|
 *   value = 0 → treat as neutral (tiny signal); default chosen = left
 */
export function PairwiseQuestion({
  question,
  disabled,
  onSubmit,
}: PairwiseQuestionProps) {
  const [value, setValue] = useState(0);
  // Reset the start timer whenever the question changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const startTime = useMemo(() => Date.now(), [question.id]);

  // For v1 we only support pairwise questions (two options).
  const [left, right] = question.options;

  const handleSubmit = () => {
    const chosenOptionId = value < 0 ? left.item_id : right.item_id;
    const strength = Math.max(0.1, Math.abs(value));
    const responseTimeMs = Date.now() - startTime;
    onSubmit({ chosenOptionId, strength, responseTimeMs });
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-semibold">{question.prompt}</h2>
        {(left.description || right.description) && (
          <p className="text-sm text-muted-foreground mt-2">
            Drag the slider toward the value that matters more to you. Stronger
            positions mean stronger preference.
          </p>
        )}
      </div>

      <PreferenceSlider
        key={question.id}
        firstOption={left.text}
        secondOption={right.text}
        defaultValue={0}
        onChange={setValue}
      />

      {(left.description || right.description) && (
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="rounded-lg border p-3">
            <div className="font-medium">{left.text}</div>
            {left.description && (
              <div className="text-muted-foreground mt-1">
                {left.description}
              </div>
            )}
          </div>
          <div className="rounded-lg border p-3">
            <div className="font-medium">{right.text}</div>
            {right.description && (
              <div className="text-muted-foreground mt-1">
                {right.description}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button onClick={handleSubmit} disabled={disabled} size="lg">
          {value === 0 ? "Skip (neutral)" : "Submit & Next"}
        </Button>
      </div>
    </div>
  );
}
