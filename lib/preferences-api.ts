/**
 * Server-side API client for the Python preferences API.
 * Called from server components/actions — never exposed to the browser.
 *
 * The preferences API is stateless: the client owns persistence, so every call
 * passes the current state and receives back the updated state.
 *
 * Wire types are inferred from the Zod schemas in
 * lib/validations/preferences-schemas.ts so the JSONB boundary and the HTTP
 * boundary can never drift apart.
 */

import type {
  EvidenceDto,
  PreferenceStateDto,
  QuestionDto,
} from "@/lib/validations/preferences-schemas";

export type {
  EvidenceDto,
  PreferenceStateDto,
  QuestionDto,
  QuestionOptionDto,
} from "@/lib/validations/preferences-schemas";

// Both voting and preferences routers live in the single Nebula Civitas API
// process on :8000. Kept as a separate env var so deployments can split if
// needed, but defaults match the unified dev setup.
const BASE_URL =
  process.env.PREFERENCES_API_URL ||
  process.env.NEBULA_API_URL ||
  "http://localhost:8000";

export type PreferenceModelName = "gaussian_linear" | "bradley_terry";
export type SelectionPolicy = "random" | "max_variance";

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

export type SubmitEvidenceResult = {
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
  model?: PreferenceModelName;
  selectionPolicy?: SelectionPolicy;
}): Promise<StartSessionResponse> {
  return apiFetch<StartSessionResponse>("/api/preferences/sessions/start", {
    method: "POST",
    body: JSON.stringify({
      user_id: input.userId,
      session_id: input.sessionId,
      target_questions: input.targetQuestions ?? 25,
      model: input.model ?? "gaussian_linear",
      selection_policy: input.selectionPolicy ?? "max_variance",
    }),
  });
}

export async function submitPreferenceEvidence(input: {
  state: PreferenceStateDto;
  evidence: EvidenceDto;
  targetQuestions?: number;
}): Promise<SubmitEvidenceResult> {
  return apiFetch<SubmitEvidenceResult>(
    "/api/preferences/sessions/evidence",
    {
      method: "POST",
      body: JSON.stringify({
        state: input.state,
        evidence: input.evidence,
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
