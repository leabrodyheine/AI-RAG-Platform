import type { AssistantAnswer, ChatErrorResponse } from "../types/platform";
import { createDemoAnswer } from "./platformFixtures";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);
export const isDemoMode = import.meta.env.VITE_USE_DEMO_DATA === "true";

export class ChatApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: ChatErrorResponse["code"],
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "ChatApiError";
  }
}

export async function askQuestion(question: string): Promise<AssistantAnswer> {
  if (isDemoMode) {
    await new Promise((resolve) => window.setTimeout(resolve, 650));
    return createDemoAnswer(question);
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new ChatApiError("Unable to reach the API gateway.", 0);
  }

  if (!response.ok) {
    const error = await parseErrorResponse(response);
    throw new ChatApiError(
      error?.message ?? `The API gateway returned ${response.status}.`,
      response.status,
      error?.code,
      error?.requestId ?? response.headers.get("X-Request-ID") ?? undefined,
    );
  }

  let answer: unknown;
  try {
    answer = await response.json();
  } catch {
    throw invalidResponseError(response);
  }
  if (!isAssistantAnswer(answer)) {
    throw invalidResponseError(response);
  }

  return answer;
}

async function parseErrorResponse(response: Response): Promise<ChatErrorResponse | null> {
  try {
    const payload: unknown = await response.json();
    return isChatErrorResponse(payload) ? payload : null;
  } catch {
    return null;
  }
}

function isChatErrorResponse(value: unknown): value is ChatErrorResponse {
  if (!isRecord(value)) return false;

  return (
    ["validation_error", "agent_unavailable", "agent_timeout"].includes(
      String(value.code),
    ) &&
    isNonEmptyString(value.message) &&
    isNonEmptyString(value.requestId)
  );
}

function isAssistantAnswer(value: unknown): value is AssistantAnswer {
  if (!isRecord(value)) return false;

  return (
    isNonEmptyString(value.content) &&
    Array.isArray(value.citations) &&
    value.citations.every(
      (citation) =>
        isRecord(citation) &&
        isNonEmptyString(citation.id) &&
        isNonEmptyString(citation.title) &&
        isNonEmptyString(citation.source) &&
        isNonEmptyString(citation.excerpt) &&
        typeof citation.relevance === "number" &&
        citation.relevance >= 0 &&
        citation.relevance <= 1,
    ) &&
    Array.isArray(value.trace) &&
    value.trace.every(
      (step) =>
        isRecord(step) &&
        isNonEmptyString(step.label) &&
        isNonEmptyString(step.detail) &&
        Number.isInteger(step.durationMs) &&
        Number(step.durationMs) >= 0,
    ) &&
    Number.isInteger(value.totalDurationMs) &&
    Number(value.totalDurationMs) >= 0
  );
}

function invalidResponseError(response: Response): ChatApiError {
  return new ChatApiError(
    "The API gateway returned an invalid chat response.",
    response.status,
    undefined,
    response.headers.get("X-Request-ID") ?? undefined,
  );
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
