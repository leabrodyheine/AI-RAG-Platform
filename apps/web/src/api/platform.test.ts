import { afterEach, expect, test, vi } from "vitest";

import { askQuestion, ChatApiError } from "./platform";
import { createDemoAnswer } from "./platformFixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("posts a question to the configured chat endpoint", async () => {
  const answer = createDemoAnswer("cache");
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(answer), {
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": "request-success",
      },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);

  await expect(askQuestion("What changed?")).resolves.toEqual(answer);
  expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: "What changed?" }),
  });
});

test("preserves safe gateway error details", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "agent_timeout",
          message: "The agent service did not respond in time.",
          requestId: "request-timeout",
        }),
        { status: 504, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );

  const error = await askQuestion("What changed?").catch((caught) => caught);

  expect(error).toBeInstanceOf(ChatApiError);
  expect(error).toMatchObject({
    message: "The agent service did not respond in time.",
    status: 504,
    code: "agent_timeout",
    requestId: "request-timeout",
  });
});

test("rejects malformed success responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ content: "Missing contract fields" }), {
        headers: { "X-Request-ID": "request-invalid" },
      }),
    ),
  );

  await expect(askQuestion("What changed?")).rejects.toMatchObject({
    message: "The API gateway returned an invalid chat response.",
    requestId: "request-invalid",
  });
});

test("replaces network details with a safe connection error", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("private network detail")));

  await expect(askQuestion("What changed?")).rejects.toMatchObject({
    message: "Unable to reach the API gateway.",
    status: 0,
  });
});
