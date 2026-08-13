"use server";

import { randomUUID } from "crypto";
import { revalidatePath } from "next/cache";

import {
  createPreferenceSession,
  getPreferenceSessionById,
  getResponsesForSession,
  getSessionsForUser,
  insertPreferenceResponse,
  updatePreferenceSession,
} from "@/db/queries/preferences-queries";
import {
  getPreferenceSummary,
  startPreferenceSession,
  submitPreferenceEvidence,
  SubmitEvidenceResult,
  SummaryResult,
} from "@/lib/preferences-api";
import {
  EvidenceDto,
  parseCurrentQuestion,
  parsePreferenceState,
  PreferenceStateDto,
  QuestionDto,
} from "@/lib/validations/preferences-schemas";
import { ActionResult } from "@/types/actions/action-types";

// ---------------------------------------------------------------------------
// Types returned to UI
// ---------------------------------------------------------------------------

export type SessionData = {
  sessionId: string;
  userId: string;
  question: QuestionDto;
  state: PreferenceStateDto;
  progress: {
    nAnswered: number;
    targetQuestions: number;
    convergencePct: number;
    isComplete: boolean;
  };
};

export type NextStepData = {
  sessionId: string;
  question: QuestionDto | null;
  state: PreferenceStateDto;
  progress: SessionData["progress"];
  isComplete: boolean;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toProgress(p: {
  n_answered: number;
  target_questions: number;
  convergence_pct: number;
  is_complete: boolean;
}) {
  return {
    nAnswered: p.n_answered,
    targetQuestions: p.target_questions,
    convergencePct: p.convergence_pct,
    isComplete: p.is_complete,
  };
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export async function startPreferenceSessionAction(input: {
  userId: string;
  targetQuestions?: number;
}): Promise<ActionResult<SessionData>> {
  try {
    // Generate the session id up front so the Python call and the DB insert
    // agree on it without a placeholder-write/update round trip (the old
    // create-then-update flow left a window where a concurrent read saw a
    // dummy state).
    const sessionId = randomUUID();
    const targetQuestions = input.targetQuestions ?? 25;

    // 1) Initialize the real state + first question in the Python API.
    const resp = await startPreferenceSession({
      userId: input.userId,
      sessionId,
      targetQuestions,
    });

    // 2) Persist the session in a single insert.
    await createPreferenceSession({
      id: sessionId,
      userId: input.userId,
      status: "active",
      modelVersion: resp.state.model_version,
      stateSnapshot: resp.state,
      currentQuestion: resp.question,
      targetQuestions,
      nQuestions: 0,
    });

    revalidatePath("/preferences");
    return {
      isSuccess: true,
      message: "Session started",
      data: {
        sessionId,
        userId: input.userId,
        question: resp.question,
        state: resp.state,
        progress: {
          nAnswered: 0,
          targetQuestions: resp.target_questions,
          convergencePct: 0,
          isComplete: false,
        },
      },
    };
  } catch (error) {
    console.error("startPreferenceSessionAction error:", error);
    return {
      isSuccess: false,
      message:
        error instanceof Error ? error.message : "Failed to start session",
    };
  }
}

export async function getPreferenceSessionAction(
  sessionId: string
): Promise<ActionResult<SessionData | null>> {
  try {
    const row = await getPreferenceSessionById(sessionId);
    if (!row) return { isSuccess: true, message: "Session not found", data: null };

    const state = parsePreferenceState(row.stateSnapshot);
    const question = parseCurrentQuestion(row.currentQuestion);

    return {
      isSuccess: true,
      message: "ok",
      data: {
        sessionId: row.id,
        userId: row.userId,
        question: question as QuestionDto, // null only after completion
        state,
        progress: {
          nAnswered: row.nQuestions,
          targetQuestions: row.targetQuestions,
          convergencePct:
            row.targetQuestions > 0
              ? Math.min(100, (row.nQuestions / row.targetQuestions) * 100)
              : 0,
          isComplete: row.status === "completed",
        },
      },
    };
  } catch (error) {
    console.error("getPreferenceSessionAction error:", error);
    return { isSuccess: false, message: "Failed to load session" };
  }
}

export async function submitPreferenceResponseAction(input: {
  sessionId: string;
  questionId: string;
  chosenOptionId: string;
  strength: number;
  responseTimeMs?: number;
}): Promise<ActionResult<NextStepData>> {
  try {
    const row = await getPreferenceSessionById(input.sessionId);
    if (!row)
      return { isSuccess: false, message: "Session not found" };
    if (row.status !== "active")
      return { isSuccess: false, message: "Session is not active" };

    const state = parsePreferenceState(row.stateSnapshot);
    const currentQuestion = parseCurrentQuestion(row.currentQuestion);
    if (!currentQuestion || currentQuestion.id !== input.questionId) {
      return {
        isSuccess: false,
        message: "Question id mismatch; refresh the page",
      };
    }

    // Convert the UI answer (chosen option + positive strength) into signed
    // pairwise evidence: positive value prefers options[0], negative prefers
    // options[1].
    const [left, right] = currentQuestion.options;
    if (
      input.chosenOptionId !== left.item_id &&
      input.chosenOptionId !== right.item_id
    ) {
      return {
        isSuccess: false,
        message: "Chosen option is not part of the current question",
      };
    }
    const magnitude = Math.min(10, Math.max(0, Math.abs(input.strength)));
    const evidence: EvidenceDto = {
      source: "pairwise",
      item_a: left.item_id,
      item_b: right.item_id,
      value: input.chosenOptionId === left.item_id ? magnitude : -magnitude,
      confirmed_by_participant: false,
      confidence: 1,
      prompt_id: currentQuestion.id,
      extracted_claims: [],
      response_time_ms: input.responseTimeMs ?? null,
      metadata: {},
    };

    // Call Python API to update state and get next question.
    const result: SubmitEvidenceResult = await submitPreferenceEvidence({
      state,
      evidence,
      targetQuestions: row.targetQuestions,
    });

    // Record the answered question in the audit table.
    await insertPreferenceResponse({
      sessionId: row.id,
      questionId: currentQuestion.id,
      questionType: currentQuestion.question_type,
      questionPrompt: currentQuestion.prompt,
      optionsJson: currentQuestion.options,
      chosenOptionId: input.chosenOptionId,
      strength: input.strength.toFixed(1),
      responseTimeMs: input.responseTimeMs ?? null,
      ordinal: row.nQuestions + 1,
      source: currentQuestion.source,
    });

    // Persist updated state.
    await updatePreferenceSession(row.id, {
      stateSnapshot: result.state,
      currentQuestion: result.next_question,
      nQuestions: row.nQuestions + 1,
      status: result.progress.is_complete ? "completed" : "active",
    });

    if (result.progress.is_complete) {
      revalidatePath("/preferences");
    }
    return {
      isSuccess: true,
      message: "ok",
      data: {
        sessionId: row.id,
        question: result.next_question,
        state: result.state,
        progress: toProgress(result.progress),
        isComplete: result.progress.is_complete,
      },
    };
  } catch (error) {
    console.error("submitPreferenceResponseAction error:", error);
    return {
      isSuccess: false,
      message:
        error instanceof Error ? error.message : "Failed to submit response",
    };
  }
}

export async function getPreferenceSummaryAction(
  sessionId: string
): Promise<ActionResult<SummaryResult>> {
  try {
    const row = await getPreferenceSessionById(sessionId);
    if (!row)
      return { isSuccess: false, message: "Session not found" };
    const state = parsePreferenceState(row.stateSnapshot);
    const summary = await getPreferenceSummary({
      state,
      targetQuestions: row.targetQuestions,
    });
    return { isSuccess: true, message: "ok", data: summary };
  } catch (error) {
    console.error("getPreferenceSummaryAction error:", error);
    return { isSuccess: false, message: "Failed to compute summary" };
  }
}

export async function listUserPreferenceSessionsAction(
  userId: string
): Promise<
  ActionResult<
    {
      id: string;
      status: string;
      nQuestions: number;
      targetQuestions: number;
      createdAt: Date;
      updatedAt: Date;
    }[]
  >
> {
  try {
    const rows = await getSessionsForUser(userId);
    return {
      isSuccess: true,
      message: "ok",
      data: rows.map((r) => ({
        id: r.id,
        status: r.status,
        nQuestions: r.nQuestions,
        targetQuestions: r.targetQuestions,
        createdAt: r.createdAt,
        updatedAt: r.updatedAt,
      })),
    };
  } catch (error) {
    console.error("listUserPreferenceSessionsAction error:", error);
    return { isSuccess: false, message: "Failed to list sessions" };
  }
}

export async function abandonPreferenceSessionAction(
  sessionId: string
): Promise<ActionResult<void>> {
  try {
    await updatePreferenceSession(sessionId, { status: "abandoned" });
    revalidatePath("/preferences");
    return { isSuccess: true, message: "ok" };
  } catch (error) {
    console.error("abandonPreferenceSessionAction error:", error);
    return { isSuccess: false, message: "Failed to abandon session" };
  }
}

export async function getPreferenceResponsesAction(sessionId: string) {
  try {
    const rows = await getResponsesForSession(sessionId);
    return { isSuccess: true, message: "ok", data: rows };
  } catch (error) {
    console.error("getPreferenceResponsesAction error:", error);
    return { isSuccess: false, message: "Failed to load responses" };
  }
}
