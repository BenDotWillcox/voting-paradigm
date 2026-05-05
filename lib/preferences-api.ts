/**
 * Server-side API client for the Python preferences API.
 * Called from server components/actions — never exposed to the browser.
 *
 * The preferences API is stateless: the client owns persistence, so every call
 * passes the current state and receives back the updated state.
 */

// Both voting and preferences routers live in the single Nebula Civitas API
// process on :8000. Kept as a separate env var so deployments can split if
// needed, but defaults match the unified dev setup.
const BASE_URL =
  process.env.PREFERENCES_API_URL ||
  process.env.NEBULA_API_URL ||
  "http://localhost:8000";

export type PreferenceStateDto = {
  user_id: string;
  session_id: string;
  item_ids: string[];
  mu: number[];
  sigma_flat: number[];
  responses: ResponseDto[];
  n_questions_asked: number;
  asked_question_ids: string[];
  model_version: string;
};

export type QuestionOptionDto = {
  item_id: string;
  text: string;
  description: string | null;
};

export type QuestionDto = {
  id: string;
  question_type: string;
  prompt: string;
  options: QuestionOptionDto[];
  domain: string | null;
  source: string;
  metadata: Record<string, unknown>;
};

export type ResponseDto = {
  question_id: string;
  chosen_option_id: string;
  strength: number | null;
  response_time_ms: number | null;
  timestamp: string | null;
};

export type ProgressDto = {
  n_answered: number;
  target_questions: number;
  convergence_pct: number;
  is_complete: boolean;
};

export type ValueSummaryDto = {
  item_id: string;
  text: string;
  description: string;
  domain: string | null;
  mean: number;
  std: number;
  rank: number;
};

export type StartSessionResponse = {
  state: PreferenceStateDto;
  question: QuestionDto;
  target_questions: number;
};

export type SubmitResponseResult = {
  state: PreferenceStateDto;
  next_question: QuestionDto | null;
  progress: ProgressDto;
};

export type SummaryResult = {
  progress: ProgressDto;
  values: ValueSummaryDto[];
  model_version: string;
};

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `Preferences API error: ${res.status} ${res.statusText} ${text}`
    );
  }
  return res.json() as Promise<T>;
}

export async function startPreferenceSession(input: {
  userId: string;
  sessionId: string;
  targetQuestions?: number;
}): Promise<StartSessionResponse> {
  return apiFetch<StartSessionResponse>(
    "/api/preferences/sessions/start",
    {
      method: "POST",
      body: JSON.stringify({
        user_id: input.userId,
        session_id: input.sessionId,
        target_questions: input.targetQuestions ?? 25,
      }),
    }
  );
}

export async function submitPreferenceResponse(input: {
  state: PreferenceStateDto;
  response: {
    questionId: string;
    chosenOptionId: string;
    strength?: number | null;
    responseTimeMs?: number | null;
  };
  questionOptions: string[];
  targetQuestions?: number;
}): Promise<SubmitResponseResult> {
  return apiFetch<SubmitResponseResult>(
    "/api/preferences/sessions/respond",
    {
      method: "POST",
      body: JSON.stringify({
        state: input.state,
        response: {
          question_id: input.response.questionId,
          chosen_option_id: input.response.chosenOptionId,
          strength: input.response.strength ?? null,
          response_time_ms: input.response.responseTimeMs ?? null,
        },
        question_options: input.questionOptions,
        target_questions: input.targetQuestions ?? 25,
      }),
    }
  );
}

export async function getPreferenceSummary(input: {
  state: PreferenceStateDto;
  targetQuestions?: number;
}): Promise<SummaryResult> {
  return apiFetch<SummaryResult>("/api/preferences/sessions/summary", {
    method: "POST",
    body: JSON.stringify({
      state: input.state,
      target_questions: input.targetQuestions ?? 25,
    }),
  });
}
