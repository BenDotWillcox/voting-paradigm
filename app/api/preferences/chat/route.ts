import { NextResponse } from "next/server";
import { z } from "zod";
import {
  ballotOptions,
  normalizeSignals,
  preferenceDimensions,
  type PreferenceEstimate,
  type PreferenceMessage,
} from "@/lib/preferences-demo";

export const runtime = "nodejs";

const messageSchema = z.object({
  id: z.string(),
  role: z.enum(["assistant", "user"]),
  content: z.string().min(1),
});

const estimateSchema = z.object({
  dimensionId: z.enum([
    "transitAccess",
    "climateAction",
    "fiscalDiscipline",
    "roadCapacity",
    "localControl",
    "publicSafety",
    "equityAccess",
    "deliverySpeed",
  ]),
  value: z.number(),
  confidence: z.number(),
  evidenceCount: z.number(),
  evidence: z.array(z.string()),
});

const requestSchema = z.object({
  messages: z.array(messageSchema).min(1),
  estimates: z.array(estimateSchema),
});

const modelSignalSchema = z.object({
  dimensionId: estimateSchema.shape.dimensionId,
  direction: z.union([z.literal(-1), z.literal(1)]),
  strength: z.number().min(0).max(1),
  confidence: z.number().min(0).max(1),
  evidence: z.string().min(1).max(220),
});

const modelResponseSchema = z.object({
  assistantMessage: z.string().min(1),
  signals: z.array(modelSignalSchema).max(8),
});

type DisabledReason = "not_enabled" | "production" | "non_local_endpoint";

export async function POST(req: Request) {
  const parsed = requestSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      {
        mode: "disabled",
        reason: "invalid_request",
        assistantMessage: "The preference chat request was malformed.",
        signals: [],
      },
      { status: 400 }
    );
  }

  const disabledReason = getDisabledReason();
  if (disabledReason) {
    return NextResponse.json(
      {
        mode: "disabled",
        reason: disabledReason,
        assistantMessage: getDisabledMessage(disabledReason),
        signals: [],
      },
      { status: 403 }
    );
  }

  const baseUrl = getPreferenceLlmBaseUrl();
  if (!baseUrl) {
    return NextResponse.json(
      {
        mode: "disabled",
        reason: "non_local_endpoint",
        assistantMessage:
          "Live preference chat is configured with a non-local model endpoint, so it is disabled.",
        signals: [],
      },
      { status: 403 }
    );
  }

  try {
    const modelPayload = await callLocalPreferenceModel({
      baseUrl,
      messages: parsed.data.messages,
      estimates: parsed.data.estimates,
    });
    const validated = modelResponseSchema.parse(modelPayload);
    const signals = normalizeSignals(
      validated.signals.map((signal) => ({ ...signal, source: "llm" }))
    );

    return NextResponse.json({
      mode: "live",
      assistantMessage: validated.assistantMessage,
      signals,
    });
  } catch (error) {
    console.error("Preference LLM call failed:", error);
    return NextResponse.json(
      {
        mode: "error",
        assistantMessage:
          "The local GPT-OSS interviewer did not return a valid structured response.",
        signals: [],
      },
      { status: 502 }
    );
  }
}

function getDisabledReason(): DisabledReason | null {
  if (process.env.NODE_ENV === "production") {
    return "production";
  }
  if (
    process.env.PREFERENCE_DEMO_MODE !== "live" ||
    process.env.ENABLE_LIVE_PREFERENCE_LLM !== "true"
  ) {
    return "not_enabled";
  }
  return getPreferenceLlmBaseUrl() ? null : "non_local_endpoint";
}

function getDisabledMessage(reason: DisabledReason) {
  if (reason === "production") {
    return "Live GPT-OSS calls are disabled in production. Use the static replay and video walkthrough instead.";
  }
  if (reason === "non_local_endpoint") {
    return "Live preference chat only accepts a local model endpoint for this demo.";
  }
  return "Live GPT-OSS calls are disabled. Set PREFERENCE_DEMO_MODE=live and ENABLE_LIVE_PREFERENCE_LLM=true for local recording.";
}

function getPreferenceLlmBaseUrl() {
  const rawUrl = process.env.PREFERENCE_LLM_BASE_URL || "http://localhost:11434/v1";
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return null;
  }

  const localHosts = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
  if (!localHosts.has(url.hostname)) {
    return null;
  }

  return rawUrl.replace(/\/$/, "");
}

async function callLocalPreferenceModel(input: {
  baseUrl: string;
  messages: PreferenceMessage[];
  estimates: PreferenceEstimate[];
}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(`${input.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${process.env.PREFERENCE_LLM_API_KEY || "ollama"}`,
      },
      body: JSON.stringify({
        model: process.env.PREFERENCE_LLM_MODEL || "gpt-oss:20b",
        temperature: 0.35,
        response_format: { type: "json_object" },
        messages: [
          {
            role: "system",
            content: buildSystemPrompt(input.estimates),
          },
          ...input.messages.map((message) => ({
            role: message.role,
            content: message.content,
          })),
        ],
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Local LLM returned ${response.status}`);
    }

    const body = await response.json();
    const content = body?.choices?.[0]?.message?.content;
    if (typeof content !== "string") {
      throw new Error("Local LLM response did not include message content");
    }

    return JSON.parse(extractJsonObject(content));
  } finally {
    clearTimeout(timeout);
  }
}

function buildSystemPrompt(estimates: PreferenceEstimate[]) {
  const dimensionGuide = preferenceDimensions
    .map(
      (dimension) =>
        `${dimension.id}: +1 means ${dimension.highAnchor}; -1 means ${dimension.lowAnchor}.`
    )
    .join("\n");
  const ballotGuide = ballotOptions
    .map((option) => `${option.title}: ${option.summary}`)
    .join("\n");
  const modelSnapshot = estimates
    .map(
      (estimate) =>
        `${estimate.dimensionId}: value=${estimate.value.toFixed(2)}, confidence=${estimate.confidence.toFixed(2)}`
    )
    .join("\n");

  return [
    "You are a civic preference interviewer for a local portfolio demo.",
    "Interview the user about a transportation and climate ballot.",
    "Extract structured evidence for a transparent deterministic preference model.",
    "Do not claim to cast the final vote yourself; deterministic code will score the ballot.",
    "Do not reveal hidden reasoning. Give concise user-facing explanations only.",
    "",
    "Return only valid JSON with this exact shape:",
    '{"assistantMessage":"string","signals":[{"dimensionId":"transitAccess","direction":1,"strength":0.7,"confidence":0.8,"evidence":"short evidence"}]}',
    "",
    "Use only these dimensions:",
    dimensionGuide,
    "",
    "Current model snapshot:",
    modelSnapshot || "No evidence yet.",
    "",
    "Curated ballot options:",
    ballotGuide,
  ].join("\n");
}

function extractJsonObject(content: string) {
  const trimmed = content.trim();
  if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
    return trimmed;
  }

  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (fenced?.[1]) {
    return extractJsonObject(fenced[1]);
  }

  const firstBrace = trimmed.indexOf("{");
  const lastBrace = trimmed.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    return trimmed.slice(firstBrace, lastBrace + 1);
  }

  throw new Error("Could not extract JSON object from local LLM response");
}
