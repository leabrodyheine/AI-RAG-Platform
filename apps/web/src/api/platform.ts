import type { AssistantAnswer } from "../types/platform";
import { createDemoAnswer } from "./platformFixtures";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const isDemoMode = import.meta.env.VITE_USE_DEMO_DATA !== "false";

export async function askQuestion(question: string): Promise<AssistantAnswer> {
  if (isDemoMode) {
    await new Promise((resolve) => window.setTimeout(resolve, 650));
    return createDemoAnswer(question);
  }

  const response = await fetch(`${apiBaseUrl}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!response.ok) {
    throw new Error(`The API gateway returned ${response.status}.`);
  }

  return (await response.json()) as AssistantAnswer;
}
