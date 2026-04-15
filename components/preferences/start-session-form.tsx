"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { startPreferenceSessionAction } from "@/actions/preferences-actions";

interface StartSessionFormProps {
  users: { id: string; name: string }[];
  existingSessions?: {
    id: string;
    userId: string;
    status: string;
    nQuestions: number;
    targetQuestions: number;
  }[];
}

export function StartSessionForm({
  users,
  existingSessions = [],
}: StartSessionFormProps) {
  const router = useRouter();
  const [userId, setUserId] = useState<string>(users[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const activeSession = existingSessions.find(
    (s) => s.userId === userId && s.status === "active"
  );

  const handleStart = () => {
    if (!userId) {
      setError("Select a user");
      return;
    }
    setError(null);
    startTransition(async () => {
      const result = await startPreferenceSessionAction({ userId });
      if (!result.isSuccess || !result.data) {
        setError(result.message);
        return;
      }
      router.push(`/preferences/${result.data.sessionId}`);
    });
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="text-sm font-medium">Who are you?</label>
        <Select value={userId} onValueChange={setUserId}>
          <SelectTrigger>
            <SelectValue placeholder="Select a user" />
          </SelectTrigger>
          <SelectContent>
            {users.map((u) => (
              <SelectItem key={u.id} value={u.id}>
                {u.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {activeSession && (
        <div className="rounded-lg border bg-muted/50 p-3 text-sm">
          <div className="mb-2">
            You already have an active session
            {activeSession.nQuestions > 0
              ? ` (${activeSession.nQuestions}/${activeSession.targetQuestions} answered)`
              : ""}
            .
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              router.push(`/preferences/${activeSession.id}`)
            }
          >
            Resume session
          </Button>
        </div>
      )}

      <div className="flex gap-2">
        <Button onClick={handleStart} disabled={isPending || !userId}>
          {isPending ? "Starting…" : "Start New Session"}
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
    </div>
  );
}
