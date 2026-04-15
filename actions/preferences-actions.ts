"use server";

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
  QuestionDto,
  startPreferenceSession,
  SubmitResponseResult,
  submitPreferenceResponse,
  SummaryResult,
  PreferenceStateDto,
} from "@/lib/preferences-api";
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
    // 1) Create DB row first to get the UUID we'll use as the session id.
    const placeholderState = {
      user_id: input.userId,
      session_id: "pending",
      item_ids: [],
      mu: [],
      sigma_flat: [],
      responses: [],
      n_questions_asked: 0,
      asked_question_ids: [],
      model_version: "thurstone_v1",
    };
    const dbRow = await createPreferenceSession({
      userId: input.userId,
      status: "active",
      modelVersion: "thurstone_v1",
      stateSnapshot: placeholderState,
      targetQuestions: input.targetQuestions ?? 25,
      nQuestions: 0,
    });

    // 2) Call Python API to initialize the real state + first question.
    const resp = await startPreferenceSession({
      userId: input.userId,
      sessionId: dbRow.id,
      targetQuestions: input.targetQuestions ?? 25,
    });

    // 3) Update the DB row with the real state and current question.
    await updatePreferenceSession(dbRow.id, {
      stateSnapshot: resp.state,
      currentQuestion: resp.question,
    });

    return {
      isSuccess: true,
      message: "Session started",
      data: {
        sessionId: dbRow.id,
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
    if (!row) return { isSuccess: false, message: "Session not found" };

    const state = row.stateSnapshot as unknown as PreferenceStateDto;
    const question = row.currentQuestion as unknown as QuestionDto | null;

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

    const state = row.stateSnapshot as unknown as PreferenceStateDto;
    const currentQuestion =
      row.currentQuestion as unknown as QuestionDto | null;
    if (!currentQuestion || currentQuestion.id !== input.questionId) {
      return {
        isSuccess: false,
        message: "Question id mismatch; refresh the page",
      };
    }

    const questionOptionIds = currentQuestion.options.map((o) => o.item_id);

    // Call Python API to update state and get next question.
    const result: SubmitResponseResult = await submitPreferenceResponse({
      state,
      response: {
        questionId: input.questionId,
        chosenOptionId: input.chosenOptionId,
        strength: input.strength,
        responseTimeMs: input.responseTimeMs,
      },
      questionOptions: questionOptionIds,
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
    const state = row.stateSnapshot as unknown as PreferenceStateDto;
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
